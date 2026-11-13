"""D0096-AC-18〜21・46〜49：調査「プラグインの eval のラウンド」の本文と、集計のスクリプト（docs/research/plugin-eval-rounds/rounds.py）。

スクリプトは importlib で読み（読む間は sys.dont_write_bytecode = True。docs/research/ に __pycache__ を作らない）、main(argv) を直に呼ぶ。
結果の JSON は、D0096 の設計（5.3 の読む鍵）の形で作った偽物で、tmp_path の中に書く。読まない鍵（suite.root・cases[].dir・
promptMarkdown・tracePath・explanation・evidence・judgeVotes など）には、手元のパス・メールアドレス・モデルの返事の文に見える文字を入れ、
出力に出ないことを見る。手元のパスとメールアドレスは、つなげて作る（tests/test_rules.py の決まり）。
SDK・子プロセス・ネットワークは使わない。
"""

from __future__ import annotations

import ast
import builtins
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from test_rules import SECRET_FILES, local_info_in

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research"
STUDY = RESEARCH / "plugin-eval-rounds"
SCRIPT = STUDY / "rounds.py"
SECTIONS = ["問い", "結論", "方法", "結果", "限界", "pipe-in への示唆", "やり直し方"]

LOCAL_ROOT = "/ho" + "me/someone/ws"
MAIL = "someone" + "@" + "example.com"
MODEL_TEXT = "モデルの返事の生の文：手元の秘密の設定を読みました"


@pytest.fixture(scope="module")
def rounds():
    """rounds.py を読む（docs/research/ に __pycache__ を作らない）。"""
    spec = importlib.util.spec_from_file_location("plugin_eval_rounds", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


# ---- 偽の結果の JSON（claude plugin eval の --json / aggregate-result.json の鍵の形） -------------------------


def g(name: str, passed: bool = True, scored: bool | None = None) -> dict:
    out = {"name": name, "passed": passed, "explanation": f"{MODEL_TEXT} {MAIL}", "evidence": [f"{LOCAL_ROOT}/trace.jsonl"]}
    if scored is not None:
        out["scored"] = scored
    return out


def run(passed: bool, graders: list[dict], error: str | None = None, skipped: bool | None = None) -> dict:
    out = {"passed": passed, "error": error, "graders": graders, "judgeVotes": [MODEL_TEXT], "tracePath": f"{LOCAL_ROOT}/t.jsonl"}
    if skipped is not None:
        # 費用の上限で審査の採点が飛ばされた回の印（D0096-AC-48）。None なら鍵を書かない（今までの見本はこの形）
        out["skippedPaidGraders"] = skipped
    return out


def case(name: str, score: float, runs: list[dict], runs_per_case: int = 3) -> dict:
    # 本物の結果では、--runs で上書きしても runsPerCase はケースの既定（3）のまま出て、arms.with の長さが実際に流れた回の数になる
    # （D0096。len(runs) を入れると、2 つが同じになって食い違いが見えない）。
    return {
        "name": name,
        "dir": f"{LOCAL_ROOT}/plugin/evals/{name}",
        "promptMarkdown": MODEL_TEXT,
        "runsPerCase": runs_per_case,
        "aggregates": {"score": score},
        "arms": {"with": runs},
    }


def result(cases: list[dict], *, passed: int, overall: float, claude: str = "2.1.323", model: str | None = "haiku",
           judge: str | None = "haiku", threshold: float | None = None, cost: float = 0.11, duration: float = 321.4,
           partial: bool = False) -> dict:
    return {
        "schemaVersion": 1,
        "claudeVersion": claude,
        "costUsd": cost,
        "durationSeconds": duration,
        "partial": partial,
        "startedAt": "2026-11-13T00:00:00Z",
        "suite": {"root": f"{LOCAL_ROOT}/plugin", "modelOverride": model, "judgeModel": judge, "threshold": threshold},
        "aggregates": {"casesTotal": len(cases), "casesPassed": passed, "overallScore": overall},
        "cases": cases,
    }


def round_1b() -> dict:
    return result(
        [
            case("build-passes-check", 1.0, [run(True, [g("04-gen-check"), g("07-check-passed")])]),
            case("eval-result-json", 0.671, [run(False, [g("01-keys"), g("02-passed", False)])]),
            case("eval-stops-without-state", 1.0, [run(True, [g("01-no-run")])]),
            case(
                "judge-rejects-bad-runs",
                0.5,
                [run(False, [g("01-no-agent"), g("02-no-score", False), g("03-range", False)], error=f"Error: {MODEL_TEXT} {LOCAL_ROOT}")],
            ),
        ],
        passed=2,
        overall=0.79,
    )


def round_2() -> dict:
    return result(
        [
            case("judge-rejects-bad-runs", 1.0, [run(True, [g("01-no-agent"), g("02-no-score"), g("03-range")])]),
            case(
                "build-passes-check",
                0.78,
                [run(False, [g("04-gen-check"), g("07-check-passed", False), g("09-note", False, scored=False)])],
            ),
            case("eval-result-json", 0.668, [run(False, [g("01-keys"), g("02-passed", False)])]),
            case("run-dry-run-asks-first", 0.86, [run(True, [g("01-dry-run")])]),
        ],
        passed=2,
        overall=0.83,
        claude="2.1.330",
        cost=0.12,
        duration=400.2,
    )


def round_runs3() -> dict:
    three = [
        run(True, [g("04-gen-check"), g("07-check-passed"), g("08-numbered-prompt")]),
        run(False, [g("04-gen-check"), g("07-check-passed", False), g("08-numbered-prompt")]),
        run(False, [g("04-gen-check"), g("07-check-passed", False), g("08-numbered-prompt", False)]),
    ]
    ok = [run(True, [g("01-no-agent"), g("02-no-score"), g("03-range")]) for _ in range(3)]
    return result(
        [case("build-passes-check", 0.7, three), case("judge-rejects-bad-runs", 1.0, ok)],
        passed=1,
        overall=0.85,
        claude="2.1.330",
        model=None,
        threshold=0.8,
        cost=0.33,
        duration=900.0,
        partial=True,
    )


def write(tmp_path: Path, name: str, data: dict | str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def call(rounds, argv: list[str], capsys) -> tuple[int, str, str]:
    rc = rounds.main(argv)
    out, err = capsys.readouterr()
    return rc, out, err


TABLE_HEAD = "| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |"
TABLE_RULE = "| --- | --- | --- | --- | --- | --- |"


def round_block(out: str, name: str) -> list[str]:
    """出力のうち「## 回 <名前>」から次の「## 回」の手前までの行。"""
    lines = out.splitlines()
    assert f"## 回 {name}" in lines, f"「## 回 {name}」が無い: {out!r}"
    start = lines.index(f"## 回 {name}")
    block: list[str] = []
    for ln in lines[start + 1 :]:
        if ln.startswith("## 回 "):
            break
        block.append(ln)
    return block


def table_rows(block: list[str]) -> list[str]:
    assert TABLE_HEAD in block and TABLE_RULE in block, block
    at = block.index(TABLE_RULE)
    rows: list[str] = []
    for ln in block[at + 1 :]:
        if not ln.startswith("|"):
            break
        rows.append(ln)
    return rows


def norm(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


# ---- AC-18：調査の本文と目次 ---------------------------------------------------------------------------------


def section(text: str, head: str) -> str:
    level = len(head) - len(head.lstrip("#"))
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == head:
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                m = re.match(r"^(#+)\s", nxt)
                if m and len(m.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return ""


def test_d0096_ac18_study_sections_and_round1_numbers():
    """D0096-AC-18: 調査の本文に 7 つの節（問い・結論・方法・結果・限界・pipe-in への示唆・やり直し方）がこの順にあり、
    「## 結果」にラウンド 1a・1b の小節とラウンド 1 の数字（5/9・0.68・0.84・$0.11）がある。「## やり直し方」が rounds.py の使い方を指す。"""
    text = (STUDY / "README.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", text, re.M)
    assert [h for h in heads if h in SECTIONS] == SECTIONS, heads
    results = section(text, "## 結果")
    assert "### ラウンド 1a" in results and "### ラウンド 1b" in results, "「## 結果」にラウンド 1a・1b の小節が無い"
    missing = [w for w in ["5/9", "0.68", "0.84", "$0.11"] if w not in results]
    assert missing == []
    assert "rounds.py" in section(text, "## やり直し方")


def test_d0096_ac18_index_row():
    """D0096-AC-18: 目次 docs/research/README.md の表の 1 行が plugin-eval-rounds/README.md を指し、日付と中身（空の形でない）がある。"""
    rows = [ln for ln in (RESEARCH / "README.md").read_text(encoding="utf-8").splitlines() if "](plugin-eval-rounds/README.md)" in ln]
    assert len(rows) == 1, "目次の表に plugin-eval-rounds/README.md を指す行が 1 つではない"
    cells = norm(rows[0])
    assert len(cells) == 3, cells
    assert "ラウンド" in cells[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月", cells[1]), cells[1]
    assert cells[2] and "空の形" not in cells[2] and "実装で書く" not in cells[2], cells[2]


# ---- AC-19：集計の表と、止まるとき -------------------------------------------------------------------------------


def test_d0096_ac19_two_rounds_make_table_and_diff(rounds, tmp_path, capsys):
    """D0096-AC-19: 結果の JSON を 2 つ渡すと終了コード 0 で、回ごとに、ケースの名前の順の表（点は小数 2 桁・合格の回・落ちた採点・エラーの回・
    前の回との差）を出す。最初の回の差は —、前の回に無いケースは「新しい」、丸めて 0 の差は符号なしの 0.00。scored が偽の採点は落ちた採点に数えない。"""
    p1, p2 = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", round_2())
    rc, out, err = call(rounds, [f"1b={p1}", f"2={p2}"], capsys)
    assert rc == 0, err
    one, two = round_block(out, "1b"), round_block(out, "2")
    assert out.splitlines().index("## 回 1b") < out.splitlines().index("## 回 2")
    assert [norm(r) for r in table_rows(one)] == [
        ["build-passes-check", "1.00", "1/1", "—", "0", "—"],
        ["eval-result-json", "0.67", "0/1", "02-passed", "0", "—"],
        ["eval-stops-without-state", "1.00", "1/1", "—", "0", "—"],
        ["judge-rejects-bad-runs", "0.50", "0/1", "02-no-score・03-range", "1", "—"],
    ]
    assert [norm(r) for r in table_rows(two)] == [
        ["build-passes-check", "0.78", "0/1", "07-check-passed", "0", "-0.22"],
        ["eval-result-json", "0.67", "0/1", "02-passed", "0", "0.00"],
        ["judge-rejects-bad-runs", "1.00", "1/1", "—", "0", "+0.50"],
        ["run-dry-run-asks-first", "0.86", "1/1", "—", "0", "新しい"],
    ]


def test_d0096_ac19_head_lines_show_versions_and_cost(rounds, tmp_path, capsys):
    """D0096-AC-19: 回の頭の 2 行に、Claude Code の版・モデル・審査役・回の数・合格の線（無ければ既定）と、
    Claude Code が数えた合格の数・全体の点・費用・時間（整数の秒）・途中で止まったか、が出る。"""
    p1, p2 = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", round_2())
    rc, out, err = call(rounds, [f"1b={p1}", f"2={p2}"], capsys)
    assert rc == 0, err
    one, two = round_block(out, "1b"), round_block(out, "2")
    assert "- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 1・合格の線 既定" in one
    assert "- 合格 2/4・全体の点 0.79・費用 $0.11・時間 321 秒・途中で止まった いいえ" in one
    assert "- Claude Code 2.1.330・モデル haiku・審査役 haiku・回の数 1・合格の線 既定" in two
    assert "- 合格 2/4・全体の点 0.83・費用 $0.12・時間 400 秒・途中で止まった いいえ" in two


def test_d0096_ac19_notes_under_table(rounds, tmp_path, capsys):
    """D0096-AC-19: 表の下に、前の回にあってこの回に無いケースと、Claude Code の版が前の回と違うことの注意が出る。最初の回には出ない。"""
    p1, p2 = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", round_2())
    rc, out, err = call(rounds, [f"1b={p1}", f"2={p2}"], capsys)
    assert rc == 0, err
    two = round_block(out, "2")
    assert "前の回にあってこの回に無いケース：eval-stops-without-state" in two
    assert "注意：Claude Code の版が前の回と違う（2.1.323 → 2.1.330）。差は比べられないことがある" in two
    one = round_block(out, "1b")
    assert not [ln for ln in one if ln.startswith(("前の回にあって", "注意："))], one


def test_d0096_ac19_runs3_counts_failed_graders_per_run(rounds, tmp_path, capsys):
    """D0096-AC-19: 回の数が 2 以上の回は、合格の回を k/n で、落ちた採点を「名前（落ちた回/回の数）」で出し、頭の行に with の回の数・合格の線・
    既定のモデル・途中で止まった（はい）が出る。途中で止まった回なので、前の回との差は比べられない（D0096-AC-46 で替えた）。"""
    p2, p3 = write(tmp_path, "r2.json", round_2()), write(tmp_path, "r3.json", round_runs3())
    rc, out, err = call(rounds, [f"2={p2}", f"final-runs3={p3}"], capsys)
    assert rc == 0, err
    block = round_block(out, "final-runs3")
    assert [norm(r) for r in table_rows(block)] == [
        ["build-passes-check", "0.70", "1/3", "07-check-passed（2/3）・08-numbered-prompt（1/3）", "0", "比べられない"],
        ["judge-rejects-bad-runs", "1.00", "3/3", "—", "0", "比べられない"],
    ]
    head = "\n".join(block)
    for word in ["回の数 3", "合格の線 0.8", "モデル 既定", "途中で止まった はい", "合格 1/2", "費用 $0.33", "時間 900 秒"]:
        assert word in head, word


def one_run_case(name: str, passed: bool) -> dict:
    """runsPerCase はケースの既定（3）のまま、with は 1 回（--runs 1 で回した本物の形）。"""
    return case(name, 1.0 if passed else 0.5, [run(passed, [g("01-x"), g("02-x", passed)])])


def three_runs_case(name: str) -> dict:
    """runsPerCase は 1 なのに、with は 3 回（合格・不合格・合格。採点 02-x が 1 回だけ落ちる）。"""
    runs = [
        run(True, [g("01-x"), g("02-x")]),
        run(False, [g("01-x"), g("02-x", False)]),
        run(True, [g("01-x"), g("02-x")]),
    ]
    return case(name, 0.83, runs, runs_per_case=1)


# 回の名前 → (結果の JSON, 頭の行の「回の数」の値, 表の行（ケース・合格の回・落ちた採点）)
RUNS_FROM_WITH = {
    "a": (
        lambda: result([one_run_case("a-pass", True), one_run_case("a-fail", False)], passed=1, overall=0.75),
        "1",
        [["a-fail", "0/1", "02-x"], ["a-pass", "1/1", "—"]],
    ),
    "b": (
        lambda: result([three_runs_case("b-three")], passed=1, overall=0.83),
        "3",
        [["b-three", "2/3", "02-x（1/3）"]],
    ),
    "c": (
        lambda: result([one_run_case("a-pass", True), three_runs_case("b-three")], passed=2, overall=0.92),
        "1〜3",
        [["a-pass", "1/1", "—"], ["b-three", "2/3", "02-x（1/3）"]],
    ),
}


@pytest.mark.parametrize("label", sorted(RUNS_FROM_WITH))
def test_d0096_ac19_runs_count_comes_from_with_not_runs_per_case(rounds, label, tmp_path, capsys):
    """D0096-AC-19: 「回の数」は arms.with の回の数から数え、cases[].runsPerCase は数えない（本物の結果では --runs で上書きしても既定のまま）。
    (a) runsPerCase 3・with 1 回のケースだけの回は、頭の行が「回の数 1」（「回の数 3」は出ない）。(b) runsPerCase 1・with 3 回のケースは「回の数 3」。
    (c) その 2 つが同じ回に混ざると「回の数 1〜3」。表の合格の回と、落ちた採点の（落ちた回/回の数）の分母は、どれも with の回の数のまま（守り）。"""
    make, runs_text, rows = RUNS_FROM_WITH[label]
    path = write(tmp_path, f"{label}.json", make())
    rc, out, err = call(rounds, [f"{label}={path}"], capsys)
    assert rc == 0, err
    block = round_block(out, label)
    # 先に表（今の作りでも with の長さから数えている。守り）を見て、そのあと頭の行を見る
    assert [[cells[0], cells[2], cells[3]] for cells in map(norm, table_rows(block))] == rows
    heads = [ln for ln in block if ln.startswith("- Claude Code ")]
    assert len(heads) == 1, block
    found = re.search(r"・回の数 ([^・]+)・合格の線 ", heads[0])
    assert found, heads[0]
    assert found.group(1) == runs_text, heads[0]
    if label == "a":
        assert "回の数 3" not in "\n".join(block), heads[0]


def test_d0096_ac19_names_from_arguments(rounds, tmp_path, capsys):
    """D0096-AC-19: 名前が無ければ並びの番号（1・2）になる。最初の = の前が名前の形でないとき（パスの途中の = など）は、全体をパスとして読む。"""
    p1 = write(tmp_path / "k=v", "r1.json", round_1b())
    p2 = write(tmp_path, "r2.json", round_2())
    rc, out, err = call(rounds, [str(p1), str(p2)], capsys)
    assert rc == 0, err
    lines = out.splitlines()
    assert "## 回 1" in lines and "## 回 2" in lines, out


@pytest.mark.parametrize("argv", [[], ["--nope"]], ids=["no-args", "unknown-flag"])
def test_d0096_ac19_usage_errors_exit_2(rounds, argv, capsys):
    """D0096-AC-19: 引数が無い・知らない旗は、argparse の使い方を出して終了コード 2。"""
    with pytest.raises(SystemExit) as e:
        rounds.main(argv)
    assert e.value.code == 2
    assert capsys.readouterr().out == ""


def _set(path: tuple, value):
    def apply(data: dict) -> None:
        cur = data
        for key in path[:-1]:
            cur = cur[key]
        cur[path[-1]] = value
    return apply


def _drop(path: tuple):
    def apply(data: dict) -> None:
        cur = data
        for key in path[:-1]:
            cur = cur[key]
        del cur[path[-1]]
    return apply


def _dup_case(data: dict) -> None:
    data["cases"].append(copy.deepcopy(data["cases"][0]))


# (壊し方, 理由の文に入る語（None なら見ない）, 出してはいけない値)
BROKEN = {
    "鍵の欠け（cases[0].aggregates.score）": (_drop(("cases", 0, "aggregates", "score")), "cases[0].aggregates.score が無いか、形が違う", None),
    "鍵の欠け（costUsd）": (_drop(("costUsd",)), "costUsd が無いか、形が違う", None),
    "鍵の欠け（arms.with の passed）": (_drop(("cases", 0, "arms", "with", 0, "passed")), "が無いか、形が違う", None),
    "ケースが 0 件": (_set(("cases",), []), "ケースが 0 件", None),
    "schemaVersion が 2": (_set(("schemaVersion",), 2), "schemaVersion が 1 でない", None),
    "schemaVersion が真偽": (_set(("schemaVersion",), True), None, None),
    "ケース名の形が違う": (_set(("cases", 0, "name"), "Build_Passes"), "cases[0].name が無いか、形が違う", "Build_Passes"),
    "ケース名の重なり": (_dup_case, None, None),
    "Claude Code の版の形が違う": (_set(("claudeVersion",), "2.1.323 local build"), "claudeVersion が無いか、形が違う", "local build"),
    "モデル名の形が違う": (_set(("suite", "modelOverride"), "haiku/../x"), "suite.modelOverride が無いか、形が違う", "haiku/../x"),
    "採点の名前の形が違う": (_set(("cases", 0, "arms", "with", 0, "graders", 0, "name"), "../x y"), None, "../x y"),
    "点が 1 を超える": (_set(("cases", 0, "aggregates", "score"), 1.5), "cases[0].aggregates.score が無いか、形が違う", None),
    "費用が真偽": (_set(("costUsd",), True), None, None),
    "時間が負": (_set(("durationSeconds",), -1), None, None),
    "合格の数が負": (_set(("aggregates", "casesPassed"), -1), None, None),
    # runsPerCase は読まない（D0096-AC-49）
    "with が空": (_set(("cases", 0, "arms", "with"), []), None, None),
    "passed が文字": (_set(("cases", 0, "arms", "with", 0, "passed"), "yes"), None, None),
    "error が数": (_set(("cases", 0, "arms", "with", 0, "error"), 5), None, None),
    "scored が文字": (_set(("cases", 0, "arms", "with", 0, "graders", 0, "scored"), "no"), None, None),
    "合格の線が 2": (_set(("suite", "threshold"), 2), None, None),
}

BROKEN_TEXT = {
    "壊れた JSON": ('{\n  "schemaVersion": 1,\n  oops\n}\n', "JSON として読めない（3 行目）"),
    "費用が NaN": (json.dumps(round_1b()).replace('"costUsd": 0.11', '"costUsd": NaN'), None),
    "一番上が並び": ("[]", None),
}


def _assert_one_line_stop(rc: int, out: str, err: str, tmp_path: Path, reason: str | None, hidden: str | None) -> None:
    assert rc == 1, (rc, out, err)
    assert out == "", "止まるときに標準出力へ出した（0 点や空の表を黙って出さない）"
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1, err
    assert lines[0].startswith("rounds.py: 2 番目の結果（2）: "), lines[0]
    if reason is not None:
        assert reason in lines[0], lines[0]
    for word in [str(tmp_path), LOCAL_ROOT, MODEL_TEXT, MAIL, *([hidden] if hidden else [])]:
        assert word not in lines[0], (word, lines[0])


@pytest.mark.parametrize("label", sorted(BROKEN))
def test_d0096_ac19_bad_input_stops_with_one_line(rounds, label, tmp_path, capsys):
    """D0096-AC-19: 鍵の欠け・形の違い（真偽の数・範囲の外・決まった形でない名前・重なり）・ケースが 0 件・schemaVersion 違いの JSON は、
    何も表を出さず、標準エラーに「rounds.py: <n> 番目の結果（<名前>）: <理由>」の 1 行を出して終了コード 1（パスと値は出さない）。"""
    broken = round_2()
    BROKEN[label][0](broken)
    good, bad = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", broken)
    rc, out, err = call(rounds, [f"1b={good}", f"2={bad}"], capsys)
    _assert_one_line_stop(rc, out, err, tmp_path, BROKEN[label][1], BROKEN[label][2])


@pytest.mark.parametrize("label", sorted(BROKEN_TEXT))
def test_d0096_ac19_bad_text_stops_with_one_line(rounds, label, tmp_path, capsys):
    """D0096-AC-19: JSON として読めない文字（行の番号を示す）・有限でない数（NaN）・一番上が対応表でない JSON も、1 行の理由と終了コード 1。"""
    text, reason = BROKEN_TEXT[label]
    assert label != "費用が NaN" or '"costUsd": NaN' in text, "NaN の見本が作れていない（テストの補助の誤り）"
    good, bad = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", text)
    rc, out, err = call(rounds, [f"1b={good}", f"2={bad}"], capsys)
    _assert_one_line_stop(rc, out, err, tmp_path, reason, None)


def test_d0096_ac19_missing_file_stops_with_one_line(rounds, tmp_path, capsys):
    """D0096-AC-19: 読めないファイル（無いパス）は、例外の型を添えた 1 行（読めない（FileNotFoundError））と終了コード 1。"""
    good = write(tmp_path, "r1.json", round_1b())
    rc, out, err = call(rounds, [f"1b={good}", f"2={tmp_path / 'nothing.json'}"], capsys)
    _assert_one_line_stop(rc, out, err, tmp_path, "読めない（FileNotFoundError）", "nothing.json")


def test_d0096_ac19_parse_round_raises_round_error(rounds):
    """D0096-AC-19: 純粋な関数 parse_round は、読めない JSON・鍵の欠けで RoundError を投げる（0 点の Round を返さない）。"""
    with pytest.raises(rounds.RoundError):
        rounds.parse_round("{")
    broken = round_1b()
    del broken["cases"][0]["aggregates"]
    with pytest.raises(rounds.RoundError):
        rounds.parse_round(json.dumps(broken))


# ---- AC-20：手元の情報を出さない ---------------------------------------------------------------------------------


def test_d0096_ac20_output_has_no_paths_mail_or_model_text(rounds, tmp_path, capsys):
    """D0096-AC-20: 偽の結果の JSON に入れた絶対パス（suite.root・cases[].dir・tracePath・evidence）・メールアドレス・モデルの返事の文
    （explanation・promptMarkdown・judgeVotes・error）が、集計の出力に出ない（出すのはケース名・採点の名前・数・合否だけ）。"""
    p1, p2 = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", round_2())
    rc, out, err = call(rounds, [f"1b={p1}", f"2={p2}"], capsys)
    assert rc == 0 and "build-passes-check" in out, (rc, out, err)  # 出力が出ていること（空の出力で通らないように）
    for word in [LOCAL_ROOT, "someone", MAIL, "@", MODEL_TEXT, "trace.jsonl", "t.jsonl", str(tmp_path), "Error:"]:
        assert word not in out + err, word
    assert local_info_in(out + err) == []


def test_d0096_ac20_study_folder_has_no_local_info_or_raw_json():
    """D0096-AC-20: 調査のフォルダには README.md と rounds.py があり、生の結果（.json）・__pycache__・秘密のファイルを置かず、
    どのファイルにも手元のパス・メールアドレス・鍵が無い。"""
    files = [p for p in STUDY.rglob("*") if p.is_file()]
    assert {"README.md", "rounds.py"} <= {p.name for p in files}
    assert [p.name for p in files if p.suffix == ".json"] == []
    assert [p for p in STUDY.rglob("__pycache__")] == []
    assert [p.name for p in files if SECRET_FILES.search(p.relative_to(STUDY).as_posix())] == []
    keys = [r"sk-[A-Za-z0-9_-]{8,}", r"ghp_[A-Za-z0-9]{10,}", r"BEGIN [A-Z ]*PRIVATE KEY", r"ANTHROPIC_API_KEY"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert local_info_in(text) == [], path.name
        assert [k for k in keys if re.search(k, text)] == [], path.name


# ---- AC-21：標準ライブラリだけ・書かない・起こさない -------------------------------------------------------------

ALLOWED_IMPORTS = {"__future__", "argparse", "json", "math", "re", "sys", "pathlib"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "breakpoint", "input"}
FORBIDDEN_ATTRS = {
    "write_text", "write_bytes", "mkdir", "touch", "unlink", "rmdir", "rename", "symlink_to", "hardlink_to", "chmod",
    "open", "system", "popen", "Popen", "spawnv", "urlopen", "import_module",
}


def test_d0096_ac21_script_imports_only_allowed_stdlib():
    """D0096-AC-21: rounds.py が import するのは __future__・argparse・json・math・re・sys・pathlib だけ（相対の import も無い）。
    今の作りのままで通る（空の形は __future__ と sys だけ。中身を書いても守り続ける）。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "相対の import"
            found.add((node.module or "").split(".")[0])
    assert found - ALLOWED_IMPORTS == set()


def test_d0096_ac21_script_has_no_write_or_process_calls():
    """D0096-AC-21: rounds.py に、ファイルを書く・開く・消す呼び出し、子プロセス・ネットワーク・動的な import・exec の呼び出しが無い
    （ファイルは Path(...).read_text で読む）。今の作りのままで通る（守り続ける）。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            bad.append(f"{node.func.id}()（{node.lineno} 行目）")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRS:
            bad.append(f".{node.func.attr}()（{node.lineno} 行目）")
    assert bad == []


def test_d0096_ac21_script_writes_nothing_when_run(rounds, tmp_path, monkeypatch, capsys):
    """D0096-AC-21: main を流す間、書き込み（Path の書く・作る・消す・名前を変える、書く形の open）・子プロセス・ネットワークを呼ぶと落ちる形にしても、
    終了コード 0 で終わり、tmp_path と調査のフォルダのファイルは増えも変わりもしない。今の作りのままで通る（守り続ける）。"""
    inputs = tmp_path / "in"
    p1, p2 = write(inputs, "r1.json", round_1b()), write(inputs, "r2.json", round_2())
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    before_tmp = {p.relative_to(tmp_path).as_posix(): p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    before_study = {p.relative_to(STUDY).as_posix(): p.stat().st_mtime_ns for p in STUDY.rglob("*")}

    def refuse(*args, **kwargs):
        raise AssertionError("書き込み・子プロセス・ネットワークを使った")

    real_open = builtins.open

    def read_only_open(file, mode="r", *args, **kwargs):
        if any(c in str(mode) for c in "wax+"):
            raise AssertionError(f"書く形で open した: {mode}")
        return real_open(file, mode, *args, **kwargs)

    with monkeypatch.context() as m:
        m.chdir(cwd)
        for name in ("write_text", "write_bytes", "mkdir", "touch", "unlink", "rmdir", "rename", "replace", "symlink_to"):
            m.setattr(Path, name, refuse)
        m.setattr(builtins, "open", read_only_open)
        m.setattr("subprocess.Popen", refuse)
        m.setattr("os.system", refuse)
        m.setattr("socket.socket", refuse)
        rc = rounds.main([f"1b={p1}", f"2={p2}"])
    capsys.readouterr()
    assert rc == 0
    assert {p.relative_to(tmp_path).as_posix(): p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before_tmp
    assert {p.relative_to(STUDY).as_posix(): p.stat().st_mtime_ns for p in STUDY.rglob("*")} == before_study


# ---- AC-46〜49：比べられない回（partial・skippedPaidGraders）と、読まない runsPerCase ----

NOT_COMPARABLE = "比べられない"
NOTE_PARTIAL = "注意：この回は途中で止まった（partial）。前の回との差は比べず、次の回の差の基準にもしない"
NOTE_NO_BASE = "注意：前に途中で止まっていない回が無いので、差は比べられない"
# 表の下の注意の行の決まった形（設計 18.3.3。名前の所は ARG_NAME・CASE_NAME の形だけ）。上の 4 つが新しく足す行
NOTE_PATTERNS = [
    re.compile(r"注意：この回は途中で止まった（partial）。前の回との差は比べず、次の回の差の基準にもしない"),
    re.compile(r"注意：差は回 [0-9A-Za-z][0-9A-Za-z.-]{0,15} と比べた（途中で止まった回 [0-9A-Za-z][0-9A-Za-z.-]{0,15}(・[0-9A-Za-z][0-9A-Za-z.-]{0,15})* は基準にしない）"),
    re.compile(r"注意：前に途中で止まっていない回が無いので、差は比べられない"),
    re.compile(r"注意：審査の採点が費用の上限で飛ばされた回を含むケース：[a-z0-9][a-z0-9-]*(・[a-z0-9][a-z0-9-]*)*（このケースの点は、前後の回と比べられない）"),
    re.compile(r"注意：(Claude Code の版|モデル|審査役)が前の回と違う（[^（）\n]+ → [^（）\n]+）。差は比べられないことがある"),
]


def note_based_on(base: str, between: list[str]) -> str:
    return f"注意：差は回 {base} と比べた（途中で止まった回 {'・'.join(between)} は基準にしない）"


def note_skipped(names: list[str]) -> str:
    return f"注意：審査の採点が費用の上限で飛ばされた回を含むケース：{'・'.join(names)}（このケースの点は、前後の回と比べられない）"


def run_rounds(rounds, folder: Path, capsys, named: list[tuple[str, dict]]) -> str:
    """名前と結果の JSON の並び（回の順）を folder に書いて流し、標準出力を返す（終了コード 0 であること）。"""
    argv = [f"{name}={write(folder, f'{name}.json', data)}" for name, data in named]
    rc, out, err = call(rounds, argv, capsys)
    assert rc == 0, err
    return out


def diff_cells(block: list[str]) -> dict[str, str]:
    """表のケースの名前 → 「前の回との差」の欄。"""
    return {cells[0]: cells[5] for cells in map(norm, table_rows(block))}


def one_case(name: str, score: float, skipped: bool | None = None, passed: bool = True) -> dict:
    """with が 1 回のケース（採点 01-x が 1 つ）。"""
    return case(name, score, [run(passed, [g("01-x", passed)], skipped=skipped)])


def ac47_rounds() -> list[tuple[str, dict]]:
    """a（途中で止まらない）・b（途中で止まった。ケースが少なく、Claude Code の版が違う）・c（途中で止まらない。a と同じ版）。
    c を b と比べると x は -0.20・y は「新しい」・版の注意が出る。a と比べると x は +0.20・y は 0.00・w は「新しい」・z が無いケース。"""
    a = result([one_case("x", 0.5), one_case("y", 0.8), one_case("z", 0.6, passed=False)], passed=2, overall=0.63, claude="2.1.323")
    b = result([one_case("x", 0.9)], passed=1, overall=0.9, claude="2.1.330", partial=True)
    c = result([one_case("w", 1.0), one_case("x", 0.7), one_case("y", 0.8)], passed=3, overall=0.83, claude="2.1.323")
    return [("a", a), ("b", b), ("c", c)]


def ac47_no_full_rounds() -> list[tuple[str, dict]]:
    """a（途中で止まった）・b（途中で止まらない）。b の前に、途中で止まっていない回が無い。"""
    a = result([one_case("x", 0.5)], passed=1, overall=0.5, partial=True)
    b = result([one_case("x", 0.7), one_case("y", 0.8)], passed=2, overall=0.75)
    return [("a", a), ("b", b)]


def ac48_rounds(*, b_y_skipped: bool = False) -> list[tuple[str, dict]]:
    """回 a：x は 2 回のうち 1 回だけ skippedPaidGraders が真（もう 1 回は偽）、y は鍵なし、v は偽。
    回 b：x は偽、y は鍵なし（b_y_skipped なら真）、v は偽。"""
    x_runs = [run(True, [g("01-x")], skipped=False), run(True, [g("01-x")], skipped=True)]
    a = result([case("x", 0.5, x_runs), one_case("y", 0.6), one_case("v", 0.4, skipped=False)], passed=3, overall=0.5)
    b = result([one_case("x", 0.7, skipped=False), one_case("y", 0.9, skipped=True if b_y_skipped else None), one_case("v", 0.5, skipped=False)], passed=3, overall=0.7)
    return [("a", a), ("b", b)]


def test_d0096_ac46_partial_round_diffs_are_not_comparable(rounds, tmp_path, capsys):
    """D0096-AC-46: partial が真の回は、その回のどのケースも「前の回との差」が「比べられない」になる（前の回に無いケースも「新しい」でなく）。
    表の下に、途中で止まったので差を比べず次の回の基準にもしない、という注意の行が出る。頭の 2 行（途中で止まった はい）と、
    点・合格の回・落ちた採点・エラーの回の欄は今までどおり（test_d0096_ac19_two_rounds_make_table_and_diff の回 2 と同じ値）。"""
    partial = round_2()
    partial["partial"] = True
    out = run_rounds(rounds, tmp_path, capsys, [("1b", round_1b()), ("2", partial)])
    two = round_block(out, "2")
    assert "- Claude Code 2.1.330・モデル haiku・審査役 haiku・回の数 1・合格の線 既定" in two
    assert "- 合格 2/4・全体の点 0.83・費用 $0.12・時間 400 秒・途中で止まった はい" in two
    assert [norm(r) for r in table_rows(two)] == [
        ["build-passes-check", "0.78", "0/1", "07-check-passed", "0", NOT_COMPARABLE],
        ["eval-result-json", "0.67", "0/1", "02-passed", "0", NOT_COMPARABLE],
        ["judge-rejects-bad-runs", "1.00", "1/1", "—", "0", NOT_COMPARABLE],
        ["run-dry-run-asks-first", "0.86", "1/1", "—", "0", NOT_COMPARABLE],
    ]
    assert NOTE_PARTIAL in two


def test_d0096_ac47_next_round_compares_with_last_full_round(rounds, tmp_path, capsys):
    """D0096-AC-47: 途中で止まった回（b）の次の回（c）は、その前の途中で止まっていない一番近い回（a）と比べる。差の値・「新しい」・
    前の回にあってこの回に無いケース・版の違いの注意は a に対して出る（b に対してではないので、版の注意は出ない）。
    表の下に「差は回 a と比べた（途中で止まった回 b は基準にしない）」が、前の回にあってこの回に無いケースの行より前に出る。"""
    out = run_rounds(rounds, tmp_path, capsys, ac47_rounds())
    c = round_block(out, "c")
    assert diff_cells(c) == {"w": "新しい", "x": "+0.20", "y": "0.00"}
    based, gone = note_based_on("a", ["b"]), "前の回にあってこの回に無いケース：z"
    assert based in c and gone in c, c
    assert c.index(based) < c.index(gone), c
    assert not [ln for ln in c if ln.startswith("注意：Claude Code の版")], c
    assert diff_cells(round_block(out, "b")) == {"x": NOT_COMPARABLE}


def test_d0096_ac47_no_full_round_before(rounds, tmp_path, capsys):
    """D0096-AC-47: 回 a（途中で止まった）・b（途中で止まらない）では、最初の回 a の差は —（途中で止まった回でも）で、表の下に途中で止まった注意。
    回 b は、前に途中で止まっていない回が無いので、どのケースも「比べられない」で、表の下にそのことの注意が出る。"""
    out = run_rounds(rounds, tmp_path, capsys, ac47_no_full_rounds())
    a, b = round_block(out, "a"), round_block(out, "b")
    assert diff_cells(a) == {"x": "—"}
    assert diff_cells(b) == {"x": NOT_COMPARABLE, "y": NOT_COMPARABLE}
    assert NOTE_PARTIAL in a
    assert NOTE_NO_BASE in b


def test_d0096_ac47_notes_have_only_names(rounds, tmp_path, capsys):
    """D0096-AC-47: AC-47 の 2 つの並びと AC-48 の 1 つ目の並びの出力に、手元のパス・メールアドレス・モデルの返事の文・tmp_path が無い。
    「注意：」で始まる行は、どれも決まった形（設計 18.3.3。名前の所は回とケースの名前の形だけ）にちょうど合い、新しい 4 つの形は出力のどこかに出る。"""
    outs = [
        run_rounds(rounds, tmp_path / "s1", capsys, ac47_rounds()),
        run_rounds(rounds, tmp_path / "s2", capsys, ac47_no_full_rounds()),
        run_rounds(rounds, tmp_path / "s3", capsys, ac48_rounds()),
    ]
    text = "\n".join(outs)
    for word in [LOCAL_ROOT, MAIL, MODEL_TEXT, str(tmp_path)]:
        assert word not in text, word
    assert local_info_in(text) == []
    notes = [ln for ln in text.splitlines() if ln.startswith("注意：")]
    unseen = [p.pattern for p in NOTE_PATTERNS[:4] if not any(p.fullmatch(ln) for ln in notes)]
    assert unseen == [], f"出るはずの注意の行が無い: {unseen}"
    odd = [ln for ln in notes if not any(p.fullmatch(ln) for p in NOTE_PATTERNS)]
    assert odd == [], f"決まった形でない注意の行: {odd}"


def test_d0096_ac48_skipped_paid_graders_not_comparable(rounds, tmp_path, capsys):
    """D0096-AC-48: skippedPaidGraders が真の回を含むケース（x。2 回のうち 1 回）は、その回の表の下にケースの名前が出て（最初の回でも）、
    その回を基準にする次の回で差が「比べられない」。鍵が無い（y）・偽（v）のケースは今までどおり数の差が出る。
    別の並びで、次の回の y に真を入れると、y も「比べられない」で、その回の表の下に y が出る。"""
    out = run_rounds(rounds, tmp_path / "s1", capsys, ac48_rounds())
    a, b = round_block(out, "a"), round_block(out, "b")
    assert diff_cells(b) == {"v": "+0.10", "x": NOT_COMPARABLE, "y": "+0.30"}
    assert diff_cells(a) == {"v": "—", "x": "—", "y": "—"}
    assert note_skipped(["x"]) in a
    assert not [ln for ln in b if ln.startswith("注意：審査の採点が費用の上限で")], b
    out = run_rounds(rounds, tmp_path / "s2", capsys, ac48_rounds(b_y_skipped=True))
    b = round_block(out, "b")
    assert diff_cells(b) == {"v": "+0.10", "x": NOT_COMPARABLE, "y": NOT_COMPARABLE}
    assert note_skipped(["y"]) in b


@pytest.mark.parametrize("value", ["yes", 1, None], ids=["string", "number", "null"])
def test_d0096_ac48_skipped_paid_graders_bad_shape_stops(rounds, value, tmp_path, capsys):
    """D0096-AC-48: skippedPaidGraders が真偽でない（文字・数・null）と、場所（cases[0].arms.with[0].skippedPaidGraders）を示す 1 行と
    終了コード 1 で止まり、標準出力に何も出さない（値は出さない）。"""
    broken = round_2()
    _set(("cases", 0, "arms", "with", 0, "skippedPaidGraders"), value)(broken)
    good, bad = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", broken)
    rc, out, err = call(rounds, [f"1b={good}", f"2={bad}"], capsys)
    _assert_one_line_stop(rc, out, err, tmp_path, "cases[0].arms.with[0].skippedPaidGraders が無いか、形が違う", "yes" if value == "yes" else None)


RUNS_PER_CASE_FORMS = {"missing": None, "zero": 0, "string": "3", "null": None}


@pytest.mark.parametrize("form", list(RUNS_PER_CASE_FORMS))
def test_d0096_ac49_runs_per_case_is_not_read(rounds, form, tmp_path, capsys):
    """D0096-AC-49: cases[].runsPerCase が無い・0・文字・null の結果も、止まらずに表を出す。回 2 の表の行と頭の行（回の数は arms.with の長さの 1）は、
    test_d0096_ac19_two_rounds_make_table_and_diff・test_d0096_ac19_head_lines_show_versions_and_cost の回 2 と同じ。"""
    data = round_2()
    for i in range(len(data["cases"])):
        if form == "missing":
            _drop(("cases", i, "runsPerCase"))(data)
        else:
            _set(("cases", i, "runsPerCase"), RUNS_PER_CASE_FORMS[form])(data)
    p1, p2 = write(tmp_path, "r1.json", round_1b()), write(tmp_path, "r2.json", data)
    rc, out, err = call(rounds, [f"1b={p1}", f"2={p2}"], capsys)
    assert rc == 0, err
    two = round_block(out, "2")
    assert [norm(r) for r in table_rows(two)] == [
        ["build-passes-check", "0.78", "0/1", "07-check-passed", "0", "-0.22"],
        ["eval-result-json", "0.67", "0/1", "02-passed", "0", "0.00"],
        ["judge-rejects-bad-runs", "1.00", "1/1", "—", "0", "+0.50"],
        ["run-dry-run-asks-first", "0.86", "1/1", "—", "0", "新しい"],
    ]
    assert "- Claude Code 2.1.330・モデル haiku・審査役 haiku・回の数 1・合格の線 既定" in two
    assert "- 合格 2/4・全体の点 0.83・費用 $0.12・時間 400 秒・途中で止まった いいえ" in two
