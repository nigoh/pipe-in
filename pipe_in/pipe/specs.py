"""パイプの段の設定：権限の型（read / docs / tests / code）から書き込める範囲を作り、段への指示文を組み立てる。"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from importlib import resources
from typing import Any

from ..engine.config import Config
from ..engine.guard import is_test_path
from ..engine.pipeline import INPUT
from ..engine.spec import EDIT_TOOLS, NO_SHELL_BYPASS, NO_WEB, READ_TOOLS, StageSpec, protect
from .definition import AgentDef, McpServerDef, PipeDef, PipeStage

DEFAULT_MAX_TURNS = 100


def _stage_rules() -> str:
    return resources.files("pipe_in.pipe").joinpath("stage_rules.md").read_text(encoding="utf-8")


def _can_write(cfg: Config, stage: PipeStage) -> tuple[Callable[[str], bool], str]:
    work = cfg.rel(cfg.work_dir)
    own = f"{work}/{stage.output}"

    def under_work(rel: str) -> bool:
        return rel == work or rel.startswith(work + "/")

    if stage.access == "docs":
        docs = cfg.rel((cfg.project_dir / (stage.docs_dir or "")).resolve())
        base, hint = (lambda rel: rel == docs or rel.startswith(docs + "/")), f"{own} と {docs}/ の下"
    elif stage.access == "tests":
        base, hint = (lambda rel: not under_work(rel) and is_test_path(rel, cfg.extra_test_globs)), f"テストファイルと {own}"
    elif stage.access == "code":
        base, hint = (
            lambda rel: not under_work(rel) and not is_test_path(rel, cfg.extra_test_globs)
        ), f"製品コードと {own}（テストファイルは除く）"
    else:
        return (lambda rel: rel == own), own

    if stage.writes:
        # 型の範囲の中を、さらに writes の glob に絞る（fnmatch なので * は / もまたぐ）
        globs = list(stage.writes)
        narrowed = base
        base = lambda rel: narrowed(rel) and any(fnmatch.fnmatch(rel, g) for g in globs)  # noqa: E731
        hint = f"{own} と {', '.join(globs)}（{hint} のうち）"
    return (lambda rel: rel == own or base(rel)), hint


def _outside_pipe(can_write: Callable[[str], bool], cfg: Config, pipe: PipeDef) -> Callable[[str], bool]:
    """パイプのフォルダ（定義・指示文）は、どの段からも書き換えさせない（このリポジトリ自身を対象にしたときのため）。"""
    pipe_rel = cfg.rel(pipe.dir.resolve())

    def wrapped(rel: str) -> bool:
        return not (rel == pipe_rel or rel.startswith(pipe_rel + "/")) and can_write(rel)

    return wrapped


def _sdk_tool_name(mcp: str) -> str:
    """mcp__<サーバー>__* は、SDK にはサーバー単位（mcp__<サーバー>）で渡す。"""
    return mcp[: -len("__*")] if mcp.endswith("__*") else mcp


def _tools(s: PipeStage) -> tuple[list[str], list[str]]:
    web_tools = ["WebFetch", "WebSearch"] if s.web else (["WebFetch"] if s.fetch_domains else [])
    # サブエージェントを使う段だけ、任せる道具（Task・Agent）を許す。任された先の道具の呼び出しにも guard が掛かる
    subagent = ["Task", "Agent"] if s.agents else []
    allowed = READ_TOOLS + EDIT_TOOLS + (["Bash"] if s.bash else []) + web_tools + [_sdk_tool_name(m) for m in s.mcp] + subagent
    disallowed = ([] if s.bash else ["Bash"]) + [w for w in NO_WEB if w not in web_tools] + NO_SHELL_BYPASS
    return allowed, disallowed


def output_format(s: PipeStage) -> dict[str, Any] | None:
    """検証の判定（verdict）と分岐の選択（routes）を、構造化出力で返させる形。"""
    props: dict[str, Any] = {}
    required: list[str] = []
    if s.check and s.check.verdict:
        props["status"] = {
            "type": "string",
            "enum": ["pass", "fail"],
            "description": "pass=この段の成果物が求められたことを満たしている / fail=直す点がある",
        }
        props["summary"] = {"type": "string", "description": "判定の要約（日本語・3行以内）"}
        props["problems"] = {"type": "array", "items": {"type": "string"}, "description": "直す点（根拠のファイルも添える）"}
        required += ["status", "summary", "problems"]
    if s.routes:
        props["choice"] = {"type": "string", "enum": list(s.routes), "description": "次に進む先"}
        required.append("choice")
    if not props:
        return None
    return {"type": "json_schema", "schema": {"type": "object", "properties": props, "required": required}}


def _agent(a: AgentDef) -> dict[str, Any]:
    d: dict[str, Any] = {"description": a.description, "prompt": a.prompt}
    if a.tools:
        d["tools"] = list(a.tools)
    if a.model:
        d["model"] = a.model
    return d


def _mcp_server(m: McpServerDef) -> dict[str, Any]:
    if m.type == "stdio":
        d: dict[str, Any] = {"type": "stdio", "command": m.command}
        if m.args:
            d["args"] = list(m.args)
        return d
    return {"type": m.type, "url": m.url}


def build_pipe_specs(cfg: Config, pipe: PipeDef) -> dict[str, StageSpec]:
    rules = _stage_rules()
    specs: dict[str, StageSpec] = {}
    for s in pipe.stages:
        can_write, hint = _can_write(cfg, s)
        allowed, disallowed = _tools(s)
        specs[s.name] = StageSpec(
            name=s.name,
            label=s.label,
            output=s.output,
            review=s.review,
            allowed_tools=allowed,
            disallowed_tools=disallowed,
            allow_bash=s.bash,
            can_write=_outside_pipe(can_write, cfg, pipe),
            write_scope_hint=hint,
            system_append=rules + (f"\n\n## この段の決まり\n\n{s.system_append.strip()}\n" if s.system_append else ""),
            output_format=output_format(s),
            permission_mode=s.permission_mode,
            max_thinking_tokens=s.max_thinking_tokens,
            fallback_model=s.fallback_model,
            add_dirs=[str((cfg.project_dir / d).resolve()) for d in s.add_dirs],
            agents={name: _agent(a) for name, a in s.agents.items()},
            mcp_servers={name: _mcp_server(m) for name, m in s.mcp_servers.items()},
            fetch_domains=list(s.fetch_domains) if s.fetch_domains else None,
            model=s.model,
            max_turns=s.max_turns or DEFAULT_MAX_TURNS,
            max_budget_usd=s.max_budget_usd,
        )
    return protect(specs, cfg)


def stage_prompt(cfg: Config, pipe: PipeDef, index: int, failure_note: str | None = None) -> str:
    """段への依頼文。渡すものは、依頼メモと、前の段のうち成果物がもうあるもの（分岐で通らなかった段は除く）。"""
    w = cfg.rel(cfg.work_dir)
    stage = pipe.stages[index]
    given: list[str] = []
    if (cfg.work_dir / INPUT).is_file():
        given.append(f"- 依頼メモ: `{w}/{INPUT}`")
    given += [
        f"- {prev.label}の成果物: `{w}/{prev.output}`"
        for prev in pipe.stages[:index]
        if (cfg.work_dir / prev.output).is_file() and not (stage.group and prev.group == stage.group)
    ]
    lines = [stage.prompt_text(), ""]
    if given:
        lines += ["## 渡すもの", "", "先に読んでください。", "", *given, ""]
    if failure_note:
        lines += ["## 前回の検証で見つかった問題", "", failure_note, "", "これを直したうえで、成果物を書き直してください。", ""]
    lines += ["## 書くもの", "", f"成果物を `{w}/{stage.output}` に書いてください。"]
    if stage.access == "docs" and stage.docs_dir:
        docs = cfg.rel((cfg.project_dir / stage.docs_dir).resolve())
        lines.append(f"図や文書のファイルは `{docs}/` の下に置き、成果物からリンクしてください。")
    if stage.check and stage.check.verdict:
        lines.append("最後に、判定（status: pass / fail・summary・problems）を構造化出力で返してください。")
    if stage.routes:
        lines.append(f"最後に、次に進む先を choice（{' / '.join(stage.routes)} のどれか）で返してください。")
    return "\n".join(lines)


def revise_prompt(cfg: Config, pipe: PipeDef, stage: str, feedback: str) -> str:
    s = next(x for x in pipe.stages if x.name == stage)
    target = f"{cfg.rel(cfg.work_dir)}/{s.output}"
    return (
        f"確認で次の指摘がありました。指摘を反映して `{target}` を更新してください"
        "（この段で作ったほかのファイルも、必要なら直してください）。\n"
        "反映しなかった指摘があれば、その理由を成果物の末尾「レビュー対応」に書いてください。\n\n"
        f"## 指摘\n{feedback}"
    )
