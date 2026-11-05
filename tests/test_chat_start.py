"""D0076-AC-01〜06：会話の中でパイプを流す道の「始める・断る」（pipe-in-gen chat start）。

SDK は呼ばない（no_sdk）。パイプは tmp_path の下の .pipe-in/pipes/pipe-in-<名前>/ に作り、--project で流す。
外の入口 chat_cmd.main(argv) だけを通す（標準出力の JSON と終了コードを読む）。
"""

from __future__ import annotations

import json

import pytest
from chat_support import OK_CMD, Run, no_sdk, pipe_toml, stage_toml, text_of  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_sdk")

DEMO = "docs/pipeline/hp"


def full_pipe() -> str:
    """4つの access・writes・bash・review・verdict・command・next を持つ、扱える形のパイプ。"""
    return pipe_toml(
        stage_toml("survey", access="read", output="01_survey.md"),
        stage_toml("design", access="docs", docs_dir="docs/out", output="02_design.md", extra="review = true\n"),
        stage_toml("tests", access="tests", output="03_tests.md", extra='bash = true\nwrites = ["tests/unit/*"]\n'),
        stage_toml(
            "impl",
            access="code",
            output="04_impl.md",
            extra=f"bash = true\nwrites = [\"src/*\"]\n[stages.check]\ncommand = '{OK_CMD}'\nmax_retries = 2\non_fail = \"impl\"\ntimeout_sec = 60\n",
        ),
        stage_toml("verify", access="read", output="05_verify.md", extra='next = "end"\n[stages.check]\nverdict = true\n'),
    )


def test_d0076_ac01_扱える形のパイプで始めると記録ができる(tmp_path):
    """D0076-AC-01: 扱える形のパイプで chat start すると、00_input.md と state.json ができ、driver が pipe-chat、stages が定義の並びになる。"""
    r = Run(tmp_path)
    r.make(full_pipe())
    out = r.start(memo="図を描いてほしい")
    assert r.code == 0 and out["ok"] is True, out
    assert out["action"] == "started"
    assert "chat probe" in text_of(out), "次にすること（chat probe）を伝える"
    state = r.state()
    assert state["driver"] == "pipe-chat"
    assert [s["name"] for s in state["stages"]] == ["survey", "design", "tests", "impl", "verify"]
    assert [s["output"] for s in state["stages"]] == ["01_survey.md", "02_design.md", "03_tests.md", "04_impl.md", "05_verify.md"]
    assert [s["review"] for s in state["stages"]] == [False, True, False, False, False]
    assert state["final"] is None and state["runs"] == [] and state["open"] is None
    assert "図を描いてほしい" in (r.run_dir / "00_input.md").read_text(encoding="utf-8")


def test_d0076_ac01_dry_runの表は段の並びを見せる(tmp_path):
    """D0076-AC-01: 段の表を見せる（開始の確認の前に使う）。"""
    r = Run(tmp_path)
    r.make(full_pipe())
    out = r.start("--dry-run")
    assert r.code == 0 and out["ok"] is True, out
    text = text_of(out)
    for name in ["survey", "design", "tests", "impl", "verify"]:
        assert name in text, name


# ---- AC-02：扱わない形 ----------------------------------------------------------------------

BAD_COMMAND = f"command = '{OK_CMD}'\n"

# (id, 段の extra, 追加の段, pipe.toml の head, pipeline.toml の中身, start の追加引数, 出力に入るはずの言葉)
BAD_SHAPES = [
    ("group", 'group = "g"\n', stage_toml("other", extra='group = "g"\n'), "", None, [], "group"),
    ("routes", '[stages.routes]\nok = "end"\n', "", "", None, [], "routes"),
    (
        "check-judge",
        f"[stages.check]\n{BAD_COMMAND}[stages.check.judge]\nthreshold = 0.7\n[[stages.check.judge.criteria]]\nname = \"a\"\ndescription = \"b\"\n",
        "",
        "",
        None,
        [],
        "judge",
    ),
    ("agents", '[stages.agents.helper]\ndescription = "d"\nprompt = "p"\ntools = ["Read"]\n', "", "", None, [], "agents"),
    ("mcp", 'mcp = ["mcp__srv__tool"]\n', "", "", None, [], "mcp"),
    (
        "mcp_servers",
        'mcp = ["mcp__srv__*"]\n[stages.mcp_servers.srv]\ntype = "stdio"\ncommand = "srv"\n',
        "",
        "",
        None,
        [],
        "mcp_servers",
    ),
    ("web-true", "web = true\n", "", "", None, [], "web"),
    ("web-domains", 'web = ["docs.python.org"]\n', "", "", None, [], "web"),
    ("max_budget_usd-pipe", "max_budget_usd = 1.0\n", "", "", None, [], "max_budget_usd"),
    ("max_budget_usd-pipeline", "", "", "", "[stages.s]\nmax_budget_usd = 1.0\n", [], "max_budget_usd"),
    ("after", "", "", "", None, ["--after", "prev"], "after"),
    ("dev", "", "", 'kind = "dev"\n', None, [], "dev"),
]


def bad_pipe(extra: str, more: str, head: str) -> str:
    if head:  # kind = "dev" は [pipe] の kind を書き換え、段を持たない
        return '[pipe]\nkind = "dev"\nlabel = "試し"\n'
    return pipe_toml(stage_toml("s", extra=extra), more)


@pytest.mark.parametrize("shape", BAD_SHAPES, ids=[s[0] for s in BAD_SHAPES])
def test_d0076_ac02_扱わない形を1つだけ持つパイプは記録を作らず断る(tmp_path, shape):
    """D0076-AC-02: group・routes・check.judge・agents・mcp・mcp_servers・web・max_budget_usd・前の実行の受け取り・kind=dev は、
    記録を作らず、その形の名前を含む文で断る（終了コードは 0 以外）。"""
    _, extra, more, head, pipeline_toml, args, needle = shape
    r = Run(tmp_path)
    r.make(bad_pipe(extra, more, head), valid=False)
    if pipeline_toml is not None:
        (tmp_path / "pipeline.toml").write_text(pipeline_toml, encoding="utf-8")
    out = r.start(*args)
    assert r.code != 0 and out["ok"] is False, out
    assert needle in text_of(out), f"断る文に「{needle}」が無い: {out}"
    assert not (r.run_dir / "state.json").exists(), "断ったのに記録ができている"
    assert not (r.run_dir / "00_input.md").exists()


def test_d0076_ac02_dry_runでも扱わない形は断る(tmp_path):
    """D0076-AC-02: --dry-run でも、扱わない形は断る（何も書かない）。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s", extra="web = true\n")))
    out = r.start("--dry-run")
    assert r.code != 0 and out["ok"] is False and "web" in text_of(out), out
    assert not (tmp_path / "docs").exists()


def test_d0076_ac03_断る形が複数あると理由が全部出る(tmp_path):
    """D0076-AC-03: 断る形を複数持つパイプでは、最初の1つで止まらず、理由が全部出る。"""
    r = Run(tmp_path)
    r.make(
        pipe_toml(
            stage_toml("a", extra="web = true\n"),
            stage_toml("b", extra='[stages.routes]\nok = "end"\n'),
            stage_toml("c", extra="max_budget_usd = 2.0\n"),
        ),
        valid=False,
    )
    out = r.start("--after", "prev")
    assert r.code != 0 and out["ok"] is False, out
    text = text_of(out)
    for needle in ["web", "routes", "max_budget_usd", "after"]:
        assert needle in text, f"理由に「{needle}」が出ていない: {text}"
    assert not (r.run_dir / "state.json").exists()


# ---- AC-04：効かない設定は断らず、一覧に出す -----------------------------------------------

INEFFECTIVE = [
    ("model", 'model = "sonnet"\n'),
    ("max_turns", "max_turns = 5\n"),
    ("max_thinking_tokens", "max_thinking_tokens = 2000\n"),
    ("fallback_model", 'fallback_model = "haiku"\n'),
    ("permission_mode", 'permission_mode = "acceptEdits"\n'),
    ("add_dirs", 'add_dirs = ["docs"]\n'),
]


@pytest.mark.parametrize("key,line", INEFFECTIVE, ids=[k for k, _ in INEFFECTIVE])
def test_d0076_ac04_効かない設定は断らず一覧に出す(tmp_path, key, line):
    """D0076-AC-04: model・max_turns・max_thinking_tokens・fallback_model・permission_mode・add_dirs は、断らず、start の出力の「効かない設定」の一覧に出る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s", extra=line)))
    out = r.start()
    assert r.code == 0 and out["ok"] is True, out
    text = text_of(out)
    assert "効かない設定" in text, text
    assert key in text, f"一覧に {key} が出ていない: {text}"
    assert (r.run_dir / "state.json").exists()


def test_d0076_ac04_pipeline_tomlの段の設定も効かない設定に出る(tmp_path):
    """D0076-AC-04: pipeline.toml の [stages.<段>] の model・max_turns も、断らず一覧に出る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s")))
    (tmp_path / "pipeline.toml").write_text('[stages.s]\nmodel = "sonnet"\nmax_turns = 3\n', encoding="utf-8")
    out = r.start()
    assert r.code == 0 and out["ok"] is True, out
    text = text_of(out)
    assert "効かない設定" in text and "model" in text and "max_turns" in text, text


def test_d0076_ac04_dry_runは何も書かずに表と効かない設定を返す(tmp_path):
    """D0076-AC-04: --dry-run は、段の表と効かない設定を返し、何も書かない（開始の確認の前に見せるため）。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s", extra='model = "sonnet"\n')))
    out = r.start("--dry-run")
    assert r.code == 0 and out["ok"] is True, out
    assert "効かない設定" in text_of(out) and "model" in text_of(out)
    assert not (tmp_path / "docs").exists(), "dry-run が記録の置き場所を作った"


# ---- AC-05：定義の誤り ------------------------------------------------------------------------


def test_d0076_ac05_段の名前の重複で断る(tmp_path):
    """D0076-AC-05: check_pipe が誤りを返す定義（段の名前の重複）では、記録を作らず、その誤りを出して断る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a", output="1.md"), stage_toml("a", output="2.md")), valid=False)
    out = r.start()
    assert r.code != 0 and out["ok"] is False, out
    assert "重複" in text_of(out), out
    assert not (r.run_dir / "state.json").exists()


def test_d0076_ac05_飛び先の段が無いと断る(tmp_path):
    """D0076-AC-05: next の飛び先の段が無い定義では、記録を作らず、その誤りを出して断る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a", extra='next = "nowhere"\n')), valid=False)
    out = r.start()
    assert r.code != 0 and out["ok"] is False, out
    assert "nowhere" in text_of(out), out
    assert not (r.run_dir / "state.json").exists()


def test_d0076_ac05_パイプが見つからないと断る(tmp_path):
    """D0076-AC-05: パイプが見つからないときも、記録を作らず断る。"""
    r = Run(tmp_path)
    out = r.start()
    assert r.code != 0 and out["ok"] is False, out
    assert not (r.run_dir / "state.json").exists()


def test_d0076_ac05_input_requiredで要件メモが無いと断る(tmp_path):
    """D0076-AC-05: input = "required" のパイプは、要件メモ（--memo）が無いと、記録を作らず断る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a"), head='input = "required"\n'))
    out = r.cmd("start")
    assert r.code != 0 and out["ok"] is False, out
    assert not (r.run_dir / "state.json").exists()


# ---- AC-06：途中の記録 ------------------------------------------------------------------------


def test_d0076_ac06_途中の記録があると断り記録は変わらない(tmp_path):
    """D0076-AC-06: 段が開いたままの途中の記録があるとき chat start は断る（record start と同じ）。記録は変わらない。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a"), stage_toml("b")))
    r.run_next("a")
    before = r.state_text()
    memo_before = (r.run_dir / "00_input.md").read_text(encoding="utf-8")
    out = r.start(memo="別のメモ")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before
    assert (r.run_dir / "00_input.md").read_text(encoding="utf-8") == memo_before
    assert not (r.run_dir / "archive").exists(), "断ったのに archive へ移した"


def test_d0076_ac06_終わった記録はarchiveへ移り新しい記録が始まる(tmp_path):
    """D0076-AC-06: 終わった記録は archive/ へ移る（state.json・00_input.md・logs・99_summary.md と、hook/・probe/ も）。新しい記録はまっさら。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a")))
    r.run_and_finish("a")
    assert r.state()["final"] == "PASSED"
    assert (r.run_dir / "hook" / "trace.jsonl").is_file(), "確かめでフックが跡を残している（archive へ一緒に移る対象）"
    out = r.start(memo="次のメモ")
    assert r.code == 0 and out["ok"] is True, out
    moved = list((r.run_dir / "archive").glob("*"))
    assert len(moved) == 1, moved
    for name in ["state.json", "00_input.md", "99_summary.md", "logs", "hook", "probe"]:
        assert (moved[0] / name).exists(), f"archive に {name} が移っていない"
    new = r.state()
    assert new["final"] is None and new["runs"] == [] and new["open"] is None
    assert not (r.run_dir / "hook").exists() and not (r.run_dir / "logs").exists()
    assert "次のメモ" in (r.run_dir / "00_input.md").read_text(encoding="utf-8")


def test_d0076_ac06_始めたばかりで段が無い記録は途中ではなくやり直せる(tmp_path):
    """D0076-AC-06: 段をまだ始めていない記録（runs・open・pending_review が空）は途中ではなく、もう一度 start できる。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a")))
    assert r.start(memo="一つ目")["ok"] is True
    out = r.start(memo="二つ目")
    assert r.code == 0 and out["ok"] is True, out
    assert "二つ目" in (r.run_dir / "00_input.md").read_text(encoding="utf-8")
    assert json.loads(r.state_text())["driver"] == "pipe-chat"
