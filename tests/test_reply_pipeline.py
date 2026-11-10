"""D0079：確認の待ちをパイプライン（開発フローとパイプ）に通した流れ。

待ち始めの印（state.json の reply_wait）・待ちごとに新しい識別子・流し始めと再開の掃除・--yes と --pause と差し替えた ask と端末でない標準入力の動きを、
偽の runner（tests/test_pipeline.py の FakeRunner・tests/test_pipe_flow.py の ScriptedRunner）と偽の行の元で、最初から最後まで通して確かめる。
待ちの環境は pipeline.reply_env = ReplyEnv(lines=偽の行の元, new_id=…) で差し替える。本物の標準入力は読まない。
SDK を呼ばない。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from reply_support import Do, ScriptLines, id_source, write_reply
from test_pipe_flow import ScriptedRunner, cfg_for, make_pipe, pipe_toml, stage_toml
from test_pipeline import FakeRunner, make_cfg

from pipe_in.dev import record
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.dev.record import Recorder
from pipe_in.engine import clock
from pipe_in.engine import reply as rp
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.live_answer import check_answer
from pipe_in.engine.pipeline import STATE, Exit
from pipe_in.pipe.pipeline import LinearPipeline

REPLY_FILE = "reply.json"  # 本体の定数 REPLY_FILE に頼らず、決めた名前を直に書く
FIXED_TIME = "2026-11-10T12:00:00+09:00"
DEV_WAITS = ["requirements", "design", "red"]


@pytest.fixture(autouse=True)
def stdin_closed(monkeypatch: pytest.MonkeyPatch):
    """本物の標準入力は読まない。うっかり input() に落ちても、EOF（中止）になるだけにする。"""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))


def work_of(tmp_path: Path) -> Path:
    return tmp_path / "docs" / "pipeline"


def state_of(work: Path) -> dict[str, Any]:
    return json.loads((work / STATE).read_text(encoding="utf-8"))


def run_dev(p: DevPipeline, text: str | None = "ログイン画面を作る", frm: str = "requirements") -> Exit:
    return asyncio.run(p.run(text, frm))


class Seen(NamedTuple):
    stage: str
    state: dict[str, Any] | None
    reply: bool


class SpyRunner(FakeRunner):
    """FakeRunner に、段を動かす直前の state.json と返事のファイルの有無を覚えさせ、段の途中の操作を差し込めるようにする。"""

    def __init__(self, verdicts: list[str], *, on_call=None) -> None:
        super().__init__(verdicts)
        self.seen: list[Seen] = []
        self.on_call = on_call

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        path = cfg.work_dir / STATE
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        self.seen.append(Seen(spec.name, data, (cfg.work_dir / REPLY_FILE).exists()))
        run = await super().__call__(spec, prompt, cfg, resume=resume, log_name=log_name)
        if self.on_call is not None:
            self.on_call(spec.name, cfg)
        return run


def counting(fn):
    calls: list[Any] = []

    def wrapped(*args, **kwargs):
        calls.append(args)
        return fn(*args, **kwargs)

    wrapped.calls = calls  # type: ignore[attr-defined]
    return wrapped


def answer_by_file(work: Path, action: str, marks: list[dict[str, Any]], feedback: str | None = None) -> Do:
    """待ちの間に、state.json の印を読んで、その待ちへの有効な返事のファイルを置く（拡張がすることの偽物）。"""

    def fn() -> None:
        data = state_of(work)
        mark = data.get("reply_wait")
        marks.append({"reply_wait": mark, "pending_review": data.get("pending_review", "なし")})
        assert mark, "待ちの間の state.json に reply_wait の印が無い"
        write_reply(work / REPLY_FILE, action, mark["stage"], mark["id"], feedback)

    return Do(fn)


def snapshot_mark(work: Path, marks: list[dict[str, Any]]) -> Do:
    def fn() -> None:
        data = state_of(work)
        marks.append({"reply_wait": data.get("reply_wait"), "pending_review": data.get("pending_review", "なし")})

    return Do(fn)


# ---- AC-20：待ち始めの印 ------------------------------------------------------------------------------------


def test_待ち始めの_state_json_に印が段_識別子_始めた時刻で書かれ_pending_review_は無い(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """D0079-AC-20: 待ち始め（ask が呼ばれる前）の state.json に、印 reply_wait が 段・識別子・始めた時刻 の 3 つで書かれ、
    pending_review は無いまま。識別子は返事の識別子の形（10 文字の 16 進）で、待ちの中で使う識別子と同じ
    （その識別子で作った返事のファイルで、待ちが終わる）。"""
    monkeypatch.setattr(clock, "now_with_offset", lambda: FIXED_TIME)
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    script = ScriptLines([answer_by_file(work, "approve", marks) for _ in DEV_WAITS])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    result = run_dev(p)
    assert len(marks) == 3, f"待ちの間に state.json を読めたのは {len(marks)} 回（3 回のはず）"
    assert result == Exit.PASSED
    for i, (stage, m) in enumerate(zip(DEV_WAITS, marks, strict=True), start=1):
        assert m["reply_wait"] == {"stage": stage, "id": f"{i:010x}", "since": FIXED_TIME}, m
        assert m["pending_review"] is None, "pending_review が入っている（--review や live のボタンが動いてしまう）"


# ---- AC-21：待ちが終わると印が消える ----------------------------------------------------------------------------


def boom(exc: BaseException, work: Path) -> Do:
    """返事のファイル（この待ちには合わない形）を置いてから、例外や中断で待ちを抜ける。"""

    def fn() -> None:
        write_reply(work / REPLY_FILE, "quit", "requirements", "0f0f0f0f0f")
        raise exc

    return Do(fn)


def test_承認で待ちが終わると印が消える(tmp_path: Path):
    """D0079-AC-21: 承認で待ちが終わると、次に保存した state.json（次の段を動かす直前と最後）に印が無い。"""
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    script = ScriptLines([snapshot_mark(work, marks), "", snapshot_mark(work, marks), "", snapshot_mark(work, marks), ""])
    runner = SpyRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=runner)
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert run_dev(p) == Exit.PASSED
    assert len(marks) == 3 and all(m["reply_wait"] for m in marks), "待ちの間に印が無い（確かめが空）"
    assert [s.stage for s in runner.seen] == ["requirements", "design", "red", "implement", "test"]
    assert all("reply_wait" not in (s.state or {}) for s in runner.seen), "待ちが終わったあとの state.json に印が残っている"
    assert "reply_wait" not in state_of(work)


def test_修正の依頼で待ちが終わると印が消え_流し直しの間の_state_json_にも印が無い(tmp_path: Path):
    """D0079-AC-21: 修正の依頼で待ちが終わると印が消え、段を流し直している間の state.json にも印が無い
    （流し直しのあと、もう一度待つとき、また印が付く）。"""
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    script = ScriptLines(
        [snapshot_mark(work, marks), "r", "直して", "", snapshot_mark(work, marks), "", snapshot_mark(work, marks), "", snapshot_mark(work, marks), ""]
    )
    runner = SpyRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=runner)
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert run_dev(p) == Exit.PASSED
    assert [s.stage for s in runner.seen][:4] == ["requirements", "requirements", "design", "red"]
    assert len(marks) == 4 and all(m["reply_wait"] for m in marks), "待ちの間に印が無い（確かめが空）"
    assert [m["reply_wait"]["stage"] for m in marks] == ["requirements", "requirements", "design", "red"]
    assert "reply_wait" not in (runner.seen[1].state or {}), "流し直しの間の state.json に印が残っている"
    assert all("reply_wait" not in (s.state or {}) for s in runner.seen)


def test_中止で待ちが終わると印が消える(tmp_path: Path):
    """D0079-AC-21: 中止で待ちが終わると、最後に保存した state.json に印が無い。"""
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    script = ScriptLines([snapshot_mark(work, marks), "q"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert run_dev(p) == Exit.STOPPED_BY_HUMAN
    assert len(marks) == 1 and marks[0]["reply_wait"], "待ちの間に印が無い（確かめが空）"
    assert "reply_wait" not in state_of(work)


@pytest.mark.parametrize("exc", [RuntimeError("待ちの中で壊れた"), KeyboardInterrupt()], ids=["例外", "KeyboardInterrupt"])
def test_待ちの中で例外や中断で抜けても印を消す(tmp_path: Path, exc: BaseException):
    """D0079-AC-21: 待ちの中で例外や中断（KeyboardInterrupt）で抜けても、state.json の印を消す（返事のファイルも消す）。"""
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    script = ScriptLines([snapshot_mark(work, marks), boom(exc, work)])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    with pytest.raises(type(exc)):
        run_dev(p)
    assert len(marks) == 1 and marks[0]["reply_wait"], "待ちの間に印が無い（確かめが空）"
    assert "reply_wait" not in state_of(work), "抜けたあとの state.json に印が残っている"
    assert not (work / REPLY_FILE).exists(), "抜けたあとに返事のファイルが残っている"


# ---- AC-22：3 か所とも同じ待ちの道を通る -------------------------------------------------------------------------


@pytest.mark.parametrize("target", DEV_WAITS)
def test_3_か所の確認が同じ待ちの道を通る_開発フロー(tmp_path: Path, target: str):
    """D0079-AC-22: 開発フローの要件定義・設計・テスト先行の 3 か所の確認が、どれも同じ待ちの道を通る：印が付き（その段・待ちごとの識別子）、
    有効な返事のファイル（中止）で終わり、返事のファイルが消え、印が消える。対象の段より前の確認は標準入力の Enter で承認する。"""
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    before = DEV_WAITS.index(target)
    script = ScriptLines([""] * before + [answer_by_file(work, "quit", marks)])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert run_dev(p) == Exit.STOPPED_BY_HUMAN
    assert len(marks) == 1, "対象の段の待ちで印が書かれていない"
    assert marks[0]["reply_wait"]["stage"] == target
    final = state_of(work)
    assert {"stage": target, "review": "quit"} in final["runs"]
    assert "reply_wait" not in final
    assert not (work / REPLY_FILE).exists()


def test_3_か所の確認が同じ待ちの道を通る_パイプの段(tmp_path: Path):
    """D0079-AC-22: パイプの確認ありの段（review = true）も同じ待ちの道を通る：印が付き、有効な返事のファイル（承認）で進み、
    返事のファイルと印が消え、次の段まで流れる。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", "review = true\n"), stage_toml("b")))
    work = work_of(tmp_path) / pipe.name
    marks: list[dict[str, Any]] = []
    script = ScriptLines([answer_by_file(work, "approve", marks)])
    runner = ScriptedRunner(pipe)
    p = LinearPipeline(cfg_for(tmp_path, pipe, auto_approve=False), pipe, runner=runner)
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert asyncio.run(p.run("やること")) == Exit.PASSED
    assert len(marks) == 1, "パイプの段の待ちで印が書かれていない"
    assert marks[0]["reply_wait"]["stage"] == "a" and marks[0]["pending_review"] is None
    assert runner.names() == ["a", "b"]
    final = state_of(work)
    assert {"stage": "a", "review": "approved"} in final["runs"]
    assert "reply_wait" not in final
    assert not (work / REPLY_FILE).exists()


def test_パイプの段の修正の依頼も返事のファイルで流し直す(tmp_path: Path):
    """D0079-AC-22: パイプの段で、返事のファイルの修正の依頼（直してほしい点つき）が、指摘を反映した流し直しになる。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", "review = true\n")))
    work = work_of(tmp_path) / pipe.name
    marks: list[dict[str, Any]] = []
    script = ScriptLines([answer_by_file(work, "revise", marks, "ここを直して"), ""])
    runner = ScriptedRunner(pipe)
    p = LinearPipeline(cfg_for(tmp_path, pipe, auto_approve=False), pipe, runner=runner)
    p.reply_env = rp.ReplyEnv(lines=script, new_id=id_source())
    assert asyncio.run(p.run("やること")) == Exit.PASSED
    assert runner.names() == ["a", "a"]
    assert "ここを直して" in runner.calls[1][2]
    assert len(marks) == 1


# ---- AC-15：同じ段の 2 回目の識別子 ---------------------------------------------------------------------------


def test_同じ段の_2_回目の待ちの識別子は_1_回目と違い_1_回目の返事は断られる(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """D0079-AC-15: 同じ段の確認で修正の依頼のあとにもう一度待つとき、2 回目の識別子は 1 回目と違う（時計が同じ値を返し続けても）。
    1 回目の識別子で作った返事は、2 回目の待ちで断られ（id_mismatch）、その返事では進まない。"""
    monkeypatch.setattr(clock, "now_with_offset", lambda: FIXED_TIME)
    work = work_of(tmp_path)
    marks: list[dict[str, Any]] = []
    said: list[str] = []
    gone: list[bool] = []

    def stale() -> None:
        data = state_of(work)
        marks.append({"reply_wait": data.get("reply_wait")})
        write_reply(work / REPLY_FILE, "approve", "requirements", marks[0]["reply_wait"]["id"])

    script = ScriptLines(
        [snapshot_mark(work, marks), "r", "直して", "", Do(stale), Do(lambda: gone.append(not (work / REPLY_FILE).exists())), "q"]
    )
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(lines=script, say=said.append)  # 識別子は本物の乱数（new_id を差し替えない）
    assert run_dev(p) == Exit.STOPPED_BY_HUMAN, "1 回目の返事（承認）で進んでしまった"
    assert len(marks) == 2 and all(m["reply_wait"] for m in marks)
    first, second = marks[0]["reply_wait"], marks[1]["reply_wait"]
    assert first["stage"] == second["stage"] == "requirements"
    assert first["id"] != second["id"], "時計が同じ値のとき、2 回目の識別子が 1 回目と同じ"
    assert first["since"] == second["since"] == FIXED_TIME
    assert any("id_mismatch" in s for s in said)
    assert gone == [True]


# ---- AC-19：流し始め・再開・待ち始めの掃除 ------------------------------------------------------------------------

STALE_STATE = {"name": "残す名前", "custom_key": 1, "pending_review": None, "reply_wait": {"stage": "requirements", "id": "0f0f0f0f0f", "since": FIXED_TIME}}


def prepare_stale(tmp_path: Path, *, docs: bool = False) -> Path:
    work = work_of(tmp_path)
    work.mkdir(parents=True)
    (work / STATE).write_text(json.dumps(STALE_STATE, ensure_ascii=False), encoding="utf-8")
    write_reply(work / REPLY_FILE, "quit", "requirements", "0f0f0f0f0f")
    if docs:
        (work / "00_input.md").write_text("メモ\n", encoding="utf-8")
        (work / "01_requirements.md").write_text("# 要件\nAC-01\n", encoding="utf-8")
        (work / "02_design.md").write_text("# 設計\n", encoding="utf-8")
    return work


@pytest.mark.parametrize("entrance", ["run", "from"])
def test_run_の入口で残っていた返事と強制終了で残った印が消える(tmp_path: Path, entrance: str):
    """D0079-AC-19: 流し始め（run）と再開（--from）の入口で、残っていた返事のファイル（有効な形のものも）が消え、
    強制終了で state.json に残った印だけが外れる（ほかの鍵は変わらない）。最初の段を動かす前に済んでいる。"""
    work = prepare_stale(tmp_path, docs=(entrance == "from"))
    runner = SpyRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=runner)
    frm = "requirements" if entrance == "run" else "red"
    text = "メモ" if entrance == "run" else None
    assert run_dev(p, text, frm) == Exit.PASSED
    first = runner.seen[0]
    assert first.reply is False, "最初の段を動かす前に、残っていた返事のファイルが消えていない"
    assert first.state is not None and "reply_wait" not in first.state, "強制終了で残った印が外れていない"
    assert first.state["custom_key"] == 1 and first.state["name"] == "残す名前", "印以外の鍵が変わった"


def test_review_の入口で残っていた返事が消える(tmp_path: Path):
    """D0079-AC-19: 再開（--review）の入口でも、残っていた返事のファイルが消える（掃除は偽の remove で見える：返事の場所を消そうとした）。"""
    work = work_of(tmp_path)
    work.mkdir(parents=True)
    pending = {"stage": "requirements", "doc": "docs/pipeline/01_requirements.md", "session_id": "s-1", "since": FIXED_TIME}
    (work / STATE).write_text(json.dumps({**STALE_STATE, "pending_review": pending, "runs": []}, ensure_ascii=False), encoding="utf-8")
    write_reply(work / REPLY_FILE, "approve", "requirements", "0f0f0f0f0f")
    removed = counting(rp.remove_reply)
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(remove=removed)
    assert asyncio.run(p.review(Decision("quit"))) == Exit.STOPPED_BY_HUMAN
    assert not (work / REPLY_FILE).exists(), "残っていた返事のファイルが消えていない"
    assert [Path(c[0]).resolve() for c in removed.calls][:1] == [(work / REPLY_FILE).resolve()]
    assert "reply_wait" not in state_of(work)


def test_review_の確認待ちが無いときは返事のファイルに触れない(tmp_path: Path):
    """D0079-AC-19: --review で確認待ちの実行が無いと、今までどおりの文で止まる。その場合は返事のファイルを消さない（入口の掃除は確認待ちを読めたあと）。"""
    work = work_of(tmp_path)
    work.mkdir(parents=True)
    (work / STATE).write_text(json.dumps({**STALE_STATE, "runs": []}, ensure_ascii=False), encoding="utf-8")
    write_reply(work / REPLY_FILE, "approve", "requirements", "0f0f0f0f0f")
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=FakeRunner(["pass"]))
    with pytest.raises(SystemExit, match="確認待ちの実行がありません"):
        asyncio.run(p.review(Decision("approve")))
    assert (work / REPLY_FILE).exists()


def test_返事のファイルも印も無いときは何も起きない(tmp_path: Path):
    """D0079-AC-19: 返事のファイルが無く、印も無いときは、入口の掃除で何も起きない：state.json は流し始めの前と同じ中身のまま、
    最初の段が動く。"""
    work = work_of(tmp_path)
    work.mkdir(parents=True)
    plain = {"name": "残す名前", "custom_key": 1}
    (work / STATE).write_text(json.dumps(plain, ensure_ascii=False), encoding="utf-8")
    removed = counting(rp.remove_reply)
    runner = SpyRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=runner)
    p.reply_env = rp.ReplyEnv(remove=removed)
    assert run_dev(p) == Exit.PASSED
    assert runner.seen[0].state == plain
    assert runner.seen[0].reply is False


def test_消せないときは止まらず流し続ける(tmp_path: Path):
    """D0079-AC-19: 入口の掃除で返事のファイルを消せないとき（偽の remove が失敗を返す。Windows で拡張がまだ開いている場合）も、
    止まらずに流し続ける（終了は成功のまま。消せなかった返事は残る）。"""
    work = prepare_stale(tmp_path)
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=FakeRunner(["pass"]))
    refused = counting(lambda path: False)
    p.reply_env = rp.ReplyEnv(remove=refused)
    assert run_dev(p) == Exit.PASSED
    assert refused.calls, "入口の掃除が返事のファイルを消そうとしていない"
    assert (work / REPLY_FILE).exists()


def test_待ち始めに残っていた返事は消え_その返事では進まない(tmp_path: Path):
    """D0079-AC-19: 待ち始めに、前から残っていた返事のファイルが消える：段の実行中に置かれた、これから作る待ちと同じ段・同じ識別子の
    有効な返事（中止）も、待ち始めの掃除で消えて、その返事では進まない（標準入力の Enter で承認になる）。"""

    def place(stage: str, cfg) -> None:
        if stage == "requirements":
            write_reply(cfg.work_dir / REPLY_FILE, "quit", "requirements", "aaaaaaaaaa")

    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=SpyRunner(["pass"], on_call=place))
    p.reply_env = rp.ReplyEnv(lines=ScriptLines([None, "", "", ""]), new_id=lambda: "aaaaaaaaaa")
    assert run_dev(p) == Exit.PASSED, "待ち始めの掃除が無く、残っていた返事の中止で終わった"


# ---- AC-23：--yes と --pause ----------------------------------------------------------------------------------


def untouched_env(script_items: list[Any] | None = None) -> tuple[rp.ReplyEnv, dict[str, Any]]:
    """呼ばれたら AssertionError になる行の元と、呼ばれた回数を数える new_id・read_file を持つ環境。"""
    reads = counting(rp.read_reply_file)
    ids = counting(id_source())
    env = rp.ReplyEnv(lines=ScriptLines(script_items or []), new_id=ids, read_file=reads)
    return env, {"reads": reads, "ids": ids, "lines": env.lines}


def drop_reply(stage: str, cfg) -> None:
    """段の途中（流し始めの掃除のあと）に、有効な形の返事を置く。"""
    if stage == "requirements":
        write_reply(cfg.work_dir / REPLY_FILE, "quit", "requirements", "0f0f0f0f0f")


def test_yes_は印も書かず返事を読まない(tmp_path: Path):
    """D0079-AC-23: --yes（確認なし）では、印も書かず、返事のファイルを読まない：流し始めの掃除のあと（段の実行中）に置かれた返事は残る。
    待ちの環境（行の元・識別子・ファイルの読み）は一度も呼ばれない。"""
    runner = SpyRunner(["pass"], on_call=drop_reply)
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=runner)
    env, spies = untouched_env()
    p.reply_env = env
    assert run_dev(p) == Exit.PASSED
    assert all("reply_wait" not in (s.state or {}) for s in runner.seen)
    assert "reply_wait" not in state_of(work_of(tmp_path))
    assert (work_of(tmp_path) / REPLY_FILE).exists(), "置かれていた返事が消えた（--yes で読んだか消した）"
    assert spies["reads"].calls == [] and spies["ids"].calls == [] and spies["lines"].events == []


def test_pause_は_pending_review_だけで印も待ちも無い(tmp_path: Path):
    """D0079-AC-23: --pause は pending_review だけを書き、印を書かず、返事の待ちをしない：待ちの環境は一度も呼ばれず、
    段の実行中に置かれた返事も読まれない。終了は確認待ち（5）。"""
    runner = SpyRunner(["pass"], on_call=drop_reply)
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False, pause_for_review=True), runner=runner)
    env, spies = untouched_env()
    p.reply_env = env
    assert run_dev(p) == Exit.AWAITING_REVIEW
    final = state_of(work_of(tmp_path))
    assert final["pending_review"]["stage"] == "requirements"
    assert "reply_wait" not in final
    assert spies["reads"].calls == [] and spies["ids"].calls == [] and spies["lines"].events == []


# ---- AC-24：印があっても --review・live の照合・record check は変わらない（守る） -----------------------------------


def test_印を持つ_state_json_でも_review_は確認待ちの実行がありませんのまま(tmp_path: Path):
    """D0079-AC-24: 印（reply_wait）だけがあって pending_review が無い state.json に --review しても、「確認待ちの実行がありません」のまま
    （今のまま通る。守る）。"""
    work = work_of(tmp_path)
    work.mkdir(parents=True)
    (work / STATE).write_text(json.dumps({**STALE_STATE, "runs": []}, ensure_ascii=False), encoding="utf-8")
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=FakeRunner(["pass"]))
    with pytest.raises(SystemExit, match="確認待ちの実行がありません"):
        asyncio.run(p.review(Decision("approve")))


def test_印を持つ_state_json_でも_check_answer_は確認待ちでないのまま():
    """D0079-AC-24: 印だけがあって pending_review が無い state でも、live の答えの照合 check_answer は「確認待ちでない」(not_pending) のまま。
    pending_review があるときは、印の識別子では通らない（印を見ない。今のまま通る。守る）。"""
    mark = {"stage": "requirements", "id": "a1b2c3d4e5", "since": FIXED_TIME}
    state = {"final": None, "pending_review": None, "reply_wait": mark}
    assert check_answer(state, "requirements", "a1b2c3d4e5") == "not_pending"
    pending = {"final": None, "pending_review": {"stage": "requirements", "since": FIXED_TIME}, "reply_wait": mark}
    assert check_answer(pending, "requirements", "a1b2c3d4e5") == "id_mismatch"


def test_印を持つ_state_json_でも_record_check_の結果は印の無い記録と同じ(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """D0079-AC-24: 印を足した state.json でも、pipe-in record check の終了コードと出力は、印の無い記録と同じ
    （順序が守られている記録も、違反のある記録も。今のまま通る。守る）。"""
    from datetime import datetime, timedelta

    t0 = datetime(2026, 10, 17, 10, 0, 0)
    good = [(0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"), (20, "review", "requirements", "approved"), (30, "begin", "design")]
    bad = [(0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"), (10, "begin", "design"), (20, "review", "requirements", "approved")]
    for label, steps in (("good", good), ("bad", bad)):
        project = tmp_path / label
        project.mkdir()
        now = [t0]
        r = Recorder(load_config(project), now=lambda: now[0])
        r.start("メモ")
        for sec, op, *args in steps:
            now[0] = t0 + timedelta(seconds=sec)
            getattr(r, op)(*args)
        capsys.readouterr()
        plain_code = record.main(["check", "--project", str(project)])
        plain_out = capsys.readouterr().out
        path = project / "docs" / "pipeline" / STATE
        data = json.loads(path.read_text(encoding="utf-8"))
        data["reply_wait"] = {"stage": "requirements", "id": "a1b2c3d4e5", "since": FIXED_TIME}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        marked_code = record.main(["check", "--project", str(project)])
        marked_out = capsys.readouterr().out
        assert (marked_code, marked_out) == (plain_code, plain_out), label
    assert plain_code != 0, "違反のある記録で record check が失敗していない（確かめが空）"


# ---- AC-25：ask を差し替えると印も返事も扱わない ------------------------------------------------------------------


def test_ask_を差し替えると印も返事も扱わない_コンストラクタ引数(tmp_path: Path):
    """D0079-AC-25: コンストラクタの ask= を差し替えた既存の形（偽の確認）は、変更なしで通る。差し替えた ask の中では印を書かず、
    返事のファイルを読まず（置かれた返事は残る）、待ちの環境を呼ばない（今のまま通る。守る）。"""
    runner = SpyRunner(["pass"], on_call=drop_reply)
    asked: list[str] = []

    def fake_ask(stage: str, doc: Path) -> Decision:
        asked.append(stage)
        assert "reply_wait" not in state_of(work_of(tmp_path)), "差し替えた ask の中で印が書かれている"
        return Decision("approve")

    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=runner, ask=fake_ask)
    env, spies = untouched_env()
    p.reply_env = env
    assert run_dev(p) == Exit.PASSED
    assert asked == DEV_WAITS
    assert (work_of(tmp_path) / REPLY_FILE).exists()
    assert spies["reads"].calls == [] and spies["ids"].calls == [] and spies["lines"].events == []


def test_ask_を差し替えると印も返事も扱わない_作ったあとの差し替え(tmp_path: Path):
    """D0079-AC-25: パイプラインを作ったあとに pipeline.ask = … と差し替えても効く（呼ぶ時点で見る）：印も返事も扱わない
    （今のまま通る。守る）。"""
    runner = SpyRunner(["pass"], on_call=drop_reply)
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=runner)
    p.ask = lambda stage, doc: Decision("approve")
    env, spies = untouched_env()
    p.reply_env = env
    assert run_dev(p) == Exit.PASSED
    assert all("reply_wait" not in (s.state or {}) for s in runner.seen)
    assert (work_of(tmp_path) / REPLY_FILE).exists()
    assert spies["reads"].calls == [] and spies["ids"].calls == [] and spies["lines"].events == []


# ---- AC-67：印が無いとき ---------------------------------------------------------------------------------------


def test_印が無いとき_state_json_に_reply_wait_の鍵が無い(tmp_path: Path):
    """D0079-AC-67: 印を書かない流し方（--yes）の state.json には、reply_wait の鍵ごと無い（今のまま通る。守る）。"""
    p = DevPipeline(make_cfg(tmp_path, auto_approve=True), runner=FakeRunner(["pass"]))
    assert run_dev(p) == Exit.PASSED
    assert "reply_wait" not in state_of(work_of(tmp_path))


# ---- AC-75：標準入力が端末でないとき -------------------------------------------------------------------------


class HookedStdin(io.StringIO):
    """読まれるたびに hook を呼ぶ標準入力の偽物（input() が sys.stdin.readline() を呼ぶ）。"""

    def __init__(self, text: str, hook) -> None:
        super().__init__(text)
        self.hook = hook

    def readline(self, *args: Any) -> str:
        self.hook()
        return super().readline(*args)


@pytest.mark.parametrize(
    "typed,result,history",
    [
        ("\n\n\n", Exit.PASSED, []),
        ("r\n指摘を足して\n\n\n\n\n", Exit.PASSED, [{"stage": "requirements", "review": "revise", "feedback": "指摘を足して"}]),
        ("q\n", Exit.STOPPED_BY_HUMAN, [{"stage": "requirements", "review": "quit"}]),
    ],
    ids=["承認", "修正の依頼", "中止"],
)
def test_標準入力が端末でないとき既定の確認は今までの道を通る(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, typed: str, result: Exit, history: list):
    """D0079-AC-75: 標準入力が端末でないとき（ReplyEnv の interactive が偽。行の元は差し替えない）、既定の確認は今までの道（input()）を通る：
    印を書かず、返事のファイルを読まず・待ちの最中に置かれた返事を消さず、打たれた答えで 承認・修正の依頼・中止 になる。
    （input() は sys.stdin から読むので、標準入力を偽物に替えて確かめる。）"""
    work = work_of(tmp_path)
    snapshots: list[dict[str, Any] | None] = []

    def hook() -> None:
        path = work / STATE
        snapshots.append(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None)
        reply = work / REPLY_FILE
        if not reply.exists():
            write_reply(reply, "quit", "requirements", "0f0f0f0f0f")

    monkeypatch.setattr(sys, "stdin", HookedStdin(typed, hook))
    reads = counting(rp.read_reply_file)
    ids = counting(id_source())
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]))
    p.reply_env = rp.ReplyEnv(interactive=lambda: False, read_file=reads, new_id=ids)
    assert run_dev(p) == result
    assert snapshots, "標準入力が読まれていない"
    assert all("reply_wait" not in (s or {}) for s in snapshots), "待ちの最中に印が書かれている"
    assert reads.calls == [] and ids.calls == []
    assert (work / REPLY_FILE).exists(), "待ちの最中に置かれた返事が消えた"
    final = state_of(work)
    for entry in history:
        assert entry in final["runs"]
    assert "reply_wait" not in final
