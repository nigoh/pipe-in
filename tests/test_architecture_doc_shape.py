"""D0075-AC-08・09：tests/test_architecture.py の既存のテスト関数が残ることと、新しい検査の置き場所（決定ごとの別ファイル）の見本。

新しいアーキテクチャの検査は、tests/test_architecture.py の末尾に足さず、決定ごとに tests/test_architecture_<名前>.py を作って置く。
共有の部品（ast で import を読む関数など）は、tests/test_architecture.py のものを import して使う（作り直さない）。
_violations・_old_imports は ROOT を使うので、別ファイルから使わない。

今の作りのままで通るテストは、名前の末尾を _守る にする。
"""

from __future__ import annotations

import ast
from pathlib import Path

from test_architecture import _imports, _module_name, _outside_stdlib  # noqa: PLC2701

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SHARED = ("_imports", "_module_name", "_outside_stdlib")

# tests/test_architecture.py にある、今のテスト関数（D0075 の時点。消す・名前を変えると落ちる。別ファイルへ移したときは、同じ名前が移り先にあれば通る）
EXISTING_TESTS = (
    "test_dependency_direction", "test_rule_catches_reverse_import", "test_d0019_ac50_state_only_adds_keys",
    "test_guard_hook_uses_only_stdlib", "test_judge_score_uses_only_stdlib", "test_findings_check_uses_only_stdlib",
    "test_judge_uses_only_stdlib", "test_d0027_ac70_live_modules_use_only_stdlib",
    "test_d0027_ac70_live_cmd_depends_only_on_config_and_the_live_parts", "test_d0027_ac70_cli_imports_live_cmd_inside_the_branch_only",
    "test_d0027_ac70_stdlib_check_finds_live_part_importing_siblings", "test_stdlib_check_finds_outside_import",
    "test_nothing_imports_old_names", "test_old_import_check_finds_old_names", "test_legacy_is_not_imported_from_lower_layers",
    "test_d0031_ac52_live_watch_uses_only_stdlib_and_live", "test_d0031_ac52_live_watch_check_finds_forbidden_imports",
    "test_d0031_ac52_live_and_live_page_do_not_read_live_watch", "test_d0031_ac52_live_cmd_may_read_live_watch",
    "test_d0031_ac52_dependencies_unchanged", "test_d0031_ac52_live_watch_is_in_an_installed_package",
    "test_d0036_ac26_bashwriteは標準ライブラリだけ", "test_pipe_lint_imports_only_definition",
    "test_d0044_ac50_live_answer_uses_only_the_standard_library", "test_d0044_ac50_live_answer_check_finds_forbidden_imports",
    "test_d0044_ac50_live_may_read_live_answer_only", "test_d0044_ac50_live_cmd_may_read_live_answer",
    "test_d0044_ac50_live_page_and_live_watch_do_not_read_live_answer", "test_d0044_ac50_record_does_not_read_live_answer",
    "test_d0044_ac50_nothing_in_engine_imports_dev", "test_d0044_ac50_dependencies_are_unchanged",
    "test_d0044_ac29_live_answer_live_and_live_cmd_start_no_child_process_and_use_no_sdk", "test_d0044_ac29_live_answer_is_in_an_installed_package",
    "test_d0066_ac12_目安の部品のソースに書き込みと子プロセスが無い", "test_d0066_ac28_目安の部品はguardを読まず書き込み先を持たない",
    "test_d0066_ac12_検査そのものが書き込みと子プロセスとguardの読み込みを見つける_守る",
    "test_d0066_ac12_usageの目安の部品は標準ライブラリとusageの中だけを読む",
    "test_d0071_ac16_record_order_imports_only_stdlib_and_engine", "test_d0071_ac16_record_order_has_no_write_calls",
    "test_d0071_ac16_check_finds_forbidden_imports_and_writes", "test_d0071_ac16_check_accepts_a_read_only_module",
    "test_python_files_have_no_invalid_escape_sequences",
)  # fmt: skip


def top_level_tests(source: str) -> set[str]:
    return {n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def missing_tests(sources: dict[str, str], names=EXISTING_TESTS) -> list[str]:
    """names のうち、どの sources にも（最上位の def test_* として）無いもの。"""
    found: set[str] = set()
    for source in sources.values():
        found |= top_level_tests(source)
    return [n for n in names if n not in found]


def architecture_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(TESTS.glob("test_architecture*.py"))}


def test_D0075_AC_08_test_architectureの既存のテスト関数が名前を残す_守る():
    """D0075-AC-08: tests/test_architecture.py の既存のテスト関数が、名前を変えずに残る（別ファイルへ移したものは、同じ名前が移り先にある）。
    「中身を変えない」は、ファイルに触らないことで満たす（検証の段で git diff が空であることを確かめる）。（今のまま通る。守る）"""
    assert len(EXISTING_TESTS) == len(set(EXISTING_TESTS))
    assert missing_tests(architecture_sources()) == []


def test_D0075_AC_08_見本_消した名前と変えた名前を見つけ_別ファイルへ移した名前は見逃す_守る():
    """D0075-AC-08: 検査そのものの確かめ。消したテスト・名前を変えたテストは欠けとして返し、別ファイルに同じ名前で移したものは見逃す。
    最上位でない関数（入れ子）は数えない。（今のまま通る。守る）"""
    names = ("test_a", "test_b")
    assert missing_tests({"x.py": "def test_a(): pass\ndef test_b(): pass"}, names) == []
    assert missing_tests({"x.py": "def test_a(): pass"}, names) == ["test_b"]
    assert missing_tests({"x.py": "def test_a(): pass\ndef test_b2(): pass"}, names) == ["test_b"]
    assert missing_tests({"x.py": "def test_a(): pass", "y.py": "def test_b(): pass"}, names) == []
    assert missing_tests({"x.py": "def test_a(): pass\ndef f():\n    def test_b(): pass"}, names) == ["test_b"]


def test_D0075_AC_09_architecture系の別ファイルは共有の部品を作り直さず_使っている_守る():
    """D0075-AC-09: tests/test_architecture_*.py は、共有の部品（_imports・_module_name・_outside_stdlib）を test_architecture から import して使うか、
    3 つのどれも自分で def していない（作り直していない）。（今のまま通る。守る）"""
    files = sorted(TESTS.glob("test_architecture_*.py"))
    assert files, "tests/test_architecture_*.py が 1 つも無い"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        redefined = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in SHARED]
        assert redefined == [], f"{path.name} が共有の部品を作り直している：{redefined}"


def test_D0075_AC_09_共有の部品が別ファイルから動く_守る(tmp_path):
    """D0075-AC-09: 別ファイルから import した共有の部品が動く。_outside_stdlib は標準ライブラリの外の名前だけを返し、_imports は import の対象を返し、
    _module_name は置き場所から Python の名前を作る。（今のまま通る。守る）"""
    src = tmp_path / "pkg" / "sub" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import json\nimport claude_agent_sdk\nfrom pipe_in.engine import config\n", encoding="utf-8")
    assert _outside_stdlib(src, "pkg.sub.mod") == ["claude_agent_sdk", "pipe_in"]
    assert {"json", "claude_agent_sdk", "pipe_in.engine"} <= set(_imports(src, "pkg.sub.mod"))
    assert _module_name(src, tmp_path / "pkg", "pkg") == "pkg.sub.mod"


def test_D0075_AC_09_test_doc_shapeは標準ライブラリとpytestとtestsの中だけを読む_守る():
    """D0075-AC-09: tests/test_doc_shape.py は標準ライブラリと pytest と tests/ の中のファイルしか import しない
    （pipe_in・SDK を読まない。_outside_stdlib の戻りから pytest と tests/ の中を除くと空）。（今のまま通る。守る）"""
    path = TESTS / "test_doc_shape.py"
    assert path.is_file()
    outside = _outside_stdlib(path, "test_doc_shape")
    stray = [n for n in outside if n != "pytest" and not (TESTS / f"{n}.py").is_file()]
    assert stray == []


def test_D0075_AC_09_test_architectureは新しいファイルの名前を持たない_守る():
    """D0075-AC-09: tests/test_architecture.py に「test_architecture_」の文字が無い（新しいファイルを足すのに、既存のファイルを直さずに済む。
    新しいファイルを登録する一覧は無い）。（今のまま通る。守る）"""
    assert "test_architecture_" not in (TESTS / "test_architecture.py").read_text(encoding="utf-8")
