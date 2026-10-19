"""1つの段を Claude Agent SDK で実行する。"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import clock
from .config import Config
from .guard import make_guard_hook
from ..usage.metrics import StageMetrics
from .spec import StageSpec


@dataclass
class StageRun:
    stage: str
    session_id: str | None = None
    is_error: bool = False
    subtype: str = ""
    result: str | None = None
    structured: Any = None
    cost_usd: float = 0.0
    num_turns: int = 0
    duration_sec: float = 0.0
    denials: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics: StageMetrics = field(default_factory=StageMetrics)


class StageRunner(Protocol):
    async def __call__(
        self, spec: StageSpec, prompt: str, cfg: Config, *, resume: str | None, log_name: str
    ) -> StageRun: ...


def _short(value: Any, limit: int = 90) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_summary(name: str, tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "notebook_path", "command", "pattern", "path"):
        if key in tool_input:
            return f"{name} {_short(tool_input[key])}"
    return name


def _to_jsonable(msg: Any) -> Any:
    if dataclasses.is_dataclass(msg):
        data = dataclasses.asdict(msg)
        data["_type"] = type(msg).__name__
        return data
    return {"_type": type(msg).__name__, "repr": repr(msg)}


def prompt_line(stage: str, resume: str | None, prompt: str, at: str) -> str:
    """段のログの最初の行（Prompt）の JSON 1行。at は段の始まりの時刻（UTC からのずれつき）。"""
    return json.dumps({"_type": "Prompt", "stage": stage, "resume": resume, "prompt": prompt, "at": at}, ensure_ascii=False)


def sdk_options(spec: StageSpec, cfg: Config, *, resume: str | None) -> dict[str, Any]:
    """段の設定から、ClaudeAgentOptions に渡す値を作る（hooks を除く）。SDK を import せずに確かめられるように、
    サブエージェントはただの dict のまま返す（run_stage_sdk で AgentDefinition にする）。書かれていない設定は入れない。"""
    sc = cfg.stage(spec.name)
    opts: dict[str, Any] = {
        "system_prompt": {"type": "preset", "preset": "claude_code", "append": spec.system_append},
        "cwd": str(cfg.project_dir),
        "permission_mode": spec.permission_mode or "default",
        "allowed_tools": spec.allowed_tools,
        "disallowed_tools": spec.disallowed_tools,
        "model": sc.model or spec.model,
        "max_turns": sc.max_turns or spec.max_turns,
        "max_budget_usd": sc.max_budget_usd or spec.max_budget_usd,
        "output_format": spec.output_format,
        "resume": resume,
        "setting_sources": cfg.setting_sources,
    }
    if spec.max_thinking_tokens:
        opts["max_thinking_tokens"] = spec.max_thinking_tokens
    if spec.fallback_model:
        opts["fallback_model"] = spec.fallback_model
    if spec.add_dirs:
        opts["add_dirs"] = list(spec.add_dirs)
    if spec.agents:
        opts["agents"] = {name: dict(a) for name, a in spec.agents.items()}
    if spec.mcp_servers:
        opts["mcp_servers"] = {name: dict(m) for name, m in spec.mcp_servers.items()}
    return opts


async def run_stage_sdk(
    spec: StageSpec, prompt: str, cfg: Config, *, resume: str | None, log_name: str
) -> StageRun:
    # 重い import はここで（テストでは SDK なしでも動くように）
    from claude_agent_sdk import (
        AgentDefinition,
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        HookMatcher,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
    )

    run = StageRun(stage=spec.name)
    label = spec.label

    def on_deny(tool: str, reason: str) -> None:
        run.denials.append(f"{tool}: {reason}")
        print(f"    ✋ 止めました: {tool} — {reason}", flush=True)

    guard = make_guard_hook(
        project_dir=cfg.project_dir,
        can_write=spec.can_write,
        allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint,
        allowed_tools=spec.allowed_tools,
        fetch_domains=spec.fetch_domains,
        on_deny=on_deny,
    )
    opts = sdk_options(spec, cfg, resume=resume)
    if "agents" in opts:
        opts["agents"] = {name: AgentDefinition(**a) for name, a in opts["agents"].items()}
    options = ClaudeAgentOptions(
        **opts,
        # すべてのツールに掛ける（段で許していないツールはガードが止める）。サブエージェントの道具の呼び出しにも掛かる
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]},
    )

    log_dir = cfg.work_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path: Path = log_dir / f"{log_name}.jsonl"
    started = time.monotonic()

    with log_path.open("a", encoding="utf-8") as log:
        log.write(prompt_line(spec.name, resume, prompt, clock.now_with_offset()) + "\n")
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                line = json.dumps(_to_jsonable(msg), ensure_ascii=False, default=str)
                log.write(line + "\n")
                run.metrics.feed(json.loads(line))  # ログと同じ形から集める
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            print(f"    · {_tool_summary(block.name, block.input)}", flush=True)
                        elif isinstance(block, TextBlock) and block.text.strip():
                            print(f"    {label}: {_short(block.text, 120)}", flush=True)
                elif isinstance(msg, ResultMessage):
                    run.session_id = msg.session_id
                    run.is_error = bool(msg.is_error)
                    run.subtype = msg.subtype
                    run.result = msg.result
                    run.structured = msg.structured_output
                    run.cost_usd = float(msg.total_cost_usd or 0.0)
                    run.num_turns = msg.num_turns
                    run.errors = list(msg.errors or [])

    run.duration_sec = round(time.monotonic() - started, 1)
    return run
