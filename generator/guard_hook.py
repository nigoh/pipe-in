"""プラグインの PreToolUse フック（pipe-in-gen guard-hook）：pipe-builder と pipe-judge が触れる範囲を絞る。

Claude Code のプラグインのエージェントには hooks を書けないため、プラグインの hooks/hooks.json から
どの道具の呼び出しでもここを呼び、入力の agent_type で pipe-builder と pipe-judge の呼び出しだけを検査する。
ただし agent_type が文字列でも null でもないときは、読む道具以外を止める。
pipe-builder に許すのは、読む道具と、パイプのフォルダの決まったファイルへの書き込みと、
pipe-in-gen list / new / check だけ。ほか（PowerShell・MCP・Web・Agent など）は止める。
書き込み先は、リンクの先をたどった判断でも書ける場所に入るときだけ通す。
pipe-judge（審査役）に許すのは読む道具（Read・Glob・Grep）だけ。ほかはすべて止める。
報告を親に渡す SubagentHandback（auto モード）は、agent_type が文字列なら止めない（許す名前は REPORT_TOOLS。D0096）。
型のおかしい agent_type・読めない入力・例外では止める。
想定外の入力で検査が落ちたときも、止めない側に倒れないよう deny を出す。

パイプのフォルダは pipe-in-<名前>/ と、前の版の名前 devpipe-<名前>/ の両方を同じ決まりで守る。
置き場所の環境変数も、PIPE_IN_PIPES_DIR と前の版の DEVPIPE_PIPES_DIR の両方を同じ決まりで見る。
Bash で許すのは新しい名前の pipe-in-gen だけ（前の名前の別名は同じ中身なので、許す形を増やさない）。

会話の中で流す段（pipe-stage・pipe-probe）の判断は chat_hook.py が decide の前にする（このファイルは標準ライブラリだけのまま）。

道具を呼ぶたびに動くので、標準ライブラリだけを使う（本体や SDK を読み込まない）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

AGENT = "pipe-builder"
JUDGE = "pipe-judge"
STAGE = "pipe-stage"
PROBE = "pipe-probe"
READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
# 報告を親の会話に渡すだけの道具（auto モードでサブエージェントに渡される。書かず、外へも出さない）。名前の完全一致だけ（D0096）。
# auto モードでないときは最後の返答の文が同じ会話に届くので、通しても新しくできることは無い
REPORT_TOOLS = frozenset({"SubagentHandback"})
# 標準入力の上限。超えたら読めない入力として止める
MAX_STDIN_BYTES = 16 * 1024 * 1024

# パイプのフォルダ名（新しい頭と、前の版の頭）
PIPE_DIR = re.compile(r"(?:pipe-in|devpipe)-[a-z0-9][a-z0-9-]*")
PROMPT_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.md")
FIXED_FILES = {"pipe.toml", "README.md"}

GEN = re.compile(r"pipe-in-gen\s+(list|new|check)(\s.*)?", re.S)
# 別のコマンドをつなぐ・書き出す・置き換える記号
SHELL_META = set(";&|`$<>(){}\n\r")
# 置き場所の環境変数（この順に見る）
PIPES_DIR_ENVS = ("PIPE_IN_PIPES_DIR", "DEVPIPE_PIPES_DIR")


def env_pipes_dirs(environ: Mapping[str, str]) -> list[str]:
    """置き場所の環境変数のうち、空でないものの値を PIPE_IN_PIPES_DIR → DEVPIPE_PIPES_DIR の順に返す。"""
    return [v for v in (environ.get(k) for k in PIPES_DIR_ENVS) if v]


def _is_agent(agent_type: Any, name: str) -> bool:
    """名前が完全一致か、<プラグイン>:<名前> の形か。前方一致・部分一致は使わない。

    プラグイン名までは見ない（後ろ一致）。--plugin-dir などでプラグインの名前が変わっても絞りが外れないように、
    別のプラグインの同じ名前のエージェントにも同じ絞りがかかる側（安全側）に倒す。
    """
    return isinstance(agent_type, str) and (agent_type == name or agent_type.endswith(":" + name))


def is_builder(agent_type: Any) -> bool:
    """pipe-builder の呼び出しか。プラグインのエージェントは <プラグイン>:<名前> になる。"""
    return _is_agent(agent_type, AGENT)


def is_judge(agent_type: Any) -> bool:
    """pipe-judge（審査役）の呼び出しか。"""
    return _is_agent(agent_type, JUDGE)


def is_stage(agent_type: Any) -> bool:
    """pipe-stage（会話の中で段を受け持つエージェント）の呼び出しか。判断は chat_hook.py がする。"""
    return _is_agent(agent_type, STAGE)


def is_probe(agent_type: Any) -> bool:
    """pipe-probe（守りの確かめ役）の呼び出しか。判断は chat_hook.py がする。"""
    return _is_agent(agent_type, PROBE)


def is_report_tool(tool: Any) -> bool:
    """報告の道具か。文字列で、REPORT_TOOLS の名前とちょうど同じときだけ True（大文字小文字・空白・前方一致・mcp__ の形は違う）。例外は出さない。"""
    return isinstance(tool, str) and tool in REPORT_TOOLS


def _in_pipe(rest: tuple[str, ...]) -> bool:
    """パイプのフォルダの中の相対パスが、書いてよいファイル（pipe.toml・README.md・prompts/*.md）か。"""
    if len(rest) == 1:
        return rest[0] in FIXED_FILES
    return len(rest) == 2 and rest[0] == "prompts" and bool(PROMPT_FILE.fullmatch(rest[1]))


def _env_list(pipes_env: str | Sequence[str] | None) -> list[str]:
    if pipes_env is None:
        return []
    if isinstance(pipes_env, str):
        return [pipes_env] if pipes_env else []
    return [p for p in pipes_env if isinstance(p, str) and p]


def _is_junction(q: Path) -> bool:
    """Windows の junction か（Python 3.12 以降。無ければ False）。"""
    return bool(getattr(os.path, "isjunction", lambda _: False)(q))


def _links_remain(path: str) -> bool:
    """path の上のどこかの部品がリンクのまま残っているか（realpath が輪を途中の形で返すときの見分け）。"""
    p = Path(path)
    return any(os.path.islink(q) or _is_junction(q) for q in (p, *p.parents))


def _dangling(path: str) -> bool:
    """path の上に、先が無い（壊れた・輪の）リンクがあるか。"""
    p = Path(path)
    return any(os.path.islink(q) and not os.path.exists(q) for q in (p, *p.parents))


def _trace(path: str) -> str | None:
    """リンクをたどった絶対パス。決められないとき（壊れたリンク・輪・例外）は None（止める側に倒す）。"""
    try:
        if _dangling(path):
            return None
        real = os.path.realpath(path)
        return None if _links_remain(real) else real
    except Exception:  # noqa: BLE001 - 決められないときは止める
        return None


def _text_bases(full: str, env_list: list[str]) -> list[str]:
    """文字の上の判断で通る組の、置き場所（…/pipes や環境変数の置き場所）を集める。"""
    bases: list[str] = []
    parts = Path(full).parts
    for i, part in enumerate(parts[:-2]):
        if part == "pipes" and PIPE_DIR.fullmatch(parts[i + 1]) and _in_pipe(parts[i + 2 :]):
            bases.append(str(Path(*parts[: i + 1])))
    # 環境変数の置き場所の下も、同じ決まり（パイプのフォルダの決まったファイルだけ）で見る
    for env in env_list:
        base = os.path.normpath(os.path.abspath(os.path.expanduser(env)))
        if os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
            rest = Path(os.path.relpath(full, base)).parts
            if rest and PIPE_DIR.fullmatch(rest[0]) and _in_pipe(rest[1:]):
                bases.append(base)
    return bases


def _real_ok(real: str, base: str) -> bool:
    """たどった書き込み先が、（たどった）置き場所の下の、書いてよいファイルか。"""
    rbase = _trace(base)
    if rbase is None or not os.path.normcase(real).startswith(os.path.normcase(rbase) + os.sep):
        return False
    rest = Path(os.path.relpath(real, rbase)).parts
    return bool(rest) and bool(PIPE_DIR.fullmatch(rest[0])) and _in_pipe(rest[1:])


def check_write(file_path: Any, cwd: str, pipes_env: str | Sequence[str] | None) -> str | None:
    if not isinstance(file_path, str) or not file_path.strip():
        return "書き込み先のパスがありません"
    if ".." in re.split(r"[\\/]", file_path):
        return f"パスに .. を含む書き込みはできません（{file_path}）"
    full = os.path.normpath(file_path if os.path.isabs(file_path) else os.path.join(cwd or os.getcwd(), file_path))
    # 文字の上の判断と、リンクの先をたどった判断の、両方が通るときだけ通す（今止まるものは止まったまま）
    bases = _text_bases(full, _env_list(pipes_env))
    if bases:
        real = _trace(full)
        if real is not None and any(_real_ok(real, b) for b in bases):
            return None
    return (
        f"pipe-builder が書けるのは、パイプのフォルダ（…/pipes/pipe-in-<名前>/）の pipe.toml・README.md・prompts/*.md だけです（{file_path}）"
    )


def check_bash(command: Any) -> str | None:
    if not isinstance(command, str) or not command.strip():
        return "空のコマンドは実行できません"
    if SHELL_META & set(command):
        return "pipe-builder の Bash では、コマンドをつなぐ・書き出す記号（; & | ` $ < > など）は使えません"
    if not GEN.fullmatch(command.strip()):
        return "pipe-builder の Bash で使えるのは pipe-in-gen list / new / check だけです（devpipe-gen は名前が変わりました）"
    if any(t == "--force" or t.startswith("--force=") for t in command.split()):
        return "作り直し（--force）は人が決めます。親に差し戻してください"
    return None


def decide(payload: dict[str, Any], *, pipes_env: str | Sequence[str] | None) -> str | None:
    """止める理由を返す。止めないときは None。pipe-builder と pipe-judge 以外の呼び出しには何もしない。
    ただし、文字列でも null でもない agent_type は、読む道具以外を止める。
    報告の道具（REPORT_TOOLS）は、agent_type が文字列なら止めない（D0096）。"""
    agent_type = payload.get("agent_type")
    tool = payload.get("tool_name")
    if agent_type is not None and not isinstance(agent_type, str):
        # 型のおかしい agent_type は、だれの呼び出しか分からない。読む道具だけ通し、ほかは止める（理由に入れるのは型の名前だけ）
        if isinstance(tool, str) and tool in READ_TOOLS:
            return None
        return f"agent_type の型が文字列ではないため止めました（{type(agent_type).__name__}）"
    if is_report_tool(tool):
        # 名前の分かる相手（pipe-judge・pipe-builder・ほか）の報告は止めない（D0096）。入力（報告の文）は見ない
        return None
    if is_judge(agent_type):
        # 許すものの一覧：読む道具だけ。型のおかしい tool_name（list など）も止める
        if isinstance(tool, str) and tool in READ_TOOLS:
            return None
        return f"pipe-judge は {tool} を使えません（使えるのは Read・Glob・Grep だけ）"
    if not is_builder(agent_type):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in READ_TOOLS:
        return None
    if tool in WRITE_TOOLS:
        return check_write(tool_input.get("file_path"), str(payload.get("cwd") or ""), pipes_env)
    if tool == "Bash":
        return check_bash(tool_input.get("command"))
    # NotebookEdit は道具ごと止める。許すことにするときは、書き込み先の項目が notebook_path（file_path でない）なので、それを見る
    return f"pipe-builder は {tool} を使えません（使えるのは Read・Glob・Grep・Write・Edit と、Bash の pipe-in-gen だけ）"


def _deny(reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


class _InputTooLarge(ValueError):
    """標準入力が上限（MAX_STDIN_BYTES）を超えた。"""


def _read_stdin() -> str:
    # Windows でも、Claude Code が渡す UTF-8 をそのまま読む。上限＋1 バイトまでしか読まず、超えたら止める
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        data = buffer.read(MAX_STDIN_BYTES + 1)
        if len(data) > MAX_STDIN_BYTES:
            raise _InputTooLarge
        return data.decode("utf-8")
    text = sys.stdin.read(MAX_STDIN_BYTES + 1)  # buffer が無い入力（テストの StringIO など）は文字数で数える
    if len(text) > MAX_STDIN_BYTES:
        raise _InputTooLarge
    return text


def _write(text: str) -> None:
    sys.stdout.write(text)
    # 書けない失敗を、終了処理でなくここで見つける（最後の砦へ渡すため）
    sys.stdout.flush()


def _last_resort(exc: Exception) -> int:
    """deny の JSON を書けなかったとき：JSON に頼らず、標準エラーの理由と終了コード 2 で止める。"""
    text = f"pipe-in のフック（pipe-in-gen guard-hook）が deny の JSON を出せなかったため、終了コード 2 で止めました（{type(exc).__name__}）。\n"
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001 - 標準エラーも書けないときは、理由は出せないが終了コード 2 で止める
        pass
    return 2


def _run(decide_fn: Callable[..., str | None]) -> int:
    try:
        payload = json.loads(_read_stdin())
    except Exception:  # noqa: BLE001 - 読めない・UTF-8 でない・壊れた JSON・入れ子が深すぎる・上限超え、のどれも止める
        payload = None
    if not isinstance(payload, dict):
        # だれの呼び出しか分からないので、安全側に倒して止める
        _write(_deny("フックへの入力が読めないため止めました"))
        return 0
    try:
        reason = decide_fn(payload, pipes_env=env_pipes_dirs(os.environ))
    except Exception:  # noqa: BLE001 - 想定外の入力で落ちると止めない側に倒れるので、止める
        reason = "フックが入力を判断できなかったため止めました"
    if reason:
        _write(_deny(reason))
    return 0


def main(decide_fn: Callable[..., str | None] | None = None) -> int:
    """標準入力の JSON を見て、止めるときだけ deny の JSON を出す。戻り値は 0（deny を出した・止めない）か 2（書けなかった）だけ。

    decide_fn は止める理由を決める関数（decide と同じ引数）。省くと decide。会話の道は chat_hook.py が渡す。
    """
    try:
        return _run(decide_fn or decide)
    except Exception as exc:  # noqa: BLE001 - deny を書けなかったときは、標準エラーと終了コード 2 で止める
        return _last_resort(exc)


def quiet_exit_streams() -> None:
    """終了コード 2 のまま終わるための後始末。書けなかったバイトが標準出力・標準エラーに残っていると、
    終了処理の flush がまた失敗し、終了コードが 120 に変わって止まらなくなる。両方の fd を捨て先へ付け替え、
    付け替えられないものは sys から外す。例外は出さない。"""
    try:
        sink = os.open(os.devnull, os.O_WRONLY)
    except Exception:  # noqa: BLE001
        sink = -1
    for name in ("stdout", "stderr"):
        try:
            if sink < 0:
                raise OSError("捨て先を開けない")
            os.dup2(sink, getattr(sys, name).fileno())
        except Exception:  # noqa: BLE001
            setattr(sys, name, None)
    if sink > 2:
        try:
            os.close(sink)
        except Exception:  # noqa: BLE001
            pass
