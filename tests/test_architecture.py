"""依存の向きの検査：devpipe_generator → devpipe.pipe → devpipe.engine → devpipe.usage（devpipe.dev → devpipe.engine）。

逆向きの import があると落ちる。共通の仕組み（engine）が、特定のパイプや入口を知らないようにするため。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# (フォルダ, そのフォルダの Python の名前, import してはいけないもの)
RULES = [
    ("devpipe/usage", "devpipe.usage", ["devpipe.engine", "devpipe.dev", "devpipe.pipe", "devpipe.cli", "devpipe_generator"]),
    ("devpipe/engine", "devpipe.engine", ["devpipe.dev", "devpipe.pipe", "devpipe.cli", "devpipe_generator"]),
    ("devpipe/dev", "devpipe.dev", ["devpipe.pipe", "devpipe.cli", "devpipe_generator"]),
    ("devpipe/pipe", "devpipe.pipe", ["devpipe.dev", "devpipe.cli", "devpipe_generator"]),
    ("devpipe", "devpipe", ["devpipe_generator"]),
    # design が段を1つ流すため、ジェネレーターは engine を使ってよい（入口と開発フローには頼らない）
    ("generator", "devpipe_generator", ["devpipe.cli", "devpipe.dev"]),
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
    bad = tmp_path / "devpipe" / "engine"
    bad.mkdir(parents=True)
    (bad / "__init__.py").write_text("", encoding="utf-8")
    (bad / "oops.py").write_text("from ..dev import specs\nfrom devpipe.pipe.pipeline import LinearPipeline\n", encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    found = _violations("devpipe/engine", "devpipe.engine", ["devpipe.dev", "devpipe.pipe"])
    assert any("devpipe.dev" in f for f in found) and any("devpipe.pipe" in f for f in found)


def test_guard_hook_uses_only_stdlib():
    """AC-19: フックは道具を呼ぶたびに動くので、devpipe や SDK を読み込まない（標準ライブラリだけ）。"""
    import sys

    path = ROOT / "generator" / "guard_hook.py"
    assert path.is_file()
    targets = {t.split(".")[0] for t in _imports(path, "devpipe_generator.guard_hook") if t}
    outside = sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")
    assert outside == []
