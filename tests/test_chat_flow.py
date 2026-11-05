"""D0076-AC-12〜21・AC-36：段の順番・確認・差し戻し・終わり（pipe-in-gen chat next / done / review / status）。

SDK は呼ばない（no_sdk）。サブエージェントの仕事は、テストが成果物のファイルを書くことで真似る。
確認用コマンド（check.command）は、tmp_path の中の小さな python スクリプトを本物で流す。
外の入口 chat_cmd.main(argv) だけを通し、記録は state.json（設計 4.1 の鍵）で確かめる。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from chat_support import PY, Run, no_sdk, pipe_toml, stage_toml, text_of  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_sdk")


def two(*, review: bool = False, a_extra: str = "") -> str:
    return pipe_toml(stage_toml("a", extra=("review = true\n" if review else "") + a_extra), stage_toml("b"))


def check_command(tmp_path: Path) -> tuple[str, Path]:
    """合格するには ok.flag が要る確認用コマンド。落ちるときは標準エラーに boom-marker を出す。"""
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    script = tools / "check.py"
    script.write_text(
        "import pathlib, sys\n"
        "if pathlib.Path(__file__).with_name('ok.flag').exists():\n"
        "    sys.exit(0)\n"
        "sys.stderr.write('boom-marker: 失敗しました\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    return f'"{PY}" "{script}"', tools / "ok.flag"


def cmd_check(command: str, retries: int, on_fail: str | None = None) -> str:
    fail = f'on_fail = "{on_fail}"\n' if on_fail else ""
    return f"[stages.check]\ncommand = '{command}'\nmax_retries = {retries}\n{fail}"


# ---- AC-12 ----------------------------------------------------------------------------------


def test_d0076_ac12_nextは最初の段を返しopenに記録しもう一度呼んでも二重に始めない(tmp_path):
    """D0076-AC-12: 確かめ済みなら chat next は最初の段の指示（段の名前・pipe-stage を呼ぶこと・指示文・書ける範囲の説明）を返し、
    open に段が記録される。段が開いている間にもう一度 chat next しても、同じ段を返し、二重に始めない。"""
    r = Run(tmp_path)
    r.ready(two())
    out = r.run_next("a")
    assert out["agent"].endswith("pipe-stage") and out["kind"] == "stage" and out["resumed"] is False and out["run"] == 1
    assert out["output"] == "docs/pipeline/hp/a.md"
    prompt = r.prompt_of(out)
    assert "aをする" in prompt, "段の指示文が入る"
    assert "docs/pipeline/hp/a.md" in prompt, "書くものの場所が指示に入る"
    assert out["scope"]["access"] == "read" and out["scope"]["hint"], out["scope"]
    state = r.state()
    assert state["open"]["stage"] == "a" and state["open"]["seq"] == 1
    assert state["chat"]["steps"] == 1
    logs = r.logs()
    assert len(logs) == 1

    again = r.run_next("a")
    assert again["resumed"] is True and again["agent_prompt"] == out["agent_prompt"]
    assert r.state()["open"]["seq"] == 1 and r.state()["chat"]["steps"] == 1
    assert r.logs() == logs, "二重に始めた（ログが増えた）"


def test_d0076_ac12_本体の段の指示文と同じ決まりを先頭に置く(tmp_path):
    """D0076-AC-12: 指示文には、段の決まり（system_append）と、渡すもの（依頼メモ・前の段の成果物）が入る。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra='system_append = "ここだけの決まり"\n'), stage_toml("b")))
    first = r.run_next("a")
    assert "ここだけの決まり" in r.prompt_of(first)
    assert "00_input.md" in r.prompt_of(first), "依頼メモを渡す"
    r.finish("a")
    second = r.run_next("b")
    assert "docs/pipeline/hp/a.md" in r.prompt_of(second), "前の段の成果物を渡す"


# ---- AC-13 ----------------------------------------------------------------------------------


def test_d0076_ac13_reviewのある段が閉じるとnextは確認待ちを返す(tmp_path):
    """D0076-AC-13: review = true の段が chat done で閉じると、chat next は「人の確認を待つ」を返し、pending_review が記録される。承認の前に次の段は始まらない。"""
    from pipe_in.dev.record_order import check_dir

    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_and_finish("a")
    out = r.next()
    assert out["action"] == "await_review", out
    assert r.state()["pending_review"]["stage"] == "a"
    assert r.state()["open"] is None
    assert "docs/pipeline/hp/a.md" in text_of(out), "確認する成果物の場所を出す"
    assert r.next()["action"] == "await_review", "何度呼んでも次の段は始まらない"
    assert r.logs() == [r.logs()[0]] and "_a" in r.logs()[0], r.logs()
    report = check_dir(r.run_dir)
    assert report.violations == ()


# ---- AC-14 ----------------------------------------------------------------------------------


def test_d0076_ac14_approvedで次の段へ進む(tmp_path):
    """D0076-AC-14: chat review approved で次の段へ進む。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_and_finish("a")
    r.next("await_review")
    out = r.review("approved")
    assert r.code == 0 and out["ok"] is True and out["action"] == "reviewed", out
    assert r.state()["pending_review"] is None
    assert r.reviews()[-1]["stage"] == "a" and r.reviews()[-1]["review"] == "approved" and r.reviews()[-1].get("at")
    r.run_next("b")
    assert r.state()["chat"]["steps"] == 2


def test_d0076_ac14_reviseはfeedbackが無いと断られ記録は変わらない(tmp_path):
    """D0076-AC-14: revise は --feedback が無ければ断られる（記録は変わらない）。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_and_finish("a")
    r.next("await_review")
    before = r.state_text()
    out = r.review("revise")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before
    out = r.review("revise", "   ")
    assert r.code != 0 and out["ok"] is False, "空白だけの指摘も断る"
    assert r.state_text() == before


def test_d0076_ac14_reviseは同じ段を直す点つきで何回目かを増やして返す(tmp_path):
    """D0076-AC-14: revise は同じ段が「直してほしい点」つきで、何回目かを増やして返る。steps・retries は変わらない。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_and_finish("a")
    r.next("await_review")
    out = r.review("revise", "ここを直して")
    assert r.code == 0 and out["ok"] is True, out
    assert r.reviews()[-1]["review"] == "revise" and r.reviews()[-1]["feedback"] == "ここを直して"
    again = r.run_next("a")
    assert again["kind"] == "revise" and again["run"] == 2 and again["resumed"] is False
    assert "ここを直して" in r.prompt_of(again), "直してほしい点が指示に入る"
    state = r.state()
    assert state["chat"]["steps"] == 1, "revise は steps を増やさない"
    assert state["chat"]["retries"] == {}, "revise は retries を増やさない"
    assert state["pending_review"] is None and state["open"]["stage"] == "a"
    assert len(r.logs()) == 2
    r.finish("a")
    assert r.next()["action"] == "await_review", "直したあともう一度確認を待つ"
    r.review("approved")
    r.run_next("b")


def test_d0076_ac14_quitで中止になる(tmp_path):
    """D0076-AC-14: quit で終了の種類が中止（STOPPED_BY_HUMAN）になり、99_summary.md ができ、次は「終わり」を返す。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_and_finish("a")
    r.next("await_review")
    out = r.review("quit")
    assert r.code == 0 and out["ok"] is True, out
    state = r.state()
    assert state["final"] == "STOPPED_BY_HUMAN" and state["pending_review"] is None
    assert r.reviews()[-1]["review"] == "quit"
    assert (r.run_dir / "99_summary.md").is_file()
    done = r.next()
    assert done["action"] == "finished", done


def test_d0076_ac14_最後の段の承認で終わる(tmp_path):
    """D0076-AC-14: 確認のある最後の段を承認すると、その場で PASSED で終わる。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra="review = true\n")))
    r.run_and_finish("a")
    r.next("await_review")
    r.review("approved")
    assert r.state()["final"] == "PASSED"
    assert r.next()["action"] == "finished"


# ---- AC-15 ----------------------------------------------------------------------------------


def test_d0076_ac15_確認待ちでないreviewは断る(tmp_path):
    """D0076-AC-15: 確認待ちでないときの chat review は断られ、記録は変わらない。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_next("a")
    before = r.state_text()
    for answer in ["approved", "quit"]:
        out = r.review(answer)
        assert r.code != 0 and out["ok"] is False, out
    out = r.review("revise", "直して")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before


def test_d0076_ac15_開いていない段のdoneは断る(tmp_path):
    """D0076-AC-15: 開いていない段への chat done は断られ、記録は変わらない。"""
    r = Run(tmp_path)
    r.ready(two())
    before = r.state_text()
    out = r.done("a")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before
    r.run_and_finish("a")
    after = r.state_text()
    out = r.done("a")
    assert r.code != 0 and out["ok"] is False, "閉じたあとの二重の done も断る"
    assert r.state_text() == after


def test_d0076_ac15_別の段へのdoneは断る(tmp_path):
    """D0076-AC-15: 開いている段と別の段への chat done は断られ、開いた段はそのまま。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_next("a")
    before = r.state_text()
    r.output_path("b").write_text("# b\n", encoding="utf-8")
    out = r.done("b")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before
    assert r.state()["open"]["stage"] == "a"


# ---- AC-16 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [None, "", " \n\n"], ids=["missing", "empty", "blank"])
def test_d0076_ac16_成果物が無いままdoneすると失敗として記録される(tmp_path, text):
    """D0076-AC-16: 成果物（段の output）が無い・空のまま chat done すると、段は失敗として記録される（STAGE_ERROR で終わる）。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_next("a")
    out = r.finish("a", text=text)
    assert out["result"] == "error", out
    state = r.state()
    assert state["final"] == "STAGE_ERROR" and state["open"] is None
    assert any(x.get("stage") == "a" and "seq" in x for x in state["runs"]), "段の実行は記録に残る"
    assert r.next()["action"] == "finished"
    assert not r.output_path("b").exists()


def test_d0076_ac16_errorを付けると成果物があっても失敗になる(tmp_path):
    """D0076-AC-16: --error を付けた chat done は、成果物があっても失敗（STAGE_ERROR）として記録される。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_next("a")
    out = r.finish("a", error=True)
    assert out["result"] == "error", out
    assert r.state()["final"] == "STAGE_ERROR"


# ---- AC-17 ----------------------------------------------------------------------------------


def test_d0076_ac17_commandが失敗したら自分へ戻り出力の末尾が次の指示に入る(tmp_path):
    """D0076-AC-17: check.command が 0 以外なら on_fail（省くと自分）の段へ戻り、直す点として出力の末尾が次の指示に入る。0 なら合格で次へ進む。"""
    command, flag = check_command(tmp_path)
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra=cmd_check(command, 2))))
    r.run_next("a")
    out = r.finish("a")
    assert out["result"] == "fail", out
    assert r.state()["chat"]["retries"] == {"a": 1}
    assert r.check_entries()[-1]["status"] == "fail" and r.check_entries()[-1]["attempt"] == 1
    retry = r.run_next("a")
    assert retry["kind"] == "retry" and retry["run"] == 2
    assert "boom-marker" in r.prompt_of(retry), "コマンドの出力の末尾が直す点として入る"
    flag.write_text("ok", encoding="utf-8")
    out = r.finish("a")
    assert out["result"] == "pass", out
    assert [c["status"] for c in r.check_entries()] == ["fail", "pass"]
    assert [c["attempt"] for c in r.check_entries()] == [1, 2]
    assert r.state()["final"] == "PASSED"
    assert r.next()["action"] == "finished"


def test_d0076_ac17_max_retriesを超えるとTEST_FAILEDで終わる(tmp_path):
    """D0076-AC-17: 不合格が max_retries を超えると、本体と同じ終了の種類（TEST_FAILED）で終わる。max_retries = 1 なら、2回目の不合格で終わる。"""
    command, _ = check_command(tmp_path)
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra=cmd_check(command, 1))))
    r.run_next("a")
    assert r.finish("a")["result"] == "fail"
    assert r.state()["final"] is None
    r.run_next("a")
    r.finish("a")
    state = r.state()
    assert state["final"] == "TEST_FAILED", state["final"]
    assert state["chat"]["retries"] == {"a": 1}
    assert (r.run_dir / "99_summary.md").is_file()
    assert r.next()["action"] == "finished"


def test_d0076_ac17_max_retriesが0なら最初の不合格で終わる(tmp_path):
    """D0076-AC-17: max_retries = 0 なら、最初の不合格で TEST_FAILED で終わる。"""
    command, _ = check_command(tmp_path)
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra=cmd_check(command, 0))))
    r.run_next("a")
    r.finish("a")
    assert r.state()["final"] == "TEST_FAILED"


def test_d0076_ac17_on_failの段へ戻る(tmp_path):
    """D0076-AC-17: on_fail の段（前の段）へ戻り、直す点はその段の指示に入る。"""
    command, flag = check_command(tmp_path)
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("draft"), stage_toml("verify", extra=cmd_check(command, 2, on_fail="draft"))))
    r.run_and_finish("draft")
    r.run_next("verify")
    assert r.finish("verify")["result"] == "fail"
    back = r.run_next("draft")
    assert back["kind"] == "retry" and "boom-marker" in r.prompt_of(back)
    r.finish("draft")
    r.run_next("verify")
    flag.write_text("ok", encoding="utf-8")
    assert r.finish("verify")["result"] == "pass"
    assert r.state()["final"] == "PASSED"
    assert r.state()["chat"]["retries"] == {"verify": 1}


# ---- AC-18 ----------------------------------------------------------------------------------


def test_d0076_ac18_verdictの段はstatusとproblemsで戻り進む(tmp_path):
    """D0076-AC-18: verdict の段は --status fail と --problems で戻り（直す点が次の指示に入る）、--status pass で進む。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("v", extra="[stages.check]\nverdict = true\nmax_retries = 2\n")))
    r.run_next("v")
    assert r.next()["verdict"] is True
    out = r.finish("v", status="fail", problems=("矢印が逆",))
    assert out["result"] == "fail", out
    retry = r.run_next("v")
    assert retry["kind"] == "retry" and "矢印が逆" in r.prompt_of(retry)
    assert r.check_entries()[-1]["problems"] and "矢印が逆" in r.check_entries()[-1]["problems"][0]
    out = r.finish("v", status="pass")
    assert out["result"] == "pass", out
    assert r.state()["final"] == "PASSED"


@pytest.mark.parametrize("status", [None, "maybe", "PASS", "ok", ""], ids=["none", "maybe", "upper", "ok", "empty"])
def test_d0076_ac18_statusが無いかpassとfail以外なら断られ記録は変わらない(tmp_path, status):
    """D0076-AC-18: --status が無いか、pass・fail 以外なら断られる（記録は変わらず、段は開いたまま）。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("v", extra="[stages.check]\nverdict = true\n")))
    r.run_next("v")
    r.output_path("v").write_text("# v\n", encoding="utf-8")
    before = r.state_text()
    out = r.done("v", status=status)
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before
    assert r.state()["open"]["stage"] == "v"


def test_d0076_ac18_verdictの無い段にstatusを渡すと断る(tmp_path):
    """D0076-AC-18: verdict の無い段に --status を渡すと断られる。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_next("a")
    r.output_path("a").write_text("# a\n", encoding="utf-8")
    before = r.state_text()
    out = r.done("a", status="pass")
    assert r.code != 0 and out["ok"] is False, out
    assert r.state_text() == before


# ---- AC-19 ----------------------------------------------------------------------------------


def test_d0076_ac19_nextで別の段へ飛べる(tmp_path):
    """D0076-AC-19: next で別の段へ飛べる（飛ばされた段は始まらない）。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra='next = "c"\n'), stage_toml("b"), stage_toml("c")))
    r.run_and_finish("a")
    r.run_next("c")
    r.finish("c")
    assert r.state()["final"] == "PASSED"
    assert [x["stage"] for x in r.state()["runs"] if "seq" in x] == ["a", "c"]


def test_d0076_ac19_endで終われる(tmp_path):
    """D0076-AC-19: next = "end" で終われる（後ろの段は始まらない）。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra='next = "end"\n'), stage_toml("b")))
    r.run_and_finish("a")
    assert r.state()["final"] == "PASSED"
    out = r.next()
    assert out["action"] == "finished", out
    assert not any("_b" in name for name in r.logs())


def test_d0076_ac19_max_stepsを超えると本体と同じ終了の種類で終わる(tmp_path):
    """D0076-AC-19: 段を流した回数が max_steps を超えると、STAGE_ERROR で終わり、警告に残る。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra="[stages.check]\nverdict = true\nmax_retries = 5\n"), head="max_steps = 2\n"))
    r.run_next("a")
    assert r.finish("a", status="fail", problems=("まだ",))["result"] == "fail"
    r.run_next("a")
    assert r.finish("a", status="fail", problems=("まだ",))["result"] == "fail"
    out = r.next()
    assert out["action"] == "finished", out
    state = r.state()
    assert state["final"] == "STAGE_ERROR"
    assert any("max_steps" in w for w in state["warnings"]), state["warnings"]
    assert state["chat"]["steps"] == 2


# ---- AC-20 ----------------------------------------------------------------------------------


def test_d0076_ac20_全段が終わると99_summaryができfinalが入る(tmp_path):
    """D0076-AC-20: 全段が終わると 99_summary.md ができ、final が入り、chat next は「終わり」を返す。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_and_finish("a")
    r.run_and_finish("b")
    state = r.state()
    assert state["final"] == "PASSED" and state["open"] is None and state["pending_review"] is None
    summary = (r.run_dir / "99_summary.md").read_text(encoding="utf-8")
    assert "a.md" in summary and "b.md" in summary, "成果物の場所がまとめに載る"
    out = r.next()
    assert out["ok"] is True and out["action"] == "finished", out
    assert "99_summary.md" in text_of(out)
    assert sys.modules.get("claude_agent_sdk") is None, "最後まで SDK を読まずに動いた"


# ---- AC-21 ----------------------------------------------------------------------------------


def test_d0076_ac21_statusは今どこかを返す(tmp_path):
    """D0076-AC-21: chat status が、段の名前・何回目か・確認待ちかを返す。"""
    r = Run(tmp_path)
    r.ready(two(review=True))
    r.run_next("a")
    out = r.cmd("status")
    assert r.code == 0 and out["ok"] is True and out["action"] == "status", out
    assert "a" in text_of(out)
    before = r.state_text()
    r.finish("a")
    r.next("await_review")
    waiting = r.cmd("status")
    assert waiting["action"] == "status" and "確認" in text_of(waiting), waiting
    assert r.state_text() != before
    r.review("revise", "直して")
    r.run_next("a")
    again = r.cmd("status")
    assert "2" in text_of(again), "何回目か（2回目）が出る"


def test_d0076_ac21_statusは読むだけで記録を変えない(tmp_path):
    """D0076-AC-21: chat status は読むだけで、記録を書き換えない。"""
    r = Run(tmp_path)
    r.ready(two())
    r.run_next("a")
    before = r.state_text()
    r.cmd("status")
    assert r.state_text() == before


def test_d0076_ac21_記録が無いと始め方を伝えて断る(tmp_path):
    """D0076-AC-21: 記録が無いときの chat status は、始め方を伝えて断る。"""
    r = Run(tmp_path)
    r.make(two())
    out = r.cmd("status")
    assert r.code != 0 and out["ok"] is False, out
    assert "chat start" in text_of(out)
    assert not (tmp_path / "docs").exists()


# ---- 本体と同じ数え方（設計 5.6） ----------------------------------------------------------------


def test_d0076_revise_の数え方は本体のLinearPipelineと同じ(tmp_path):
    """D0076-AC-14（設計 5.6）: revise は steps も retries も増やさず、revise のあとも検査がかかる（落ちれば retries に数える）。
    check の attempt は revise をまたいで続く。"""
    command, flag = check_command(tmp_path)
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a", extra="review = true\n" + cmd_check(command, 2))))
    r.run_next("a")
    assert r.finish("a")["result"] == "fail"
    r.run_next("a")
    flag.write_text("ok", encoding="utf-8")
    assert r.finish("a")["result"] == "pass"
    r.next("await_review")
    r.review("revise", "もう少し")
    assert r.state()["chat"]["steps"] == 2 and r.state()["chat"]["retries"] == {"a": 1}
    again = r.run_next("a")
    assert again["kind"] == "revise"
    flag.unlink()
    out = r.finish("a")
    assert out["result"] == "fail", "revise のあとも検査がかかる"
    state = r.state()
    assert [c["attempt"] for c in r.check_entries()] == [1, 2, 3]
    assert [c["status"] for c in r.check_entries()] == ["fail", "pass", "fail"]
    assert state["chat"]["steps"] == 2 and state["chat"]["retries"] == {"a": 2}
    assert r.run_next("a")["kind"] == "retry"
    assert r.state()["chat"]["steps"] == 3, "検査の戻りは新しく始めるので steps が増える"


# ---- 定義が途中で変わったとき（指紋。設計 5.2） -----------------------------------------------------


@pytest.mark.parametrize("which", ["pipe.toml", "pipeline.toml"])
def test_d0076_ac29_始めたあとに定義が変わるとnextも断る(tmp_path, which):
    """D0076-AC-29（司会役の側）: pipe.toml・pipeline.toml が始めたときから変わると、chat next は断る（フックが止めるのと同じ条件）。"""
    r = Run(tmp_path)
    r.ready(two())
    if which == "pipe.toml":
        path = r.pipe_dir / "pipe.toml"
        path.write_text(path.read_text(encoding="utf-8") + "\n# 変えた\n", encoding="utf-8")
    else:
        (tmp_path / "pipeline.toml").write_text('[pipeline]\nextra_test_globs = ["x/*"]\n', encoding="utf-8")
    before = r.state_text()
    out = r.cmd("next")
    assert r.code != 0 and out["ok"] is False, out
    assert which in text_of(out)
    assert r.state_text() == before
    assert r.state()["open"] is None
