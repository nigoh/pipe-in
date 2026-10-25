"""D0039：/pipe-in のスキルを、長い会話でも決まりが残る形に整える。定義（.claude/）と設定の検査。

読むだけで書かない（偽の文は、文字列で組み立てる）。SDK は呼ばない。
文書（CLAUDE.md・docs/）と決定の記録の検査は tests/test_skill_tidy_docs.py、
フックの判断が変わらないことの総当たりは tests/test_pipe_in_guard.py の末尾にある。

- 補助ファイル（record.md・artifact.md・screen-check.md）がまだ無いときは、read_doc が「が無い」で落とす。
  そのテストだけが落ち、ファイルごと読めずに全部が落ちることはない。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
- 前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。
  探すときは test_rename.OLD_NAME を使い、語が要るときは文字をつないで作る。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

import pytest

from test_rename import OLD_NAME

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "pipe-in"
SKILL = SKILL_DIR / "SKILL.md"
AGENTS_DIR = ROOT / ".claude" / "agents"
HOOKS_DIR = ROOT / ".claude" / "hooks"
SETTINGS = ROOT / ".claude" / "settings.json"
SKILL_REL = ".claude/skills/pipe-in/"
HELPERS = ("record.md", "artifact.md", "screen-check.md")

OLD = "dev" + "pipe"  # 前の名前（文字をつないで作る）


# ---- 補助：読む・見出しで節を切り出す --------------------------------------------------------


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_doc(path: Path) -> str:
    """読む。無ければ「が無い」でそのテストだけを落とす。"""
    if not path.is_file():
        pytest.fail(f"{rel(path)} が無い（まだ作っていない）", pytrace=False)
    return path.read_text(encoding="utf-8")


class Head(NamedTuple):
    depth: int
    title: str
    start: int  # 見出しの行の始まり（文字の位置）
    body: int  # 見出しの次の行の始まり


HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def parse_headings(md: str) -> list[Head]:
    """見出し（# から ######）を上から。``` で囲んだコードの中の # は見出しにしない。"""
    out: list[Head] = []
    pos = 0
    in_code = False
    for line in md.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if text.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code:
            m = HEADING_LINE.match(text)
            if m:
                out.append(Head(len(m.group(1)), m.group(2), pos, pos + len(line)))
        pos += len(line)
    return out


def find_head(md: str, title: str, *, depth: int | None = None, exact: bool = False) -> Head | None:
    for h in parse_headings(md):
        if depth is not None and h.depth != depth:
            continue
        if (h.title == title) if exact else (title in h.title):
            return h
    return None


def section_end(md: str, head: Head, *, direct: bool = False) -> int:
    """節の終わり（文字の位置）。direct なら次の見出し（どの階層でも）、そうでなければ次の同じか上の階層の見出しの前。"""
    for nxt in parse_headings(md):
        if nxt.start <= head.start:
            continue
        if direct or nxt.depth <= head.depth:
            return nxt.start
    return len(md)


def section_text(md: str, title: str, *, depth: int | None = None, exact: bool = False, direct: bool = False) -> str | None:
    """見出しの次の行から、節の終わりの前まで。節が無ければ None。"""
    head = find_head(md, title, depth=depth, exact=exact)
    if head is None:
        return None
    return md[head.body : section_end(md, head, direct=direct)]


def need_section(md: str, title: str, *, where: str = "SKILL.md", **kw) -> str:
    """節の本文。節が無ければ「節が無い」でそのテストだけを落とす。"""
    body = section_text(md, title, **kw)
    if body is None:
        shown = [f"{'#' * h.depth} {h.title}" for h in parse_headings(md) if h.depth <= 3]
        pytest.fail(f"{where} に見出し「{title}」の節が無い（今の見出し：{shown}）", pytrace=False)
    return body


def lacking(text: str, words) -> list[str]:
    return [w for w in words if w not in text]


def line_with(text: str, needle: str, where: str) -> str:
    """needle を含む最初の行。無ければ「行が無い」で落とす。"""
    for line in text.splitlines():
        if needle in line:
            return line
    pytest.fail(f"{where} に「{needle}」を含む行が無い", pytrace=False)


def front_matter(md: str) -> str:
    parts = md.split("---")
    assert len(parts) >= 3, "前置き（--- で囲んだ部分）が無い"
    return parts[1]


def skill() -> str:
    return read_doc(SKILL)


# ---- AC-01：冒頭に必ず守る決まりを置く ----------------------------------------------------------


def test_D0039_AC_01_最初の二つの見出しが必ず守ることと始める前に():
    """D0039-AC-01: SKILL.md の # /pipe-in の次の ## の見出しが「必ず守ること」で、その次の ## が「0. 始める前に」になる。"""
    titles = [h.title for h in parse_headings(skill()) if h.depth == 2]
    assert titles[:2] == ["必ず守ること", "0. 始める前に"], f"## の見出しの最初の二つ：{titles[:2]}"


def test_D0039_AC_01_前置きは今のまま_守る():
    """D0039-AC-01: 前置き（name・disable-model-invocation・argument-hint）は今の文字のまま。（今のまま通る。守る）"""
    lines = front_matter(skill()).splitlines()
    for want in ("name: pipe-in", "disable-model-invocation: true", "argument-hint: [--auto] [--artifact] <足したい機能の要件メモ>"):
        assert want in lines, f"前置きに「{want}」の行が無い"


def test_D0039_AC_01_ARGUMENTSの行は始める前にの先頭にあり_節より後ろで_全体で1回():
    """D0039-AC-01: $ARGUMENTS は SKILL.md に 1 回だけ。「0. 始める前に」の見出しのあとの最初の空でない行にあり、その次の空でない行が「（空なら」。
    「必ず守ること」の節より後ろ（要件メモ全文が入っても、冒頭の節が先頭から押し出されないように）。"""
    md = skill()
    assert md.count("$ARGUMENTS") == 1, f"$ARGUMENTS が {md.count('$ARGUMENTS')} 回ある"
    args_at = md.index("$ARGUMENTS")
    zero = find_head(md, "0. 始める前に", depth=2, exact=True)
    assert zero is not None, "「## 0. 始める前に」の見出しが無い"
    line_no = md[:args_at].count("\n") + 1
    assert args_at > zero.body, f"$ARGUMENTS の行（{line_no} 行目）が「## 0. 始める前に」の見出しより前にある"
    after = [line for line in md[zero.body :].splitlines() if line.strip()]
    assert "$ARGUMENTS" in after[0], f"「0. 始める前に」の次の本文の行が $ARGUMENTS の行でない：{after[0]}"
    assert after[1].startswith("（空なら"), f"$ARGUMENTS の次の空でない行が「（空なら」で始まらない：{after[1]}"
    must = find_head(md, "必ず守ること", depth=2, exact=True)
    assert must is not None and must.start < zero.start, "「## 必ず守ること」が「## 0. 始める前に」より前に無い"


# ---- AC-02：必ず守ることの節の語句 -------------------------------------------------------------

MUST_TITLE = "必ず守ること"
MUST_RULES: dict[str, tuple[str, ...]] = {
    "approval": ("要件定義・設計・テスト先行", "承認されるまで次の段に進まない", "revise", "quit"),
    "auto": ("--auto", "--yes", "決めきれない点", "文書係の案", "監査と助言", "不合格"),
    "commit": ("コミット", "main に入れる", "push", "人に言われるまで"),
    "reread": ("読み直", "SKILL.md", "補助ファイル"),
}


def must_body(md: str) -> str | None:
    return section_text(md, MUST_TITLE, depth=2, exact=True)


def need_must(md: str) -> str:
    return need_section(md, MUST_TITLE, depth=2, exact=True)


@pytest.mark.parametrize("rule", list(MUST_RULES))
def test_D0039_AC_02_必ず守ることの節に決まりの語句がある(rule):
    """D0039-AC-02: 「必ず守ること」の節に、4 つの決まり（承認で止まる・--auto は引数だけ・コミットは言われるまでしない・読み直す）の語句がある。"""
    assert lacking(need_must(skill()), MUST_RULES[rule]) == []


def fake_skill(must: str | None, rest: str = "") -> str:
    head = "---\nname: x\n---\n\n# /pipe-in — 題\n\n導入。\n\n"
    body = "" if must is None else f"## {MUST_TITLE}\n\n{must}\n\n"
    return head + body + "## 0. 始める前に\n\n足したい機能: $ARGUMENTS\n\n" + rest


@pytest.mark.parametrize("rule", list(MUST_RULES))
def test_D0039_AC_02_見本_語句を1つ消した文はその語句だけを欠けとして返す_守る(rule):
    """D0039-AC-02: 検査そのものの確かめ。語句をすべて含む節は欠け 0 件、語句を 1 つ消した節は、その語句だけを欠けとして返し、節が無ければ None。
    （今のまま通る。守る）"""
    words = MUST_RULES[rule]
    full = fake_skill("・".join(words))
    assert lacking(must_body(full) or "", words) == []
    for gone in words:
        body = must_body(fake_skill("・".join(w for w in words if w != gone)))
        assert body is not None and lacking(body, words) == [gone]
    assert must_body(fake_skill(None)) is None


# ---- AC-03：冒頭の字数 -------------------------------------------------------------------------

MUST_BODY_LIMIT = 800
HEAD_LIMIT = 1600


def head_until_must_end(md: str) -> str | None:
    """先頭（前置きを含む）から「必ず守ること」の節の終わりまで。節が無ければ None。"""
    head = find_head(md, MUST_TITLE, depth=2, exact=True)
    return None if head is None else md[: section_end(md, head)]


def test_D0039_AC_03_必ず守ることの節の本文は800字以内():
    """D0039-AC-03: 「必ず守ること」の節の本文（見出しの次の行から次の ## の前まで）は 800 字以内。"""
    body = need_must(skill())
    assert len(body) <= MUST_BODY_LIMIT, f"節の本文が {len(body)} 字（上限 {MUST_BODY_LIMIT}）"


def test_D0039_AC_03_先頭から節の終わりまでは1600字以内():
    """D0039-AC-03: SKILL.md の先頭（前置きを含む）から「必ず守ること」の節の終わりまでは 1,600 字以内
    （1 字を 3 トークンと数えても 5,000 トークンに収まる、安全側の目安。トークンの数え方は確かめていない）。"""
    md = skill()
    need_must(md)
    head = head_until_must_end(md)
    assert head is not None and len(head) <= HEAD_LIMIT, f"先頭から節の終わりまでが {len(head or '')} 字（上限 {HEAD_LIMIT}）"


def test_D0039_AC_03_見本_節の切り出しは次の見出しで止まる_守る():
    """D0039-AC-03: 検査そのものの確かめ。節の本文と先頭からの長さは、次の ## の前で数え終わる（後ろの節の長さを数えない）。
    長すぎる節は上限を超えたと分かる。（今のまま通る。守る）"""
    short = fake_skill("あ" * 100, rest="い" * 5000)
    body = must_body(short)
    head = head_until_must_end(short)
    assert body is not None and len(body) <= MUST_BODY_LIMIT
    assert head is not None and len(head) <= HEAD_LIMIT and "い" not in head
    long = fake_skill("あ" * 900)
    assert len(must_body(long) or "") > MUST_BODY_LIMIT
    assert head_until_must_end(fake_skill(None)) is None


# ---- AC-04：承認の決まりの本文は冒頭の節に 1 か所だけ ------------------------------------------------

APPROVAL = "承認されるまで次の段に進まない"
AUTO_ITEM_WORDS = ("各段の結果", "決めきれない点", "guard.py", "3回", "文書係の案", "監査と助言", "コミット・push")


def flow_body(md: str) -> str:
    """「段の進め方」の節の、すぐ下の本文（小見出しの前まで）。"""
    return need_section(md, "段の進め方", depth=2, exact=True, direct=True)


def test_D0039_AC_04_承認の決まりの文は全体で1回で_冒頭の節の中():
    """D0039-AC-04: 「承認されるまで次の段に進まない」は SKILL.md に 1 回だけ出て、「必ず守ること」の節の中にある。"""
    md = skill()
    assert md.count(APPROVAL) == 1, f"「{APPROVAL}」が {md.count(APPROVAL)} 回ある"
    assert APPROVAL in need_must(md), "その文が「必ず守ること」の節の中に無い（今は「段の進め方」にある）"


def test_D0039_AC_04_段の進め方はその文を持たず_冒頭の節を指す():
    """D0039-AC-04: 「段の進め方」の節に承認の文が無く、止まる決まりは「必ず守ること」と指す。"""
    flow = flow_body(skill())
    assert APPROVAL not in flow, "「段の進め方」に承認の文が残っている"
    assert "必ず守ること" in flow, "「段の進め方」が「必ず守ること」を指していない"


def test_D0039_AC_04_段の進め方に差し戻しと中止の書き方が残る_守る():
    """D0039-AC-04: 「段の進め方」に review <段> revise・--note 指摘を反映・review <段> quit・finish STOPPED_BY_HUMAN の書き方が残る。
    （今のまま通る。守る）"""
    flow = flow_body(skill())
    assert lacking(flow, ("review <段> revise", "--note 指摘を反映", "review <段> quit", "finish STOPPED_BY_HUMAN")) == []


def test_D0039_AC_04_auto_の節に7項目が残る_守る():
    """D0039-AC-04: --auto の節の 7 項目（各段の結果／決めきれない点／guard.py を狭める変更／不合格 3 回／文書係の案／監査と助言／コミット・push）が、
    項目の数でなく 7 つそれぞれの語句で残る。（今のまま通る。守る）"""
    body = need_section(skill(), "止まらずに進めるとき", depth=3, direct=True)
    assert lacking(body, AUTO_ITEM_WORDS) == []


def test_D0039_AC_04_コミットの禁止は冒頭と_auto_の節と仕上げの3か所にある():
    """D0039-AC-04: コミット・push は人に言われるまでしない、という禁止が、冒頭の節・--auto の節・「決定の記録と仕上げ」の 3 か所にある（重ねてよい）。"""
    md = skill()
    places = {
        "冒頭の「必ず守ること」": section_text(md, MUST_TITLE, depth=2, exact=True),
        "--auto の節": section_text(md, "止まらずに進めるとき", depth=3, direct=True),
        "決定の記録と仕上げ": section_text(md, "決定の記録と仕上げ", depth=3),
    }
    without = [name for name, body in places.items() if body is None or "コミット" not in body or "人に言われるまで" not in body]
    assert without == [], f"コミットの禁止の文が無い場所：{without}"


# ---- AC-05：補助ファイルがあり、SKILL.md が「いつ読むか」を添えて指す -----------------------------------


def referenced_helpers(md: str) -> set[str]:
    """SKILL.md が（.claude/skills/pipe-in/ の完全な形で）指す .md の名前。SKILL.md 自身は除く。"""
    return set(re.findall(r"\.claude/skills/pipe-in/([\w-]+\.md)", md)) - {"SKILL.md"}


def helper_set_problems(md: str, folder_names: set[str]) -> list[str]:
    """SKILL.md が指す補助ファイルと、フォルダにある SKILL.md 以外の .md の食い違い。3 つ（HELPERS）と違えば、それも。"""
    referenced = referenced_helpers(md)
    others = set(folder_names) - {"SKILL.md"}
    problems = {f"{n} を指しているが、フォルダに無い" for n in referenced - others}
    problems |= {f"{n} がフォルダにあるが、SKILL.md が指していない" for n in others - referenced}
    problems |= {f"{n} を SKILL.md が指していない" for n in set(HELPERS) - referenced}
    return sorted(problems)


def pointer_problems(md: str) -> list[str]:
    """「0. 始める前に」の節だけを見て、3 つの補助ファイルを「いつ読むか」を添えて指しているかの問題。"""
    zero = section_text(md, "0. 始める前に", depth=2, exact=True)
    if zero is None:
        return ["「## 0. 始める前に」の節が無い"]
    problems = [f"「0. 始める前に」の節に {SKILL_REL}{n} が無い" for n in HELPERS if SKILL_REL + n not in zero]
    artifact_lines = [line for line in zero.splitlines() if SKILL_REL + "artifact.md" in line]
    if artifact_lines and not any("--artifact" in line for line in artifact_lines):
        problems.append("artifact.md を指す文に --artifact が無い")
    screen_lines = [line for line in zero.splitlines() if SKILL_REL + "screen-check.md" in line]
    if screen_lines and not any("画面の AC" in line for line in screen_lines):
        problems.append("screen-check.md を指す文に「画面の AC」が無い")
    first = md.find(SKILL_REL + "record.md")
    stage1 = find_head(md, "1. 要件定義", depth=3)
    if first == -1:
        problems.append("record.md の完全なパスが SKILL.md のどこにも無い")
    elif stage1 is not None and first > stage1.start:
        problems.append("record.md を指す文が「1. 要件定義」の見出しより後ろにしか無い")
    return problems


GOOD_POINTERS = (
    "## 0. 始める前に\n\n足したい機能: $ARGUMENTS\n\n"
    f"- `{SKILL_REL}record.md`（記録のコマンド）：最初の `record start` の前に1回読む。\n"
    f"- `{SKILL_REL}artifact.md`（`--artifact` の手順）：引数に `--artifact` があるときに読む。\n"
    f"- `{SKILL_REL}screen-check.md`（画面の確認の手順）：検証で画面の AC があるときに読む。\n\n"
    "### 1. 要件定義\n\n本文。\n"
)


def test_D0039_AC_05_補助ファイルが3つある():
    """D0039-AC-05: .claude/skills/pipe-in/ に record.md・artifact.md・screen-check.md がある。"""
    absent = [n for n in HELPERS if not (SKILL_DIR / n).is_file()]
    assert absent == [], f"{SKILL_REL} に無い補助ファイル：{absent}"


def test_D0039_AC_05_始める前にが3つの補助ファイルを_いつ読むかを添えて指す():
    """D0039-AC-05: 「0. 始める前に」の節が 3 つの補助ファイルを（リポジトリからの相対パスで）指し、artifact.md の文に --artifact、
    screen-check.md の文に「画面の AC」があり、record.md を指す文は「1. 要件定義」の見出しより前にある。"""
    assert pointer_problems(skill()) == []


def test_D0039_AC_05_SKILLが指す補助ファイルはすべて実在し_フォルダの補助ファイルはすべて指される():
    """D0039-AC-05: SKILL.md が指す補助ファイルはすべて実在し、フォルダにある SKILL.md 以外の .md はすべて SKILL.md から指されている
    （この 3 つだけ）。"""
    names = {p.name for p in SKILL_DIR.glob("*.md")}
    assert helper_set_problems(skill(), names) == []


def test_D0039_AC_05_補助ファイルの案内は表にしない_守る():
    """D0039-AC-05: 補助ファイルの名前を含む行は、| で始まる行（表の行）でない（段の表の行を数える D0015-AC-26 を壊さないため）。
    （今のまま通る。守る）"""
    rows = [line for line in skill().splitlines() if line.lstrip().startswith("|") and any(n in line for n in HELPERS)]
    assert rows == []


def test_D0039_AC_05_旗の綴りが補助ファイルにしか無いコマンドには_record_md_の指しがある():
    """D0039-AC-05: 旗の綴りが record.md にしか残らない 3 か所（「段の進め方」の review <段> revise の行・「3. テスト先行」の record red red の行・
    「5. 検証」の record verdict <pass の行）に、record.md を指す一言がある（要約のあとでも綴りを探しに行けるように）。"""
    md = skill()
    sites = [
        ("段の進め方の review <段> revise", flow_body(md), "review <段> revise"),
        ("3. テスト先行の record red red", need_section(md, "3. テスト先行", depth=3), "record red red"),
        ("5. 検証の record verdict <pass", need_section(md, "5. 検証", depth=3), "record verdict <pass"),
    ]
    without = [name for name, body, needle in sites if "record.md" not in line_with(body, needle, name)]
    assert without == [], f"record.md を指していない行：{without}"


def test_D0039_AC_05_見本_短い名前だけの行と他の文書は補助ファイルの集合に入れない_守る():
    """D0039-AC-05: 検査そのものの確かめ。.claude/skills/pipe-in/ の完全な形で書いたものだけを数え、短い名前だけの行・workflow.md・specs.md・
    SKILL.md 自身は数えない。4 つ目の補助ファイルをフォルダに足したのに SKILL.md が指さない形は見つける。（今のまま通る。守る）"""
    text = "`record.md` と書くだけ。`docs/development/workflow.md`・`docs/development/specs.md`・`.claude/skills/pipe-in/SKILL.md`"
    assert referenced_helpers(text) == set()
    assert referenced_helpers(GOOD_POINTERS) == set(HELPERS)
    assert helper_set_problems(GOOD_POINTERS, {"SKILL.md", *HELPERS}) == []
    extra = helper_set_problems(GOOD_POINTERS, {"SKILL.md", *HELPERS, "extra.md"})
    assert extra == ["extra.md がフォルダにあるが、SKILL.md が指していない"], extra
    ghost = helper_set_problems(GOOD_POINTERS + f"`{SKILL_REL}ghost.md`", {"SKILL.md", *HELPERS})
    assert ghost == ["ghost.md を指しているが、フォルダに無い"], ghost


def test_D0039_AC_05_見本_始める前にの外にだけ指しがある_SKILL_は見つける_守る():
    """D0039-AC-05: 検査そのものの確かめ。3 つとも「0. 始める前に」の中で指す形は問題なし。「0.」の外（段の進め方）にだけ指しがある形は
    3 つとも欠けとして返し、artifact.md の文に --artifact が無い形・screen-check.md の文に「画面の AC」が無い形・
    record.md を指す文が「1. 要件定義」より後ろにしかない形も見つける。（今のまま通る。守る）"""
    assert pointer_problems(GOOD_POINTERS) == []
    outside = (
        "## 0. 始める前に\n\n足したい機能: $ARGUMENTS\n\n- 空。\n\n## 段の進め方\n\n"
        + "".join(f"- `{SKILL_REL}{n}`\n" for n in HELPERS)
    )
    assert len(pointer_problems(outside)) >= 3
    no_flag = GOOD_POINTERS.replace("`--artifact` の手順", "手順").replace("引数に `--artifact` がある", "あるとき")
    assert "artifact.md を指す文に --artifact が無い" in pointer_problems(no_flag)
    no_screen = GOOD_POINTERS.replace("画面の AC", "画面")
    assert "screen-check.md を指す文に「画面の AC」が無い" in pointer_problems(no_screen)
    late = GOOD_POINTERS.replace(f"- `{SKILL_REL}record.md`（記録のコマンド）：最初の `record start` の前に1回読む。\n", "") + f"後ろで `{SKILL_REL}record.md`\n"
    assert any("record.md" in p for p in pointer_problems(late))


# ---- AC-06：記録のコマンドの書き方は record.md に移る --------------------------------------------------

RECORD_WORDS = (
    "--text", "--input", "--name", "--session-id", "--agent", "--attempt", "--note", "--summary", "--error", "--feedback",
    "--test", "--command", "--failure", "approved", "revise", "quit", "blocked", "PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN",
    "STAGE_ERROR", "BLOCKED", "archive/",
)


def test_D0039_AC_06_record_md_に記録のコマンドの書き方の語が残る():
    """D0039-AC-06: record.md に、記録のコマンド 8 つの書き方と注意が移り、旗・結果の語・archive/ の 23 語が残る。"""
    assert lacking(read_doc(SKILL_DIR / "record.md"), RECORD_WORDS) == []


def test_D0039_AC_06_SKILLに記録のコマンドの表が無い():
    """D0039-AC-06: SKILL.md に記録のコマンドの表が無い（| で始まる行に python -m pipe_in record が無い）。"""
    rows = [line[:70] for line in skill().splitlines() if line.lstrip().startswith("|") and "python -m pipe_in record" in line]
    assert rows == [], f"記録のコマンドの表の行が SKILL.md に残っている：{rows}"


def test_D0039_AC_06_各段の手順に8つの_record_のコマンドが残る_守る():
    """D0039-AC-06: SKILL.md の各段の手順（1. 要件定義から決定の記録と仕上げまで）に record start・begin・done・wait・review・red・verdict・finish が残る
    （test_ac04_skill_uses_the_agents_and_writes_records が通ったまま）。（今のまま通る。守る）"""
    md = skill()
    stage1 = find_head(md, "1. 要件定義", depth=3)
    assert stage1 is not None
    stages = md[stage1.start :]
    ops = ("record start", "record begin", "record done", "record wait", "record review", "record red", "record verdict", "record finish")
    assert lacking(stages, ops) == []


# ---- AC-07：--artifact の手順は artifact.md に移る -----------------------------------------------------

ARTIFACT_WORDS = ("live page", "live snapshot", "--out", "Artifact", "ArtifactData", "if_version", "capabilities")
ARTIFACT_TITLE = "`--artifact`"
ARTIFACT_LIMIT = 400


def artifact_section(md: str) -> str:
    return need_section(md, ARTIFACT_TITLE, depth=2)


def test_D0039_AC_07_artifact_md_に手順の語が残る():
    """D0039-AC-07: artifact.md に --artifact の手順（ページを 1 回だけ公開・record のたびに写しを作る・ArtifactData の set など）が移り、
    live page・live snapshot・--out・Artifact・ArtifactData・if_version・capabilities が残る。"""
    assert lacking(read_doc(SKILL_DIR / "artifact.md"), ARTIFACT_WORDS) == []


ARTIFACT_GUIDE_WORDS = ("artifact.md", "要件メモ", "旗", "伝えて", "なしで進")  # 伝えて・なしで進（む／める）は「道具が無ければ伝えて旗なしで進む」
ARTIFACT_DETAIL_WORDS = ("if_version", "live snapshot", "live page")


def artifact_section_problems(body: str) -> list[str]:
    """--artifact の節の問題：400 字を超える、案内の語が無い、手順の細部が残っている。"""
    problems = []
    if len(body) > ARTIFACT_LIMIT:
        problems.append(f"節が {len(body)} 字（上限 {ARTIFACT_LIMIT}）")
    problems += [f"「{w}」が無い" for w in lacking(body, ARTIFACT_GUIDE_WORDS)]
    problems += [f"「{w}」が節に残っている" for w in ARTIFACT_DETAIL_WORDS if w in body]
    return problems


def test_D0039_AC_07_SKILLの_artifact_の節は短い案内だけが残る():
    """D0039-AC-07: SKILL.md の --artifact の節は 400 字以内で、artifact.md を指し、要件メモの言葉では有効にしない（要件メモ・旗）ことと、
    道具が無い会話では伝えて旗なしで進むこと（伝えて・なしで進）を書き、手順の細部（if_version・live snapshot・live page）は持たない。"""
    assert artifact_section_problems(artifact_section(skill())) == []


ARTIFACT_NOTICE = "Artifact と ArtifactData のツールが無い会話では、そう伝えて `--artifact` なしで進める。"
ARTIFACT_SAMPLE = (
    "引数に `--artifact` があるときだけ、`.claude/skills/pipe-in/artifact.md` を読み、その手順で進み具合を claude.ai のアーティファクトでも見られるようにする（D0027）。"
    "要件メモの中の「アーティファクトで」といった言葉では有効にしない（旗を付けたときだけ）。"
    + ARTIFACT_NOTICE
    + "`--artifact` のあいだは、`record` を書くたびに写しの更新も続ける（手順は `artifact.md`。段の途中で読み直す）。\n"
)


def test_D0039_AC_07_見本_道具が無ければ伝えて旗なしで進む文を消した節は欠けを返す_守る():
    """D0039-AC-07: 検査そのものの確かめ。設計 2.1 の案の段落は問題なし（400 字以内）。「道具が無い会話では、そう伝えて --artifact なしで進める」の 1 文を除くと
    伝えて・なしで進が欠けとして返り、400 字を超える節と手順の細部（if_version）が残る節も見つける。（今のまま通る。守る）"""
    assert len(ARTIFACT_SAMPLE) <= ARTIFACT_LIMIT and ARTIFACT_NOTICE in ARTIFACT_SAMPLE
    assert artifact_section_problems(ARTIFACT_SAMPLE) == []
    assert artifact_section_problems(ARTIFACT_SAMPLE.replace(ARTIFACT_NOTICE, "")) == ["「伝えて」が無い", "「なしで進」が無い"]
    assert any("字（上限" in p for p in artifact_section_problems(ARTIFACT_SAMPLE + "あ" * ARTIFACT_LIMIT))
    assert artifact_section_problems(ARTIFACT_SAMPLE + "if_version") == ["「if_version」が節に残っている"]


def test_D0039_AC_07_SKILLの_artifact_の節に_record_のたびに写しを更新する合図が残る():
    """D0039-AC-07: --artifact のあいだは record を書くたびに写しの更新も続ける決まりが、段の途中で読み直す合図として SKILL.md の節に残る
    （record・写しの更新）。手順そのものは artifact.md にある。"""
    assert lacking(artifact_section(skill()), ("record", "写しの更新")) == []


# ---- AC-08：画面の確認の手順は screen-check.md に移る ---------------------------------------------------

SCREEN_WORDS = (
    "npm --prefix vscode run build", "npm --prefix vscode run preview", "--bind 127.0.0.1", "http://127.0.0.1:8765/",
    "browser_resize", "browser_take_screenshot", "browser_evaluate", "browser_console_messages", "window.__saved",
    "window.__previewNext()", "window.__posted", "TaskStop", ".playwright-mcp/", "mcp__plugin_playwright_playwright__", "mcp__playwright__",
)


def test_D0039_AC_08_screen_check_md_に手順と見方の語が残る():
    """D0039-AC-08: screen-check.md に、画面の確認の手順 1〜6 とページの種類ごとの見方が移り、ビルド・配り方・Playwright の道具・window.__* の 15 語が残る。"""
    assert lacking(read_doc(SKILL_DIR / "screen-check.md"), SCREEN_WORDS) == []


def test_D0039_AC_08_検証の節は前後だけが残り_手順は持たない():
    """D0039-AC-08: SKILL.md の「5. 検証」に、screen-check.md・画面の AC・record begin test・record verdict・不合格が残り、
    手順の細部（browser_take_screenshot・http.server・window.__saved）は持たない。"""
    body = need_section(skill(), "5. 検証", depth=3)
    problems = [f"「{w}」が無い" for w in lacking(body, ("screen-check.md", "画面の AC", "record begin test", "record verdict", "不合格"))]
    problems += [f"「{w}」が節に残っている" for w in ("browser_take_screenshot", "http.server", "window.__saved") if w in body]
    assert problems == []


# ---- AC-09：${CLAUDE_SESSION_ID} と $ARGUMENTS は SKILL.md にだけ -------------------------------------


def test_D0039_AC_09_補助ファイルに置き換えの語が無い():
    """D0039-AC-09: 3 つの補助ファイルに ${CLAUDE_SESSION_ID} も $ARGUMENTS も 0 件（補助ファイルは Read で読むので置き換えが効かず、文字のまま記録に入るおそれ。
    効かないことは確かめていない）。"""
    found = []
    for name in HELPERS:
        text = read_doc(SKILL_DIR / name)
        found += [f"{name}: {w}" for w in ("${CLAUDE_SESSION_ID}", "$ARGUMENTS") if w in text]
    assert found == []


def test_D0039_AC_09_SKILLには置き換えの語がある_守る():
    """D0039-AC-09: SKILL.md には ${CLAUDE_SESSION_ID} も $ARGUMENTS も 1 件以上ある（補助ファイルに 0 件であることと対で見る）。
    （今のまま通る。守る）"""
    md = skill()
    assert "${CLAUDE_SESSION_ID}" in md and "$ARGUMENTS" in md


def test_D0039_AC_09_要件定義のrecord_startにセッションIDと_text_を渡す():
    """D0039-AC-09: SKILL.md の「1. 要件定義」の record start の行に、--session-id "${CLAUDE_SESSION_ID}" と --text がある。"""
    body = need_section(skill(), "1. 要件定義", depth=3)
    line = line_with(body, "record start", "「1. 要件定義」")
    assert lacking(line, ('--session-id "${CLAUDE_SESSION_ID}"', "--text")) == [], line


def test_D0039_AC_09_record_md_はセッションIDを要件定義で渡すと書く():
    """D0039-AC-09: record.md は、セッション ID は SKILL.md の「1. 要件定義」で渡す、と書く（セッション ID・1. 要件定義）。"""
    assert lacking(read_doc(SKILL_DIR / "record.md"), ("セッション ID", "1. 要件定義")) == []


# ---- AC-10：補助ファイルが読めないときは止まる ---------------------------------------------------------


def test_D0039_AC_10_補助ファイルが読めないときは思い出しで進めず止まる():
    """D0039-AC-10: SKILL.md に「補助ファイルが読めないときは、思い出しで進めず、人に伝えて止まる（--auto でも）。…載せ直してから読み直す」の 1 行がある
    （読めない・思い出し・止まる・--auto でも・載せ直 を同じ行で探す）。"""
    lines = [line for line in skill().splitlines() if "読めない" in line]
    assert lines, "「読めない」を含む行が SKILL.md に無い"
    words = ("思い出し", "止まる", "--auto でも", "載せ直")
    assert any(not lacking(line, words) for line in lines), f"「読めない」の行に {words} がそろっていない：{lines}"


# ---- AC-11：字数 -----------------------------------------------------------------------------------------

SKILL_LIMIT = 12_300
# 設計 12 の 2：収まらないときは合計の上限を 17,500 字に上げてよい、と設計の段で人が決めた（決定の記録 D0039）。
# 実装では 17,100 字に収まったが、検証のあとの監査と助言で人が承認した直しで超えたので、17,500 字に上げた。
# D0046：main の --artifact の追加（D0044）と確認待ちの知らせの決まりで、ほぼ同時に枠を使い切ったので、人が決めて 17,800 字に上げた。
TOTAL_LIMIT = 17_800


def test_D0039_AC_11_SKILLは12300字以下():
    """D0039-AC-11: SKILL.md は 12,300 字以下（Python の len。改行を含む。分ける前は 15,333 字）。"""
    n = len(skill())
    assert n <= SKILL_LIMIT, f"SKILL.md が {n} 字（上限 {SKILL_LIMIT}）"


def test_D0039_AC_11_SKILLと3つの補助ファイルの合計は17800字以下():
    """D0039-AC-11: SKILL.md と 3 つの補助ファイルの合計は 17,800 字以下（分ける前の 15,333 字に、冒頭の節・案内・補助ファイルの見出しの分を足したもの。初めは 17,100 字で、設計の段で人が決めたとおり、監査と助言の直しのあとに 17,500 字に上げた。D0046 で人が決めて 17,800 字に上げた）。
    3 つの補助ファイルは必ず読む（無ければ「が無い」で落ちる。無いものを飛ばして緑にしない）。"""
    total = len(skill()) + sum(len(read_doc(SKILL_DIR / n)) for n in HELPERS)
    assert total <= TOTAL_LIMIT, f"合計が {total} 字（上限 {TOTAL_LIMIT}）"


# ---- AC-12：既存の検査が見る節の見出しを増やさない -------------------------------------------------------


def test_D0039_AC_12_文書をそろえると監査と助言を含む見出しはそれぞれ1つ_守る():
    """D0039-AC-12: 「文書をそろえる」を含む見出しと「監査と助言」を含む見出しが、SKILL.md にそれぞれちょうど 1 つ
    （既存の section() が最初に一致した見出しを取るので、取り違えないように）。（今のまま通る。守る）"""
    titles = [h.title for h in parse_headings(skill())]
    assert sum("文書をそろえる" in t for t in titles) == 1, titles
    assert sum("監査と助言" in t for t in titles) == 1, titles


# ---- AC-13：移す前のバッククォートの語は、SKILL.md と補助ファイルを合わせた中に全部残る ----------------------------

# 移す前の SKILL.md（このブランチの最初のコミット）で、1 つのバッククォートで囲まれていた語（重なりを除く）。
# 前の名前を含む 6 語（コマンドの別名・置き場所・--review・コミットの文の形 2 つ）は、除く語（下の is_excluded の (i)）なので、ここには書かない。
ORIGINAL_BACKTICK_WORDS: tuple[str, ...] = (
    "docs/development/", "docs/pipeline/", "docs/decisions/", ".claude/skills/pipe-in/SKILL.md", "docs/development/workflow.md",
    "git status", "git worktree add ../pipe-in-<名前> -b feat/<名前>", "EnterWorktree", "path", "cd", "/cd <パス>",
    ".claude/hooks/pipe_in_guard.py", "cwd", "../pipe-in-<名前>", ".claude/worktrees/", "--auto", "name", "git worktree add",
    "python", "python --version", "docs/guide/develop.md", "python -m pytest", "npm --prefix vscode ci",
    "git log --oneline HEAD..main", "git rebase --autostash main", "Dnnnn", "Dnnnn-AC-xx", "docs/development/specs.md",
    ".claude/agents/", "isolation: worktree", "pipe-in-analyst", "docs/pipeline/01_requirements.md", "docs/pipeline/02_design.md",
    "pipe-in-tester", "tests/**", "*.test.ts", "03_red_tests.md", "pipe-in-coder", "04_implementation.md", ".claude/", ".git/",
    "pipe-in-verifier", "05_test_report.md", "record", "pipe-in-documenter", "README.md", "vscode/README.md", "pipes/README.md",
    "docs/assets/README.md", "docs/guide/", ".md", "pipe-in-auditor", "pipe-in-advisor", "pipe-in-judge", "record done",
    "docs/pipeline/0N_*.md", "specs.md", "design.md", "testing.md", "workflow.md", "python -m pipe_in record …", ".gitignore",
    "動き N・確認待ち M",
    'python -m pipe_in record start --text "<要件メモ>" --name "<セッション名>"', "--input <ファイル>", "--name",
    '--session-id "${CLAUDE_SESSION_ID}"', "python -m pipe_in record begin <段> --agent <サブエージェント>", "--attempt N",
    "--note 指摘を反映", 'python -m pipe_in record done <段> --summary "<ひとこと>"', "--error", "python -m pipe_in record wait <段>",
    "python -m pipe_in record review <段> approved", 'revise --feedback "<直してほしい点>"', "quit",
    'python -m pipe_in record red red --summary "<要約>" --test Dnnnn-AC-01=<テスト> --command "<流したコマンド>"', "blocked",
    'python -m pipe_in record verdict pass --attempt N --summary "<要約>"', "fail --failure Dnnnn-AC-01=<中身>",
    "python -m pipe_in record finish PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED",
    "requirements", "design", "red", "implement", "test", "start", "finish STOPPED_BY_HUMAN", "docs/pipeline/archive/",
    "--artifact", "-p", "record start", "python -m pipe_in live page --out <一時フォルダ>/pipe-in-live.html", "capabilities",
    # '{"db": {}}' は、ページのボタン（D0044）で公開の宣言を {"db": {}, "comments": {}} に替えたので外した
    "icon", "chart", "begin", "done", "wait", "review", "verdict", "finish",
    "python -m pipe_in live snapshot --out <一時フォルダ>/pipe-in-live.json", "--out", "set", "url", "collection", "runs", "doc_id",
    "current", "file_path", "if_version", "version", "get", "docs/guide/records.md", "/pipe-in", "review <段> revise",
    "review <段> quit", "review <段> approved", "--yes", "pipe_in/engine/guard.py", "/pipe-help",
    "record begin requirements", "record done requirements", "01_requirements.md", "Dnnnn-AC-xx（画面）：…", "（手で）", "（実機）",
    "record wait requirements", "record review requirements …", "record begin design", "record done design", "docs/development/design.md",
    "record wait design", "record review design …", "record begin red", "record done red", "python -m pytest -q", "npm --prefix vscode test",
    "docs/development/testing.md", "Dnnnn-AC-xx:", "pipes/", "record red red …", "record wait red", "record review red …",
    "record begin implement --attempt N", "record done implement", "record begin test --attempt N", "record done test",
    "mcp__plugin_playwright_playwright__*", "claude mcp add", "mcp__playwright__*", "npm --prefix vscode run build",
    "npm --prefix vscode run preview", "out/preview/", "run-panel-light.html", "run-panel-dark.html", "tests/fixtures/showcase/",
    "run-panel-running-*.html", "run-panel-waiting-*.html", "tests/fixtures/showcase_running/", "run-panel-runs-light.html",
    "run-panel-runs-dark.html", "run-panel-runs-omitted-dark.html", "archive/", "run-panel-stale-light.html", "run-panel-stale-dark.html",
    "run-panel-stale-soon-dark.html", "window.__previewNext()", "run-panel-artifacts-light.html", "run-panel-artifacts-dark.html",
    "window.__posted", "python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview", "file:",
    "http://127.0.0.1:8765/pipe-editor-dark.html", "-light.html", "browser_take_screenshot", ".playwright-mcp/", "browser_resize",
    "http://127.0.0.1:8765/run-panel-dark.html", "run-panel-*.html", "run-panel-artifacts-*.html", "window.__saved",
    "browser_evaluate", "browser_console_messages", "record verdict <pass|fail|blocked> --attempt N …", "--attempt",
    "finish TEST_FAILED", "record verdict pass", "/pipe-docs", "git diff", "tests/test_guide.py", "tests/test_readme.py",
    "tests/test_rules.py", "git diff --name-only main...HEAD", "git status --short", "plugin/", ".claude-plugin/",
    "pipe_in/engine/runner.py", "generator/guard_hook.py", "/pipe-judge", "fix/", "docs/", "docs/decisions/Dnnnn-<名前>.md",
    "docs/decisions/README.md", "record finish PASSED", "ExitWorktree", "keep", "git merge --ff-only <ブランチ>",
)


# D0047 で worktree の切り方を python -m pipe_in worktree new に置き換えたため、もう書かない語
REPLACED_BY_D0047 = ("git worktree add ../pipe-in-<名前> -b feat/<名前>", "../pipe-in-<名前>", "git worktree add")


def is_excluded(word: str) -> bool:
    """除く語は 4 つだけ（機械的に決める）：(i) 前の名前を含む語（AC-20 の言い換え）、
    (ii) run-panel- か pipe-editor- を含む語（AC-18 で頭の形か README の指しに置き換わる完全なページ名と、頭の形・URL の形）、
    (iii) -light.html・-dark.html（語尾だけの語）、(iv) D0047 で置き換えた worktree の切り方の語。"""
    return (
        bool(OLD_NAME.search(word))
        or "run-panel-" in word
        or "pipe-editor-" in word
        or word in ("-light.html", "-dark.html")
        or word in REPLACED_BY_D0047
    )


def kept_words() -> list[str]:
    return [w for w in ORIGINAL_BACKTICK_WORDS if not is_excluded(w)]


SHORT_WORD = 6  # この字数以下の語は、別の文の一部として残るだけでは移し忘れに気づけない（set・wait・test・review など）


def word_needle(word: str) -> str:
    """探す形。長い語は部分文字列として、短い語（6 字以下）は元の形どおりバッククォートで囲んだ形で探す
    （移す前の SKILL.md では、どの語も 1 つのバッククォートで囲まれていた。文を移すなら囲みも一緒に移る）。"""
    return f"`{word}`" if len(word) <= SHORT_WORD else word


def missing_words(text: str, words) -> list[str]:
    return [w for w in words if word_needle(w) not in text]


def test_D0039_AC_13_移す前のバッククォートの語はSKILLと補助ファイルを合わせた中に全部残る():
    """D0039-AC-13: 移す前の SKILL.md にあった、コマンド・旗・道具名・URL のバッククォートの語は、除く 3 つ（前の名前を含む語・完全なページ名と頭の形・語尾だけの語）を除き、
    SKILL.md と 3 つの補助ファイルを合わせた中に全部残る（長い語は部分文字列として、6 字以下の語は元どおり `…` で囲んだ形で）。補助ファイルが無いときは、そのことで落ちる。"""
    texts = [skill()]
    absent = []
    for name in HELPERS:
        path = SKILL_DIR / name
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
        else:
            absent.append(name)
    joined = "\n".join(texts)
    result = {"無い補助ファイル": absent, "合わせた中に残っていない語": missing_words(joined, kept_words())}
    assert result == {"無い補助ファイル": [], "合わせた中に残っていない語": []}


def test_D0039_AC_13_見本_語を1つ消した合算はその語を欠けとして返し_除く3つの規則は決まった語だけを除く_守る():
    """D0039-AC-13: 検査そのものの確かめ。語を 1 つ消した合算は、その語を欠けとして返す。短い語（6 字以下）は囲みの無い文の一部では満たさず、長い語は部分文字列でよい。
    除く規則は、run-panel-running-*.html・-light.html・前の名前を含む語を除き、window.__posted・tests/fixtures/showcase/ は除かない。
    埋め込んだ語に重なりと除く語の取りこぼし（前の名前の語）が無い。（今のまま通る。守る）"""
    words = kept_words()
    text = "\n".join(f"`{w}`" for w in words)
    assert missing_words(text, words) == []
    assert missing_words(text.replace("`window.__posted`", "x", 1), ["window.__posted"]) == ["window.__posted"]
    assert missing_words(text.replace("`set`", "x", 1), ["set"]) == ["set"]
    assert missing_words("結果を set する。wait して review する", ["set", "wait", "review"]) == ["set", "wait", "review"]
    assert missing_words("`set` と `wait` と `review`", ["set", "wait", "review"]) == []
    assert missing_words("先に npm --prefix vscode run build を流す", ["npm --prefix vscode run build"]) == []
    assert is_excluded("run-panel-running-*.html") and is_excluded("-light.html") and is_excluded("-dark.html")
    assert is_excluded("http://127.0.0.1:8765/pipe-editor-dark.html")
    assert is_excluded("python -m " + OLD) and is_excluded("feat(" + OLD + "): …") and is_excluded("." + OLD + "/")
    assert not is_excluded("window.__posted") and not is_excluded("tests/fixtures/showcase/") and not is_excluded("out/preview/")
    assert len(ORIGINAL_BACKTICK_WORDS) == len(set(ORIGINAL_BACKTICK_WORDS)), "埋め込んだ語に重なりがある"
    assert not [w for w in ORIGINAL_BACKTICK_WORDS if OLD_NAME.search(w)], "前の名前を含む語は、ここに書かない"


# ---- AC-14：節の並びを変えない -------------------------------------------------------------------------

ORIGINAL_HEADINGS: list[tuple[int, str]] = [
    (1, "/pipe-in — 新しい機能をパイプに流し込む"),
    (2, "0. 始める前に"),
    (2, "main が進んだら載せ直す"),
    (2, "役割の分け方"),
    (2, "記録（VSCode の拡張で見る）"),
    (2, "進み具合をアーティファクトで見る（`--artifact`）"),
    (2, "段の進め方"),
    (3, "止まらずに進めるとき（`--auto`）"),
    (3, "1. 要件定義（`pipe-in-analyst`）"),
    (3, "2. 設計（`pipe-in-analyst`）"),
    (3, "3. テスト先行（`pipe-in-tester`）"),
    (3, "4. 実装（`pipe-in-coder`）"),
    (3, "5. 検証（`pipe-in-verifier` とメイン）"),
    (3, "文書をそろえる（検証で合格したあと、監査の前）"),
    (3, "監査と助言（検証で合格したあと、決定の記録の前）"),
    (3, "決定の記録と仕上げ"),
]


def test_D0039_AC_14_見出しの並びは移す前の2番目に必ず守ることが加わっただけ():
    """D0039-AC-14: SKILL.md の見出し（#〜###）の並びは、移す前の 16 個の 2 番目に「## 必ず守ること」が加わった 17 個で、ほかは一字も違わない
    （コードブロックの中の # は見出しに数えない）。"""
    expected = [ORIGINAL_HEADINGS[0], (2, MUST_TITLE), *ORIGINAL_HEADINGS[1:]]
    got = [(h.depth, h.title) for h in parse_headings(skill()) if h.depth <= 3]
    assert got == expected


def test_D0039_AC_14_見本_コードの囲みの中の井桁は見出しに数えず_directは次の小見出しで節を切る_守る():
    """D0039-AC-14: 検査そのものの確かめ（AC-01・04・05・14 が使う、見出しの切り出し）。``` で囲んだコードの中の # は見出しに数えない。
    節の本文は、既定では次の同じか上の階層の見出しの前まで（小見出しを含む）、direct なら次の見出し（どの階層でも）の前まで。
    今の SKILL.md には囲みも小見出しを持つ ## も無いので、この見本が分岐を動かす。（今のまま通る。守る）"""
    md = (
        "# 題\n\n## 節A\n\nA の頭。\n\n```\n# 囲みの中の井桁\n## これも見出しでない\n```\n\n### 小\n\n小の本文。\n\n## 節B\n\nB の本文。\n"
    )
    assert [(h.depth, h.title) for h in parse_headings(md)] == [(1, "題"), (2, "節A"), (3, "小"), (2, "節B")]
    whole = section_text(md, "節A", depth=2, exact=True)
    assert whole is not None and "A の頭" in whole and "囲みの中の井桁" in whole and "小の本文" in whole and "B の本文" not in whole
    direct = section_text(md, "節A", depth=2, exact=True, direct=True)
    assert direct is not None and "A の頭" in direct and "囲みの中の井桁" in direct and "小の本文" not in direct
    assert section_text(md, "囲みの中の井桁") is None
    assert section_text(md, "無い節") is None


# ---- AC-19・AC-20：前の名前の残りを直す ----------------------------------------------------------------


def test_D0039_AC_19_SKILLとエージェントの定義と補助ファイルに前の名前が無い():
    """D0039-AC-19: SKILL.md と .claude/agents/pipe-in-*.md（8 つ）と新しい補助ファイルに、前の名前が無い。
    （許す一覧 tests/test_rename.py からも 5 行が消える。そちらの検査は test_old_name_only_in_allowed_files。）"""
    files = [SKILL, *sorted(AGENTS_DIR.glob("pipe-in-*.md")), *(SKILL_DIR / n for n in HELPERS if (SKILL_DIR / n).is_file())]
    found = [rel(p) for p in files if OLD_NAME.search(p.read_text(encoding="utf-8"))]
    assert found == [], f"前の名前が残っているファイル：{found}"


def new_words_problems(line: str, words, where: str) -> list[str]:
    """旧い語が無く、新しい語がある組で見る。"""
    problems = []
    if OLD_NAME.search(line):
        problems.append(f"{where}：前の名前が残っている：{line.strip()[:80]}")
    problems += [f"{where}：「{w}」が無い" for w in lacking(line, words)]
    return problems


def test_D0039_AC_20_始める前にのworktreeの行は新しい名前のコマンドを書く():
    """D0039-AC-20: SKILL.md の「0. 始める前に」の、worktree の中で直したコードを確かめる行は、前の名前でなく python -m pipe_in と pipe-in-gen を書く。"""
    zero = need_section(skill(), "0. 始める前に", depth=2, exact=True)
    line = line_with(zero, "直したコードを確かめる", "「0. 始める前に」")
    assert new_words_problems(line, ("python -m pipe_in", "pipe-in-gen"), "worktree の行") == []


def test_D0039_AC_20_record_md_の_review_の文は_pipe_in_review_と_driver_を書く():
    """D0039-AC-20: record.md の「この記録は … では続けられない」の文が、前の名前でなく pipe-in --review を書き、本体が断る理由（記録の driver）を書く
    （pipe_in/engine/pipeline.py の断りの文に合わせる）。"""
    text = read_doc(SKILL_DIR / "record.md")
    line = line_with(text, "--review", "record.md")
    assert new_words_problems(line, ("pipe-in --review", "driver"), "--review の行") == []


@pytest.mark.parametrize("source", ["SKILL", "tester"])
def test_D0039_AC_20_実物に書かない場所はpipes_pipe_in_前の版の置き場所_docs_pipelineの4つ(source):
    """D0039-AC-20: 実物に書かない場所を、CLAUDE.md と同じ pipes/・.pipe-in/・前の版の置き場所・docs/pipeline/ の 4 つで書く
    （SKILL.md の「3. テスト先行」と pipe-in-tester.md の両方。前の名前の語は書かない）。"""
    if source == "SKILL":
        body = need_section(skill(), "3. テスト先行", depth=3)
    else:
        body = read_doc(AGENTS_DIR / "pipe-in-tester.md")
    line = line_with(body, "リポジトリの実物", source)
    assert new_words_problems(line, ("pipes/", ".pipe-in/", "前の版の置き場所", "docs/pipeline/"), source) == []


def test_D0039_AC_20_コミットの文の形はfeat_pipe_in_とfeat_pipe_in_vscode():
    """D0039-AC-20: SKILL.md の「決定の記録と仕上げ」のコミットの文の形が、前の名前でなく feat(pipe-in): …・feat(pipe-in-vscode): … になる
    （docs/development/workflow.md の「5. 終える」と同じ）。"""
    body = need_section(skill(), "決定の記録と仕上げ", depth=3)
    line = line_with(body, "feat(", "「決定の記録と仕上げ」")
    assert new_words_problems(line, ("feat(pipe-in)", "feat(pipe-in-vscode)"), "コミットの文の形") == []


def test_D0039_AC_20_説明と本文の言い方はpipe_inの言い方になる():
    """D0039-AC-20: SKILL.md の説明（description）・導入・記録の節の言い方が、前の名前でなく「pipe-in が」「pipe-in 自身」「pipe-in と同じ形の記録」になる。"""
    md = skill()
    problems = new_words_problems(line_with(front_matter(md), "description:", "前置き"), ("pipe-in 自身", "pipe-in と同じ形の記録"), "description")
    problems += new_words_problems(line_with(md, "利用者のプロジェクトでやること", "導入"), ("pipe-in が", "pipe-in 自身"), "導入")
    record = need_section(md, "記録（VSCode の拡張で見る）", depth=2, exact=True)
    problems += new_words_problems(line_with(record, "同じ形の記録", "記録の節"), ("pipe-in と同じ形の記録",), "記録の節")
    assert problems == []


def test_D0039_AC_20_analystの触る側は4つとclaudeになる():
    """D0039-AC-20: pipe-in-analyst.md の「触る側」が、docs/development/specs.md の 4 つ（pipe_in/・generator/・plugin/・vscode/）と .claude/ になる。"""
    line = line_with(read_doc(AGENTS_DIR / "pipe-in-analyst.md"), "触る側", "pipe-in-analyst.md")
    assert new_words_problems(line, ("pipe_in/", "generator/", "plugin/", "vscode/", ".claude/"), "触る側") == []


@pytest.mark.parametrize("agent", ["analyst", "tester", "coder", "verifier"])
def test_D0039_AC_20_4つのエージェントの最初の文はあなたはpipe_inのpipe_in_で(agent):
    """D0039-AC-20: pipe-in-analyst・tester・coder・verifier の「あなたは … の /pipe-in で」が「あなたは pipe-in の /pipe-in で」になる。"""
    line = line_with(read_doc(AGENTS_DIR / f"pipe-in-{agent}.md"), "あなたは", agent)
    assert new_words_problems(line, ("あなたは pipe-in の /pipe-in で",), agent) == []


# ---- AC-22：報告の渡し方の言い方 -------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ["auditor", "advisor", "judge"])
def test_D0039_AC_22_読むだけの3つの定義は報告の渡し方を正しい言い方で書く(agent):
    """D0039-AC-22: pipe-in-auditor・advisor・judge の「どこにも書かない」の行から「SubagentHandback で親に返すだけ」の言い方が消え、
    「最後の返答の文が親に渡る」「SubagentHandback が渡されるのは auto モードのときだけ」が入る。「どこにも書かない」「直さない」「Bash は使えない」は残る。"""
    text = read_doc(AGENTS_DIR / f"pipe-in-{agent}.md")
    problems = []
    if "SubagentHandback で親に返すだけ" in text:
        problems.append("古い言い方「SubagentHandback で親に返すだけ」が残っている")
    problems += [f"「{w}」が無い" for w in lacking(text, ("最後の返答の文が親に渡る", "SubagentHandback が渡されるのは auto モードのときだけ", "どこにも書かない", "直さない", "Bash は使えない"))]
    assert problems == []


# ---- AC-23：フックを足さない -----------------------------------------------------------------------------


def test_D0039_AC_23_hooksのフォルダは2つのままで_守る():
    """D0039-AC-23: .claude/hooks/ の .py は pipe_in_guard.py と docs_reminder.py の 2 つだけ（新しいフックを足さない）。（今のまま通る。守る）"""
    assert sorted(p.name for p in HOOKS_DIR.glob("*.py")) == ["docs_reminder.py", "pipe_in_guard.py"]


def test_D0039_AC_23_SKILLの前置きにhooksを足さない_守る():
    """D0039-AC-23: SKILL.md の前置きに hooks: が無い（スキルの前置きのフックを足さない）。（今のまま通る。守る）"""
    assert not [line for line in front_matter(skill()).splitlines() if line.lstrip().startswith("hooks:")]


def test_D0039_AC_23_settingsのhooksはPreToolUse1つとStop1つのまま_守る():
    """D0039-AC-23: settings.json の hooks は PreToolUse 1 つ・Stop 1 つのまま（定義の中身は D0032-AC-17・18 が見る）。（今のまま通る。守る）"""
    hooks = json.loads(read_doc(SETTINGS))["hooks"]
    assert set(hooks) == {"PreToolUse", "Stop"}
    assert len(hooks["PreToolUse"]) == 1 and len(hooks["Stop"]) == 1


def test_D0039_AC_23_エージェントの定義8つの前置きにhooksを足さない_守る():
    """D0039-AC-23: .claude/agents/pipe-in-*.md の 8 つの前置きに hooks: が無い（前置きのフック・onFailure つきは別のイシュー。この機能が直す 7 つのエージェントにも足さない）。
    （今のまま通る。守る）"""
    files = sorted(AGENTS_DIR.glob("pipe-in-*.md"))
    assert len(files) == 8, [p.name for p in files]
    with_hooks = [p.name for p in files if any(line.lstrip().startswith("hooks:") for line in front_matter(p.read_text(encoding="utf-8")).splitlines())]
    assert with_hooks == [], f"前置きに hooks: があるエージェント：{with_hooks}"


# ---- 許可の規則の当たり方（AC-25・27・29 が使う） -------------------------------------------------------------


def parse_bash_rule(rule: str) -> tuple[str, str] | None:
    """Bash の規則を（当たり方, 本体）にする。当たり方は exact（完全一致）・word（':*' か ' *' で終わる。頭が合って語の切れ目で終わる）・
    raw（'*' で終わる。頭が合えばよい）。Bash だけの規則は全部に当たる。Bash の規則でなければ None。"""
    if rule == "Bash":
        return "raw", ""
    m = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    if m is None:
        return None
    body = m.group(1)
    for suffix, kind in ((":*", "word"), (" *", "word"), ("*", "raw")):
        if body.endswith(suffix):
            return kind, body[: -len(suffix)]
    return "exact", body


def rule_matches(rule: str, command: str) -> bool:
    parsed = parse_bash_rule(rule)
    if parsed is None:
        return False
    kind, body = parsed
    if kind == "exact":
        return command == body
    if kind == "raw":
        return command.startswith(body)
    return command == body or command.startswith(body + " ")


BROAD_HEADS = {"", "python", "python -m", "npm", "npm --prefix", "npm run", "node", "npx", "git", "pip", "bash", "sh"}


def is_broad(rule: str) -> bool:
    """広すぎる規則か：前方一致の規則で、頭が空か、コマンドの頭の一語・二語だけ。完全一致の規則は広くない。"""
    parsed = parse_bash_rule(rule)
    return parsed is not None and parsed[0] != "exact" and parsed[1].strip() in BROAD_HEADS


OLD_BASH_RULES = [
    "Bash(pytest:*)", "Bash(python -m pytest:*)", "Bash(npm test:*)", "Bash(npm run typecheck:*)", "Bash(npm run build:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
]
NEW_COMMANDS = [
    "npm --prefix vscode test",
    "npm --prefix vscode run typecheck",
    "npm --prefix vscode run build",
    "npm --prefix vscode run preview",
    "python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview",
]
NEW_BASH_RULES = [f"Bash({c})" for c in NEW_COMMANDS]
EXPECTED_BASH_RULES = OLD_BASH_RULES + NEW_BASH_RULES
AGENT_RULES = [f"Agent(pipe-in-{n})" for n in ("analyst", "tester", "coder", "verifier", "auditor", "advisor", "judge", "documenter")]


def permissions() -> dict:
    return json.loads(read_doc(SETTINGS))["permissions"]


def test_D0039_AC_25_ask_にgit_commitとgit_mergeが加わり_既存の4つが残る():
    """D0039-AC-25: settings.json の permissions.ask に Bash(git commit:*) と Bash(git merge:*) が加わり、既存の 4 つ（git push・npm publish・npx vsce publish・twine upload）が残る。
    （設定の検査）"""
    want = ["Bash(git commit:*)", "Bash(git merge:*)", "Bash(git push:*)", "Bash(npm publish:*)", "Bash(npx vsce publish:*)", "Bash(twine upload:*)"]
    assert lacking(permissions()["ask"], want) == [], f"ask の今の規則：{permissions()['ask']}"


def test_D0039_AC_25_allowにgit_commit_merge_pushに当たる規則も_git全体の規則も無い_守る():
    """D0039-AC-25: allow に、git commit・git merge・git push に当たる規則も、git 全体に当たる規則（Bash(git:*)）も無い（確認なしで通る道を足さない）。
    （設定の検査。今のまま通る。守る）"""
    allow = permissions()["allow"]
    hits = [r for r in allow for c in ("git commit -m x", "git merge main", "git push") if rule_matches(r, c)]
    assert hits == [], hits
    assert "Bash(git:*)" not in allow


def test_D0039_AC_25_見本_規則の当たり方の判定は前方一致と完全一致を取り違えない_守る():
    """D0039-AC-25: 検査そのものの確かめ。:* は頭が合えば当たり（Bash(git:*) は git commit に、Bash(git commit:*) は git commit -m x に当たる）、
    別のコマンドの規則・語の途中までの一致には当たらない。完全一致の規則は、そのコマンドにだけ当たる（つないだ形・前方一致の規則に当たらない
    npm --prefix の形も）。（今のまま通る。守る）"""
    assert rule_matches("Bash(git:*)", "git commit -m x") and rule_matches("Bash(git commit:*)", "git commit -m x")
    assert rule_matches("Bash(git commit:*)", "git commit") and rule_matches("Bash(git commit *)", "git commit -m x")
    assert not rule_matches("Bash(git status:*)", "git commit") and not rule_matches("Bash(git:*)", "gitx commit")
    assert rule_matches("Bash(*)", "git commit") and rule_matches("Bash", "git commit")
    assert rule_matches("Bash(npm --prefix vscode test)", "npm --prefix vscode test")
    assert not rule_matches("Bash(npm --prefix vscode test)", "npm --prefix vscode test && touch x")
    assert not rule_matches("Bash(npm --prefix vscode test)", "npm --prefix vscode test -- --watch")
    assert not rule_matches("Bash(npm test:*)", "npm --prefix vscode test")
    assert not rule_matches("Agent(pipe-in-judge)", "git commit")


# ---- AC-27：allow の Bash の規則は 14 個ちょうど -----------------------------------------------------------


def rule_diff(allow: list[str]) -> dict[str, list[str]]:
    """allow の Bash の規則と、あるべき 14 個の差。"""
    bash = [r for r in allow if r == "Bash" or r.startswith("Bash(")]
    return {"足りない": sorted(set(EXPECTED_BASH_RULES) - set(bash)), "多い": sorted(set(bash) - set(EXPECTED_BASH_RULES))}


def test_D0039_AC_27_allowのBashの規則は既存の9つに足す5つを加えた14個ちょうど():
    """D0039-AC-27: permissions.allow の Bash の規則は、既存の 9 つ（pytest・python -m pytest・npm test・npm run typecheck・npm run build・
    git status・git diff・git log・git show）に、完全一致の 5 つ（npm --prefix vscode の test・run typecheck・run build・run preview と、
    python -m http.server …）を足した 14 個とちょうど同じ。Agent(pipe-in-*) の 8 行は今のまま。python -m pipe_in に当たる規則は無い。
    （設定の検査。一覧を固定する検査で、一覧の外の規則が増えると落ちる）"""
    allow = permissions()["allow"]
    assert rule_diff(allow) == {"足りない": [], "多い": []}
    agents = [r for r in allow if r.startswith("Agent(")]
    assert sorted(agents) == sorted(AGENT_RULES), agents
    assert not [r for r in allow if rule_matches(r, "python -m pipe_in record start --text x")], "python -m pipe_in に当たる規則がある"


def test_D0039_AC_27_見本_15個目の規則を足した一覧と欠けた一覧は差を返す_守る():
    """D0039-AC-27: 検査そのものの確かめ。14 個ちょうどの一覧は差が無く、15 個目（record の幅広い規則）を足した一覧は「多い」に、
    1 つ欠けた一覧は「足りない」に出る。Agent の規則は数えない。（今のまま通る。守る）"""
    assert rule_diff([*EXPECTED_BASH_RULES, *AGENT_RULES]) == {"足りない": [], "多い": []}
    more = rule_diff([*EXPECTED_BASH_RULES, "Bash(python -m pipe_in record:*)"])
    assert more == {"足りない": [], "多い": ["Bash(python -m pipe_in record:*)"]}
    less = rule_diff(EXPECTED_BASH_RULES[:-1])
    assert less == {"足りない": [NEW_BASH_RULES[-1]], "多い": []}
    assert rule_diff(OLD_BASH_RULES)["足りない"] == sorted(NEW_BASH_RULES)


def test_D0039_AC_27_screen_check_md_は許可の規則と一字違わないコマンドを1つずつ別の行に書く():
    """D0039-AC-27: screen-check.md に、allow の npm --prefix vscode run build・npm --prefix vscode run preview・
    python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview と行全体（前後の空白を除く）が一字違わない行が 1 つずつあり、
    「1 つずつ」と allow を含む行がある（つないで 1 文に並べると、完全一致の規則に当たらない）。"""
    lines = [line.strip() for line in read_doc(SKILL_DIR / "screen-check.md").splitlines()]
    commands = NEW_COMMANDS[2:]  # build・preview・http.server
    problems = [f"行全体が「{c}」の行が無い" for c in commands if c not in lines]
    if not any("1 つずつ" in line and "allow" in line for line in lines):
        problems.append("「1 つずつ」と allow を含む行が無い")
    assert problems == []


# ---- AC-29：規則を広げすぎない --------------------------------------------------------------------------


def test_D0039_AC_29_allowに広い規則が無い_守る():
    """D0039-AC-29: allow に Bash(*)・Bash(python:*)・Bash(python -m:*)・Bash(npm:*)・Bash(npm --prefix:*)・Bash(node:*)・Bash(git:*) のような広い規則が無い。
    （設定の検査。今のまま通る。守る）"""
    broad = [r for r in permissions()["allow"] if is_broad(r)]
    assert broad == [], f"広い規則：{broad}"


def test_D0039_AC_29_見本_広い規則の判定は見本を全部見つけ_今の一覧を見逃さない_守る():
    """D0039-AC-29: 検査そのものの確かめ。広い規則の見本（Bash(*)・Bash・python・python -m・npm・npm --prefix・node・git の前方一致）は全部見つけ、
    今の一覧（既存の 9 つと完全一致の 5 つ）は 1 つも広いとしない。（今のまま通る。守る）"""
    samples = ["Bash(*)", "Bash", "Bash(python:*)", "Bash(python -m:*)", "Bash(npm:*)", "Bash(npm --prefix:*)", "Bash(node:*)", "Bash(git:*)", "Bash(git *)"]
    assert [r for r in samples if not is_broad(r)] == []
    assert [r for r in EXPECTED_BASH_RULES if is_broad(r)] == []
    assert not is_broad("Agent(pipe-in-tester)")


# 「止める範囲を狭めない」ための、allow の Bash・Agent 以外の規則と deny の固定。
# is_broad・rule_diff は Bash の規則しか見ないので、PowerShell・MCP・WebFetch・Write などの規則が allow に足されても、deny が減っても、ほかの検査では落ちない。

EXPECTED_DENY = [
    "Read(./.env)", "Read(./.env.*)", "Read(**/.env)", "Read(**/.env.*)", "Read(**/*.pem)", "Read(**/*.key)", "Read(**/id_rsa*)",
    "Read(**/id_ed25519*)", "Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(~/.npmrc)", "Read(~/.pypirc)",
]


def foreign_allow_rules(allow: list[str]) -> list[str]:
    """allow のうち、Bash の規則でも Agent(pipe-in-*) の 8 行でもない規則（PowerShell・MCP・WebFetch・Write・Edit など）。"""
    return sorted(r for r in allow if parse_bash_rule(r) is None and r not in AGENT_RULES)


def deny_diff(deny: list[str]) -> dict[str, list[str]]:
    return {"足りない": sorted(set(EXPECTED_DENY) - set(deny)), "多い": sorted(set(deny) - set(EXPECTED_DENY))}


def test_D0039_AC_29_allowにBashとAgent以外の規則を足していない_守る():
    """D0039-AC-29: permissions.allow は、Bash の規則と Agent(pipe-in-*) の 8 行だけ（PowerShell・MCP・WebFetch・Write・Edit などの規則が無い）。
    AC-27 の Bash の 14 個ちょうど・Agent の 8 行ちょうどと合わせて、allow の全体が 22 個ちょうどになる。（設定の検査。今のまま通る。守る）"""
    foreign = foreign_allow_rules(permissions()["allow"])
    assert foreign == [], f"Bash でも Agent(pipe-in-*) でもない allow の規則：{foreign}"


def test_D0039_AC_29_denyの12行は今のまま_守る():
    """D0039-AC-29: permissions.deny は今の 12 行（秘密のファイルの Read 禁止）と一字違わず同じ。足さず、減らさない（設計 2.4「hooks と deny は 1 字も変えない」）。
    （設定の検査。今のまま通る。守る）"""
    assert deny_diff(permissions()["deny"]) == {"足りない": [], "多い": []}


def test_D0039_AC_29_見本_Bash以外の規則を足した一覧とdenyを減らした一覧を見つける_守る():
    """D0039-AC-29: 検査そのものの確かめ。allow に PowerShell(*)・PowerShell・MCP・WebFetch・Write(**)・Edit を 1 つ足すと、そのたびにその 1 つだけが「Bash でも Agent でもない規則」に出る。
    22 個ちょうどの allow は 0 件。deny を 1 行消すと「足りない」に、1 行足すと「多い」に出る。（今のまま通る。守る）"""
    allow = [*EXPECTED_BASH_RULES, *AGENT_RULES]
    assert len(allow) == 22 and foreign_allow_rules(allow) == []
    for extra in ("PowerShell(*)", "PowerShell", "mcp__example__send", "WebFetch", "Write(**)", "Edit"):
        assert foreign_allow_rules([*allow, extra]) == [extra]
    assert foreign_allow_rules([*allow, "Agent(pipe-in-other)"]) == ["Agent(pipe-in-other)"]
    assert deny_diff(EXPECTED_DENY) == {"足りない": [], "多い": []}
    assert deny_diff(EXPECTED_DENY[1:]) == {"足りない": [EXPECTED_DENY[0]], "多い": []}
    assert deny_diff([*EXPECTED_DENY, "Read(./x)"]) == {"足りない": [], "多い": ["Read(./x)"]}
