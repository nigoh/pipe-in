"""D0096-AC-33〜37：警告 W8（審査（judge）の不合格で on_fail へ差し戻すのに、機械の検査（command）が無い）。SDK は呼ばない。定義は tmp_path に書く。

段の TOML・定義の作り方・プロジェクトのフォルダは tests/test_pipe_lint.py の補助を、ガイドの節の読み方は tests/test_guide.py の補助を使う（書き写さない）。
W8 を拾う語は、実装の定数を読まずにここへ書く（文が勝手に変わったら赤になるように）。
ひな形は pipe-in-gen new（cli.main）で tmp_path に写す（本物の pipes/ を見ないよう、isolate_pipes で置き場所を差し替える）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_guide import GUIDE, heading_part, read_doc
from test_pipe_lint import FINDING_PROMPT, isolate_pipes, make_pipe, project, stage_toml  # noqa: F401

from pipe_in.pipe.definition import check_pipe, load_pipe
from pipe_in.pipe.lint import lint_pipe
from pipe_in_generator import cli

ROOT = Path(__file__).resolve().parents[1]
W8_MARK = "機械の検査（command）がありません"


# ---- 補助 -----------------------------------------------------------------------------------------------


def judge_toml() -> str:
    """stage_toml(...) の後ろにつなぐ審査の表（[stages.check.judge] と項目 1 つ）。check_pipe が誤りを返さない形。"""
    return '[stages.check.judge]\n[[stages.check.judge.criteria]]\nname = "clarity"\ndescription = "読みやすい"\n'


def w8(warnings: list[str]) -> list[str]:
    return [w for w in warnings if W8_MARK in w]


def heads(warnings: list[str]) -> list[str]:
    """警告の頭（「段 i（名前）」）の並び。"""
    return [w.split(": ", 1)[0] for w in warnings]


def w8_stages(**check) -> list[str]:
    """2 段（write は docs・review は read）。review に judge と、check の行（on_fail・verdict・command など）を書く。"""
    return [stage_toml("write", access="docs"), stage_toml("review", **check) + judge_toml()]


# ---- AC-33：W8 が出る形 -----------------------------------------------------------------------------------

W8_FORMS = {
    "ほかの段へ": {"on_fail": "write"},
    "自分へ": {"on_fail": "review"},
    "verdict もある": {"on_fail": "write", "verdict": True},
}


@pytest.mark.parametrize("form", list(W8_FORMS))
def test_d0096_ac33_w8_judge_on_fail_without_command(tmp_path, form):
    """D0096-AC-33: check に judge と on_fail（ほかの段を指す・自分を指す・verdict もある）があり command が無い段に、lint_pipe が W8 を 1 件だけ出す。
    文は「段 2（review）: 」で始まる。定義そのものは誤りではない（check_pipe は []）。"""
    pipe = make_pipe(tmp_path, w8_stages(**W8_FORMS[form]))
    assert pipe.stages[1].check is not None and pipe.stages[1].check.judge is not None, "審査の表が読めていない（補助の誤り）"
    assert check_pipe(pipe, project(tmp_path)) == []
    warnings = lint_pipe(pipe)
    found = w8(warnings)
    assert len(found) == 1, warnings
    assert found[0].startswith("段 2（review）: "), found


def test_d0096_ac33_w8_text_has_rule_and_fixes(tmp_path):
    """D0096-AC-33: W8 の文に、judge・on_fail・command と、直し方の 2 つ（command と組む・on_fail を書かずに指摘だけにする）がある。"""
    found = w8(lint_pipe(make_pipe(tmp_path, w8_stages(on_fail="write"))))
    assert len(found) == 1, found
    missing = [w for w in ["judge", "on_fail", "command", "組", "指摘だけ"] if w not in found[0]]
    assert missing == [], found[0]


# ---- AC-34：W8 が出ない形 ---------------------------------------------------------------------------------

# 形の名前 → (review の段の check の行, judge を足すか)
NOT_W8_FORMS: dict[str, tuple[dict, bool]] = {
    "judge だけ": ({"has_check": True}, True),
    "judge と verdict": ({"verdict": True}, True),
    "verdict と on_fail": ({"verdict": True, "on_fail": "write"}, False),
    "command と on_fail": ({"command": "pytest -q", "on_fail": "write"}, False),
    "judge と on_fail と command": ({"command": "pytest -q", "on_fail": "write"}, True),
}


@pytest.mark.parametrize("form", list(NOT_W8_FORMS))
def test_d0096_ac34_w8_not_raised(tmp_path, form):
    """D0096-AC-34: on_fail を書かない段（judge だけ・judge と verdict）・judge の無い段（verdict と on_fail・command と on_fail）・
    command のある段（judge と on_fail と command）には、W8 が出ない。どれも定義そのものは誤りではない（check_pipe は []）。"""
    check, judged = NOT_W8_FORMS[form]
    review = stage_toml("review", **check) + (judge_toml() if judged else "")
    pipe = make_pipe(tmp_path, [stage_toml("write", access="docs"), review])
    assert (pipe.stages[1].check is not None and pipe.stages[1].check.judge is not None) is judged, "審査の表の有無が形と違う（補助の誤り）"
    assert check_pipe(pipe, project(tmp_path)) == []
    assert w8(lint_pipe(pipe)) == []


# ---- AC-35：今の警告の文と順を変えない・pipe-in-gen check ---------------------------------------------------


def base_stages() -> list[str]:
    """D0053-AC-10（D0038-AC-10）と同じ 3 段：W1（a）・W3（red）・W5（verify）が 1 件ずつ。"""
    return [
        stage_toml("a", bash=True, prompt="下書きを保存する"),
        stage_toml("red", access="tests"),
        stage_toml("verify", verdict=True, on_fail="a", command="pytest -q"),
    ]


def fix_stage(*, judged: bool) -> str:
    """4 段目 fix：docs_dir = ".claude" で W7、指摘を出す指示文で W6、verdict と on_fail = "a"（read の段）で W5。judged なら judge を足して W8 の形にする。
    stage_toml は docs の段に docs_dir = "work" を足すので、TOML の文字を直に書く。"""
    text = (
        '[[stages]]\nname = "fix"\nlabel = "fix の段"\noutput = "fix.md"\naccess = "docs"\ndocs_dir = ".claude"\n'
        f"prompt = {json.dumps(FINDING_PROMPT, ensure_ascii=False)}\n"
        '[stages.check]\nverdict = true\non_fail = "a"\n'
    )
    return text + (judge_toml() if judged else "")


def test_d0096_ac35_w8_is_last_and_keeps_existing_warnings(tmp_path):
    """D0096-AC-35・NFR-05: W1・W3・W5・W6・W7 が出る定義（前）の 4 段目に judge を足して W8 の形にした定義（後）では、
    前の警告 6 件の文と順はそのままで、その後ろに「段 4（fix）: 」で始まる W8 が 1 件だけ足される。どちらも check_pipe は []。"""
    proj = project(tmp_path)
    before_pipe = make_pipe(tmp_path / "before", [*base_stages(), fix_stage(judged=False)])
    after_pipe = make_pipe(tmp_path / "after", [*base_stages(), fix_stage(judged=True)])
    before = lint_pipe(before_pipe)
    # 前の定義の確かめ（補助の誤りを赤と取り違えないため）：W1・W3・W5、4 段目の W5・W6・W7 の順に 6 件
    assert heads(before) == ["段 1（a）", "段 2（red）", "段 3（verify）", "段 4（fix）", "段 4（fix）", "段 4（fix）"], before
    assert 'access = "read"' in before[3] and "findings-check" in before[4] and "既定で守る場所" in before[5], before
    assert w8(before) == [], before
    assert check_pipe(before_pipe, proj) == []
    assert check_pipe(after_pipe, proj) == []
    after = lint_pipe(after_pipe)
    assert after[:6] == before, after
    assert len(after) == 7, after
    assert after[6].startswith("段 4（fix）: ") and W8_MARK in after[6], after


def test_d0096_ac35_w8_follows_stage_order(tmp_path):
    """D0096-AC-35: 1 段目に W8 の形（judge と自分への on_fail）、2 段目に W6 の形（指摘を出す指示文）の定義で、警告は「段 1 の W8 → 段 2 の W6」の順に並ぶ。"""
    pipe = make_pipe(tmp_path, [stage_toml("review", on_fail="review") + judge_toml(), stage_toml("find", prompt=FINDING_PROMPT)])
    warnings = lint_pipe(pipe)
    assert heads(warnings) == ["段 1（review）", "段 2（find）"], warnings
    assert W8_MARK in warnings[0] and "findings-check" in warnings[1], warnings


def test_d0096_ac35_check_cli_prints_w8_and_exits_0(tmp_path, capsys):
    """D0096-AC-35・NFR-05: W8 だけが出る定義を pipe-in-gen check に通すと、終了コード 0 で、「✓ パイプ「w8」: 誤りはありません（注意 1 件）」の行と、
    W8 を含む ⚠ の行を 1 つ出す（誤りにしない）。"""
    proj = project(tmp_path)
    make_pipe(tmp_path, w8_stages(on_fail="write"), folder="pipe-in-w8", base=tmp_path / "pipes")
    code = cli.main(["check", "w8", "--pipes-dir", str(tmp_path / "pipes"), "--project", str(proj)])
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert code == 0, out
    assert "✓ パイプ「w8」: 誤りはありません（注意 1 件）" in lines, out
    marks = [ln for ln in lines if ln.startswith("⚠")]
    assert len(marks) == 1 and W8_MARK in marks[0], out
    assert "✗" not in out, out


# ---- AC-36：ひな形と見本には出ない ---------------------------------------------------------------------------

TEMPLATE_NAMES = ["dev", "diagrams", "spec-qa", "spec-review", "review-quorum"]
EXAMPLE_NAMES = ["diagrams", "spec-qa", "research", "video"]
SOURCES = [("ひな形", n) for n in TEMPLATE_NAMES] + [("見本", n) for n in EXAMPLE_NAMES]
# 審査（judge）を持つ段があるもの（設計 17.7）。審査の確かめが空回りしないよう、これらには審査の段があることも見る
JUDGED = {("ひな形", "diagrams"), ("見本", "diagrams"), ("見本", "research")}


def load_source(tmp_path: Path, kind: str, name: str):
    if kind == "見本":
        return load_pipe(ROOT / "examples" / name / "pipes" / f"pipe-in-{name}")
    proj = project(tmp_path)
    assert cli.main(["new", f"my-{name}", "--from", name, "--project", str(proj), "--pipes-dir", str(tmp_path / "pipes")]) == 0
    return load_pipe(tmp_path / "pipes" / f"pipe-in-my-{name}")


@pytest.mark.usefixtures("isolate_pipes")
@pytest.mark.parametrize("kind,name", SOURCES, ids=[f"{k}-{n}" for k, n in SOURCES])
def test_d0096_ac36_templates_and_examples_have_no_w8(tmp_path, kind, name):
    """D0096-AC-36: ひな形 5 つ（pipe-in-gen new で tmp_path に写したもの）と見本（examples/ の 4 つ）に、W8 が出ない。
    審査（judge）を持つ段（diagrams のひな形と見本・research の見本）は、command と on_fail を両方持つ。"""
    pipe = load_source(tmp_path, kind, name)
    assert w8(lint_pipe(pipe)) == []
    judged = [s for s in pipe.stages if s.check is not None and s.check.judge is not None]
    if (kind, name) in JUDGED:
        assert judged, f"{kind} {name} に審査を持つ段が無い"
    for s in judged:
        assert s.check.command and s.check.on_fail, (kind, name, s.name)


# ---- AC-37：ガイドの「検査の警告」 ---------------------------------------------------------------------------

PIPES_MD_W8_WORDS = ["judge", "on_fail", "command", "指摘だけ"]


def test_d0096_ac37_pipes_md_lists_six_warnings_with_w8():
    """D0096-AC-37: docs/guide/pipes.md の「検査の警告」の節が「警告は6つ」と書き（「警告は5つ」は残らない）、W8 の説明（judge・on_fail・command・指摘だけ）を持つ。"""
    part = heading_part(read_doc(GUIDE / "pipes.md"), "検査の警告")
    assert part.strip(), "「検査の警告」の節が無い"
    got = {
        "警告は6つ がある": "警告は6つ" in part,
        "警告は5つ が残る": "警告は5つ" in part,
        "無い語": [w for w in PIPES_MD_W8_WORDS if w not in part],
    }
    assert got == {"警告は6つ がある": True, "警告は5つ が残る": False, "無い語": []}
