"""インストールせずにテストを流せるよう、generator/ を pipe_in_generator として読み込めるようにする。

pip install -e . 済みなら、そちらを使う（pyproject.toml の package-dir で同じ名前に対応づけている）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generator"

# 入れ直していない worktree でも、この作業フォルダの pipe_in を読むように先頭に足す
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pipe_in_generator  # noqa: F401
except ImportError:
    if (GENERATOR / "__init__.py").is_file():
        spec = importlib.util.spec_from_file_location(
            "pipe_in_generator", GENERATOR / "__init__.py", submodule_search_locations=[str(GENERATOR)]
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["pipe_in_generator"] = module
        spec.loader.exec_module(module)


# ---- テストがリポジトリの実物を変えていないかの見張り（docs/development/testing.md） ----------
#
# テストは tmp_path の中だけに書く。リポジトリの pipes/・.pipe-in/・.devpipe/（前の版の置き場所）・docs/pipeline/ に書いたら、
# テストがすべて通っていても、最後に失敗にする（前に、テストが本物の pipes/ にパイプを作ったことがあるため）。

WATCHED = ("pipes", ".pipe-in", ".devpipe", "docs/pipeline")


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """見張るフォルダの中のファイル → （大きさ, 更新の時刻）。"""
    found: dict[str, tuple[int, int]] = {}
    for name in WATCHED:
        base = root / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                st = p.stat()
                found[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return found


def changes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    """足された・消された・変わったファイル。"""
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def pytest_sessionstart(session) -> None:
    session.config._pipe_in_watch = snapshot(ROOT)


def pytest_sessionfinish(session, exitstatus) -> None:
    before = getattr(session.config, "_pipe_in_watch", None)
    if before is None:
        return
    changed = changes(before, snapshot(ROOT))
    if changed:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        lines = "\n".join(f"  - {c}" for c in changed)
        message = f"テストがリポジトリの実物を変えました（tmp_path に書いてください）:\n{lines}"
        if reporter:
            reporter.write_line(message, red=True)
        session.exitstatus = 1
