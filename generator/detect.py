"""対象プロジェクトの環境（言語・テストのコマンド・フォルダの形）を、ファイルを見て推し量る。

パイプのひな形を埋めるのに使う。外へは問い合わせず、コマンドも実行しない。
テストのコマンドは、最初に見つかったものを使う（Python → Node → Go → Rust → Java → Ruby → PHP → .NET → Deno → Makefile）。
"""

from __future__ import annotations

import json
import re
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


def _json(path: Path) -> dict:
    try:
        data = json.loads(_read(path) or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _script(data: dict, name: str) -> str | None:
    scripts = data.get("scripts")
    value = scripts.get(name) if isinstance(scripts, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _python(p: Path) -> tuple[bool, str | None]:
    files = [p / n for n in ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini")]
    files += sorted(p.glob("requirements*.txt"))
    present = [f for f in files if f.is_file()]
    is_python = any(f.name not in ("pytest.ini", "tox.ini") for f in present)
    uses_pytest = (p / "conftest.py").is_file() or any("pytest" in _read(f) for f in present)
    if not uses_pytest:
        return is_python, None
    if (p / "uv.lock").is_file():
        return True, "uv run pytest -q"
    if (p / "poetry.lock").is_file():
        return True, "poetry run pytest -q"
    return True, "pytest -q"


def _node(p: Path) -> tuple[bool, str | None]:
    pkg = p / "package.json"
    if not pkg.is_file():
        return False, None
    test = _script(_json(pkg), "test")
    if not test or NPM_PLACEHOLDER in test:
        return True, None
    for lock, tool in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
        if (p / lock).is_file():
            return True, f"{tool} test"
    return True, "npm test"


def _java(p: Path) -> tuple[bool, str | None]:
    if (p / "pom.xml").is_file():
        return True, "./mvnw -q test" if (p / "mvnw").is_file() else "mvn -q test"
    if (p / "build.gradle").is_file() or (p / "build.gradle.kts").is_file():
        return True, "./gradlew test" if (p / "gradlew").is_file() else "gradle test"
    return False, None


def _ruby(p: Path) -> tuple[bool, str | None]:
    if not (p / "Gemfile").is_file():
        return False, None
    return True, "bundle exec rspec" if (p / "spec").is_dir() or (p / ".rspec").is_file() else "bundle exec rake test"


def _php(p: Path) -> tuple[bool, str | None]:
    if not (p / "composer.json").is_file():
        return False, None
    if _script(_json(p / "composer.json"), "test"):
        return True, "composer test"
    if (p / "phpunit.xml").is_file() or (p / "phpunit.xml.dist").is_file():
        return True, "vendor/bin/phpunit"
    return True, None


def _dotnet(p: Path) -> tuple[bool, str | None]:
    found = any(p.glob("*.sln")) or any(p.glob("*.csproj")) or any(p.glob("*.fsproj"))
    return (True, "dotnet test") if found else (False, None)


def _deno(p: Path) -> tuple[bool, str | None]:
    found = (p / "deno.json").is_file() or (p / "deno.jsonc").is_file()
    return (True, "deno test") if found else (False, None)


def _make(p: Path) -> str | None:
    text = _read(p / "Makefile")
    return "make test" if re.search(r"^test\s*:", text, re.MULTILINE) else None


def detect(project_dir: Path) -> Env:
    env = Env()
    probes = [
        ("python", _python),
        ("node", _node),
        ("go", lambda p: ((p / "go.mod").is_file(), "go test ./..." if (p / "go.mod").is_file() else None)),
        ("rust", lambda p: ((p / "Cargo.toml").is_file(), "cargo test" if (p / "Cargo.toml").is_file() else None)),
        ("java", _java),
        ("ruby", _ruby),
        ("php", _php),
        ("dotnet", _dotnet),
        ("deno", _deno),
    ]
    for language, probe in probes:
        found, command = probe(project_dir)
        if found:
            env.languages.append(language)
            env.test_command = env.test_command or command
    env.test_command = env.test_command or _make(project_dir)

    env.source_dirs = [d for d in SOURCE_CANDIDATES if (project_dir / d).is_dir()]
    # 直下の Python のパッケージ（src/ を使わない形）
    if "python" in env.languages:
        for d in sorted(p for p in project_dir.iterdir() if p.is_dir()):
            if d.name not in NOT_SOURCE and not d.name.startswith(".") and (d / "__init__.py").is_file():
                env.source_dirs.append(d.name)
    env.source_dirs = env.source_dirs or ["."]
    env.docs_dirs = [d for d in DOCS_CANDIDATES if (project_dir / d).is_dir()]
    return env
