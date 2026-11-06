"""プラグインの PreToolUse フックのうち、会話の中で流す段（pipe-stage・pipe-probe）を絞る部分（D0077）。

標準入力の JSON（Claude Code のフックの入力）を読み、今の段の範囲の外なら deny の JSON を出す。
- pipe-stage：開いている段（記録の open）の範囲を、本体の判断（guard.check_tool）と同じ関数で絞る。
- pipe-probe：読む道具のほかは止める（止めたことを跡に残す。司会役が読んで守りを確かめる）。
- 段が開いている間のほかのエージェント：すべて止める。
- それ以外（会話本体・記録の無い作業フォルダ）は、今の guard_hook.decide に渡す（pipe-builder・pipe-judge の絞りは変えない）。
読めない・分からない・例外のときは止める側に倒す。入口の読み書きと deny の形は guard_hook.main と同じ。
SDK は読まない。agent_type の無い呼び出し（会話本体）は、記録も本体の部品も読まずに decide へ渡す。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import guard_hook

READ_TOOLS = guard_hook.READ_TOOLS
WRITE_PATH_KEYS = ("file_path", "notebook_path")


def _target(tool_input: Any, cwd: str) -> str | None:
    """跡に残す書き込み先（パスは絶対に直す。Bash はコマンドの頭）。"""
    if not isinstance(tool_input, dict):
        return None
    for key in WRITE_PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            return os.path.normpath(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    command = tool_input.get("command")
    return command[:200] if isinstance(command, str) else None


def _trace(run_dir: Path, event: str, as_name: str | None, payload: dict[str, Any], reason: str, seq: Any) -> None:
    from pipe_in.pipe import chat_record

    try:
        chat_record.append_trace(
            run_dir,
            {
                "at": _now(),
                "event": event,
                "as": as_name,
                "agent_type": payload.get("agent_type"),
                "tool": payload.get("tool_name") if isinstance(payload.get("tool_name"), str) else None,
                "target": _target(payload.get("tool_input"), str(payload.get("cwd") or "")),
                "reason": reason,
                "seq": seq,
            },
        )
    except OSError:
        pass  # 跡が書けなくても、止める判断は変えない


def _now() -> str:
    from pipe_in.engine import clock

    return clock.now_with_offset()


def _probe(payload: dict[str, Any], project: Path | None) -> str | None:
    tool = payload.get("tool_name")
    if isinstance(tool, str) and tool in READ_TOOLS:
        return None
    reason = f"pipe-probe は {tool} を使えません（確かめ役が使えるのは読む道具だけで、何も書けません）"
    if project is not None:
        from pipe_in.pipe import chat_record

        recs, _ = chat_record.scan(project)
        for rec in recs:
            if rec.chat.get("probe", {}).get("status") == "asked":
                _trace(rec.run_dir, "probe_denied", "pipe-probe", payload, reason, None)
    return reason


def _stage(payload: dict[str, Any], project: Path, recs: list[Any], broken: list[Path]) -> str | None:
    from pipe_in.engine.config import load_config
    from pipe_in.engine.guard import check_tool
    from pipe_in.pipe import chat_record, definition

    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return "道具の名前が読めないため止めました"
    if broken:
        return "会話の中で流している記録（state.json）が読めないため止めました"
    opens = [r for r in recs if r.open]
    if not opens:
        return "いま開いている段がありません。pipe-stage は chat next で段が開いている間だけ使えます"
    if len(opens) > 1:
        return "開いている段が複数あり、どの段か決められないため止めました"
    rec = opens[0]
    o = rec.open or {}
    chat = rec.chat
    pipe_name = rec.state.get("pipe")
    if not isinstance(pipe_name, str) or pipe_name != rec.run_dir.name:
        return "記録のパイプの名前が読めないため止めました"
    pipe_dir = chat_record.resolve_pipe_dir(project, chat.get("pipe_dir", ""))
    if chat_record.fingerprint(pipe_dir, project.resolve()) != chat.get("fingerprint"):
        return "pipe.toml か pipeline.toml が、始めたときから変わっているため止めました"
    pipe = definition.load_pipe(pipe_dir)
    stage = o.get("stage")
    if stage not in [s.name for s in pipe.stages]:
        return f"開いている段「{stage}」が定義にないため止めました"
    cfg = load_config(project).for_pipe(pipe_name, own_work_dir=True)
    if cfg.work_dir.resolve() != rec.run_dir.resolve():
        return "記録の場所が設定と合わないため止めました"
    spec = chat_record.chat_specs(cfg, pipe)[stage]
    if tool == "Skill":
        return "会話の中で流す段では Skill を使えません（範囲外の操作をする道を残さないため）"
    bash_state = chat_record.load_bash_state(rec.run_dir, o.get("seq"), cfg.project_dir) if tool == "Bash" else None
    reason = check_tool(
        tool,
        payload.get("tool_input", {}),
        project_dir=cfg.project_dir,
        can_write=spec.can_write,
        allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint,
        allowed_tools=spec.allowed_tools,
        fetch_domains=spec.fetch_domains,
        bash_state=bash_state,
    )
    if reason:
        _trace(rec.run_dir, "stage_denied", "pipe-stage", payload, reason, o.get("seq"))
    elif bash_state is not None:
        chat_record.save_bash_state(rec.run_dir, o.get("seq"), bash_state)
    return reason


def _agent(payload: dict[str, Any], pipes_env: Any) -> str | None:
    agent = payload["agent_type"]
    cwd = payload.get("cwd")
    project = Path(cwd) if isinstance(cwd, str) and cwd else None
    if guard_hook.is_probe(agent):
        return _probe(payload, project)
    is_stage = guard_hook.is_stage(agent)
    if project is None:
        if is_stage:
            return "作業フォルダ（cwd）が分からないため止めました"
        return guard_hook.decide(payload, pipes_env=pipes_env)
    from pipe_in.pipe import chat_record

    recs, broken = chat_record.scan(project)
    if is_stage:
        return _stage(payload, project, recs, broken)
    opens = [r for r in recs if r.open]
    if opens or broken:
        reason = "会話の中で段が開いている間は、pipe-stage と pipe-probe 以外のエージェントは使えません"
        if len(opens) == 1:
            _trace(opens[0].run_dir, "agent_denied", None, payload, reason, (opens[0].open or {}).get("seq"))
        return reason
    return guard_hook.decide(payload, pipes_env=pipes_env)


def decide(payload: dict[str, Any], *, pipes_env: Any) -> str | None:
    """止める理由を返す。止めないときは None。"""
    if payload.get("agent_type") is None:
        return guard_hook.decide(payload, pipes_env=pipes_env)
    try:
        return _agent(payload, pipes_env)
    except (Exception, SystemExit):  # noqa: BLE001 - 判断できないときは止める側に倒す
        return "フックが入力を判断できなかったため止めました"


def main() -> int:
    """標準入力のフックの入力を読み、止めるなら deny の JSON を標準出力に書く。終了コードを返す。"""
    return guard_hook.main(decide_fn=decide)
