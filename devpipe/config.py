"""設定の読み込み（pipeline.toml とコマンドライン引数）。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STAGES: tuple[str, ...] = ("requirements", "design", "red", "implement", "test")

STAGE_LABELS: dict[str, str] = {
    "requirements": "要件定義",
    "design": "設計",
    "red": "テスト先行",
    "implement": "実装",
    "test": "検証",
}


@dataclass
class StageConfig:
    model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None


@dataclass
class Config:
    project_dir: Path
    work_dir: Path
    max_retries: int = 3
    test_command: str | None = None
    test_timeout_sec: int = 1800
    auto_approve: bool = False
    extra_test_globs: list[str] = field(default_factory=list)
    stages: dict[str, StageConfig] = field(default_factory=dict)
    # ドメインの文書（用語集・コンテキストの地図など）を積み上げるフォルダ。設計の段だけが書ける。
    domain_dir: Path | None = None
    # SDK に読ませる設定の出どころ（"project" で CLAUDE.md・.claude/ の規約やフックを効かせる）
    setting_sources: list[str] | None = None
    # どの段も書き換えられないパス（glob）。層の検査など、テストの形をした「規則」を守る。
    protected_paths: list[str] = field(default_factory=list)

    def stage(self, name: str) -> StageConfig:
        return self.stages.get(name, StageConfig())

    def rel(self, path: Path) -> str:
        """プロジェクトからの相対パス（表示・プロンプト用）。"""
        try:
            return path.resolve().relative_to(self.project_dir).as_posix()
        except ValueError:
            return str(path)


DEFAULT_MAX_TURNS = {"requirements": 40, "design": 60, "red": 100, "implement": 150, "test": 100}


def load_config(
    project_dir: Path,
    config_path: Path | None = None,
    *,
    max_retries: int | None = None,
    test_command: str | None = None,
    auto_approve: bool = False,
) -> Config:
    project_dir = project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"プロジェクトのフォルダが見つかりません: {project_dir}")

    raw: dict[str, Any] = {}
    candidates = [config_path] if config_path else [project_dir / "pipeline.toml"]
    for c in candidates:
        if c and c.is_file():
            with c.open("rb") as f:
                raw = tomllib.load(f)
            break
        if config_path:
            raise SystemExit(f"設定ファイルが見つかりません: {config_path}")

    p = raw.get("pipeline", {})
    work_dir = (project_dir / p.get("work_dir", "docs/pipeline")).resolve()
    if project_dir not in (work_dir, *work_dir.parents):
        raise SystemExit("work_dir はプロジェクトの中に置いてください")
    domain_dir: Path | None = None
    if p.get("domain_dir"):
        domain_dir = (project_dir / p["domain_dir"]).resolve()
        if project_dir not in domain_dir.parents:
            raise SystemExit("domain_dir はプロジェクトの中に置いてください")

    stages: dict[str, StageConfig] = {}
    raw_stages = raw.get("stages", {})
    for name in STAGES:
        s = raw_stages.get(name, {})
        stages[name] = StageConfig(
            model=s.get("model"),
            max_turns=s.get("max_turns", DEFAULT_MAX_TURNS[name]),
            max_budget_usd=s.get("max_budget_usd"),
        )

    return Config(
        project_dir=project_dir,
        work_dir=work_dir,
        max_retries=max_retries if max_retries is not None else int(p.get("max_retries", 3)),
        test_command=test_command or p.get("test_command"),
        test_timeout_sec=int(p.get("test_timeout_sec", 1800)),
        auto_approve=auto_approve,
        extra_test_globs=list(p.get("extra_test_globs", [])),
        stages=stages,
        domain_dir=domain_dir,
        setting_sources=list(p["setting_sources"]) if "setting_sources" in p else None,
        protected_paths=list(p.get("protected_paths", [])),
    )
