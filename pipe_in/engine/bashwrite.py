"""Bash のコマンドの文字列から書き込み先を読み取り、段の書き込み範囲で止める（D0036）。

Write・Edit に掛けている can_write・write_scope_hint を、Bash の書き込みの形（リダイレクト・tee・sed -i・cp など）にも掛ける。
決まりは「止める形の一覧」：
  1. 書き込みの形があり、先が文字で読み取れる → can_write で判定（範囲外なら止める）
  2. 書き込みの形があり、先が読み取れない → 止める
  3. 書き込みの形が見つからない（pytest・make・python file.py など）→ 通す。ガードはサンドボックスではない
読み取れない入力（引用符が閉じない・入れ子が深すぎるなど）は、安全側に倒して止める。
標準ライブラリだけで書く（依存の向きは pipe_in.engine の中で閉じる）。
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

MAX_DEPTH = 5  # $(…)・bash -c・eval の入れ子の上限
MAX_TREE_FILES = 5000  # 根を指すフォルダ操作で見るファイルの数の上限。超えたら止める
MAX_CWDS = 8 # ありうる作業フォルダの数の上限。超えたら「不明」にする

UNPARSE = "Bash のコマンドを読み取れなかったため止めました"
OUTSIDE = "プロジェクトの外には書き込めません"

TAINT_VARS = frozenset({"TMPDIR", "TEMP", "TMP", "HOME"})
TEMP_ROOTS = ("/tmp", "/var/tmp", "/private/tmp")
DEV_OK = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"})
HEREDOC_OPS = ("<<", "<<-")
WRITE_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
REDIRECT_OPS = (">>", ">|", ">&", "<>", "<<<", "<<-", "<<", "<&", ">", "<")
KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "case", "esac", "in",
                      "select", "function", "!", "{", "}"})
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
ENV_BUILTINS = frozenset({"export", "declare", "typeset", "local", "readonly"})
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PYTHON = re.compile(r"(python|pypy)[0-9.]*|py")

# 引数の形が同じ単純なコマンド：名前 -> （値を取る短いオプション, 値を取る長いオプション, 先の種類）
SIMPLE = {
    "tee": ("", (), "file"),  # --output-error は値を取らない（=つきのときだけ値）
    "touch": ("dtr", ("date", "reference", "time"), "file"),
    "rm": ("", (), "file"),
    "unlink": ("", (), "file"),
    "rmdir": ("", (), "dir"),
    "truncate": ("sr", ("size", "reference"), "file"),
    "mkdir": ("m", ("mode",), "mkdir"),
}
COPY_SHORT = {"cp": "tS", "mv": "tS", "ln": "tS", "install": "tmogS"}


class _Unreadable(Exception):
    """コマンドの文字列を読み取れなかった。"""


class _Deny(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class BashState:
    """ガード（段の1回の実行）ごとに1つ。呼び出しをまたいで覚える。"""

    cwds: list[Path]  # ありうる作業フォルダ（最大 MAX_CWDS。超えたら空にして「不明」）
    cwd_unknown: bool  # True のあいだ、相対パスの書き込みは止める
    env_tainted: bool  # TMPDIR/TEMP/TMP/HOME への代入を見たら True（戻さない）

    @classmethod
    def new(cls, project_dir: Path) -> "BashState":
        return cls([Path(os.path.realpath(project_dir))], False, False)

    def copy(self) -> "BashState":
        return BashState(list(self.cwds), self.cwd_unknown, self.env_tainted)

    def set_cwds(self, cwds: list[Path]) -> None:
        unique = list(dict.fromkeys(cwds))
        if len(unique) > MAX_CWDS:
            self.cwds, self.cwd_unknown = [], True
        else:
            self.cwds = unique


# ---- 字句（語・演算子・リダイレクト） ---------------------------------------------------


@dataclass
class Word:
    text: str  # 引用符を外した文字
    expands: bool = False  # 展開（$name・$(…)・バッククォート・{a,b} など）を含む
    glob: bool = False  # 引用符の外に * ? [ がある
    tilde: bool = False  # 引用符の外の ~ で始まる
    quoted: bool = False  # 引用符か \ を使った
    subs: tuple[str, ...] = ()  # $(…)・バッククォート・<(…) の中身
    exps: tuple[str, ...] = ()  # 展開の元の文字（$TMPDIR など）


@dataclass
class Op:
    s: str


@dataclass
class Redir:
    op: str
    fd: str = ""
    target: Word | None = None
    body: str = ""  # ヒアドキュメントの本文
    quoted: bool = False  # ヒアドキュメントの区切りが引用符つき


UNREAD_WORD = Word("（読み取れない名前）", expands=True)


def _backtick_end(s: str, i: int) -> int:
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
        elif s[j] == "`":
            return j
        else:
            j += 1
    raise _Unreadable()


def _unbacktick(inner: str) -> str:
    return inner.replace("\\`", "`").replace("\\$", "$").replace("\\\\", "\\")


def _skip_dq(s: str, i: int) -> int:
    """" の中を飛ばし、閉じる " の次の位置を返す。"""
    while i < len(s):
        if s[i] == "\\":
            i += 2
        elif s[i] == '"':
            return i + 1
        elif s.startswith("$(", i):
            i = _paren_end(s, i + 2) + 1
        elif s[i] == "`":
            i = _backtick_end(s, i) + 1
        else:
            i += 1
    raise _Unreadable()


def _paren_end(s: str, i: int) -> int:
    """( の次の位置 i から、釣り合う ) の位置を返す。"""
    depth = 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise _Unreadable()
            i = j + 1
            continue
        if c == '"':
            i = _skip_dq(s, i + 1)
            continue
        if c == "`":
            i = _backtick_end(s, i) + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise _Unreadable()


def _brace_end(s: str, i: int) -> int:
    depth = 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise _Unreadable()


def _subs_in_text(text: str) -> list[str]:
    """文字の中の $(…)・バッククォートの中身を集める（ヒアドキュメントの本文・${…}・$((…)) の中で使う）。"""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text.startswith("$((", i):
            e = _paren_end(text, i + 2)
            out += _subs_in_text(text[i + 3 : e - 1])
            i = e + 1
        elif text.startswith("$(", i):
            e = _paren_end(text, i + 2)
            out.append(text[i + 2 : e])
            i = e + 1
        elif text[i] == "`":
            e = _backtick_end(text, i)
            out.append(_unbacktick(text[i + 1 : e]))
            i = e + 1
        else:
            i += 1
    return out


class _Buf:
    """いま作っている語。"""

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.has = False
        self.expands = self.glob = self.tilde = self.quoted = self.brace = False
        self.subs: list[str] = []
        self.exps: list[str] = []

    def add(self, text: str, quoted: bool = False) -> None:
        self.chars.append(text)
        self.has = True
        if quoted:
            self.quoted = True

    def expand(self, text: str, subs: list[str] | tuple[str, ...] = ()) -> None:
        self.add(text)
        self.expands = True
        self.exps.append(text)
        self.subs.extend(subs)

    def digits(self) -> bool:
        return self.has and not self.quoted and not self.expands and "".join(self.chars).isdigit()

    def word(self) -> Word:
        text = "".join(self.chars)
        expands, exps = self.expands, list(self.exps)
        if self.brace and text not in ("{", "}"):  # {a,b} の展開は読めない
            expands = True
            exps.append("{}")
        return Word(text, expands, self.glob, self.tilde, self.quoted, tuple(self.subs), tuple(exps))


class _Lexer:
    """コマンドの文字列を、語・演算子・リダイレクトに分ける（shlex は引用符の区別を失うので使わない）。"""

    def __init__(self, src: str) -> None:
        self.s = src
        self.i = 0
        self.out: list[Word | Op | Redir] = []
        self.b = _Buf()
        self.want: Redir | None = None  # 先の語を待っているリダイレクト
        self.heredocs: list[tuple[Redir, Word]] = []

    def run(self) -> list[Word | Op | Redir]:
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t":
                self.end_word()
                self.i += 1
            elif c == "\n":
                self.newline()
            elif c == "\\":
                self.backslash()
            elif c == "'":
                self.single()
            elif c == '"':
                self.double()
            elif c == "$":
                self.dollar()
            elif c == "`":
                self.backtick(False)
            elif c == "#" and not self.b.has:
                while self.i < len(s) and s[self.i] != "\n":
                    self.i += 1
            elif c in ";&|()<>":
                self.operator()
            else:
                self.plain(c)
        self.end_word()
        if self.want is not None:
            raise _Unreadable()
        return self.out

    def end_word(self) -> None:
        if not self.b.has:
            return
        w = self.b.word()
        self.b = _Buf()
        if self.want is not None:
            self.want.target = w
            if self.want.op in HEREDOC_OPS:
                self.heredocs.append((self.want, w))
            self.want = None
        else:
            self.out.append(w)

    def emit_op(self, s: str) -> None:
        if self.want is not None:
            raise _Unreadable()
        self.out.append(Op(s))

    def newline(self) -> None:
        self.end_word()
        self.emit_op("\n")
        self.i += 1
        for redir, delim in self.heredocs:
            self.read_body(redir, delim)
        self.heredocs = []

    def read_body(self, redir: Redir, delim: Word) -> None:
        s, strip = self.s, redir.op == "<<-"
        lines: list[str] = []
        while self.i < len(s):
            j = s.find("\n", self.i)
            end = len(s) if j < 0 else j
            line = s[self.i : end]
            self.i = len(s) if j < 0 else j + 1
            if (line.lstrip("\t") if strip else line) == delim.text:
                break
            lines.append(line)
        redir.body = "\n".join(lines)
        redir.quoted = delim.quoted

    def backslash(self) -> None:
        s, i = self.s, self.i
        nxt = s[i + 1 : i + 2]
        if nxt == "\n":
            self.i += 2  # 行の連結
        elif nxt == "":
            self.b.add("\\", True)
            self.i += 1
        else:
            self.b.add(nxt, True)
            self.i += 2

    def single(self) -> None:
        j = self.s.find("'", self.i + 1)
        if j < 0:
            raise _Unreadable()
        self.b.add(self.s[self.i + 1 : j], True)
        self.i = j + 1

    def double(self) -> None:
        s = self.s
        self.b.add("", True)
        self.i += 1
        while True:
            if self.i >= len(s):
                raise _Unreadable()
            c = s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\":
                nxt = s[self.i + 1 : self.i + 2]
                if nxt in ('$', "`", '"', "\\") and nxt:
                    self.b.add(nxt, True)
                    self.i += 2
                elif nxt == "\n":
                    self.i += 2
                else:
                    self.b.add("\\", True)
                    self.i += 1
            elif c == "$":
                self.dollar(True)
            elif c == "`":
                self.backtick(True)
            else:
                self.b.add(c, True)
                self.i += 1

    def backtick(self, in_dq: bool) -> None:
        e = _backtick_end(self.s, self.i)
        self.b.expand(self.s[self.i : e + 1], [_unbacktick(self.s[self.i + 1 : e])])
        self.i = e + 1

    def dollar(self, in_dq: bool = False) -> None:
        s, i, b = self.s, self.i, self.b
        nxt = s[i + 1 : i + 2]
        if s.startswith("$((", i):
            e = _paren_end(s, i + 2)
            b.expand(s[i : e + 1], _subs_in_text(s[i + 3 : e - 1]))
            self.i = e + 1
        elif s.startswith("$(", i):
            e = _paren_end(s, i + 2)
            b.expand(s[i : e + 1], [s[i + 2 : e]])
            self.i = e + 1
        elif nxt == "{":
            e = _brace_end(s, i + 2)
            b.expand(s[i : e + 1], _subs_in_text(s[i + 2 : e]))
            self.i = e + 1
        elif nxt and nxt.isascii() and (nxt.isalpha() or nxt == "_"):
            m = NAME.match(s, i + 1)
            assert m is not None
            b.expand("$" + m.group())
            self.i = m.end()
        elif nxt and nxt in "@*#?$!-0123456789":
            b.expand(s[i : i + 2])
            self.i = i + 2
        elif nxt == "'" and not in_dq:
            b.expands = True  # $'…' は読まない
            self.i = i + 1
        elif nxt == '"' and not in_dq:
            self.i = i + 1
        else:
            b.add("$", in_dq)
            self.i = i + 1

    def plain(self, c: str) -> None:
        b = self.b
        if c == "~" and not b.has:
            b.tilde = True
        elif c in "*?[":
            b.glob = True
        elif c in "{}":
            b.brace = True
        b.add(c)
        self.i += 1

    def operator(self) -> None:
        s, i = self.s, self.i
        c = s[i]
        if c in "<>" and s.startswith("(", i + 1):  # <(…)・>(…)
            e = _paren_end(s, i + 2)
            self.b.expand(s[i : e + 1], [s[i + 2 : e]])
            self.i = e + 1
            return
        if c in "<>":
            self.redirect()
            return
        self.end_word()
        if c == "&" and s.startswith("&>", i):
            op = "&>>" if s.startswith("&>>", i) else "&>"
            self.emit_redir(op, "")
            self.i += len(op)
            return
        if c == "&" and s.startswith("&&", i):
            self.emit_op("&&")
            self.i += 2
        elif c == "|" and s.startswith("||", i):
            self.emit_op("||")
            self.i += 2
        elif c == "|" and s.startswith("|&", i):
            self.emit_op("|")
            self.i += 2
        elif c == ";" and s.startswith(";;", i):
            self.emit_op(";")
            self.i += 2
        else:
            self.emit_op(";" if c == ";" else c)
            self.i += 1

    def redirect(self) -> None:
        fd = ""
        if self.b.digits():
            fd = "".join(self.b.chars)
            self.b = _Buf()
        else:
            self.end_word()
        op = next(o for o in REDIRECT_OPS if self.s.startswith(o, self.i))
        self.emit_redir(op, fd)
        self.i += len(op)

    def emit_redir(self, op: str, fd: str) -> None:
        if self.want is not None:
            raise _Unreadable()
        r = Redir(op, fd)
        self.out.append(r)
        self.want = r


# ---- 判定 -----------------------------------------------------------------------------


@dataclass
class _Cmd:
    words: list[Word]
    redirs: list[Redir]


def _name(w: Word) -> str | None:
    """コマンド名（展開を含むなら None）。"""
    if w.expands:
        return None
    return w.text.rsplit("/", 1)[-1].removesuffix(".exe")


def _parse_args(args: list[Word], short_arg: str = "", long_arg: tuple[str, ...] = (), stop: bool = False):
    """（オペランドの語, [（オプション, 値の語）]）。値を取るオプションは short_arg（1文字ずつ）と long_arg で渡す。
    stop=True なら、最初のオペランドから後ろはすべてオペランド。"""
    ops: list[Word] = []
    opts: list[tuple[str, Word | None]] = []
    i, done = 0, False
    while i < len(args):
        w = args[i]
        t = w.text
        i += 1
        if done or w.expands or not t.startswith("-") or t == "-":
            if stop:
                ops.extend(args[i - 1 :])
                break
            ops.append(w)
        elif t == "--":
            done = True
        elif t.startswith("--"):
            name, eq, val = t[2:].partition("=")
            if name in long_arg and eq:
                opts.append((name, replace(w, text=val, tilde=False)))
            elif name in long_arg and i < len(args):
                opts.append((name, args[i]))
                i += 1
            else:
                opts.append((name, None))
        else:
            i = _short_cluster(w, args, i, short_arg, opts)
    return ops, opts


def _short_cluster(w: Word, args: list[Word], i: int, short_arg: str, opts: list) -> int:
    t = w.text
    for j in range(1, len(t)):
        ch = t[j]
        if ch not in short_arg:
            opts.append((ch, None))
            continue
        rest = t[j + 1 :]
        if rest:
            opts.append((ch, replace(w, text=rest, tilde=False)))
        elif i < len(args):
            opts.append((ch, args[i]))
            i += 1
        else:
            opts.append((ch, None))
        break
    return i


# 文字列リテラル（接頭 r・b・u つき。f は展開があるので読まない）
_LIT = re.compile(r"""\s*[rRbBuU]{0,2}(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`([^`\\$]*)`)\s*""", re.S)
_KW = re.compile(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.*)$", re.S)


def _lit(arg: str | None) -> str | None:
    """引数が1つの文字列リテラルならその中身。バックスラッシュを含むもの・リテラルでないものは None。"""
    if arg is None:
        return None
    m = _LIT.fullmatch(arg)
    if not m:
        return None
    text = next(g for g in m.groups() if g is not None)
    return None if "\\" in text else text


def _call_args(code: str, pos: int) -> list[str] | None:
    """code[pos:]（開きかっこの次）から、呼び出しの引数を最上位のコンマで分けて返す。閉じなければ None。"""
    args: list[str] = []
    cur: list[str] = []
    depth, i, n = 0, pos, len(code)
    while i < n:
        c = code[i]
        if c in "'\"`":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            cur.append(code[i : j + 1])
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                args.append("".join(cur))
                return [a.strip() for a in args if a.strip()]
            depth -= 1
        elif c == "," and depth == 0:
            args.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    return None


def _split_kw(args: list[str]) -> tuple[list[str], dict[str, str]]:
    pos: list[str] = []
    kw: dict[str, str] = {}
    for a in args:
        m = _KW.match(a)
        if m:
            kw[m.group(1)] = m.group(2)
        else:
            pos.append(a)
    return pos, kw


def _pick(pos: list[str], how: str) -> list[str | None]:
    chosen = pos if how == "all" else pos[-1:] if how == "last" else pos[:1]
    return [_lit(a) for a in chosen] or [None]


# 関数名 -> 先にする引数（first・last・all）
_PY_FUNCS = {
    "remove": "first", "unlink": "first", "rmdir": "first", "removedirs": "first", "mkdir": "first", "makedirs": "first",
    "truncate": "first", "rmtree": "first", "rename": "all", "replace": "all", "move": "all", "symlink": "last",
    "link": "last", "copy": "last", "copy2": "last", "copyfile": "last", "copytree": "last", "copymode": "last",
}
_JS_FUNCS = {
    "writeFileSync": "first", "appendFileSync": "first", "writeFile": "first", "appendFile": "first",
    "unlinkSync": "first", "unlink": "first", "rmSync": "first", "rm": "first", "mkdirSync": "first", "mkdir": "first",
    "rmdirSync": "first", "rmdir": "first", "truncateSync": "first", "copyFileSync": "last", "copyFile": "last",
    "cpSync": "last", "cp": "last", "symlinkSync": "last", "renameSync": "all", "rename": "all",
}
_PY_MODULE_CALL = re.compile(r"\b(?:os|shutil)\s*\.\s*(" + "|".join(_PY_FUNCS) + r")\s*\(")
_PY_BARE_CALL = re.compile(r"(?<![\w.])(" + "|".join(_PY_FUNCS) + r")\s*\(")
_PY_FROM_IMPORT = re.compile(r"\bfrom\s+(?:os|shutil)\s+import\b")
_PY_PATH_METHOD = re.compile(
    r"\.\s*(write_text|write_bytes|touch|unlink|mkdir|rmdir|rename|replace|symlink_to|hardlink_to|open)\s*\("
)
_PY_PATH_RECEIVER = re.compile(r"""\bPath\s*\(\s*('[^'\\]*'|"[^"\\]*")\s*\)\s*$""")
_JS_CALL = re.compile(r"(?<![\w$])(" + "|".join(_JS_FUNCS) + r")\s*\(")


def _py_open(code: str) -> list[str | None]:
    out: list[str | None] = []
    for m in re.finditer(r"\bopen\s*\(", code):
        args = _call_args(code, m.end())
        if args is None:
            out.append(None)
            continue
        pos, kw = _split_kw(args)
        mode_arg = kw.get("mode") if "mode" in kw else (pos[1] if len(pos) > 1 else None)
        if mode_arg is None:
            continue  # モードが無い＝読み取り
        mode = _lit(mode_arg)
        if mode is None:
            out.append(None)
        elif any(c in mode for c in "wax+"):
            out.append(_lit(pos[0] if pos else kw.get("file")))
    return out


_OPEN_MODULES = re.compile(r"\b(?:gzip|bz2|lzma|io|codecs|os|tarfile|zipfile|webbrowser)\s*\.\s*$")


def _py_open_writes(args: list[str] | None) -> bool:
    """Path(…).open(モード) の呼び出しが書き込みのモードか（読めないモードも True）。モードが無ければ読み取り。"""
    if args is None:
        return True
    pos, kw = _split_kw(args)
    mode_arg = kw.get("mode") if "mode" in kw else (pos[0] if pos else None)
    if mode_arg is None:
        return False
    mode = _lit(mode_arg)
    return mode is None or any(c in mode for c in "wax+")


_MODE_SHAPE = re.compile(r"^[rwaxbtU+]{1,4}$")


def _first_is_filename(args: list[str] | None) -> bool:
    """.open の最初の引数が、モードの形でない文字（＝ファイル名）か。

    Path(…).open は最初の引数がモードだが、Image.open('a.png') などはファイル名を取る。ファイル名なら、
    組み込みの open と同じく 2 つ目の引数か mode= がモードで、それは _py_open（open( の形は .open( にも当たる）が判定する。
    最初の引数が文字でないとき・モードの形のときは False（今までどおり Path の open として見る）。"""
    if not args:
        return False
    pos, _ = _split_kw(args)
    first = _lit(pos[0]) if pos else None
    return first is not None and not _MODE_SHAPE.match(first)


def _py_path_methods(code: str) -> list[str | None]:
    out: list[str | None] = []
    for m in _PY_PATH_METHOD.finditer(code):
        before = code[: m.start()]
        if re.search(r"\b(?:os|shutil)\s*$", before):
            continue  # os.unlink など。下の関数の表で見る
        args = _call_args(code, m.end())
        name = m.group(1)
        if name == "replace" and args is not None and len(args) != 1:
            continue  # 文字の replace
        recv = _PY_PATH_RECEIVER.search(before)
        if name == "open":
            if not recv and _first_is_filename(args):
                continue  # Image.open('a.png', …) など。組み込みの open と同じ形として _py_open が見る
            if _py_open_writes(args) and not (recv or _OPEN_MODULES.search(before)):
                out.append(None)
            elif _py_open_writes(args) and recv:
                out.append(_lit(recv.group(1)))
            continue
        out.append(_lit(recv.group(1)) if recv else None)
        if name in ("rename", "replace", "symlink_to", "hardlink_to"):
            out.append(_lit(args[0]) if args else None)
    return out


def _py_functions(code: str) -> list[str | None]:
    out: list[str | None] = []
    calls = list(_PY_MODULE_CALL.finditer(code))
    if _PY_FROM_IMPORT.search(code):
        calls += list(_PY_BARE_CALL.finditer(code))
    for m in calls:
        args = _call_args(code, m.end())
        pos = _split_kw(args)[0] if args is not None else []
        out += _pick(pos, _PY_FUNCS[m.group(1)])
    return out


def _python_targets(code: str) -> list[str | None]:
    """python のコードの書き込み先。リテラルならその文字、読めなければ None。構文は解析せず、形で拾う。"""
    return _py_open(code) + _py_path_methods(code) + _py_functions(code)


def _node_targets(code: str) -> list[str | None]:
    out: list[str | None] = []
    for m in _JS_CALL.finditer(code):
        args = _call_args(code, m.end())
        pos = _split_kw(args)[0] if args is not None else []
        out += _pick(pos, _JS_FUNCS[m.group(1)])
    return out


class _Run:
    """1回の呼び出しの判定。st は作業用の写しで、通ったときだけ呼び出し側が持ち帰る。"""

    def __init__(self, project_dir: Path, can_write: Callable[[str], bool], hint: str, st: BashState,
                 environ: Mapping[str, str]) -> None:
        self.root = Path(os.path.realpath(project_dir))
        self.can_write = can_write
        self.hint = hint
        self.st = st
        self.environ = environ

    # -- 走査 --

    def run(self, src: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise _Deny(UNPARSE)
        cmd = _Cmd([], [])
        stack: list[tuple[list[Path], bool]] = []
        for t in _Lexer(src).run() + [Op("\n")]:
            if isinstance(t, Word):
                cmd.words.append(t)
            elif isinstance(t, Redir):
                cmd.redirs.append(t)
            else:
                self.command(cmd, depth)
                cmd = _Cmd([], [])
                if t.s == "(":
                    stack.append((list(self.st.cwds), self.st.cwd_unknown))
                elif t.s == ")" and stack:
                    self.st.cwds, self.st.cwd_unknown = stack.pop()

    def sub(self, src: str, depth: int) -> None:
        """サブシェルで動くものを調べる（cd は外へ出さない）。"""
        saved = (list(self.st.cwds), self.st.cwd_unknown)
        try:
            self.run(src, depth + 1)
        finally:
            self.st.cwds, self.st.cwd_unknown = saved

    def command(self, cmd: _Cmd, depth: int) -> None:
        for w in cmd.words:
            for s in w.subs:
                self.sub(s, depth)
        for r in cmd.redirs:
            for s in (r.target.subs if r.target else ()):
                self.sub(s, depth)
            if r.op in HEREDOC_OPS and not r.quoted:
                for s in _subs_in_text(r.body):
                    self.sub(s, depth)
        words = self.strip_head(cmd.words)
        for r in cmd.redirs:
            self.redirect(r)
        if words:
            self.body(words, cmd.redirs, depth)

    def redirect(self, r: Redir) -> None:
        t = r.target
        if t is None:
            return
        if r.op in WRITE_REDIRECTS:
            self.check(t)
        elif r.op == ">&" and (t.expands or not re.fullmatch(r"\d+-?|-", t.text)):
            self.check(t)

    # -- 先頭の飾りを外す --

    def taint(self, text: str) -> None:
        m = ASSIGN.match(text)
        if m and m.group(1) in TAINT_VARS:
            self.st.env_tainted = True

    def strip_head(self, words: list[Word]) -> list[Word]:
        while words and not words[0].expands and words[0].text in KEYWORDS:
            words = words[1:]
        while words and ASSIGN.match(words[0].text):
            self.taint(words[0].text)
            words = words[1:]
        while words:
            name = _name(words[0])
            rest = self.strip_one(name, words[1:])
            if rest is None:
                break
            words = rest
        return words

    def strip_one(self, name: str | None, rest: list[Word]) -> list[Word] | None:
        """接頭のコマンド（env・nohup・timeout など）を1つ外した残り。接頭でなければ None。"""
        if name in ("nohup", "time", "command", "exec", "builtin", "stdbuf"):
            return _drop_options(rest)
        if name == "nice":
            return rest[2:] if rest and rest[0].text == "-n" else _drop_options(rest)
        if name == "timeout":
            while rest and rest[0].text.startswith("-"):
                rest = rest[2:] if rest[0].text in ("-k", "-s", "--kill-after", "--signal") else rest[1:]
            return rest[1:]
        if name == "env":
            return self.strip_env(rest)
        return None

    def strip_env(self, rest: list[Word]) -> list[Word]:
        while rest:
            t = rest[0].text
            if ASSIGN.match(t):
                self.taint(t)
                rest = rest[1:]
            elif t in ("-C", "--chdir"):
                self.st.cwd_unknown = True
                rest = rest[2:]
            elif t in ("-u", "-S", "--unset"):
                rest = rest[2:]
            elif t.startswith("-") and t != "-":
                rest = rest[1:]
            else:
                break
        return rest

    # -- コマンドごとの書き込み先 --

    def body(self, words: list[Word], redirs: list[Redir], depth: int) -> None:
        name = _name(words[0])
        args = words[1:]
        if name is None:
            return
        if name in SIMPLE:
            short, long_, kind = SIMPLE[name]
            for w in _parse_args(args, short, long_)[0]:
                self.check(w, kind)
        elif name in COPY_SHORT:
            self.copy_like(name, args)
        elif name in ("cd", "pushd", "popd"):
            self.cd(name, args)
        elif name in ENV_BUILTINS:
            for w in args:
                self.taint(w.text)
        elif name == "dd":
            for w in args:
                if w.text.startswith("of="):
                    self.check(replace(w, text=w.text[3:], tilde=False))
        elif name == "sed":
            self.sed(args)
        elif name == "perl":
            self.perl(args)
        elif name == "find":
            self.find(args, depth)
        elif name == "xargs":
            self.xargs(args, depth)
        elif name == "git":
            self.git(args)
        elif name == "eval":
            self.run(" ".join(w.text for w in args), depth + 1)
        elif name in SHELLS:
            self.shell(args, redirs, depth)
        elif PYTHON.fullmatch(name):
            self.interpreter(args, redirs, ("-c",), "-m", _python_targets)
        elif name == "node":
            self.interpreter(args, redirs, ("-e", "--eval", "-p", "--print"), "", _node_targets)

    def simple(self, words: list[Word], depth: int) -> None:
        words = self.strip_head(words)
        if words:
            self.body(words, [], depth)

    def copy_like(self, name: str, args: list[Word]) -> None:
        ops, opts = _parse_args(args, COPY_SHORT[name], ("target-directory", "suffix", "mode", "owner", "group"))
        if name == "install" and any(o in ("d", "directory") for o, _ in opts):
            for w in ops:
                self.check(w, "mkdir")
            return
        tdir = next((v for o, v in opts if o in ("t", "target-directory") and v is not None), None)
        if tdir is None and name == "ln" and len(ops) == 1:
            tdir, srcs = Word("./"), ops
        elif tdir is not None:
            srcs = ops
        elif len(ops) < 2:
            return
        else:
            srcs = ops[:-1]
        if name == "mv":
            for s in srcs:
                self.check(s, "dir" if self.is_dir(s) else "file")  # フォルダは、その下も見る
        dest = tdir if tdir is not None else ops[-1]
        into = tdir is not None or len(srcs) > 1 or dest.text.endswith("/") or self.is_dir(dest)
        for d in ([_derive(dest, s) for s in srcs] if into else [dest]):
            self.check(d)

    def sed(self, args: list[Word]) -> None:
        in_place, script, ops, done, i = False, False, [], False, 0
        while i < len(args):
            w = args[i]
            t = w.text
            i += 1
            if done or w.expands or not t.startswith("-") or t == "-":
                ops.append(w)
            elif t == "--":
                done = True
            elif t.startswith("--"):
                name, eq, _ = t[2:].partition("=")
                in_place = in_place or name == "in-place"
                script = script or name in ("expression", "file")
                i += 0 if eq or name not in ("expression", "file", "line-length") else 1
            else:
                flags, took = self.sed_cluster(t)
                in_place, script = in_place or flags[0], script or flags[1]
                i += 1 if took else 0
        if in_place:
            for w in ops if script else ops[1:]:
                self.check(w)

    @staticmethod
    def sed_cluster(t: str) -> tuple[tuple[bool, bool], bool]:
        """sed の短いオプションの連なり → （（-i あり, -e/-f あり）, 次の語を値に使ったか）。"""
        in_place = script = False
        for j in range(1, len(t)):
            ch = t[j]
            if ch == "i":
                return (True, script), False  # 残りは接尾
            if ch in "efl":
                return (in_place, script or ch != "l"), j + 1 >= len(t)
        return (in_place, script), False

    def perl(self, args: list[Word]) -> None:
        in_place, code, ops, done, i = False, False, [], False, 0
        while i < len(args):
            w = args[i]
            t = w.text
            i += 1
            if done or w.expands or not t.startswith("-") or t == "-":
                ops.append(w)
            elif t == "--":
                done = True
            else:
                for j in range(1, len(t)):
                    ch = t[j]
                    if ch == "i":
                        in_place = True
                        break
                    if ch in "eEI":
                        code = code or ch != "I"
                        i += 1 if j + 1 >= len(t) else 0
                        break
                    if ch in "FMm":
                        break
        if in_place:
            for w in ops if code else ops[1:]:
                self.check(w)

    def find(self, args: list[Word], depth: int) -> None:
        starts: list[Word] = []
        i = 0
        while i < len(args):
            t = args[i].text
            if t in ("-H", "-L", "-P"):
                pass
            elif args[i].expands or not (t.startswith("-") or t in ("(", "!")):
                starts.append(args[i])
            else:
                break
            i += 1
        delete, files, execs = False, [], []
        while i < len(args):
            t = args[i].text
            if t == "-delete":
                delete = True
            elif t in ("-fprint", "-fprint0", "-fls"):
                delete = True  # 探す場所のフォルダも見る
                if i + 1 < len(args):
                    files.append(args[i + 1])
                    i += 1
            elif t in ("-exec", "-execdir", "-ok", "-okdir"):
                j = i + 1
                while j < len(args) and args[j].text not in (";", "+"):
                    j += 1
                execs.append(args[i + 1 : j])
                i = j
            i += 1
        for tpl in execs:
            self.simple(tpl, depth)
        if delete:
            for s in starts or [Word(".")]:
                self.check(s, "dir")
        for f in files:
            self.check(f)

    def xargs(self, args: list[Word], depth: int) -> None:
        rest = _parse_args(args, "IndPLsEa", stop=True)[0]
        if rest:
            self.simple(rest + [UNREAD_WORD], depth)

    def git(self, args: list[Word]) -> None:
        i, moved = 0, False
        while i < len(args) and args[i].text.startswith("-"):
            t = args[i].text
            takes = t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace")
            moved = moved or t in ("-C", "--git-dir", "--work-tree") or t.startswith(("--git-dir=", "--work-tree="))
            i += 2 if takes else 1
        if i >= len(args) or args[i].text not in ("restore", "rm", "mv"):
            return
        ops = _parse_args(args[i + 1 :], "s", ("source", "pathspec-from-file"))[0]
        for w in ops:
            if w.expands or w.text.startswith(":") or any(c in w.text for c in "*?["):
                raise _Deny(_unread(w.text))  # glob・pathspec の特別な書き方は先を読めない
            if moved:
                self.check(UNREAD_WORD)
            self.check(w, "dir" if w.text in (".", "") or w.text.endswith("/") or self.is_dir(w) else "file")

    def shell(self, args: list[Word], redirs: list[Redir], depth: int) -> None:
        i = 0
        while i < len(args):
            t = args[i].text
            if t.startswith("-") and not t.startswith("--") and "c" in t[1:]:
                if i + 1 < len(args):
                    self.sub(args[i + 1].text, depth)
                return
            if t == "-":
                break
            if not t.startswith("-"):
                return  # スクリプトのファイル。中身は読まない
            i += 2 if t in ("-o", "-O") else 1
        for text in _stdin_texts(redirs):
            self.sub(text, depth)

    def interpreter(self, args: list[Word], redirs: list[Redir], code_opts: tuple[str, ...], module_opt: str,
                    targets: Callable[[str], list[str | None]]) -> None:
        """python・node のコード（-c・-e・標準入力）の書き込み先を調べる。コードの構文は読まず、形で拾う。"""
        codes: list[Word] = []
        i = 0
        while i < len(args):
            t = args[i].text
            eq = next((o for o in code_opts if o.startswith("--") and t.startswith(o + "=")), None)
            if eq:
                codes = [replace(args[i], text=t[len(eq) + 1 :])]
                break
            if t in code_opts or (t.startswith("-") and not t.startswith("--") and t.endswith("c") and "-c" in code_opts):
                codes = args[i + 1 : i + 2]
                break
            if t == module_opt:
                return
            if t == "-":
                codes = [Word(x) for x in _stdin_texts(redirs)]
                break
            if t.startswith("-"):
                i += 2 if t in ("-W", "-X", "-Q") else 1
                continue
            return  # スクリプトのファイル。中身は読まない
        else:
            codes = [Word(x) for x in _stdin_texts(redirs)]
        for c in codes:
            for lit in targets(c.text):
                if lit is None or (c.expands and ("$" in lit or "`" in lit)):
                    raise _Deny(_unread("コードの中の書き込み先"))
                self.check(Word(lit))

    def cd(self, name: str, args: list[Word]) -> None:
        st = self.st
        ops = [w for w in args if not w.text.startswith("-") or w.text == "-"]
        if name == "popd" or not ops or ops[0].text == "-" or ops[0].glob:
            st.cwd_unknown = True
            return
        cands = self.candidates(ops[0])
        if cands is None or not all(os.path.isdir(c) for c in cands):
            st.cwd_unknown = True
            return
        st.set_cwds([Path(os.path.realpath(c)) for c in cands])
        if os.path.isabs(cands[0]) and len(cands) == 1:
            st.cwd_unknown = False

    # -- 先の判定 --

    def candidates(self, w: Word) -> list[str] | None:
        """先の語を、判定にかける絶対パスの一覧にする。読めなければ None。"""
        text = w.text
        if w.expands:
            text = self.tmpdir_path(w)
            if text is None:
                return None
        elif w.tilde:
            if self.st.env_tainted or not (text == "~" or text.startswith("~/")):
                return None
            text = (self.environ.get("HOME") or str(Path.home())) + text[1:]
        first = min((text.find(c) for c in "*?[" if c in text), default=-1)
        if w.glob and first >= 0 and "/" in text[first:]:
            return None
        if os.path.isabs(text):
            return [text]
        if self.st.cwd_unknown:
            return None
        return [os.path.join(str(b), text) for b in self.st.cwds]

    def tmpdir_path(self, w: Word) -> str | None:
        """$TMPDIR/… だけは読める（書き換えを見ていないとき）。"""
        if self.st.env_tainted or w.subs or len(w.exps) != 1 or w.exps[0] not in ("$TMPDIR", "${TMPDIR}"):
            return None
        if not w.text.startswith(w.exps[0] + "/"):
            return None
        tmp = self.environ.get("TMPDIR") or tempfile.gettempdir()
        return tmp.rstrip("/") + w.text[len(w.exps[0]) :]

    def is_dir(self, w: Word) -> bool:
        cands = self.candidates(w)
        return bool(cands) and any(os.path.isdir(c) for c in cands or [])

    def check(self, w: Word, kind: str = "file") -> None:
        if w.text == "" and not w.expands:
            return
        if w.glob and not w.expands or w.glob and w.expands and not w.subs:
            self.check_glob(w, kind)
            return
        cands = self.candidates(w)
        if cands is None:
            raise _Deny(_unread(w.text))
        for c in cands:
            why = self.judge(c, kind)
            if why:
                raise _Deny(why)

    def check_glob(self, w: Word, kind: str) -> None:
        """最後の部品に glob を含む先。何に当たるか読めないので、次のときだけ通す。
        一時フォルダの中（プロジェクトの外）なら通す。プロジェクトの中は、根の直下なら止め、
        下のフォルダなら書いた文字のまま判定する（そのフォルダが範囲外ならそこで止まる）。"""
        t = w.text
        first = min((t.find(c) for c in "*?[" if c in t), default=-1)
        if first >= 0 and "/" not in t[first:] and "/" in t:
            cands = self.candidates(replace(w, text=t[: t.rfind("/") + 1], glob=False))
            if cands:
                reals = [Path(os.path.realpath(c)) for c in cands]
                inside = [r == self.root or self.root in r.parents for r in reals]
                if not any(inside) and all(self.in_temp(r) for r in reals):
                    return
                if all(inside) and all(r != self.root for r in reals):
                    for c in self.candidates(w) or []:
                        why = self.judge(c, kind)
                        if why:
                            raise _Deny(why)
                    return
        raise _Deny(_unread(w.text))

    def judge(self, path: str, kind: str) -> str | None:
        norm = os.path.normpath(path)
        if norm in DEV_OK or re.fullmatch(r"/dev/fd/\d+", norm):
            return None
        real = Path(os.path.realpath(path))
        try:
            rel = real.relative_to(self.root).as_posix()
        except ValueError:
            return None if self.in_temp(real) else OUTSIDE
        if kind == "mkdir":
            return None
        ok = self.can_write(rel)
        if kind == "dir":  # フォルダは、その下に書けるかも見る
            ok = ok and self.can_write("_" if rel == "." else rel + "/_")
            if ok and rel == ".":
                return self.judge_tree(real)
        return None if ok else f"この段で書き込めるのは {self.hint} だけです（{rel} は対象外）"

    def judge_tree(self, top: Path) -> str | None:
        """根を指すフォルダ操作：実際にあるファイルを下まで見て、書けないものが1つでもあれば止める。
        .git は見ない・symlink はたどらない・MAX_TREE_FILES を超えたら止める（ファイルシステムを読むのはここだけ）。"""
        count = 0
        for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
            if Path(dirpath) == top and ".git" in dirnames:
                dirnames.remove(".git")
            for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
                count += 1
                if count > MAX_TREE_FILES:
                    return f"根を指すフォルダ操作で見るファイルが多すぎる（{MAX_TREE_FILES} 超）ため止めました"
                rel = Path(dirpath, name).relative_to(top).as_posix()
                if not self.can_write(rel):
                    return f"この段で書き込めるのは {self.hint} だけです（{rel} は対象外）"
        return None

    @staticmethod
    def in_temp(real: Path) -> bool:
        roots = {*TEMP_ROOTS, os.path.realpath(tempfile.gettempdir())}
        roots |= {os.path.realpath(r) for r in roots}
        return any(real == Path(r) or Path(r) in real.parents for r in roots)


def _unread(what: str) -> str:
    return f"Bash の書き込み先を読み取れません（{what}）。変数や $(...) を使わず、書き込み先を文字で書いてください"


def _drop_options(rest: list[Word]) -> list[Word]:
    while rest and rest[0].text.startswith("-") and rest[0].text != "-":
        rest = rest[1:]
    return rest


def _derive(dest: Word, src: Word) -> Word:
    """宛先がフォルダのとき、元ごとの書き込み先（宛先/元の最後の名前）。名前が読めなければ読めない先。"""
    if src.expands:
        return UNREAD_WORD
    base = src.text.rstrip("/").rsplit("/", 1)[-1]
    return replace(dest, text=dest.text.rstrip("/") + "/" + base)


def _stdin_texts(redirs: list[Redir]) -> list[str]:
    """標準入力から渡されるコード（ヒアドキュメントの本文・<<< の語）。"""
    out = []
    for r in redirs:
        if r.op in HEREDOC_OPS:
            out.append(r.body)
        elif r.op == "<<<" and r.target is not None:
            out.append(r.target.text)
    return out


def check_bash_writes(
    command: str,
    *,
    project_dir: Path,
    can_write: Callable[[str], bool],
    write_scope_hint: str,
    state: BashState | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Bash のコマンドの書き込み先を段の範囲で判定する。止めるなら理由を返す。通すなら None。

    state を渡すと、通したときだけ作業フォルダ・TMPDIR の書き換えの覚えを更新する（止めたコマンドは動かないので覚えない）。
    渡さないときは、プロジェクトの直下だけを作業フォルダとして判定し、何も覚えない。
    """
    work = state.copy() if state is not None else BashState.new(project_dir)
    runner = _Run(project_dir, can_write, write_scope_hint, work, os.environ if environ is None else environ)
    try:
        runner.run(command, 0)
    except _Deny as e:
        return e.reason
    except Exception:  # 読み取れない入力・想定外の形は、落ちずに安全側（止める）へ
        return UNPARSE
    if state is not None:
        work.set_cwds(work.cwds + [runner.root])  # 次の呼び出しでは、cd が効いていないかもしれない
        state.cwds, state.cwd_unknown, state.env_tainted = work.cwds, work.cwd_unknown, work.env_tainted
    return None
