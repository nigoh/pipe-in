"""流す前の費用の目安（D0066）：pipe-in estimate の本体と、本流の確認前の 2 行。

読むだけ。段は流さず（SDK を呼ばず）、work_dir に何も書かない。
段のリストの組み立て（設定・パイプ → StageInput）はここで行い、計算は usage/estimate.py に任せる。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .dev.specs import DEFAULT_MAX_TURNS, STAGES, build_specs
from .engine.config import Config, load_config, positive_budget
from .engine.spec import stage_budget_usd
from .pipe import definition as pd
from .pipe.specs import DEFAULT_MAX_TURNS as PIPE_DEFAULT_MAX_TURNS
from .usage.estimate import Estimate, StageInput, actual_usd, estimate, format_line, format_table

# 開発フローで、差し戻しの輪（実装 → 検証 → 実装 …）に入る段。cfg.max_retries がこの 2 段に効く
DEV_RETRY_STAGES = ("implement", "test")


def stage_inputs(cfg: Config, pipe: pd.PipeDef | None) -> list[StageInput]:
    """段の入力のリスト。cfg は流すときの設定（記録の場所は state_path と同じ決め方で済んだもの）。"""
    if pipe is not None and pipe.kind != "dev":
        return _pipe_inputs(cfg, pipe)
    specs = build_specs(cfg)
    inputs: list[StageInput] = []
    for name in STAGES:
        spec = specs[name]
        sc = cfg.stage(name)
        inputs.append(
            StageInput(
                name=name,
                model=sc.model if sc.model is not None else spec.model,
                max_turns=sc.max_turns if sc.max_turns is not None else spec.max_turns,
                default_turns=DEFAULT_MAX_TURNS[name],
                max_budget_usd=stage_budget_usd(spec, cfg),
                max_retries=cfg.max_retries if name in DEV_RETRY_STAGES else 0,
            )
        )
    return inputs


def _pipe_inputs(cfg: Config, pipe: pd.PipeDef) -> list[StageInput]:
    inputs: list[StageInput] = []
    for s in pipe.stages:
        sc = cfg.stage(s.name)
        inputs.append(
            StageInput(
                name=s.name,
                model=sc.model if sc.model is not None else s.model,
                max_turns=sc.max_turns if sc.max_turns is not None else s.max_turns,
                default_turns=PIPE_DEFAULT_MAX_TURNS,
                max_budget_usd=positive_budget(sc.max_budget_usd or s.max_budget_usd),
                max_retries=s.check.max_retries if s.check is not None else 0,
            )
        )
    return inputs


def read_actual(cfg: Config) -> float | None:
    """今の記録（<work_dir>/state.json）の実績。無い・壊れているときは None。読むだけ。"""
    try:
        state: Any = json.loads((cfg.work_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return actual_usd(state)


def _estimate_for(cfg: Config, pipe: pd.PipeDef | None) -> Estimate:
    return estimate(stage_inputs(cfg, pipe), date.today())


def line_for_run(cfg: Config, pipe: pd.PipeDef | None) -> str | None:
    """本流の確認前に出す 2 行。cfg は流す設定（pipeline.cfg）。作れなければ None（流すことは止めない）。"""
    try:
        return format_line(_estimate_for(cfg, pipe), read_actual(cfg))
    except Exception:  # 目安は添え物。どんな形の設定でも、流すことを止めない
        return None


def main(
    argv: list[str],
    load_pipe: Callable[[str, Path], pd.PipeDef],
    run_cfg: Callable[[Config, pd.PipeDef | None], Config],
) -> int:
    """pipe-in estimate [--pipe 名前] [--project dir] [--config file]。段は流さない。"""
    p = argparse.ArgumentParser(prog="pipe-in estimate", description="流す前の費用の目安を出します（段は流しません）。")
    p.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    p.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    p.add_argument("--pipe", help="目安を出すパイプの名前かパス。省くと組み込みの開発フロー")
    args = p.parse_args(argv)
    pipe = load_pipe(args.pipe, args.project) if args.pipe else None
    cfg = run_cfg(load_config(args.project, args.config), pipe)
    print(format_table(_estimate_for(cfg, pipe), read_actual(cfg)))
    sys.stdout.flush()
    return 0
