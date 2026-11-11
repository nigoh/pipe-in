"""会話の中でパイプを流す道（D0077）の記録の読み書き。司会役（chat.py）とフック（generator/chat_hook.py）が共有する。

state.json を探す・読む、定義の指紋、段の書ける範囲（chat_specs）、フックが残す跡（hook/trace.jsonl）、
Bash の cd をまたいだ覚え（hook/bash_state.json）を持つ。SDK は読まない。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine.bashwrite import BashState
from ..engine.config import Config
from ..engine.pipeline import CHAT_DRIVER, STATE
from .definition import PIPE_FILE, PipeDef
from .specs import build_pipe_specs

HOOK_DIR = "hook"
TRACE = "trace.jsonl"
BASH_STATE = "bash_state.json"
PROBE_DIR = "probe"
USAGE_UNAVAILABLE = {"available": False, "reason": "会話の中で流したため、費用とトークンは取れません"}


def fingerprint(pipe_dir: Path, project: Path) -> str:
    """定義の指紋。pipe.toml と pipeline.toml（無ければ空）の中身から作る。始めたときから変わると、段を流さない。"""
    h = hashlib.sha256()
    for path in (pipe_dir / PIPE_FILE, project / "pipeline.toml"):
        h.update(path.read_bytes() if path.is_file() else b"")
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


# ---- 記録を探す・読む -----------------------------------------------------------------------


@dataclass
class Rec:
    run_dir: Path
    state: dict[str, Any]

    @property
    def open(self) -> dict[str, Any] | None:
        o = self.state.get("open")
        return o if isinstance(o, dict) else None

    @property
    def chat(self) -> dict[str, Any]:
        c = self.state.get("chat")
        return c if isinstance(c, dict) else {}


def work_base(project: Path) -> Path:
    """記録を置く親のフォルダ（既定は docs/pipeline）。設定を読めなければ既定を使う。"""
    from ..engine.config import load_config

    try:
        return load_config(project).work_dir
    except (Exception, SystemExit):  # noqa: BLE001 - 設定が読めなくても探せるように既定へ
        return project / "docs" / "pipeline"


def scan(project: Path) -> tuple[list[Rec], list[Path]]:
    """作業フォルダの <パイプ>/state.json のうち、会話の道の記録を返す。壊れていて読めない会話の道の記録は別に返す。"""
    recs: list[Rec] = []
    broken: list[Path] = []
    base = work_base(project)
    try:
        files = sorted(base.glob(f"*/{STATE}"))
    except OSError:
        return recs, broken
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            if CHAT_DRIVER in text:
                broken.append(path)
            continue
        if isinstance(data, dict) and data.get("driver") == CHAT_DRIVER:
            recs.append(Rec(path.parent, data))
    return recs, broken


def resolve_pipe_dir(project: Path, value: Any) -> Path:
    """chat.pipe_dir（プロジェクトからの相対か絶対）を実際のフォルダにする。"""
    p = Path(str(value))
    return p if p.is_absolute() else project / p


# ---- 段の範囲 -------------------------------------------------------------------------------


def _only_own(can_write: Any, base: str, own: str) -> Any:
    def wrapped(rel: str) -> bool:
        if rel == base or rel.startswith(base + "/"):
            return rel == own and can_write(rel)
        return can_write(rel)

    return wrapped


def chat_specs(cfg: Config, pipe: PipeDef) -> dict[str, Any]:
    """段ごとの範囲。本体の build_pipe_specs が作ったものに、記録・.claude/・.git/・.pipe-in/・pipeline.toml を書けなくする。

    cfg は for_pipe 済み。記録のフォルダの親（docs/pipeline など）の下は、その段の成果物のほか書けない。
    """
    specs = build_pipe_specs(cfg, pipe)
    parent = cfg.work_dir.parent
    base = cfg.rel(parent if parent != cfg.project_dir else cfg.work_dir)
    work = cfg.rel(cfg.work_dir)
    for spec in specs.values():
        spec.can_write = _only_own(spec.can_write, base, f"{work}/{spec.output}")
        spec.write_scope_hint += "（記録・.claude/・パイプのフォルダは書けません）"
    return specs


# ---- フックの跡 -----------------------------------------------------------------------------


def append_trace(run_dir: Path, row: dict[str, Any]) -> None:
    d = run_dir / HOOK_DIR
    d.mkdir(parents=True, exist_ok=True)
    with (d / TRACE).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"v": 1, **row}, ensure_ascii=False) + "\n")


def read_trace(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / HOOK_DIR / TRACE
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def same_path(a: Any, b: Any) -> bool:
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


# ---- Bash の覚え ----------------------------------------------------------------------------


def load_bash_state(run_dir: Path, seq: Any, project: Path) -> BashState:
    """hook/bash_state.json から覚えを戻す。無い・段（seq）が違えば新しく作る。壊れていれば相対パスの書き込みを止める側（不明）にする。"""
    path = run_dir / HOOK_DIR / BASH_STATE
    if not path.is_file():
        return BashState.new(project)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("seq") != seq:
            return BashState.new(project)
        cwds = [Path(c) for c in data["cwds"] if isinstance(c, str)]
        return BashState(cwds, bool(data["cwd_unknown"]), bool(data["env_tainted"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        state = BashState.new(project)
        state.cwd_unknown = True
        return state


def save_bash_state(run_dir: Path, seq: Any, state: BashState) -> None:
    d = run_dir / HOOK_DIR
    d.mkdir(parents=True, exist_ok=True)
    data = {"seq": seq, "cwds": [str(c) for c in state.cwds], "cwd_unknown": state.cwd_unknown, "env_tainted": state.env_tainted}
    tmp = d / (BASH_STATE + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / BASH_STATE)
