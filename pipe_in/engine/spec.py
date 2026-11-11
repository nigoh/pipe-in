"""段の設定（使えるツール・書き込める範囲・指示文）の型と、どのパイプにも共通の決まり。"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config import Config, positive_budget
from .guard import DEFAULT_MAX_AGENT_CALLS
from .reply import REPLY_FILE

READ_TOOLS = ["Read", "Glob", "Grep"]
EDIT_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit"]
NO_WEB = ["WebFetch", "WebSearch"]
# Bash と同じことができるのにガードの判定を通らない道。ガードでも止めるが、最初から使えなくしておく。
NO_SHELL_BYPASS = ["PowerShell"]


@dataclass
class StageSpec:
    name: str
    label: str
    allowed_tools: list[str]
    disallowed_tools: list[str]
    allow_bash: bool
    can_write: Callable[[str], bool]
    write_scope_hint: str
    system_append: str
    output_format: dict[str, Any] | None = None
    # 段の成果物（記録の置き場所の中のファイル名）と、このあとに人の確認を取るか。
    # state.json の stages に残し、VSCode の拡張が図と成果物の一覧を作るのに使う。
    output: str | None = None
    review: bool = False
    # WebFetch を許すドメイン（None は制限なし。WebFetch を許すかは allowed_tools で決める）
    fetch_domains: list[str] | None = None
    # Agent SDK の設定（パイプの段が書いたもの。開発フローでは使わない）
    permission_mode: str | None = None
    max_thinking_tokens: int | None = None
    fallback_model: str | None = None
    add_dirs: list[str] = field(default_factory=list)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 段の既定。pipeline.toml の [stages.<段>] に書いたほうが優先される。
    model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    # 段の1回の実行で通すサブエージェント（Agent・Task）の数の上限（D0035）。ガードが数えて、超えたら止める
    max_agent_calls: int = DEFAULT_MAX_AGENT_CALLS


def stage_budget_usd(spec: StageSpec, cfg: Config) -> float | None:
    """段の費用の上限（ドル）。pipeline.toml の値が優先、無ければ段の定義（pipe.toml など）の値。
    戻りは「0 より大きい有限な数か None」だけ。
    SDK に渡す値（runner.sdk_options）と、runs[] に残す値（BasePipeline._run）は、必ずこの関数から取る（D0051）。"""
    return positive_budget(cfg.stage(spec.name).max_budget_usd or spec.max_budget_usd)


# 設定なしでも、どの段も書けない場所（D0084）。設定・フック・エージェント・スキル（.claude/）、
# git の中（.git/ と、worktree でファイルになる .git 自身）、パイプと設定の置き場所、前の版の置き場所、
# プロジェクトの MCP の定義 .mcp.json（setting_sources の project で読まれる。D0086）。
# 外す設定は作らない。足したいときは pipeline.toml の protected_paths に書く。
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    ".claude/*",
    "*/.claude/*",
    ".git/*",
    ".git",
    ".pipe-in/*",
    "pipeline.toml",
    ".mcp.json",
    ".devpipe/*",
)


def work_dir_conflict(cfg: Config) -> str | None:
    """work_dir が既定で守る場所の中か、プロジェクトそのもの（.）なら、直し方つきの文を返す。重ならなければ None。
    段が自分の成果物を書けなくなる設定を、流す前に断るために使う。ファイルは読み書きしない。"""
    rel = cfg.rel(cfg.work_dir).replace("\\", "/")
    parts = rel.split("/")
    # 自分と、上の階層のどれか（.mcp.json/x のように、ファイルの型の下も断る）、自分の下
    paths = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)] + [f"{rel}/x"]
    hit = rel == "." or any(fnmatch.fnmatch(p, g) for p in paths for g in DEFAULT_PROTECTED_PATHS)
    if not hit:
        return None
    return (
        f"work_dir「{rel}」は、段が書いてはいけない場所（.claude/・.git/・.pipe-in/・.devpipe/・.mcp.json・pipeline.toml）の中か、"
        "それを含んでいます。段が自分の成果物を書けなくなるので、流しません。"
        'pipeline.toml の [pipeline] work_dir を、その外（例: work_dir = "docs/pipeline"）に直してください。'
    )


def protect(specs: dict[str, StageSpec], cfg: Config) -> dict[str, StageSpec]:
    """返事の場所（実行のフォルダの reply.json。D0079）と、既定で守る場所と protected_paths を、どの段の書き込み範囲からも外す。"""
    reply_rel = f"{cfg.rel(cfg.work_dir)}/{REPLY_FILE}"
    extra = [g for g in cfg.protected_paths if g not in DEFAULT_PROTECTED_PATHS]
    globs = [*DEFAULT_PROTECTED_PATHS, *extra]
    base = f"既定で守る場所 {', '.join(DEFAULT_PROTECTED_PATHS)}"
    hint = f"（{base}" + (f" と、protected_paths の {', '.join(extra)}" if extra else "") + " は、どの段も変更できません）"
    for spec in specs.values():
        spec.can_write = _unless_reply(spec.can_write, reply_rel)
        spec.can_write = _unless_protected(spec.can_write, globs)
        spec.write_scope_hint += hint
    return specs


def _unless_reply(can_write: Callable[[str], bool], reply_rel: str) -> Callable[[str], bool]:
    """返事の場所だけを書けなくする。Windows・macOS では REPLY.JSON も同じファイルなので、大文字小文字は区別しない。"""
    target = reply_rel.casefold()

    def wrapped(rel: str) -> bool:
        return rel.casefold() != target and can_write(rel)

    return wrapped


def _unless_protected(can_write: Callable[[str], bool], globs: list[str]) -> Callable[[str], bool]:
    def wrapped(rel: str) -> bool:
        return not any(fnmatch.fnmatch(rel, g) for g in globs) and can_write(rel)

    return wrapped
