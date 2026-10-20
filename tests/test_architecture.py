"""依存の向きの検査：pipe_in_generator → pipe_in.pipe → pipe_in.engine → pipe_in.usage（pipe_in.dev → pipe_in.engine）。

逆向きの import があると落ちる。共通の仕組み（engine）が、特定のパイプや入口を知らないようにするため。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# (フォルダ, そのフォルダの Python の名前, import してはいけないもの)
RULES = [
    ("pipe_in/usage", "pipe_in.usage", ["pipe_in.engine", "pipe_in.dev", "pipe_in.pipe", "pipe_in.cli", "pipe_in.legacy", "pipe_in_generator"]),
    ("pipe_in/engine", "pipe_in.engine", ["pipe_in.dev", "pipe_in.pipe", "pipe_in.cli", "pipe_in.legacy", "pipe_in_generator"]),
    ("pipe_in/dev", "pipe_in.dev", ["pipe_in.pipe", "pipe_in.cli", "pipe_in.legacy", "pipe_in_generator"]),
    ("pipe_in/pipe", "pipe_in.pipe", ["pipe_in.dev", "pipe_in.cli", "pipe_in.legacy", "pipe_in_generator"]),
    ("pipe_in", "pipe_in", ["pipe_in_generator"]),
    # design が段を1つ流すため、ジェネレーターは engine を使ってよい（入口と開発フローには頼らない）
    ("generator", "pipe_in_generator", ["pipe_in.cli", "pipe_in.legacy", "pipe_in.dev"]),
]


def _module_name(path: Path, folder: Path, package: str) -> str:
    rel = path.relative_to(folder).with_suffix("")
    parts = [package, *rel.parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path, module: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    is_package = path.name == "__init__.py"
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module.split(".")
                base = base if is_package else base[:-1]
                base = base[: len(base) - (node.level - 1)]
                target = ".".join([*base, node.module] if node.module else base)
            else:
                target = node.module or ""
            found.append(target)
            found += [f"{target}.{a.name}" for a in node.names]
    return found


def _violations(folder: str, package: str, forbidden: list[str]) -> list[str]:
    base = ROOT / folder
    out: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_name(path, base, package)
        for target in _imports(path, module):
            for f in forbidden:
                if target == f or target.startswith(f + "."):
                    out.append(f"{path.relative_to(ROOT).as_posix()} → {target}")
    return sorted(set(out))


@pytest.mark.parametrize("folder,package,forbidden", RULES, ids=[r[0] for r in RULES])
def test_dependency_direction(folder, package, forbidden):
    assert (ROOT / folder).is_dir(), folder
    assert _violations(folder, package, forbidden) == []


def test_rule_catches_reverse_import(tmp_path, monkeypatch):
    """検査そのものが逆向きの import を見つけられること。"""
    bad = tmp_path / "pipe_in" / "engine"
    bad.mkdir(parents=True)
    (bad / "__init__.py").write_text("", encoding="utf-8")
    (bad / "oops.py").write_text("from ..dev import specs\nfrom pipe_in.pipe.pipeline import LinearPipeline\n", encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    found = _violations("pipe_in/engine", "pipe_in.engine", ["pipe_in.dev", "pipe_in.pipe"])
    assert any("pipe_in.dev" in f for f in found) and any("pipe_in.pipe" in f for f in found)


def test_d0019_ac50_state_only_adds_keys(tmp_path):
    """D0019-AC-50: 新しい項目（name・session_id・runs[].agent）を全部付けて書いた state.json は、見本（古い形）の鍵をすべて含み、
    増えるのは name・session_id・runs[].agent だけ（既存の項目の名前・意味を変えない）。"""
    import json
    from datetime import datetime

    from pipe_in.dev.record import Recorder
    from pipe_in.engine.config import load_config

    fixtures = ROOT / "tests" / "fixtures" / "pipe_dev"
    old = json.loads((fixtures / "finished" / "state.json").read_text(encoding="utf-8"))

    r = Recorder(load_config(tmp_path), now=lambda: datetime(2026, 10, 17, 10, 0, 0))
    r.start("足したい機能のメモ", name="N", session_id="S-1")
    r.begin("requirements", agent="pipe-in-analyst")
    r.done("requirements", summary="要件定義を書いた")
    r.wait("requirements")
    r.review("requirements", "revise", feedback="AC を分けて")
    r.begin("requirements", note="指摘を反映", agent="pipe-in-analyst")
    r.done("requirements", summary="直した")
    r.wait("requirements")
    r.review("requirements", "approved")
    r.begin("design", agent="pipe-in-analyst")
    r.done("design", summary="設計を書いた")
    r.wait("design")
    r.review("design", "approved")
    r.begin("red", agent="pipe-in-tester")
    r.done("red", summary="テストを書いた")
    r.red("red", "AC-01 が赤", tests=[("AC-01", "tests/test_a.py::test_a")], commands=["python -m pytest -q"])
    r.wait("red")
    r.review("red", "approved")
    r.begin("implement", attempt=1, agent="pipe-in-coder")
    r.done("implement", summary="実装した")
    r.begin("test", attempt=1, agent="pipe-in-verifier")
    r.done("test", summary="検証した")
    r.verdict("fail", 1, "AC-01 不合格", failures=[("AC-01", "期待と違う")], commands=["python -m pytest -q"])
    r.begin("implement", attempt=2, note="差し戻し", agent="pipe-in-coder")
    r.done("implement", summary="直した")
    r.begin("test", attempt=2, agent="pipe-in-verifier")
    r.done("test", summary="検証した")
    r.verdict("pass", 2, "すべて合格", commands=["python -m pytest -q"])
    r.finish("PASSED")

    new = json.loads((tmp_path / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))
    assert set(old) <= set(new)
    assert set(new) - set(old) == {"name", "session_id"}
    old_run_keys = {k for run in old["runs"] for k in run}
    new_run_keys = {k for run in new["runs"] for k in run}
    assert old_run_keys <= new_run_keys
    assert new_run_keys - old_run_keys == {"agent"}
    for key in set(old) - {"started_at", "updated_at", "runs", "name"}:
        assert type(new[key]) is type(old[key]) or old[key] is None or new[key] is None, key  # 既存の項目の型を変えていない
    assert [s["name"] for s in new["stages"]] == [s["name"] for s in old["stages"]]


def test_guard_hook_uses_only_stdlib():
    """D0001-AC-19・D0006-AC-03: フックは道具を呼ぶたびに動くので、pipe_in や SDK を読み込まない（標準ライブラリだけ）。"""
    import sys

    path = ROOT / "generator" / "guard_hook.py"
    assert path.is_file()
    targets = {t.split(".")[0] for t in _imports(path, "pipe_in_generator.guard_hook") if t}
    outside = sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")
    assert outside == []


# ---- D0006-AC-03: 古い名前を import しない ------------------------------------------------

OLD_MODULES = ("devpipe", "devpipe_generator")
SOURCES = [("pipe_in", "pipe_in"), ("generator", "pipe_in_generator"), ("tests", "tests")]


def _old_imports(folder: str, package: str) -> list[str]:
    base = ROOT / folder
    out: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for target in _imports(path, _module_name(path, base, package)):
            if any(target == m or target.startswith(m + ".") for m in OLD_MODULES):
                out.append(f"{path.relative_to(ROOT).as_posix()} → {target}")
    return sorted(set(out))


@pytest.mark.parametrize("folder,package", SOURCES, ids=[s[0] for s in SOURCES])
def test_nothing_imports_old_names(folder, package):
    """D0006-AC-03: pipe_in/・generator/・tests/ のどれも、古いパッケージの名前を import しない。"""
    assert (ROOT / folder).is_dir(), folder
    assert _old_imports(folder, package) == []


def test_old_import_check_finds_old_names(tmp_path, monkeypatch):
    """D0006-AC-03: 検査そのものが、古い名前の import を見つけられること。"""
    bad = tmp_path / "pipe_in"
    bad.mkdir()
    (bad / "oops.py").write_text("import devpipe.cli\nfrom devpipe_generator import guard_hook\n", encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    found = _old_imports("pipe_in", "pipe_in")
    assert any("devpipe.cli" in f for f in found) and any("devpipe_generator" in f for f in found)


def test_legacy_is_not_imported_from_lower_layers(tmp_path, monkeypatch):
    """D0006-AC-03: 別名の入口（pipe_in.legacy）を下の層から読むと、依存の向きの検査が見つける。"""
    bad = tmp_path / "pipe_in" / "engine"
    bad.mkdir(parents=True)
    (bad / "oops.py").write_text("from ..legacy import NOTICE\n", encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    forbidden = dict((r[0], r[2]) for r in RULES)["pipe_in/engine"]
    assert any("pipe_in.legacy" in f for f in _violations("pipe_in/engine", "pipe_in.engine", forbidden))
