"""検査の二重化（check_pipe と、作業台の validatePipe）の突き合わせ（D0061）。Python 側。

見本は tests/fixtures/check_parity/<ケース>/（pipe-in-<名前>/pipe.toml と expected.json）。拡張側のテスト
（vscode/src/app/pipeCheckParity.test.ts）が同じ見本・同じ expected.json・同じ突き合わせの規則を読む。
ここは SDK を呼ばず、見本を読むだけで、書かない。
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from pipe_in.engine.guard import DANGEROUS_BASH
from pipe_in.pipe.definition import PREFIXES, RESERVED_OUTPUTS, PipeDef, check_pipe, load_pipe

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "check_parity"
EXPECTED_KEYS = {"note", "valid", "errors", "keywords", "only", "reason"}
CASE_NAME = re.compile(r"(ok|err|ext)-[a-z0-9]+(-[a-z0-9]+)*")


def case_names() -> list[str]:
    if not FIXTURES.is_dir():
        return []
    return sorted(p.name for p in FIXTURES.iterdir() if p.is_dir() and not p.name.startswith("_"))


CASES = case_names()


def expected_of(case: Path) -> dict[str, Any]:
    return json.loads((case / "expected.json").read_text(encoding="utf-8"))


def pipe_dir_of(case: Path) -> Path:
    dirs = [p for p in case.iterdir() if p.is_dir()]
    assert len(dirs) == 1, f"{case.name} のパイプのフォルダが1つではありません: {[d.name for d in dirs]}"
    return dirs[0]


def python_errors(name: str) -> list[str]:
    case = FIXTURES / name
    return check_pipe(load_pipe(pipe_dir_of(case)), case)


# ---- 突き合わせの規則（拡張のテストにも同じものがある。_matcher.json で両側を確かめる） ----------------


def keyword_words(keywords: list[Any]) -> list[str]:
    return [w for k in keywords for w in ([k] if isinstance(k, str) else k)]


def matches(errors: list[str], expected: dict[str, Any]) -> bool:
    """誤りの一覧が expected に合うか：件数が等しい・各キーワード（配列はどれか1つ）を含む誤りがある・どの誤りもどれかのキーワードを含む。"""
    keywords = expected["keywords"]
    if len(errors) != expected["errors"]:
        return False
    for k in keywords:
        alts = [k] if isinstance(k, str) else k
        if not any(any(a in e for a in alts) for e in errors):
            return False
    words = keyword_words(keywords)
    return all(any(w in e for w in words) for e in errors)


# ---- 見本の形の検査 ------------------------------------------------------------------------------


def reason_problems(expected: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    only, reason = expected.get("only"), expected.get("reason")
    if "only" in expected:
        if only not in ("python", "extension"):
            problems.append(f"only は python か extension: {only!r}")
        if not isinstance(reason, str) or not reason.strip():
            problems.append("only があるのに reason（理由の文）が空か無い")
    elif "reason" in expected:
        problems.append("only が無いのに reason がある")
    return problems


def shape_problems(case: Path) -> list[str]:
    problems: list[str] = []
    if not CASE_NAME.fullmatch(case.name):
        problems.append("ケース名は ok-・err-・ext- で始まる英小文字・数字・- だけ")
    path = case / "expected.json"
    if not path.is_file():
        return [*problems, "expected.json が無い"]
    try:
        e = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        return [*problems, f"expected.json を読めない: {ex}"]
    if not isinstance(e, dict):
        return [*problems, "expected.json は表（オブジェクト）で書く"]
    extra = set(e) - EXPECTED_KEYS
    if extra:
        problems.append(f"知らないキー: {sorted(extra)}")
    if not isinstance(e.get("note"), str) or not e.get("note", "").strip():
        problems.append("note（何を確かめるかの1文）が無い")
    valid, errors, keywords = e.get("valid"), e.get("errors"), e.get("keywords")
    if not isinstance(valid, bool):
        problems.append("valid は真偽")
    if not isinstance(errors, int) or isinstance(errors, bool) or errors < 0:
        problems.append("errors は 0 以上の整数")
    elif isinstance(valid, bool) and valid != (errors == 0):
        problems.append("valid は errors == 0 と同じ値")
    if not isinstance(keywords, list):
        problems.append("keywords は配列")
    else:
        for k in keywords:
            ok = (isinstance(k, str) and k) or (isinstance(k, list) and k and all(isinstance(x, str) and x for x in k))
            if not ok:
                problems.append(f"keywords の要素は文字列か、文字列の配列: {k!r}")
        if valid is False and not keywords:
            problems.append("valid が偽のときは keywords が1つ以上")
        if valid is True and keywords:
            problems.append("valid が真のときは keywords は空")
    problems += reason_problems(e)

    dirs = [p for p in case.iterdir() if p.is_dir()]
    if len(dirs) != 1:
        problems.append(f"パイプのフォルダが1つではない: {[d.name for d in dirs]}")
    else:
        d = dirs[0]
        if not d.name.startswith(PREFIXES):
            problems.append(f"パイプのフォルダ名の頭が {PREFIXES} のどれでもない: {d.name}")
        if not (d / "pipe.toml").is_file():
            problems.append(f"{d.name}/pipe.toml が無い")
    return problems


def make_case(root: Path, name: str, expected: Any, folders: tuple[str, ...] = ("pipe-in-demo",), toml: bool = True) -> Path:
    case = root / name
    case.mkdir()
    if expected is not None:
        (case / "expected.json").write_text(expected if isinstance(expected, str) else json.dumps(expected), encoding="utf-8")
    for f in folders:
        (case / f).mkdir()
        if toml:
            (case / f / "pipe.toml").write_text('[pipe]\nkind = "linear"\n', encoding="utf-8")
    return case


GOOD = {"note": "n", "valid": False, "errors": 1, "keywords": ["x"]}


@pytest.mark.parametrize("name", CASES)
def test_expected_json_is_well_formed(name: str):
    """D0061-AC-01: 見本の各ケースに pipe.toml と expected.json があり、形が合う（フォルダが1つ・名前の頭・キー・valid と errors の一致・keywords）。"""
    assert shape_problems(FIXTURES / name) == []


def test_cases_exist():
    """D0061-AC-01: 見本のフォルダが読め、ok-minimal を含む（見本が読めず全部飛ばして通る、を防ぐ）。"""
    assert "ok-minimal" in CASES
    assert len(CASES) >= 30


def test_shape_checker_catches_broken_expected(tmp_path: Path):
    """D0061-AC-01: 形の検査そのものが、崩れた見本を見つける（良い見本は通る）。"""
    assert shape_problems(make_case(tmp_path, "err-good", GOOD)) == []
    broken = {
        "no-expected": make_case(tmp_path, "err-a", None),
        "bad-json": make_case(tmp_path, "err-b", "{not json"),
        "extra-key": make_case(tmp_path, "err-c", {**GOOD, "extra": 1}),
        "valid-mismatch": make_case(tmp_path, "err-d", {**GOOD, "valid": True}),
        "errors-negative": make_case(tmp_path, "err-e", {**GOOD, "errors": -1, "valid": False}),
        "keywords-empty": make_case(tmp_path, "err-f", {**GOOD, "keywords": []}),
        "keywords-for-valid": make_case(tmp_path, "ok-g", {"note": "n", "valid": True, "errors": 0, "keywords": ["x"]}),
        "note-missing": make_case(tmp_path, "err-h", {k: v for k, v in GOOD.items() if k != "note"}),
        "two-folders": make_case(tmp_path, "err-i", GOOD, folders=("pipe-in-a", "pipe-in-b")),
        "bad-prefix": make_case(tmp_path, "err-j", GOOD, folders=("pipe-demo",)),
        "no-toml": make_case(tmp_path, "err-k", GOOD, toml=False),
        "bad-case-name": make_case(tmp_path, "Bad_Case", GOOD),
    }
    for label, case in broken.items():
        assert shape_problems(case) != [], f"{label} の崩れを見つけられなかった"


@pytest.mark.parametrize("name", CASES)
def test_only_cases_have_a_reason(name: str):
    """D0061-AC-12: only を持つケースには理由の文がある（only が無いのに理由がある・only の値が不正でも落ちる）。"""
    assert reason_problems(expected_of(FIXTURES / name)) == []


def test_reason_checker_catches_missing_reason():
    """D0061-AC-12: 理由の検査そのものが、理由が空・理由だけある・only の値が不正なものを見つける。"""
    assert reason_problems({"only": "python", "reason": "理由"}) == []
    assert reason_problems({"only": "extension", "reason": "理由"}) == []
    assert reason_problems({}) == []
    assert reason_problems({"only": "python"}) != []
    assert reason_problems({"only": "python", "reason": ""}) != []
    assert reason_problems({"only": "python", "reason": "  "}) != []
    assert reason_problems({"reason": "理由だけ"}) != []
    assert reason_problems({"only": "both", "reason": "理由"}) != []


def test_matcher_agrees_with_matcher_json():
    """D0061-AC-19: 突き合わせの規則の実装が、_matcher.json の全件と合う（拡張側も同じ表で確かめる）。"""
    table = json.loads((FIXTURES / "_matcher.json").read_text(encoding="utf-8"))
    assert len(table) >= 8
    wrong = [t["name"] for t in table if matches(t["errors"], t["expected"]) != t["matches"]]
    assert wrong == []


@pytest.mark.parametrize("name", [n for n in CASES if expected_of(FIXTURES / n).get("valid") is True and expected_of(FIXTURES / n).get("only") != "extension"])
def test_ok_cases_have_no_errors_in_python(name: str):
    """D0061-AC-02: 通るケースを check_pipe にかけると誤りが0件。"""
    assert python_errors(name) == []


@pytest.mark.parametrize("name", [n for n in CASES if "only" not in expected_of(FIXTURES / n)])
def test_cases_match_expected_in_python(name: str):
    """D0061-AC-03: only の無いケースを check_pipe にかけると、expected.json の件数とキーワードに合う。"""
    errors = python_errors(name)
    assert matches(errors, expected_of(FIXTURES / name)), "\n".join([f"{name}: 件数 {len(errors)}", *errors])


@pytest.mark.parametrize("name", [n for n in CASES if expected_of(FIXTURES / n).get("only") == "python"])
def test_python_only_cases_match_expected_in_python(name: str):
    """D0061-AC-13: only が python のケースも Python で expected に合う（誤りのままで、意図した差の見本が古くならない）。"""
    errors = python_errors(name)
    assert matches(errors, expected_of(FIXTURES / name)), "\n".join([f"{name}: 件数 {len(errors)}", *errors])


# 受け入れ基準ごとの、両側で照らすケース（only が無く、valid が偽で、キーワードが入っている）
SHARED = {
    "D0061-AC-05": ["err-access-read-writes"],
    "D0061-AC-06": ["err-check-command-dangerous"],
    "D0061-AC-07": ["err-writes-paths", "err-add-dirs-paths", "err-docs-dir"],
    "D0061-AC-08": ["err-output-reserved"],
    "D0061-AC-09": ["err-mcp-server-name"],
    "D0061-AC-10": ["err-judge-threshold", "err-judge-no-criteria", "err-judge-items", "err-max-budget"],
    "D0061-AC-11": ["err-group-not-contiguous", "err-group-review", "err-group-on-fail"],
}


@pytest.mark.parametrize("ac", sorted(SHARED))
def test_ac_cases_are_shared_by_both_sides(ac: str):
    """D0061-AC-05〜11: 受け入れ基準ごとのケースがあり、片側だけの only が付かず、誤りとキーワードを持つ（実際の照らしは AC-03・04）。"""
    for name in SHARED[ac]:
        assert name in CASES, f"{ac}: ケース {name} が無い"
        e = expected_of(FIXTURES / name)
        assert "only" not in e, f"{ac}: {name} に only が付いている（両側で照らす）"
        assert e["valid"] is False and e["errors"] >= 1 and keyword_words(e["keywords"]), f"{ac}: {name} が誤りのケースになっていない"


def stage_tables(name: str) -> list[dict[str, Any]]:
    path = pipe_dir_of(FIXTURES / name) / "pipe.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")).get("stages", [])


def test_every_dangerous_bash_pattern_has_a_sample():
    """D0061-AC-06: DANGEROUS_BASH の各正規表現に当たる check.command が、見本に1つ以上ある（表に語を足したら見本も足す）。"""
    commands = [s["check"]["command"] for s in stage_tables("err-check-command-dangerous") if "command" in s.get("check", {})]
    assert commands
    missing = [pattern for pattern, _ in DANGEROUS_BASH if not any(re.search(pattern, c) for c in commands)]
    assert missing == [], f"見本の command に当たらない正規表現: {missing}"


def test_reserved_outputs_are_all_in_the_sample():
    """D0061-AC-08: RESERVED_OUTPUTS を全部、見本の output が持っている（表に名前を足したら見本も足す）。"""
    outputs = {s["output"] for s in stage_tables("err-output-reserved")}
    assert RESERVED_OUTPUTS <= outputs, f"見本に無い予約名: {sorted(RESERVED_OUTPUTS - outputs)}"


def test_legacy_folder_case_loads_as_linear():
    """D0061-AC-14: 前の形（devpipe- のフォルダ・kind 無し）を、Python は従来どおり linear として読み、通す。"""
    case = FIXTURES / "ok-legacy-folder"
    pipe_dir = pipe_dir_of(case)
    assert pipe_dir.name.startswith("devpipe-")
    assert "kind" not in tomllib.loads((pipe_dir / "pipe.toml").read_text(encoding="utf-8")).get("pipe", {})
    pipe: PipeDef = load_pipe(pipe_dir)
    assert pipe.kind == "linear"
    assert pipe.name == pipe_dir.name.removeprefix("devpipe-")
    assert check_pipe(pipe, case) == []


def test_design_md_describes_the_parity_rules():
    """D0061-AC-15: design.md に節「検査の二重化（Python と拡張）」と意図した差があり、testing.md・workflow.md に見本の場所がある。"""
    design = (ROOT / "docs" / "development" / "design.md").read_text(encoding="utf-8")
    assert re.search(r"^#+ .*検査の二重化（Python と拡張）", design, re.MULTILINE), "design.md に節「検査の二重化（Python と拡張）」が無い"
    for word in ("check_pipe", "validatePipe", "tests/fixtures/check_parity/", "意図した差"):
        assert word in design, f"design.md に「{word}」が無い"
    assert "tests/test_check_parity.py" in design and "vscode/src/app/pipeCheckParity.test.ts" in design
    for doc in ("testing.md", "workflow.md"):
        text = (ROOT / "docs" / "development" / doc).read_text(encoding="utf-8")
        assert "check_parity" in text, f"{doc} に見本の場所（check_parity）が無い"
