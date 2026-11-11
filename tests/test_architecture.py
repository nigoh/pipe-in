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
    増えるのは name・session_id・runs[].agent だけ（既存の項目の名前・意味を変えない）。D0071: review の要素の runs[].at も足された。"""
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
    assert set(new) - set(old) == {"name", "schema", "session_id"}  # D0080: 新しい記録に schema を足した
    old_run_keys = {k for run in old["runs"] for k in run}
    new_run_keys = {k for run in new["runs"] for k in run}
    assert old_run_keys - new_run_keys == {"metrics"}  # D0080: 取れない記録は metrics の鍵を書かない
    assert new_run_keys - old_run_keys == {"agent", "at"}  # D0071: review の要素に at を足した
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
    """D0027-AC-70・D0044-AC-50: 進み具合の写し（live.py）とページ（live_page.py）は、標準ライブラリだけ（pipe_in の他の部品も SDK も読まない。互いにも読まない）。
    例外は live.py が識別子と段の形のために live_answer.py を読むことだけ（D0044）。"""
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
    """D0038-AC-12: 警告の部品（pipe_in/pipe/lint.py）は、標準ライブラリと pipe_in.pipe.definition と pipe_in.engine.spec（既定で守る場所の定数。D0084）のほかを読まない（pipe_in_generator も、engine のほかの部品も読まない）。"""
    import sys

    path = ROOT / "pipe_in" / "pipe" / "lint.py"
    assert path.is_file(), "pipe_in/pipe/lint.py がありません（新しい部品をまだ作っていない）"
    targets = {t for t in _imports(path, "pipe_in.pipe.lint") if t}
    outside = sorted(
        t for t in targets if t.split(".")[0] not in sys.stdlib_module_names and t.split(".")[0] != "__future__" and not (t == "pipe_in.pipe.definition" or t.startswith("pipe_in.pipe.definition.") or t == "pipe_in.engine.spec" or t.startswith("pipe_in.engine.spec."))
    )
    assert outside == []


def test_d0082_ac11_capabilityは標準ライブラリだけ():
    """D0082-AC-11: 会話の道の能力表（pipe_in/pipe/capability.py）は、標準ライブラリだけを読む（definition・config・SDK も読まない）。依存の向きは test_dependency_direction が見る。"""
    path = ROOT / "pipe_in" / "pipe" / "capability.py"
    assert path.is_file(), "pipe_in/pipe/capability.py がありません"
    assert _outside_stdlib(path, "pipe_in.pipe.capability") == []


# ---- D0044：答えの文（live_answer.py）の依存 ----------------------------------------------------------------------------------

ANSWER_STDLIB = {"__future__", "hashlib", "json", "re", "typing", "unicodedata"}


def _answer_violations(path: Path, module: str) -> list[str]:
    """live_answer は葉：標準ライブラリのうち hashlib・json・re・typing・unicodedata だけを読み、pipe_in の部品も SDK も子プロセスも読まない。違反を返す。"""
    found = _imports(path, module)
    tops = {t.split(".")[0] for t in found if t}
    bad = [f"pipe_in の部品: {t}" for t in sorted(found) if t.split(".")[0] == "pipe_in"]
    bad += [f"許す一覧に無い: {t}" for t in sorted(tops) if t not in ANSWER_STDLIB and t != "pipe_in"]
    bad += [f"禁止: {t}" for t in sorted(tops) if t in WATCH_NEVER]
    return bad


def test_d0044_ac50_live_answer_uses_only_the_standard_library():
    """D0044-AC-50: live_answer.py は標準ライブラリ（hashlib・re・json・unicodedata・typing）だけ。pipe_in のほかの部品・SDK・子プロセスを読まない（葉）。"""
    path = ROOT / "pipe_in" / "engine" / "live_answer.py"
    assert path.is_file()
    assert _outside_stdlib(path, "pipe_in.engine.live_answer") == []
    assert _answer_violations(path, "pipe_in.engine.live_answer") == []


def test_d0044_ac50_live_answer_check_finds_forbidden_imports(tmp_path):
    """D0044-AC-50: live_answer の依存の検査そのものが、pipe_in の部品・SDK・子プロセス・一覧に無い標準ライブラリを読んだ場合を見つけられること。"""
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


def test_d0044_ac50_live_may_read_live_answer_only():
    """D0044-AC-50: live.py が読んでよい pipe_in の部品は live_answer だけ（識別子と段の形のため）。実際に読んでいる（識別子を自分で作らない）。"""
    path = ROOT / "pipe_in" / "engine" / "live.py"
    parts = _pipe_in_parts(path, "pipe_in.engine.live")
    assert parts, "live.py が live_answer を読んでいない"
    assert all(t == LIVE_ANSWER or t.startswith(LIVE_ANSWER + ".") for t in parts), parts


def test_d0044_ac50_live_cmd_may_read_live_answer():
    """D0044-AC-50: live_cmd.py は live_answer を読んでよく、実際に読んでいる（answer の下位コマンド）。cli.py は live_answer を直接読まない。"""
    path = ROOT / "pipe_in" / "engine" / "live_cmd.py"
    assert LIVE_ANSWER in _imports(path, "pipe_in.engine.live_cmd")
    assert "live_answer" not in (ROOT / "pipe_in" / "cli.py").read_text(encoding="utf-8")


def test_d0044_ac50_live_page_and_live_watch_do_not_read_live_answer():
    """D0044-AC-50: live_page.py・live_watch.py は live_answer を読まない（ページは何も読まず、見張りは live だけ）。"""
    for name in ("live_page", "live_watch"):
        path = ROOT / "pipe_in" / "engine" / f"{name}.py"
        assert not [t for t in _imports(path, f"pipe_in.engine.{name}") if "live_answer" in t], name


def test_d0044_ac50_record_does_not_read_live_answer():
    """D0044-AC-50: pipe_in/dev/record.py（--feedback-file）は live_answer を読まない（dev の中で完結する。上限の数字は record.py に持つ）。"""
    path = ROOT / "pipe_in" / "dev" / "record.py"
    assert not [t for t in _imports(path, "pipe_in.dev.record") if "live_answer" in t or t.startswith("pipe_in.engine.live")]
    assert "RECORD_FEEDBACK_LIMIT" in path.read_text(encoding="utf-8")


def test_d0044_ac50_nothing_in_engine_imports_dev():
    """D0044-AC-50: pipe_in/engine/ の新しいコードを含め、engine から dev・pipe・generator を読まない（依存の向き）。"""
    assert _violations("pipe_in/engine", "pipe_in.engine", ["pipe_in.dev", "pipe_in.pipe", "pipe_in_generator"]) == []
    assert (ROOT / "pipe_in" / "engine" / "live_answer.py").is_file()


def test_d0044_ac50_dependencies_are_unchanged():
    """D0044-AC-50: 外部のパッケージの依存を足さない（dependencies が claude-agent-sdk だけ、extras は dev だけ）。今のままで通る（守り続ける検査）。"""
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["claude-agent-sdk>=0.2.159,<0.3"]
    assert set(project.get("optional-dependencies", {})) == {"dev"}


def test_d0044_ac29_live_answer_live_and_live_cmd_start_no_child_process_and_use_no_sdk():
    """D0044-AC-29: live_answer.py・live.py・live_cmd.py は subprocess・SDK・multiprocessing を読まず、os.system / Popen / fork を呼ばない（ソースの検査）。"""
    for name in ("live_answer", "live", "live_cmd"):
        path = ROOT / "pipe_in" / "engine" / f"{name}.py"
        assert path.is_file(), name
        found = _imports(path, f"pipe_in.engine.{name}")
        assert not {t for t in (x.split(".")[0] for x in found) if t in WATCH_NEVER}, name
        source = path.read_text(encoding="utf-8")
        for word in ("os.system", "Popen", "os.fork", "os.exec", "posix_spawn", "create_subprocess", "claude_agent_sdk"):
            assert word not in source, (name, word)


def test_d0044_ac29_live_answer_is_in_an_installed_package():
    """D0044-AC-29: 新しい .py は pipe_in.engine の中（packages に載っている）。package-data を増やさない。"""
    import tomllib

    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    assert "pipe_in.engine" in cfg["packages"]
    assert (ROOT / "pipe_in" / "engine" / "live_answer.py").is_file()


# ---- D0066：流す前の費用の目安の部品は、読むだけで書かず、guard に触れない ----------------------------------------

ESTIMATE_PARTS = ["pipe_in/usage/prices.py", "pipe_in/usage/estimate.py", "pipe_in/estimate_cmd.py"]
WRITE_CALLS = [
    r"\bwrite_text\b",
    r"\bwrite_bytes\b",
    r"\bopen\([^)]*['\"][wax+]",
    r"\bmkdir\b",
    r"\bmakedirs\b",
    r"\bunlink\b",
    r"\brmtree\b",
    r"\bshutil\b",
    r"\bsubprocess\b",
    r"\bclaude_agent_sdk\b",
    r"\.touch\(",
    r"\brename\(",
]


def estimate_part_problems(rel: str, source: str) -> list[str]:
    """書き込み・子プロセス・SDK の呼び出しと、guard の読み込みがあれば、その文。コメント行は見ない。"""
    import re

    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    problems = [f"{rel}: {pat}" for pat in WRITE_CALLS if re.search(pat, code)]
    for node in ast.walk(ast.parse(source)):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        names += [a.name for a in node.names] if isinstance(node, ast.ImportFrom) else []
        problems += [f"{rel}: guard を読んでいる（{n}）" for n in names if "guard" in n.split(".")[-1]]
    return problems


def test_d0066_ac12_目安の部品のソースに書き込みと子プロセスが無い():
    """D0066-AC-12: 目安の 3 つの部品（usage/prices.py・usage/estimate.py・estimate_cmd.py）のソースに、書き込みの呼び出し（write_text・
    open(…, "w")・mkdir・makedirs・unlink・subprocess・claude_agent_sdk など）が無い。estimate は読むだけ。"""
    problems: list[str] = []
    for rel in ESTIMATE_PARTS:
        path = ROOT / rel
        assert path.is_file(), f"{rel} が無い（まだ作っていない）"
        problems += estimate_part_problems(rel, path.read_text(encoding="utf-8"))
    assert problems == []


def test_d0066_ac28_目安の部品はguardを読まず書き込み先を持たない():
    """D0066-AC-28: 目安の 3 つの部品は、guard（engine/guard.py・generator/guard_hook.py）を import しない。止める範囲は変わらない
    （3 つの guard のファイル自体を変えていないことは、検証の段で git diff で確かめる）。"""
    for rel in ESTIMATE_PARTS:
        path = ROOT / rel
        assert path.is_file(), f"{rel} が無い（まだ作っていない）"
        assert [p for p in estimate_part_problems(rel, path.read_text(encoding="utf-8")) if "guard" in p] == []


def test_d0066_ac12_検査そのものが書き込みと子プロセスとguardの読み込みを見つける_守る():
    """D0066-AC-12: 検査そのもの：書き込み・子プロセス・SDK・guard の読み込みを含む見本は見つけ、読むだけの見本・コメントの行は見逃す（今のまま通る。守る）。"""
    bad = [
        "p.write_text('x')",
        "open(path, 'w')",
        "open(path, mode='a')",
        "p.mkdir(parents=True)",
        "import os\nos.makedirs(d)",
        "p.unlink()",
        "import subprocess",
        "import claude_agent_sdk",
        "from .engine.guard import check_write",
        "from .engine import guard",
    ]
    for src in bad:
        assert estimate_part_problems("x.py", src), src
    ok = ["data = p.read_text()", "open(path)", "open(path, 'r')", "# p.write_text('x') は使わない\nx = 1", "from .metrics import summarize_runs"]
    for src in ok:
        assert estimate_part_problems("x.py", src) == [], src


def test_d0066_ac12_usageの目安の部品は標準ライブラリとusageの中だけを読む():
    """D0066-AC-12: usage/prices.py・usage/estimate.py は、標準ライブラリと usage の中（.prices・.metrics）だけを import する（一番下の層。
    engine・dev・pipe は読まない）。"""
    import sys

    for rel in ["pipe_in/usage/prices.py", "pipe_in/usage/estimate.py"]:
        path = ROOT / rel
        assert path.is_file(), f"{rel} が無い（まだ作っていない）"
        outside: list[str] = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                outside += [a.name for a in node.names if a.name.split(".")[0] not in sys.stdlib_module_names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    if (node.module or "").split(".")[0] not in sys.stdlib_module_names:
                        outside.append(node.module or "")
                elif node.level == 1 and (node.module or "") not in {"prices", "metrics"}:
                    outside.append("." + (node.module or ""))
                elif node.level > 1:
                    outside.append("." * node.level + (node.module or ""))
        assert outside == [], f"{rel}: {outside}"


# ---- D0071：記録の順序の検査（pipe_in/dev/record_order.py）は読むだけ -------------------------------------

RECORD_ORDER = "pipe_in.dev.record_order"
ORDER_NEVER_IMPORTS = {"subprocess", "shutil", "multiprocessing", "socket", "urllib", "http", "tempfile", "claude_agent_sdk"}
WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "touch", "rename", "symlink_to", "hardlink_to", "chmod", "truncate"}
WRITE_OS = {"remove", "removedirs", "makedirs", "mkdir", "rmdir", "rename", "replace", "unlink", "truncate", "chmod", "system", "popen"}
WRITE_MODE_CHARS = set("wax+")


def _order_import_problems(path: Path, module: str) -> list[str]:
    """標準ライブラリと pipe_in.engine 以外を読んでいる import（record・SDK・subprocess なども含む）。"""
    import sys

    problems: list[str] = []
    for target in sorted({t for t in _imports(path, module) if t}):
        top = target.split(".")[0]
        if top in ORDER_NEVER_IMPORTS:
            problems.append(f"{target}（読んではいけない）")
        elif top == "pipe_in":
            if not (target == "pipe_in" or target == "pipe_in.engine" or target.startswith("pipe_in.engine.")):
                problems.append(f"{target}（engine 以外の本体）")
        elif top not in sys.stdlib_module_names and top != "__future__":
            problems.append(f"{target}（標準ライブラリでない）")
    return problems


def _open_writes(node: ast.Call) -> bool:
    mode: ast.expr | None = None
    func = node.func
    is_builtin = isinstance(func, ast.Name) and func.id == "open"
    is_method = isinstance(func, ast.Attribute) and func.attr == "open"
    if not (is_builtin or is_method):
        return False
    pos = 1 if is_builtin else 0  # open(path, mode) / path.open(mode)
    if len(node.args) > pos:
        mode = node.args[pos]
    for kw in node.keywords:
        if kw.arg == "mode":
            mode = kw.value
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return bool(WRITE_MODE_CHARS & set(mode.value))
    return True  # 文字で読めないモードは、安全側に書き込みとみなす


def _order_write_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if _open_writes(node):
            found.append(f"{node.lineno}: open（書き込みモード）")
        elif isinstance(func, ast.Attribute):
            if func.attr in WRITE_METHODS:
                found.append(f"{node.lineno}: .{func.attr}()")
            elif isinstance(func.value, ast.Name) and func.value.id == "os" and func.attr in WRITE_OS:
                found.append(f"{node.lineno}: os.{func.attr}()")
            elif func.attr == "replace" and len(node.args) == 1 and not node.keywords:
                found.append(f"{node.lineno}: .replace(1 つの引数)（Path.replace の形）")
    return found


def test_d0071_ac16_record_order_imports_only_stdlib_and_engine():
    """D0071-AC-16: pipe_in/dev/record_order.py は標準ライブラリと pipe_in.engine だけを読む（record・SDK・subprocess は読まない）。"""
    path = ROOT / "pipe_in" / "dev" / "record_order.py"
    assert path.is_file(), "pipe_in/dev/record_order.py がまだ無い"
    assert _order_import_problems(path, RECORD_ORDER) == []


def test_d0071_ac16_record_order_has_no_write_calls():
    """D0071-AC-16: record_order.py は書き込みの呼び出し（write_text・write_bytes・open の書き込みモード・mkdir・unlink・rename・shutil・os.remove など）を使わない。"""
    path = ROOT / "pipe_in" / "dev" / "record_order.py"
    assert path.is_file(), "pipe_in/dev/record_order.py がまだ無い"
    assert _order_write_calls(path) == []


def test_d0071_ac16_check_finds_forbidden_imports_and_writes(tmp_path):
    """D0071-AC-16: 検査そのものが、禁止の import と書き込みの呼び出しを見つけられる（見つからないと検査が空振りしている）。"""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import subprocess\nimport shutil\nimport yaml\nimport os\nfrom pathlib import Path\n"
        "from pipe_in.dev import record\nfrom pipe_in.dev.record import Recorder\nfrom pipe_in.pipe import definition\n"
        "from pipe_in.engine.pipeline import STATE\n"
        "def f(p: Path, mode):\n"
        "    p.write_text('x')\n    p.write_bytes(b'x')\n    p.mkdir()\n    p.unlink()\n    p.rename(p)\n    p.replace(p)\n"
        "    open(p, 'w')\n    open(p, mode='a')\n    p.open('r+')\n    open(p, mode)\n    os.remove(p)\n    shutil.rmtree(p)\n",
        encoding="utf-8",
    )
    imports = _order_import_problems(bad, "pipe_in.dev.bad")
    for word in ("subprocess", "shutil", "yaml", "pipe_in.dev.record", "pipe_in.pipe"):
        assert any(word in p for p in imports), (word, imports)
    assert not any("pipe_in.engine.pipeline" in p for p in imports), imports
    writes = _order_write_calls(bad)
    for word in ("write_text", "write_bytes", ".mkdir", ".unlink", ".rename", "Path.replace", "os.remove"):
        assert any(word in w for w in writes), (word, writes)
    assert len([w for w in writes if "open（書き込みモード）" in w]) == 4, writes


def test_d0071_ac16_check_accepts_a_read_only_module(tmp_path):
    """D0071-AC-16: 検査が読むだけのコード（open の読み取り・read_text・str.replace・datetime.replace）を誤って止めない。"""
    ok = tmp_path / "ok.py"
    ok.write_text(
        "from __future__ import annotations\nimport json\nfrom datetime import datetime\nfrom pathlib import Path\n"
        "from ..engine.pipeline import STATE\n"
        "def f(p: Path, t: datetime):\n"
        "    open(p)\n    open(p, 'r')\n    p.open(encoding='utf-8')\n    p.read_text()\n    'a'.replace('a', 'b')\n    t.replace(tzinfo=None)\n"
        "    return json.loads('{}')\n",
        encoding="utf-8",
    )
    assert _order_import_problems(ok, "pipe_in.dev.ok") == []
    assert _order_write_calls(ok) == []


def test_python_files_have_no_invalid_escape_sequences():
    """リポジトリの .py に、無効なエスケープ（`"\\("`・`'\\ '` など）が無い。今は SyntaxWarning だが、新しい Python では誤りになる。"""
    import warnings

    bad: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        if {".venv", "node_modules", ".git", "out"} & set(path.relative_to(ROOT).parts):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as e:
                bad.append(f"{path.relative_to(ROOT).as_posix()}:{e.lineno}: {e.msg}")
    assert bad == []
