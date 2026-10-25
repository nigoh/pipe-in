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


def test_judge_score_uses_only_stdlib():
    """D0022-AC-27: 審査の計算（pipe-in-gen judge-score）も、本体や SDK を読み込まない（標準ライブラリだけ）。"""
    import sys

    path = ROOT / "generator" / "judge_score.py"
    assert path.is_file()
    targets = {t.split(".")[0] for t in _imports(path, "pipe_in_generator.judge_score") if t}
    outside = sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")
    assert outside == []


def test_findings_check_uses_only_stdlib():
    """D0043-AC-22: 指摘の検査（pipe-in-gen findings-check）も、本体や SDK を読み込まない（標準ライブラリだけ）。"""
    import sys

    path = ROOT / "generator" / "findings_check.py"
    assert path.is_file()
    targets = {t.split(".")[0] for t in _imports(path, "pipe_in_generator.findings_check") if t}
    outside = sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")
    assert outside == []


def _outside_stdlib(path: Path, module: str) -> list[str]:
    import sys

    targets = {t.split(".")[0] for t in _imports(path, module) if t}
    return sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")


def test_judge_uses_only_stdlib():
    """D0028-AC-22: 検証の審査の計算（pipe_in/pipe/judge.py）は標準ライブラリだけ（definition.py など本体の他の部品も SDK も読まない）。"""
    path = ROOT / "pipe_in" / "pipe" / "judge.py"
    assert path.is_file()
    assert _outside_stdlib(path, "pipe_in.pipe.judge") == []


LIVE_ANSWER = "pipe_in.engine.live_answer"


def _pipe_in_parts(path: Path, module: str) -> list[str]:
    """path が読む pipe_in の部品（pipe_in・pipe_in.engine の枠そのものは除く）。"""
    return sorted({t for t in _imports(path, module) if t.split(".")[0] == "pipe_in" and t not in ("pipe_in", "pipe_in.engine")})


@pytest.mark.parametrize("name", ["live", "live_page"])
def test_d0027_ac70_live_modules_use_only_stdlib(name):
    """D0027-AC-70・D0039-AC-50: 進み具合の写し（live.py）とページ（live_page.py）は、標準ライブラリだけ（pipe_in の他の部品も SDK も読まない。互いにも読まない）。
    例外は live.py が識別子と段の形のために live_answer.py を読むことだけ（D0039）。"""
    path = ROOT / "pipe_in" / "engine" / f"{name}.py"
    assert path.is_file()
    outside = _outside_stdlib(path, f"pipe_in.engine.{name}")
    if name == "live":
        assert [t for t in _pipe_in_parts(path, "pipe_in.engine.live") if t != LIVE_ANSWER and not t.startswith(LIVE_ANSWER + ".")] == []
        outside = [t for t in outside if t != "pipe_in"]
    assert outside == []


def test_d0027_ac70_live_cmd_depends_only_on_config_and_the_live_parts():
    """D0027-AC-70・D0031-AC-52: コマンドの口（live_cmd.py）は、標準ライブラリと config.py と live・live_page・live_watch だけを読む（SDK・runner・dev・pipe を読まない）。"""
    path = ROOT / "pipe_in" / "engine" / "live_cmd.py"
    assert path.is_file()
    allowed = ("pipe_in.engine.config", "pipe_in.engine.live", "pipe_in.engine.live_answer", "pipe_in.engine.live_page", "pipe_in.engine.live_watch")
    found = [t for t in _imports(path, "pipe_in.engine.live_cmd") if t.split(".")[0] == "pipe_in" and t != "pipe_in.engine" and t != "pipe_in"]
    assert [t for t in found if not t.startswith(allowed)] == []
    outside = [t for t in _outside_stdlib(path, "pipe_in.engine.live_cmd") if t != "pipe_in"]
    assert outside == []


def test_d0027_ac70_cli_imports_live_cmd_inside_the_branch_only():
    """D0027-AC-70: cli.py は live_cmd を分岐の中で読む（record と同じ。cli を読み込んだだけでは live の部品を読み込まない）。分岐はある。"""
    source = (ROOT / "pipe_in" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top if "live" in ast.dump(n)]
    assert "live_cmd" in source and '"live"' in source, "cli.py に live の分岐がまだ無い"


def test_d0027_ac70_stdlib_check_finds_live_part_importing_siblings(tmp_path):
    """D0027-AC-70: 標準ライブラリの検査そのものが、live.py が別の部品（live_page・config・SDK）を読んだ場合を見つけられること。"""
    bad = tmp_path / "live.py"
    bad.write_text("import json\nfrom .live_page import build_page\nfrom .config import load_config\nimport claude_agent_sdk\n", encoding="utf-8")
    assert _outside_stdlib(bad, "pipe_in.engine.live") == ["claude_agent_sdk", "pipe_in"]


def test_stdlib_check_finds_outside_import(tmp_path):
    """D0022-AC-27: 標準ライブラリの検査そのものが、外の import（pipe_in・SDK）を見つけられること。"""
    import sys

    bad = tmp_path / "oops.py"
    bad.write_text("import json\nfrom pipe_in.engine import config\nimport claude_agent_sdk\n", encoding="utf-8")
    targets = {t.split(".")[0] for t in _imports(bad, "pipe_in_generator.oops") if t}
    outside = sorted(t for t in targets if t not in sys.stdlib_module_names and t != "__future__")
    assert outside == ["claude_agent_sdk", "pipe_in"]


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


# ---- D0031：見張り（live_watch.py）の依存 ---------------------------------------------------------------------------------

WATCH_NEVER = {"subprocess", "claude_agent_sdk", "anyio", "mcp", "multiprocessing"}


def _watch_violations(path: Path, module: str) -> list[str]:
    """live_watch が読んでよいのは、標準ライブラリと pipe_in.engine.live だけ。それ以外と、子プロセス・SDK を読むものを返す。"""
    found = _imports(path, module)
    bad = [t for t in found if t.split(".")[0] == "pipe_in" and t not in ("pipe_in", "pipe_in.engine", "pipe_in.engine.live")]
    bad += [t for t in _outside_stdlib(path, module) if t != "pipe_in"]
    bad += sorted({t for t in (x.split(".")[0] for x in found) if t in WATCH_NEVER})
    return sorted(set(bad))


def test_d0031_ac52_live_watch_uses_only_stdlib_and_live():
    """D0031-AC-52: 見張り（live_watch.py）は、標準ライブラリと pipe_in.engine.live だけを読む（config・pipeline・runner・live_page・live_cmd・SDK・子プロセスを読まない）。"""
    path = ROOT / "pipe_in" / "engine" / "live_watch.py"
    assert path.is_file()
    assert _watch_violations(path, "pipe_in.engine.live_watch") == []


def test_d0031_ac52_live_watch_check_finds_forbidden_imports(tmp_path):
    """D0031-AC-52: 見張りの検査そのものが、config・pipeline・live_page・live_cmd・subprocess・SDK を読んだ場合を見つけられること。"""
    bad = tmp_path / "live_watch.py"
    bad.write_text(
        "import json\nimport subprocess\nimport claude_agent_sdk\nfrom . import live\nfrom .config import load_config\n"
        "from .pipeline import Pipeline\nfrom .live_page import build_page\nfrom . import live_cmd\n",
        encoding="utf-8",
    )
    found = _watch_violations(bad, "pipe_in.engine.live_watch")
    for word in ("subprocess", "claude_agent_sdk", "pipe_in.engine.config", "pipe_in.engine.pipeline", "pipe_in.engine.live_page", "pipe_in.engine.live_cmd"):
        assert any(word in f for f in found), (word, found)
    assert not any(f.endswith("engine.live") for f in found), "live は読んでよい"


def test_d0031_ac52_live_and_live_page_do_not_read_live_watch():
    """D0031-AC-52: live.py・live_page.py は live_watch を読まない（写しとページは見張りを知らない。依存は live_cmd → live_watch → live の向き）。"""
    for name in ("live", "live_page"):
        path = ROOT / "pipe_in" / "engine" / f"{name}.py"
        assert not [t for t in _imports(path, f"pipe_in.engine.{name}") if "live_watch" in t], name


def test_d0031_ac52_live_cmd_may_read_live_watch():
    """D0031-AC-52: live_cmd.py は live_watch を読んでよく、実際に読んでいる（watch の下位コマンド）。cli.py は分岐の中で live_cmd を読むだけで live_watch を直接読まない。"""
    path = ROOT / "pipe_in" / "engine" / "live_cmd.py"
    assert "pipe_in.engine.live_watch" in _imports(path, "pipe_in.engine.live_cmd")
    cli = (ROOT / "pipe_in" / "cli.py").read_text(encoding="utf-8")
    assert "live_watch" not in cli


def test_d0031_ac52_dependencies_unchanged():
    """D0031-AC-52: 外部のパッケージの依存を足さない（pyproject.toml の dependencies が claude-agent-sdk だけ、extras は dev だけ）。今のままで通る（守り続ける検査）。"""
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["claude-agent-sdk>=0.2.159,<0.3"]
    assert set(project.get("optional-dependencies", {})) == {"dev"}


def test_d0031_ac52_live_watch_is_in_an_installed_package():
    """D0031-AC-52: 新しい .py は pipe_in.engine の中（packages に載っている）。package-data を増やさない。"""
    import tomllib

    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    assert "pipe_in.engine" in cfg["packages"]
    assert not any("live" in str(v) for v in cfg.get("package-data", {}).values())
    assert (ROOT / "pipe_in" / "engine" / "live_watch.py").is_file()


def test_d0036_ac26_bashwriteは標準ライブラリだけ():
    """D0036-AC-26: pipe_in/engine/bashwrite.py は標準ライブラリだけを読む（pipe_in.dev・pipe_in.pipe・pipe_in_generator・SDK を読まない）。"""
    path = ROOT / "pipe_in" / "engine" / "bashwrite.py"
    assert path.is_file(), "pipe_in/engine/bashwrite.py がまだ無い"
    assert _outside_stdlib(path, "pipe_in.engine.bashwrite") == []


def test_pipe_lint_imports_only_definition():
    """D0038-AC-12: 警告の部品（pipe_in/pipe/lint.py）は、標準ライブラリと pipe_in.pipe.definition のほかを読まない（pipe_in_generator も engine も読まない）。"""
    import sys

    path = ROOT / "pipe_in" / "pipe" / "lint.py"
    assert path.is_file(), "pipe_in/pipe/lint.py がありません（新しい部品をまだ作っていない）"
    targets = {t for t in _imports(path, "pipe_in.pipe.lint") if t}
    outside = sorted(
        t for t in targets if t.split(".")[0] not in sys.stdlib_module_names and t.split(".")[0] != "__future__" and not (t == "pipe_in.pipe.definition" or t.startswith("pipe_in.pipe.definition."))
    )
    assert outside == []


# ---- D0039：答えの文（live_answer.py）の依存 ----------------------------------------------------------------------------------

ANSWER_STDLIB = {"__future__", "hashlib", "json", "re", "typing", "unicodedata"}


def _answer_violations(path: Path, module: str) -> list[str]:
    """live_answer は葉：標準ライブラリのうち hashlib・json・re・typing・unicodedata だけを読み、pipe_in の部品も SDK も子プロセスも読まない。違反を返す。"""
    found = _imports(path, module)
    tops = {t.split(".")[0] for t in found if t}
    bad = [f"pipe_in の部品: {t}" for t in sorted(found) if t.split(".")[0] == "pipe_in"]
    bad += [f"許す一覧に無い: {t}" for t in sorted(tops) if t not in ANSWER_STDLIB and t != "pipe_in"]
    bad += [f"禁止: {t}" for t in sorted(tops) if t in WATCH_NEVER]
    return bad


def test_d0039_ac50_live_answer_uses_only_the_standard_library():
    """D0039-AC-50: live_answer.py は標準ライブラリ（hashlib・re・json・unicodedata・typing）だけ。pipe_in のほかの部品・SDK・子プロセスを読まない（葉）。"""
    path = ROOT / "pipe_in" / "engine" / "live_answer.py"
    assert path.is_file()
    assert _outside_stdlib(path, "pipe_in.engine.live_answer") == []
    assert _answer_violations(path, "pipe_in.engine.live_answer") == []


def test_d0039_ac50_live_answer_check_finds_forbidden_imports(tmp_path):
    """D0039-AC-50: live_answer の依存の検査そのものが、pipe_in の部品・SDK・子プロセス・一覧に無い標準ライブラリを読んだ場合を見つけられること。"""
    bad = tmp_path / "live_answer.py"
    bad.write_text(
        "import hashlib\nimport subprocess\nimport claude_agent_sdk\nimport os\nfrom . import live\nfrom .config import load_config\nfrom pipe_in.dev import record\n",
        encoding="utf-8",
    )
    found = " ".join(_answer_violations(bad, "pipe_in.engine.live_answer"))
    for word in ("subprocess", "claude_agent_sdk", "os", "pipe_in.engine.live", "pipe_in.engine.config", "pipe_in.dev"):
        assert word in found, (word, found)
    good = tmp_path / "ok.py"
    good.write_text("from __future__ import annotations\nimport hashlib\nimport json\nimport re\nimport unicodedata\nfrom typing import Any, NamedTuple\n", encoding="utf-8")
    assert _answer_violations(good, "pipe_in.engine.live_answer") == []


def test_d0039_ac50_live_may_read_live_answer_only():
    """D0039-AC-50: live.py が読んでよい pipe_in の部品は live_answer だけ（識別子と段の形のため）。実際に読んでいる（識別子を自分で作らない）。"""
    path = ROOT / "pipe_in" / "engine" / "live.py"
    parts = _pipe_in_parts(path, "pipe_in.engine.live")
    assert parts, "live.py が live_answer を読んでいない"
    assert all(t == LIVE_ANSWER or t.startswith(LIVE_ANSWER + ".") for t in parts), parts


def test_d0039_ac50_live_cmd_may_read_live_answer():
    """D0039-AC-50: live_cmd.py は live_answer を読んでよく、実際に読んでいる（answer の下位コマンド）。cli.py は live_answer を直接読まない。"""
    path = ROOT / "pipe_in" / "engine" / "live_cmd.py"
    assert LIVE_ANSWER in _imports(path, "pipe_in.engine.live_cmd")
    assert "live_answer" not in (ROOT / "pipe_in" / "cli.py").read_text(encoding="utf-8")


def test_d0039_ac50_live_page_and_live_watch_do_not_read_live_answer():
    """D0039-AC-50: live_page.py・live_watch.py は live_answer を読まない（ページは何も読まず、見張りは live だけ）。"""
    for name in ("live_page", "live_watch"):
        path = ROOT / "pipe_in" / "engine" / f"{name}.py"
        assert not [t for t in _imports(path, f"pipe_in.engine.{name}") if "live_answer" in t], name


def test_d0039_ac50_record_does_not_read_live_answer():
    """D0039-AC-50: pipe_in/dev/record.py（--feedback-file）は live_answer を読まない（dev の中で完結する。上限の数字は record.py に持つ）。"""
    path = ROOT / "pipe_in" / "dev" / "record.py"
    assert not [t for t in _imports(path, "pipe_in.dev.record") if "live_answer" in t or t.startswith("pipe_in.engine.live")]
    assert "RECORD_FEEDBACK_LIMIT" in path.read_text(encoding="utf-8")


def test_d0039_ac50_nothing_in_engine_imports_dev():
    """D0039-AC-50: pipe_in/engine/ の新しいコードを含め、engine から dev・pipe・generator を読まない（依存の向き）。"""
    assert _violations("pipe_in/engine", "pipe_in.engine", ["pipe_in.dev", "pipe_in.pipe", "pipe_in_generator"]) == []
    assert (ROOT / "pipe_in" / "engine" / "live_answer.py").is_file()


def test_d0039_ac50_dependencies_are_unchanged():
    """D0039-AC-50: 外部のパッケージの依存を足さない（dependencies が claude-agent-sdk だけ、extras は dev だけ）。今のままで通る（守り続ける検査）。"""
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["claude-agent-sdk>=0.2.159,<0.3"]
    assert set(project.get("optional-dependencies", {})) == {"dev"}


def test_d0039_ac29_live_answer_live_and_live_cmd_start_no_child_process_and_use_no_sdk():
    """D0039-AC-29: live_answer.py・live.py・live_cmd.py は subprocess・SDK・multiprocessing を読まず、os.system / Popen / fork を呼ばない（ソースの検査）。"""
    for name in ("live_answer", "live", "live_cmd"):
        path = ROOT / "pipe_in" / "engine" / f"{name}.py"
        assert path.is_file(), name
        found = _imports(path, f"pipe_in.engine.{name}")
        assert not {t for t in (x.split(".")[0] for x in found) if t in WATCH_NEVER}, name
        source = path.read_text(encoding="utf-8")
        for word in ("os.system", "Popen", "os.fork", "os.exec", "posix_spawn", "create_subprocess", "claude_agent_sdk"):
            assert word not in source, (name, word)


def test_d0039_ac29_live_answer_is_in_an_installed_package():
    """D0039-AC-29: 新しい .py は pipe_in.engine の中（packages に載っている）。package-data を増やさない。"""
    import tomllib

    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    assert "pipe_in.engine" in cfg["packages"]
    assert (ROOT / "pipe_in" / "engine" / "live_answer.py").is_file()
