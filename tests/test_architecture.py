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
