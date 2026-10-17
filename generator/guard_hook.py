"""プラグインの PreToolUse フック（pipe-in-gen guard-hook）：pipe-builder が触れる範囲を絞る。

Claude Code のプラグインのエージェントには hooks を書けないため、プラグインの hooks/hooks.json から
どの道具の呼び出しでもここを呼び、入力の agent_type で pipe-builder の呼び出しだけを検査する。
pipe-builder に許すのは、読む道具と、パイプのフォルダの決まったファイルへの書き込みと、
pipe-in-gen list / new / check だけ。ほか（PowerShell・MCP・Web・Agent など）は止める。

パイプのフォルダは pipe-in-<名前>/ と、前の版の名前 devpipe-<名前>/ の両方を同じ決まりで守る。
置き場所の環境変数も、PIPE_IN_PIPES_DIR と前の版の DEVPIPE_PIPES_DIR の両方を同じ決まりで見る。
Bash で許すのは新しい名前の pipe-in-gen だけ（前の名前の別名は同じ中身なので、許す形を増やさない）。

道具を呼ぶたびに動くので、標準ライブラリだけを使う（本体や SDK を読み込まない）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

AGENT = "pipe-builder"
READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}

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


def is_builder(agent_type: Any) -> bool:
    """pipe-builder の呼び出しか。プラグインのエージェントは <プラグイン>:<名前> になる。"""
    return isinstance(agent_type, str) and (agent_type == AGENT or agent_type.endswith(":" + AGENT))


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


def check_write(file_path: Any, cwd: str, pipes_env: str | Sequence[str] | None) -> str | None:
    if not isinstance(file_path, str) or not file_path.strip():
        return "書き込み先のパスがありません"
    if ".." in re.split(r"[\\/]", file_path):
        return f"パスに .. を含む書き込みはできません（{file_path}）"
    full = os.path.normpath(file_path if os.path.isabs(file_path) else os.path.join(cwd or os.getcwd(), file_path))
    parts = Path(full).parts
    for i, part in enumerate(parts[:-2]):
        if part == "pipes" and PIPE_DIR.fullmatch(parts[i + 1]) and _in_pipe(parts[i + 2 :]):
            return None
    # 環境変数の置き場所の下も、同じ決まり（パイプのフォルダの決まったファイルだけ）で見る
    for env in _env_list(pipes_env):
        base = os.path.normpath(os.path.abspath(os.path.expanduser(env)))
        if os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
            rest = Path(os.path.relpath(full, base)).parts
            if rest and PIPE_DIR.fullmatch(rest[0]) and _in_pipe(rest[1:]):
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
    """止める理由を返す。止めないときは None。pipe-builder 以外の呼び出しには何もしない。"""
    if not is_builder(payload.get("agent_type")):
        return None
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in READ_TOOLS:
        return None
    if tool in WRITE_TOOLS:
        return check_write(tool_input.get("file_path"), str(payload.get("cwd") or ""), pipes_env)
    if tool == "Bash":
        return check_bash(tool_input.get("command"))
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


def _read_stdin() -> str:
    # Windows でも、Claude Code が渡す UTF-8 をそのまま読む
    buffer = getattr(sys.stdin, "buffer", None)
    return buffer.read().decode("utf-8") if buffer is not None else sys.stdin.read()


def main() -> int:
    """標準入力の JSON を見て、止めるときだけ deny の JSON を出す。終了コードはいつも 0。"""
    try:
        payload = json.loads(_read_stdin())
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        # だれの呼び出しか分からないので、安全側に倒して止める
        sys.stdout.write(_deny("フックへの入力が読めないため止めました"))
        return 0
    reason = decide(payload, pipes_env=env_pipes_dirs(os.environ))
    if reason:
        sys.stdout.write(_deny(reason))
    return 0
