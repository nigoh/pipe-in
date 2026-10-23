"""D0028: 段の検証（[stages.check]）の審査（[stages.check.judge]）を、SDK を呼ばずに確かめる。

定義の読み込み・検査、構造化出力のスキーマ、依頼文、差し戻しの流れ、state.json と 99_summary.md の記録。
runner と shell は手で書いた偽物に差し替える（tests/test_pipe_flow.py と同じやり方）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.pipeline import STATE, SUMMARY, Exit, ShellResult
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as ps
from pipe_in.pipe.pipeline import LinearPipeline

from test_pipe_flow import PASS, ScriptedRunner, cfg_for, make_pipe, pipe_toml, run, stage_toml, state

CRITERIA = (("clarity", "読みやすい"), ("accuracy", "事実に合っている"))
MUSTS = (("safe", "秘密を書かない"),)


def judge_toml(check: str = "", *, threshold: str | None = None, criteria=CRITERIA, must=MUSTS, extra: str = "") -> str:
    """段に足す `[stages.check]` と、その下の審査の表。check には verdict・command・on_fail などの行を書く。"""
    out = "[stages.check]\n" + check + "[stages.check.judge]\n"
    if threshold is not None:
        out += f"threshold = {threshold}\n"
    out += extra
    for n, d in criteria:
        out += f'[[stages.check.judge.criteria]]\nname = "{n}"\ndescription = "{d}"\n'
    for n, d in must:
        out += f'[[stages.check.judge.must]]\nname = "{n}"\ndescription = "{d}"\n'
    return out


def jr(scores: dict | None = None, must: dict | None = None, **top) -> dict:
    """審査つきの段の構造化出力。点の既定は全項目 1.0、must は違反なし。top に status などを足せる。"""
    scores = {"clarity": 1.0, "accuracy": 1.0} if scores is None else scores
    must = {"safe": False} if must is None else must

    def m(name, v):
        if isinstance(v, tuple):  # (violated, evidence)
            return {"violated": v[0], "evidence": v[1]}
        return {"violated": v, "evidence": "根拠あり" if v else ""}

    return {
        **top,
        "judge": {
            "criteria": {k: {"reason": f"{k}の理由", "score": s} for k, s in scores.items()},
            "must": {k: m(k, v) for k, v in must.items()},
        },
    }


GOOD = jr()
VIOLATED = jr(must={"safe": (True, "out.md の3行目に秘密の値")})


def two_stage(check: str = "", **kw) -> str:
    return pipe_toml(stage_toml("draw"), stage_toml("verify", judge_toml(check + 'on_fail = "draw"\n', **kw)))


def checks_of(tmp_path, pipe) -> list[dict]:
    return [h["check"] for h in state(tmp_path, pipe)["runs"] if "check" in h]


# ---- AC-01 〜 AC-07 流れ -------------------------------------------------------------------


def test_ac01_judge_pass_moves_on(tmp_path):
    """D0028-AC-01: must の違反が無く、平均がしきい値以上なら、検証は合格し段は先へ進む。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw"), stage_toml("verify", judge_toml('on_fail = "draw"\n')), stage_toml("after")))
    r = ScriptedRunner(pipe, {"verify": [jr({"clarity": 1.0, "accuracy": 0.5})]})  # 平均 0.75 >= 0.7
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["draw", "verify", "after"]
    assert [c["status"] for c in checks_of(tmp_path, pipe)] == ["pass"]


def test_ac02_must_violation_goes_back(tmp_path):
    """D0028-AC-02: must の違反が 1 つあれば、点が満点でも不合格になり、on_fail の段へ戻る。"""
    pipe = make_pipe(tmp_path, two_stage())
    r = ScriptedRunner(pipe, {"verify": [VIOLATED, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["draw", "verify", "draw", "verify"]
    assert [c["status"] for c in checks_of(tmp_path, pipe)] == ["fail", "pass"]


def test_ac03_unchecked_must_is_in_problems(tmp_path):
    """D0028-AC-03: must が null（確かめられない）でも不合格。戻った段の依頼文に「確かめられなかった」と根拠が出る。"""
    pipe = make_pipe(tmp_path, two_stage())
    unchecked = jr(must={"safe": (None, "ファイルが読めなかった")})
    r = ScriptedRunner(pipe, {"verify": [unchecked, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    redo = r.calls[2][2]
    assert "前回の検証" in redo and "確かめられ" in redo and "ファイルが読めなかった" in redo


def test_ac04_null_score_is_excluded_in_flow(tmp_path):
    """D0028-AC-04: null の点は平均から外れる（1.0 と null → 平均 1.0 で合格）。全部 null なら不合格。"""
    pipe = make_pipe(tmp_path, two_stage())
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [jr({"clarity": 1.0, "accuracy": None})]})) == Exit.PASSED
    pipe2 = make_pipe(tmp_path, two_stage("max_retries = 0\n"), name="q")
    assert run(tmp_path, pipe2, ScriptedRunner(pipe2, {"verify": [jr({"clarity": None, "accuracy": None})]})) == Exit.TEST_FAILED


def test_ac05_ac06_threshold_from_pipe_toml(tmp_path):
    """D0028-AC-05・AC-06: しきい値は pipe.toml の threshold。書かなければ 0.7。平均 0.75 は 0.75 で合格、0.8 で不合格。"""
    half = jr({"clarity": 1.0, "accuracy": 0.5})
    for threshold, name, expected in ((None, "a", Exit.PASSED), ("0.75", "b", Exit.PASSED), ("0.8", "c", Exit.TEST_FAILED)):
        pipe = make_pipe(tmp_path, two_stage("max_retries = 0\n", threshold=threshold), name=name)
        assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [half]})) == expected, threshold
    low = jr({"clarity": 0.5, "accuracy": 0.75})  # 0.63 は既定の 0.7 に届かない
    pipe = make_pipe(tmp_path, two_stage("max_retries = 0\n"), name="d")
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [low]})) == Exit.TEST_FAILED


def test_ac07_pass_claim_with_must_violation_fails(tmp_path):
    """D0028-AC-07: 審査役の返りが status: pass・overall: 1.0 と言っても、must 違反ならエンジンの計算で不合格。"""
    pipe = make_pipe(tmp_path, two_stage())
    claim = {**VIOLATED, "status": "pass", "overall": 1.0, "summary": "全部よい", "problems": []}
    r = ScriptedRunner(pipe, {"verify": [claim, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["draw", "verify", "draw", "verify"]
    assert [c["status"] for c in checks_of(tmp_path, pipe)] == ["fail", "pass"]


def test_ac07_judge_only_ignores_status_key_inside_judge(tmp_path):
    """D0028-AC-07: judge の中に合否や平均のキーがあっても使わない（点が低ければ不合格のまま）。"""
    pipe = make_pipe(tmp_path, two_stage("max_retries = 0\n"))
    low = jr({"clarity": 0.25, "accuracy": 0.25})
    low["judge"].update({"status": "pass", "overall": 1.0, "verdict": "pass"})
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [low]})) == Exit.TEST_FAILED


# ---- AC-08 決まりに合わない返りは、段のエラーにせず差し戻す ---------------------------------------------


def _bad(fn):
    def make():
        d = jr()
        fn(d)
        return d

    return make


BAD_REPLIES = {
    "点が 0.3": _bad(lambda d: d["judge"]["criteria"]["clarity"].update(score=0.3)),
    "理由なし": _bad(lambda d: d["judge"]["criteria"]["clarity"].pop("reason")),
    "項目の欠け": _bad(lambda d: d["judge"]["criteria"].pop("accuracy")),
    "must の欠け": _bad(lambda d: d["judge"]["must"].pop("safe")),
    "知らない項目名": _bad(lambda d: d["judge"]["criteria"].update(zzz={"reason": "x", "score": 1.0})),
    "違反で根拠なし": _bad(lambda d: d["judge"]["must"]["safe"].update(violated=True, evidence="")),
    "型違い": _bad(lambda d: d["judge"].update(criteria=["clarity", "accuracy"])),
    "judge が無い": _bad(lambda d: d.pop("judge")),
}


@pytest.mark.parametrize("name", list(BAD_REPLIES))
def test_ac08_malformed_goes_back_not_stage_error(tmp_path, name):
    """D0028-AC-08: 返りが決まりに合わないときは段のエラーにならず、不合格で on_fail へ戻る。上限まで続けて合わなければ終了コード 1（TEST_FAILED）。"""
    pipe = make_pipe(tmp_path, two_stage("max_retries = 1\n"))
    r = ScriptedRunner(pipe, {"verify": [BAD_REPLIES[name](), BAD_REPLIES[name]()]})
    assert run(tmp_path, pipe, r) == Exit.TEST_FAILED
    assert r.names() == ["draw", "verify", "draw", "verify"]
    redo = r.calls[2][2]
    assert "審査役の返りが決まりに合いませんでした" in redo
    first = checks_of(tmp_path, pipe)[0]
    assert first["status"] == "fail" and "審査役の返りが決まりに合いませんでした" in "\n".join(first["problems"])


def test_ac08_malformed_then_valid_passes(tmp_path):
    """D0028-AC-08: 合わない返りの次に正しい返りが来れば、合格して先へ進む。"""
    pipe = make_pipe(tmp_path, two_stage())
    r = ScriptedRunner(pipe, {"verify": [BAD_REPLIES["点が 0.3"](), GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert checks_of(tmp_path, pipe)[0]["judge"]["valid"] is False


# ---- AC-09・AC-10 verdict・command との併用 -----------------------------------------------------


@pytest.mark.parametrize(
    "verdict_ok,judge_ok",
    [(True, True), (True, False), (False, True), (False, False)],
    ids=["両方通る", "審査だけ不合格", "verdict だけ不合格", "両方不合格"],
)
def test_ac09_judge_and_verdict_both_must_pass(tmp_path, verdict_ok, judge_ok):
    """D0028-AC-09: 審査と verdict を両方書いたら、両方通ったときだけ合格。片方でも不合格なら不合格。"""
    pipe = make_pipe(tmp_path, two_stage("verdict = true\nmax_retries = 0\n"))
    base = jr() if judge_ok else jr(must={"safe": (True, "禁止語")})
    base.update({"status": "pass" if verdict_ok else "fail", "summary": "要約", "problems": [] if verdict_ok else ["矢印が逆"]})
    got = run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [base]}))
    assert got == (Exit.PASSED if verdict_ok and judge_ok else Exit.TEST_FAILED)
    rec = checks_of(tmp_path, pipe)[0]
    assert rec["status"] == ("pass" if verdict_ok and judge_ok else "fail")
    assert rec["summary"] == "要約" and rec["judge"]["status"] == ("pass" if judge_ok else "fail")
    if not verdict_ok:
        assert "矢印が逆" in "\n".join(rec["problems"])
    if not judge_ok:
        assert "禁止語" in "\n".join(rec["problems"])


@pytest.mark.parametrize(
    "returncode,judge_ok",
    [(0, True), (0, False), (3, True), (3, False)],
    ids=["両方通る", "審査だけ不合格", "コマンドだけ不合格", "両方不合格"],
)
def test_ac10_judge_and_command_both_must_pass(tmp_path, returncode, judge_ok):
    """D0028-AC-10: 審査と command を両方書いたら、両方通ったときだけ合格。コマンドは審査が不合格でも流す。"""
    pipe = make_pipe(tmp_path, two_stage('command = "make check"\nmax_retries = 0\n'))
    calls: list[str] = []

    def shell(cmd, cwd, timeout):
        calls.append(cmd)
        return ShellResult(returncode, "lint error" if returncode else "ok")

    reply = jr() if judge_ok else jr(must={"safe": (True, "禁止語")})
    got = run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [reply]}), shell=shell)
    assert got == (Exit.PASSED if returncode == 0 and judge_ok else Exit.TEST_FAILED)
    assert calls == ["make check"]
    rec = checks_of(tmp_path, pipe)[0]
    assert rec["command"] == "make check" and rec["returncode"] == returncode
    assert rec["status"] == ("pass" if returncode == 0 and judge_ok else "fail")


# ---- AC-11 差し戻し --------------------------------------------------------------------------------


def test_ac11_on_fail_prompt_has_evidence_and_low_reasons(tmp_path):
    """D0028-AC-11: 戻った段の依頼文に、must の違反の根拠と、点の低い項目の理由が入る。"""
    pipe = make_pipe(tmp_path, two_stage())
    bad = jr({"clarity": 0.25, "accuracy": 1.0}, {"safe": (True, "out.md の3行目に秘密の値")})
    bad["judge"]["criteria"]["clarity"]["reason"] = "見出しが無く読みにくい"
    bad["judge"]["criteria"]["accuracy"]["reason"] = "事実どおり"
    r = ScriptedRunner(pipe, {"verify": [bad, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    redo = r.calls[2][2]
    assert r.calls[2][0] == "draw" and r.calls[2][1] is None
    assert "## 前回の検証で見つかった問題" in redo
    assert "out.md の3行目に秘密の値" in redo and "safe" in redo
    assert "見出しが無く読みにくい" in redo and "clarity" in redo


def test_ac11_below_threshold_prompt_has_mean_and_threshold(tmp_path):
    """D0028-AC-11: 違反が無く平均がしきい値に届かないときも、平均としきい値と、低い項目の理由が戻った段に渡る。"""
    pipe = make_pipe(tmp_path, two_stage())
    low = jr({"clarity": 0.25, "accuracy": 1.0})  # 平均 0.63
    low["judge"]["criteria"]["clarity"]["reason"] = "見出しが無く読みにくい"
    r = ScriptedRunner(pipe, {"verify": [low, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    redo = r.calls[2][2]
    assert "0.63" in redo and "0.7" in redo and "見出しが無く読みにくい" in redo


def test_ac11_retries_exhausted_exit_1(tmp_path):
    """D0028-AC-11: max_retries を超えたら終了コード 1（TEST_FAILED）で止まる。"""
    pipe = make_pipe(tmp_path, two_stage("max_retries = 1\n"))
    r = ScriptedRunner(pipe, {"verify": [VIOLATED, VIOLATED, GOOD]})
    got = run(tmp_path, pipe, r)
    assert got == Exit.TEST_FAILED and int(got) == 1
    assert r.names() == ["draw", "verify", "draw", "verify"]
    summary = (tmp_path / "docs/pipeline/p" / SUMMARY).read_text(encoding="utf-8")
    assert "検証に通りませんでした" in summary


def test_ac11_default_on_fail_is_self(tmp_path):
    """D0028-AC-11: on_fail を省くと自分の段をやり直す。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("verify", judge_toml())))
    r = ScriptedRunner(pipe, {"verify": [VIOLATED, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["verify", "verify"]


# ---- AC-12 グループ ---------------------------------------------------------------------------------


def test_ac12_group_member_retries_itself_with_judge(tmp_path):
    """D0028-AC-12: グループ（並列）の段の検証でも審査が使え、自分だけをやり直す。"""
    toml = pipe_toml(
        stage_toml("survey"),
        stage_toml("flow", 'group = "draw"\n' + judge_toml()),
        stage_toml("klass", 'group = "draw"\n'),
        stage_toml("report"),
    )
    pipe = make_pipe(tmp_path, toml)
    assert pd.check_pipe(pipe, tmp_path) == []
    r = ScriptedRunner(pipe, {"flow": [VIOLATED, GOOD]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names().count("flow") == 2 and r.names().count("klass") == 1
    assert "out.md の3行目に秘密の値" in [c for c in r.calls if c[0] == "flow"][1][2]


# ---- AC-13 構造化出力のスキーマ ----------------------------------------------------------------------


def schema_of(tmp_path, toml: str, stage: str = "verify") -> dict:
    pipe = make_pipe(tmp_path, toml)
    return ps.build_pipe_specs(cfg_for(tmp_path, pipe), pipe)[stage].output_format["schema"]


def test_ac13_output_format_has_judge_keys(tmp_path):
    """D0028-AC-13: output_format に、項目ごとの reason / score（5段階と null）と must ごとの violated / evidence が入る。"""
    schema = schema_of(tmp_path, pipe_toml(stage_toml("verify", judge_toml())))
    assert "judge" in schema["required"]
    j = schema["properties"]["judge"]
    assert set(j["required"]) == {"criteria", "must"}
    crit = j["properties"]["criteria"]
    assert set(crit["properties"]) == {"clarity", "accuracy"} and set(crit["required"]) == {"clarity", "accuracy"}
    assert crit["additionalProperties"] is False
    item = crit["properties"]["clarity"]
    assert list(item["properties"]) == ["reason", "score"]  # 理由を先に書かせる
    assert set(item["required"]) == {"reason", "score"}
    assert item["properties"]["reason"]["type"] == "string"
    assert item["properties"]["score"]["enum"] == [0.0, 0.25, 0.5, 0.75, 1.0, None]
    must = j["properties"]["must"]
    assert set(must["properties"]) == {"safe"} and must["required"] == ["safe"]
    m = must["properties"]["safe"]
    assert set(m["required"]) == {"violated", "evidence"}
    assert set(m["properties"]["violated"]["type"]) == {"boolean", "null"}
    assert m["properties"]["evidence"]["type"] == "string"


def test_ac13_no_verdict_or_overall_keys(tmp_path):
    """D0028-AC-13: 合否や平均のキーは入らない。審査だけなら、トップのキーは judge だけ。"""
    schema = schema_of(tmp_path, pipe_toml(stage_toml("verify", judge_toml())))
    assert set(schema["properties"]) == {"judge"} and schema["required"] == ["judge"]
    assert set(schema["properties"]["judge"]["properties"]) == {"criteria", "must"}
    text = json.dumps(schema)
    assert '"overall"' not in text and '"verdict"' not in text and '"pass"' not in text


def test_ac13_merges_with_verdict_and_routes(tmp_path):
    """D0028-AC-13: verdict・routes と併用しても、status・summary・problems・choice が消えずに合わさる。"""
    toml = pipe_toml(
        stage_toml("verify", 'next = "end"\n[stages.routes]\na = "end"\nb = "other"\n' + judge_toml("verdict = true\n")),
        stage_toml("other"),
    )
    schema = schema_of(tmp_path, toml)
    assert set(schema["properties"]) == {"status", "summary", "problems", "choice", "judge"}
    assert schema["properties"]["status"]["enum"] == ["pass", "fail"]
    assert schema["properties"]["choice"]["enum"] == ["a", "b"]
    assert {"status", "summary", "problems", "choice", "judge"} <= set(schema["required"])


def test_ac13_stage_without_judge_has_no_judge_key(tmp_path):
    """D0028-AC-13・AC-17: 審査を書かない段のスキーマに judge は入らない（今の作りのまま。守り続けるための検査）。"""
    schema = schema_of(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nverdict = true\n")))
    assert set(schema["properties"]) == {"status", "summary", "problems"}


# ---- AC-14 依頼文 ---------------------------------------------------------------------------------------


def test_ac14_prompt_has_rubric_and_no_compute_note(tmp_path):
    """D0028-AC-14: 依頼文に、項目の説明・must・点の付け方（5段階）が入り、「平均や合否は計算しない」と書かれる。"""
    pipe = make_pipe(tmp_path, two_stage())
    cfg = cfg_for(tmp_path, pipe)
    prompt = ps.stage_prompt(cfg, pipe, 1)
    for text in ("clarity", "読みやすい", "accuracy", "事実に合っている", "safe", "秘密を書かない"):
        assert text in prompt, text
    for level in ("1.0", "0.75", "0.5", "0.25", "0.0", "null"):
        assert level in prompt, level
    assert "平均や合否は計算しない" in prompt
    assert "理由を先に" in prompt


def test_ac14_prompt_keeps_verdict_sentence(tmp_path):
    """D0028-AC-14: verdict を併用しても、判定を返す一文は残る。審査を書かない段の依頼文に審査の語は出ない。"""
    pipe = make_pipe(tmp_path, two_stage("verdict = true\n"))
    prompt = ps.stage_prompt(cfg_for(tmp_path, pipe), pipe, 1)
    assert "判定（status: pass / fail・summary・problems）を構造化出力で返してください" in prompt and "平均や合否は計算しない" in prompt
    plain = make_pipe(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nverdict = true\n")), name="plain")
    assert "平均や合否は計算しない" not in ps.stage_prompt(cfg_for(tmp_path, plain), plain, 0)


# ---- AC-15・AC-16 記録 ----------------------------------------------------------------------------------


def test_ac15_state_history_has_judge_and_keeps_old_keys(tmp_path):
    """D0028-AC-15: history の check に judge（点・平均・しきい値・must の結果）と status が入り、既存のキーは変わらない。"""
    pipe = make_pipe(tmp_path, two_stage('verdict = true\ncommand = "make check"\n'))
    ok = {"status": "pass", "summary": "要約", "problems": []}
    bad = {**jr({"clarity": 0.5, "accuracy": 1.0}, {"safe": (True, "禁止語")}), **ok}
    r = ScriptedRunner(pipe, {"verify": [bad, {**GOOD, **ok}]})
    assert run(tmp_path, pipe, r, shell=lambda c, cwd, t: ShellResult(0, "ok")) == Exit.PASSED
    first, second = checks_of(tmp_path, pipe)
    assert first["status"] == "fail" and second["status"] == "pass"
    assert first["judge"] == {
        "status": "fail",
        "overall": 0.75,
        "threshold": 0.7,
        "scores": {"clarity": 0.5, "accuracy": 1.0},
        "must": {"safe": {"violated": True, "evidence": "禁止語"}},
        "valid": True,
    }
    assert second["judge"]["status"] == "pass" and second["judge"]["overall"] == 1.0
    for rec in (first, second):  # 既存のキーはそのまま。足したのは judge だけ
        assert set(rec) == {"status", "problems", "summary", "command", "returncode", "judge"}
        assert rec["command"] == "make check" and rec["returncode"] == 0 and rec["summary"] == "要約"
    assert "禁止語" in "\n".join(first["problems"])
    assert "の理由" not in json.dumps(first["judge"], ensure_ascii=False)  # 理由は記録しない


def test_ac15_judge_only_record_keys(tmp_path):
    """D0028-AC-15: 審査だけの検証の記録は status・problems・judge だけ（ほかの記録は足さない）。"""
    pipe = make_pipe(tmp_path, two_stage())
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [GOOD]})) == Exit.PASSED
    (rec,) = checks_of(tmp_path, pipe)
    assert set(rec) == {"status", "problems", "judge"} and rec["problems"] == []


def test_ac15_stage_without_judge_has_no_judge_record(tmp_path):
    """D0028-AC-15・AC-17: 審査を書かない検証の記録に judge は足されない（守り続けるための検査）。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nverdict = true\n")))
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [PASS]})) == Exit.PASSED
    (rec,) = checks_of(tmp_path, pipe)
    assert set(rec) == {"status", "problems", "summary"}


def summary_of(tmp_path) -> str:
    return (tmp_path / "docs/pipeline/p" / SUMMARY).read_text(encoding="utf-8")


def test_ac16_summary_has_judge_line(tmp_path):
    """D0028-AC-16: 99_summary.md の検証の下に、審査の 1 行（平均・しきい値・合否）が出る。"""
    pipe = make_pipe(tmp_path, two_stage())
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [jr({"clarity": 1.0, "accuracy": 0.5})]})) == Exit.PASSED
    assert "  - 審査: 平均 0.75 / しきい値 0.7 → pass" in summary_of(tmp_path)


def test_ac16_summary_lists_violated_and_unchecked_must(tmp_path):
    """D0028-AC-16: 違反した must と確かめられなかった must が 1 行に出る。"""
    pipe = make_pipe(tmp_path, two_stage("max_retries = 0\n", must=(("safe", "秘密を書かない"), ("legal", "法に触れない"))))
    reply = jr(must={"safe": (True, "禁止語"), "legal": (None, "")})
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [reply]})) == Exit.TEST_FAILED
    text = summary_of(tmp_path)
    assert "審査: 平均 1.0 / しきい値 0.7 → fail" in text
    assert "must の違反: safe" in text and "確かめられず: legal" in text


def test_ac16_summary_for_invalid_return(tmp_path):
    """D0028-AC-16: 返りが決まりに合わなかったときの行。"""
    pipe = make_pipe(tmp_path, two_stage("max_retries = 0\n"))
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [BAD_REPLIES["点が 0.3"]()]})) == Exit.TEST_FAILED
    assert "審査: 返りが決まりに合いませんでした" in summary_of(tmp_path)


# ---- AC-17 〜 AC-19 定義と検査 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "check",
    ["verdict = true\n", 'command = "make check"\n', 'verdict = true\ncommand = "make check"\nmax_retries = 3\n'],
    ids=["verdict だけ", "command だけ", "両方"],
)
def test_ac17_pipe_without_judge_loads_and_validates_unchanged(tmp_path, check):
    """D0028-AC-17: 審査を書かない pipe.toml は、読み込み・検査の結果が変わらない（judge は None）。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw"), stage_toml("verify", "[stages.check]\n" + check)))
    assert pipe.stages[1].check.judge is None
    assert pd.check_pipe(pipe, tmp_path) == []


def test_ac17_load_judge_settings(tmp_path):
    """D0028-AC-17・FR-01: [stages.check.judge] を読む。threshold を書かなければ 0.7。verdict / command と並べて書ける。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw"), stage_toml("verify", judge_toml('verdict = true\ncommand = "make check"\non_fail = "draw"\n'))))
    c = pipe.stages[1].check
    assert (c.verdict, c.command, c.on_fail) == (True, "make check", "draw")
    assert c.judge is not None and c.judge.threshold == 0.7
    assert [(i.name, i.description) for i in c.judge.criteria] == list(CRITERIA)
    assert [(i.name, i.description) for i in c.judge.must] == list(MUSTS)
    assert pd.check_pipe(pipe, tmp_path) == []
    other = make_pipe(tmp_path, pipe_toml(stage_toml("verify", judge_toml(threshold="0.85", must=()))), name="o")
    assert other.stages[0].check.judge.threshold == 0.85 and other.stages[0].check.judge.must == []
    assert pd.check_pipe(other, tmp_path) == []


def errors_of(tmp_path, toml: str) -> list[str]:
    return pd.check_pipe(make_pipe(tmp_path, toml), tmp_path)


INVALID_JUDGE = {
    "しきい値が 1.5": (dict(threshold="1.5"), "threshold"),
    "しきい値が負": (dict(threshold="-0.1"), "threshold"),
    "しきい値が文字列": (dict(threshold='"0.7"'), "threshold"),
    "しきい値が真偽値": (dict(threshold="true"), "threshold"),
    "項目が空": (dict(criteria=()), "criteria"),
    "項目名の重なり": (dict(criteria=(("clarity", "a"), ("clarity", "b"))), "clarity"),
    "must 名の重なり": (dict(must=(("safe", "a"), ("safe", "b"))), "safe"),
    "judge の中の知らないキー": (dict(extra="weight = 2\n"), "weight"),
    "項目の名前が空": (dict(criteria=(("", "a"),)), "name"),
}


@pytest.mark.parametrize("name", list(INVALID_JUDGE))
def test_ac18_judge_settings_are_validated(tmp_path, name):
    """D0028-AC-18: しきい値が範囲外・文字列、項目が空、名前の重なり、知らないキーは、validate が止めて理由を出す。"""
    kw, word = INVALID_JUDGE[name]
    errors = errors_of(tmp_path, pipe_toml(stage_toml("verify", judge_toml(**kw))))
    assert any(word in e for e in errors), (name, errors)


@pytest.mark.parametrize(
    "item,word",
    [
        ('[[stages.check.judge.criteria]]\nname = "x"\n', "description"),
        ('[[stages.check.judge.criteria]]\nname = "x"\ndescription = "d"\nweight = 2\n', "weight"),
        ('[[stages.check.judge.must]]\ndescription = "d"\n', "name"),
        ('[[stages.check.judge.criteria]]\nname = 3\ndescription = "d"\n', "name"),
    ],
    ids=["説明なし", "項目の中の知らないキー", "must に名前なし", "名前が文字列でない"],
)
def test_ac18_item_keys_are_validated(tmp_path, item, word):
    """D0028-AC-18: 項目に name / description の文字列が無い・知らないキーがあるときも止まる（verdict を書いて、それ以外の誤りで止まらないようにする）。"""
    head = '[stages.check]\nverdict = true\n[stages.check.judge]\n[[stages.check.judge.criteria]]\nname = "ok"\ndescription = "d"\n'
    errors = errors_of(tmp_path, pipe_toml(stage_toml("verify", head + item)))
    assert any(word in e for e in errors), (item, errors)


def test_ac18_same_name_in_criteria_and_must_is_allowed(tmp_path):
    """D0028-AC-18: 項目と must の間の同名は許す（スキーマの別の入れ物に入る）。"""
    toml = pipe_toml(stage_toml("verify", judge_toml(criteria=(("same", "a"),), must=(("same", "b"),))))
    assert errors_of(tmp_path, toml) == []


def test_ac19_empty_check_still_fails_validate(tmp_path):
    """D0028-AC-19: verdict も command も審査も無い [stages.check] は、今と同じく validate で止まる。"""
    errors = errors_of(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nmax_retries = 2\n")))
    assert any("verdict か command" in e for e in errors), errors


def test_ac19_message_mentions_judge(tmp_path):
    """D0028-AC-19: 止めるときの文に、審査（judge）も書けることが出る。"""
    errors = errors_of(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nmax_retries = 2\n")))
    assert any("verdict か command" in e and "judge" in e for e in errors), errors


# ---- AC-21 古い記録 -------------------------------------------------------------------------------------------


def test_ac21_old_state_without_judge_resumes(tmp_path):
    """D0028-AC-21: 審査の項目が無い前の版の state.json（check に judge が無い）を読んで再開しても落ちない。"""
    toml = pipe_toml(stage_toml("draw", "review = true\n"), stage_toml("verify", judge_toml('on_fail = "draw"\n')))
    pipe = make_pipe(tmp_path, toml)

    def make(runner):
        cfg = cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True)
        return LinearPipeline(cfg, pipe, runner=runner)

    assert asyncio.run(make(ScriptedRunner(pipe)).run("やること")) == Exit.AWAITING_REVIEW
    path = tmp_path / "docs/pipeline" / pipe.name / STATE
    data = json.loads(path.read_text(encoding="utf-8"))
    # 前の版の書き方の検証の記録（judge が無い）を、履歴に足しておく
    data["runs"].append({"stage": "draw", "check": {"status": "pass", "problems": [], "summary": "前の版の記録"}})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    r2 = ScriptedRunner(pipe, {"verify": [GOOD]})
    assert asyncio.run(make(r2).review(Decision("approve"))) == Exit.PASSED
    assert r2.names() == ["verify"]
    text = summary_of(tmp_path)
    assert "前の版の記録" in text  # 古い記録の行は出て、
    assert text.count("審査:") == 1  # 審査の行は新しい検証の 1 行だけ（古い記録からは足さない）
