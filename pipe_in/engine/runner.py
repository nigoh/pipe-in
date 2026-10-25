"""1つの段を Claude Agent SDK で実行する。"""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import clock
from .config import MIB, Config
from .guard import make_guard_hook
from ..usage.metrics import StageMetrics
from .spec import StageSpec, stage_budget_usd

# SDK が受信バッファの上限を超えたときの例外の文の一部。今の SDK では CLIJSONDecodeError のまま届くが、
# SDK の中の予備の経路で素の Exception に平らになって届くこともあるので、型（その2つだけ）と文の両方で見分ける
BUFFER_OVERFLOW_MARK = "maximum buffer size"
# 上限を超えて止めた段の StageRun.subtype。SDK の ResultMessage.subtype の値ではなく、pipe-in が付ける値
BUFFER_OVERFLOW_SUBTYPE = "error_max_buffer_size"
# API の1つのリクエストの大きさの上限（MB）。受信バッファをこれより上げても、大きいメッセージは API で通らないおそれがある
API_REQUEST_LIMIT_MB = 32


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


def buffer_overflow_notice(error_text: str, limit_bytes: int) -> str | None:
    """SDK の例外の文が受信バッファの上限を超えたことを表すなら、直し方の入った日本語の案内を返す。ほかの文には None。"""
    if BUFFER_OVERFLOW_MARK not in error_text:
        return None
    limit_mb = limit_bytes / MIB
    head = (
        f"SDK の受信バッファの上限（今は {limit_mb:g}MB）を超えるメッセージが届いたため、この段を止めました。"
        "大きい画像などを読むと超えます。"
        "画像を小さくするか、必要な所だけを切り出してから読ませてください。"
    )
    if limit_mb < API_REQUEST_LIMIT_MB:
        raise_hint = f"または、pipeline.toml の [pipeline] に max_buffer_mb = {limit_mb * 2:g} のように、今より大きい値を書いてから流し直してください。"
    else:
        # 倍の値は勧めない（API のリクエストの上限を超えるので、上げても通らないおそれがある）
        raise_hint = (
            f"pipeline.toml の max_buffer_mb をこれより上げても、API のリクエストの上限も {API_REQUEST_LIMIT_MB}MB なので、"
            "通らないおそれがあります。"
        )
    return f"{head}{raise_hint}（SDK の文: {error_text[:200]}）"


def sdk_options(spec: StageSpec, cfg: Config, *, resume: str | None) -> dict[str, Any]:
    """段の設定から、ClaudeAgentOptions に渡す値を作る（hooks を除く）。SDK を import せずに確かめられるように、
    サブエージェントはただの dict のまま返す（run_stage_sdk で AgentDefinition にする）。書かれていない設定は入れない。
    ただし受信バッファの上限（max_buffer_size）だけは、既定（32MB）でも必ず入れる。公式の文書では max_buffer_size の既定は None で、
    そのとき SDK はソースの中の定数（_DEFAULT_MAX_BUFFER_SIZE、1MB）を使う。1MB では大きい画像で止まる。"""
    sc = cfg.stage(spec.name)
    opts: dict[str, Any] = {
        "system_prompt": {"type": "preset", "preset": "claude_code", "append": spec.system_append},
        "cwd": str(cfg.project_dir),
        "permission_mode": spec.permission_mode or "default",
        "allowed_tools": spec.allowed_tools,
        "disallowed_tools": spec.disallowed_tools,
        "model": sc.model or spec.model,
        "max_turns": sc.max_turns or spec.max_turns,
        "max_budget_usd": stage_budget_usd(spec, cfg),
        "output_format": spec.output_format,
        "resume": resume,
        "setting_sources": cfg.setting_sources,
        "max_buffer_size": cfg.max_buffer_bytes,
        # 裏の作業を止め、サブエージェントの入れ子を 1 段までにする（D0035）。手元の環境変数では上書きされない。
        "env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"},
    }
    if spec.max_thinking_tokens:
        opts["max_thinking_tokens"] = spec.max_thinking_tokens
    if spec.fallback_model:
        opts["fallback_model"] = spec.fallback_model
    if spec.add_dirs:
        opts["add_dirs"] = list(spec.add_dirs)
    if spec.agents:
        # サブエージェントの中から Agent・Task を呼ばせない（ガードの入れ子の検査に加える二重の守り）。
        opts["agents"] = {name: {**a, "disallowedTools": ["Agent", "Task"]} for name, a in spec.agents.items()}
    if spec.mcp_servers:
        opts["mcp_servers"] = {name: dict(m) for name, m in spec.mcp_servers.items()}
    return opts


def stage_guard(spec: StageSpec, cfg: Config, on_deny: Callable[[str, str], None] | None = None):
    """段の1回の実行のガード。呼ぶたびに新しい数（0 から）を持つので、差し戻しのやり直し・人の指摘の反映・
    グループの段の1つは、それぞれ 0 から数える（D0035）。"""
    return make_guard_hook(
        project_dir=cfg.project_dir,
        can_write=spec.can_write,
        allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint,
        allowed_tools=spec.allowed_tools,
        fetch_domains=spec.fetch_domains,
        max_agent_calls=spec.max_agent_calls,
        on_deny=on_deny,
    )


async def run_stage_sdk(
    spec: StageSpec, prompt: str, cfg: Config, *, resume: str | None, log_name: str
) -> StageRun:
    # 重い import はここで（テストでは SDK なしでも動くように）
    from claude_agent_sdk import (
        AgentDefinition,
        AssistantMessage,
        ClaudeAgentOptions,
        CLIJSONDecodeError,
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

    guard = stage_guard(spec, cfg, on_deny)
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
        # try は async with の外に置く（SDK が子プロセスを閉じてから例外がここに来る）
        try:
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
        except Exception as e:  # Ctrl+C・取り消し（BaseException）は受けない
            # 受け止めるのは、型が CLIJSONDecodeError か、ちょうど素の Exception（予備の経路で平らになったもの）で、
            # 文に上限超えの印があるときだけ。ほかの型（ProcessError など）は文に印があっても外へ出す
            caught_type = isinstance(e, CLIJSONDecodeError) or type(e) is Exception
            notice = buffer_overflow_notice(str(e), cfg.max_buffer_bytes) if caught_type else None
            if notice is None:
                raise  # 上限を超えたこと以外は、今までどおり外へ出す
            run.is_error = True
            run.subtype = BUFFER_OVERFLOW_SUBTYPE
            run.errors = [notice]
            print(f"    ✗ {notice}", flush=True)

    run.duration_sec = round(time.monotonic() - started, 1)
    return run
