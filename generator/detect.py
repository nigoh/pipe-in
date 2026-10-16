"""対象プロジェクトの環境（言語・テストのコマンド・フォルダの形）を、ファイルを見て推し量る。

パイプのひな形を埋めるのに使う。外へは問い合わせず、コマンドも実行しない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_CANDIDATES = ["src", "lib", "app", "pkg", "cmd", "internal"]
DOCS_CANDIDATES = ["docs", "doc", "spec", "specs", "documents"]
NOT_SOURCE = {"tests", "test", "docs", "doc", "examples", "build", "dist", "node_modules"}
NPM_PLACEHOLDER = "no test specified"


@dataclass
class Env:
    languages: list[str] = field(default_factory=list)
    test_command: str | None = None
    source_dirs: list[str] = field(default_factory=list)
    docs_dirs: list[str] = field(default_factory=list)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _python(project: Path) -> tuple[bool, bool]:
    """(Python のプロジェクトか, pytest を使っているか)"""
    files = [project / n for n in ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini")]
    files += sorted(project.glob("requirements*.txt"))
    present = [f for f in files if f.is_file()]
    is_python = any(f.name != "pytest.ini" and f.name != "tox.ini" for f in present)
    uses_pytest = (project / "conftest.py").is_file() or any("pytest" in _read(f) for f in present)
    return is_python or uses_pytest, uses_pytest


def _npm_test(project: Path) -> tuple[bool, bool]:
    """(Node のプロジェクトか, 本物の test スクリプトがあるか)"""
    path = project / "package.json"
    if not path.is_file():
        return False, False
    try:
        data = json.loads(_read(path) or "{}")
    except json.JSONDecodeError:
        return True, False
    scripts = data.get("scripts") if isinstance(data, dict) else None
    test = scripts.get("test") if isinstance(scripts, dict) else None
    return True, isinstance(test, str) and bool(test.strip()) and NPM_PLACEHOLDER not in test


def detect(project_dir: Path) -> Env:
    env = Env()
    is_python, uses_pytest = _python(project_dir)
    if is_python:
        env.languages.append("python")
        if uses_pytest:
            env.test_command = "pytest -q"
    is_node, has_npm_test = _npm_test(project_dir)
    if is_node:
        env.languages.append("node")
        if has_npm_test and env.test_command is None:
            env.test_command = "npm test"
    if (project_dir / "go.mod").is_file():
        env.languages.append("go")
        env.test_command = env.test_command or "go test ./..."
    if (project_dir / "Cargo.toml").is_file():
        env.languages.append("rust")
        env.test_command = env.test_command or "cargo test"

    env.source_dirs = [d for d in SOURCE_CANDIDATES if (project_dir / d).is_dir()]
    # 直下の Python のパッケージ（src/ を使わない形）
    if is_python:
        for d in sorted(p for p in project_dir.iterdir() if p.is_dir()):
            if d.name not in NOT_SOURCE and not d.name.startswith(".") and (d / "__init__.py").is_file():
                env.source_dirs.append(d.name)
    env.source_dirs = env.source_dirs or ["."]
    env.docs_dirs = [d for d in DOCS_CANDIDATES if (project_dir / d).is_dir()]
    return env
