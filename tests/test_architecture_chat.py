"""D0077-AC-35：会話の中でパイプを流す司会役のコードは SDK を読まず、依存の向きを守り、依存を増やさない。

新しいアーキテクチャの検査は、並列の作業でぶつからないよう、別のファイル（これ）に置く（docs/development/testing.md）。
空の形のファイル（pipe_in/pipe/chat.py など）は今は何も import しないので、ここは今のまま通る検査（守り続けるための検査）。
実装が SDK を読んだり、逆向きの import を足したりしたら落ちる。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 司会役のコード 4 つ：(ファイル, 読んでよい pipe_in の部品)
CHAT_FILES = {
    "pipe_in/pipe/chat.py": ("pipe_in.pipe", "pipe_in.engine", "pipe_in.usage"),
    "pipe_in/pipe/chat_record.py": ("pipe_in.pipe", "pipe_in.engine", "pipe_in.usage"),
    "generator/chat_cmd.py": ("pipe_in.pipe", "pipe_in.engine", "pipe_in.usage", "pipe_in_generator"),
    "generator/chat_hook.py": ("pipe_in.pipe", "pipe_in.engine", "pipe_in.usage", "pipe_in_generator"),
}
MODULES = {
    "pipe_in/pipe/chat.py": "pipe_in.pipe.chat",
    "pipe_in/pipe/chat_record.py": "pipe_in.pipe.chat_record",
    "generator/chat_cmd.py": "pipe_in_generator.chat_cmd",
    "generator/chat_hook.py": "pipe_in_generator.chat_hook",
}
FORBIDDEN_IMPORTS = ("claude_agent_sdk", "pipe_in.engine.runner", "subprocess", "pipe_in.dev", "pipe_in.cli", "pipe_in.legacy")
FORBIDDEN_NAMES = ("run_stage_sdk", "StageRunner", "claude_agent_sdk", "ClaudeSDKClient")


def imports_of(source: str, module: str, *, is_package: bool = False) -> list[str]:
    """import している名前（相対 import は絶対の名前に直す）。tests/test_architecture.py の _imports と同じ読み方。"""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
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


def violations(source: str, module: str, allowed: tuple[str, ...]) -> list[str]:
    """禁止の import・禁止の名前・読んでよい部品の外の pipe_in の import を、文の一覧で返す。"""
    out: list[str] = []
    for target in imports_of(source, module):
        if any(target == f or target.startswith(f + ".") for f in FORBIDDEN_IMPORTS):
            out.append(f"禁止の import: {target}")
        elif target.split(".")[0] in ("pipe_in", "pipe_in_generator") and not any(target == a or target.startswith(a + ".") for a in allowed):
            out.append(f"読んではいけない部品: {target}")
    out += [f"禁止の名前: {name}" for name in FORBIDDEN_NAMES if name in source]
    return out


@pytest.mark.parametrize("rel", sorted(CHAT_FILES))
def test_d0077_ac35_司会役のコードはSDKを読まず依存の向きを守る_守る(rel):
    """D0077-AC-35: chat.py・chat_record.py・chat_cmd.py・chat_hook.py は、claude_agent_sdk・engine.runner・subprocess を import せず、
    run_stage_sdk・StageRunner を使わず、pipe_in.engine / pipe_in.pipe の下の層だけを読む（今のまま通る。守る）。"""
    path = ROOT / rel
    assert path.is_file(), rel
    assert violations(path.read_text(encoding="utf-8"), MODULES[rel], CHAT_FILES[rel]) == []


def test_d0077_ac35_検査そのものが違反を見つけられる():
    """D0077-AC-35: 検査そのものが、SDK の import・subprocess・開発フローや入口への import・runner の名前を見つける。"""
    bad = (
        "import subprocess\n"
        "from claude_agent_sdk import ClaudeSDKClient\n"
        "from pipe_in.engine.runner import run_stage_sdk\n"
        "from pipe_in.dev import record\n"
        "from ..cli import main\n"
    )
    found = violations(bad, "pipe_in.pipe.chat", CHAT_FILES["pipe_in/pipe/chat.py"])
    text = "\n".join(found)
    for word in ["subprocess", "claude_agent_sdk", "pipe_in.engine.runner", "pipe_in.dev", "pipe_in.cli", "run_stage_sdk", "ClaudeSDKClient"]:
        assert word in text, f"{word} を見つけられない: {text}"
    assert violations("import json\nfrom pathlib import Path\nfrom ..engine.config import Config\n", "pipe_in.pipe.chat", CHAT_FILES["pipe_in/pipe/chat.py"]) == []


_PROBE_CODE = """
import importlib.util, sys
root, gen = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
try:
    import pipe_in_generator
except ImportError:
    spec = importlib.util.spec_from_file_location("pipe_in_generator", gen + "/__init__.py", submodule_search_locations=[gen])
    module = importlib.util.module_from_spec(spec)
    sys.modules["pipe_in_generator"] = module
    spec.loader.exec_module(module)
import pipe_in_generator.chat_cmd, pipe_in_generator.chat_hook
bad = sorted(n for n in sys.modules if n == "claude_agent_sdk" or n.startswith("claude_agent_sdk."))
print("SDK:" + ",".join(bad))
"""


def test_d0077_ac35_chat_cmdとchat_hookを読んでもSDKは読み込まれない_守る():
    """D0077-AC-35: 別のプロセスで pipe_in_generator.chat_cmd と chat_hook を import したあと、claude_agent_sdk が sys.modules に無い（今のまま通る。守る）。"""
    done = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE_CODE, str(ROOT), str(ROOT / "generator")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "SDK:", done.stdout


def test_d0077_ac35_依存は増えない_守る():
    """D0077-AC-35: pyproject.toml の依存と、vscode/package.json の依存が増えていない（今のまま通る。守る）。"""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dependencies"] == ["claude-agent-sdk>=0.2.159,<0.3"]
    assert pyproject["project"]["optional-dependencies"] == {"dev": ["pytest>=8"]}
    package = json.loads((ROOT / "vscode" / "package.json").read_text(encoding="utf-8"))
    assert "dependencies" not in package
    assert sorted(package["devDependencies"]) == ["@types/node", "@types/vscode", "@vscode/vsce", "esbuild", "typescript"]
