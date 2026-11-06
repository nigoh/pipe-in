"""D0077-AC-07〜11：守りの確かめ（pipe-in-gen chat probe）。

確かめは二段：1回目が乱数入りの範囲外のパスと確かめ役への指示を出し、会話が確かめ役を呼んだあと、2回目が
「範囲外のファイルが無い」ことと「フックが pipe-probe の agent_type を見て止めた跡」を読んで「確かめ済み」にする。
フックは本物の入口 chat_hook.main() を通す（確かめ役の返事は信じない）。
"""

from __future__ import annotations

import json

import pytest
from chat_support import NONCE, PROBE, Run, no_sdk, pipe_toml, stage_toml, text_of  # noqa: F401

from pipe_in.engine.config import load_config
from pipe_in.pipe import definition as pd
from pipe_in.pipe.specs import build_pipe_specs

pytestmark = pytest.mark.usefixtures("no_sdk")


def four_access() -> str:
    return pipe_toml(
        stage_toml("r", access="read", output="01_r.md"),
        stage_toml("d", access="docs", docs_dir="docs/out", output="02_d.md"),
        stage_toml("d2", access="docs", docs_dir="docs/out", output="03_d2.md", extra='writes = ["docs/out/a/*"]\n'),
        stage_toml("t", access="tests", output="04_t.md"),
        stage_toml("c", access="code", output="05_c.md", extra='bash = true\n'),
        stage_toml("c2", access="code", output="06_c2.md", extra='writes = ["src/*"]\n'),
    )


def started(tmp_path, toml: str | None = None) -> Run:
    r = Run(tmp_path)
    r.make(toml or pipe_toml(stage_toml("a"), stage_toml("b")))
    assert r.start()["ok"] is True
    return r


# ---- AC-07 ----------------------------------------------------------------------------------


def test_d0077_ac07_確かめが済んでいないとnextは先にprobeを返す(tmp_path):
    """D0077-AC-07: 確かめが済んでいないと、chat next は段の指示を出さず、「先に chat probe を」と返す。"""
    r = started(tmp_path)
    out = r.next()
    assert out["action"] == "probe", out
    assert "chat probe" in text_of(out)
    assert "agent_prompt" not in out
    assert r.state()["open"] is None, "確かめの前に段が開いた"
    assert r.logs() == []


def test_d0077_ac07_確かめ役を呼んだだけでは済みにならない(tmp_path):
    """D0077-AC-07: 1回目のあと、2回目（読んで確かめる）の前は、まだ段の指示が出ない。"""
    r = started(tmp_path)
    r.ask_probe()
    assert r.next()["action"] == "probe"


# ---- AC-08 ----------------------------------------------------------------------------------


def test_d0077_ac08_確かめの1回目は乱数入りの範囲外のパスを出し4つのaccessのどれの範囲にも入らない(tmp_path):
    """D0077-AC-08: 確かめの1回目は、乱数を含む範囲外のパスと、確かめ役 pipe-probe へ渡す指示を出す。そのパスは read・docs・tests・code のどの段の書ける範囲にも入らない。"""
    r = started(tmp_path, four_access())
    out = r.ask_probe()
    probe = r.state()["chat"]["probe"]
    assert probe["status"] == "asked"
    assert NONCE.fullmatch(probe["nonce"]), probe
    path = r.probe_path()
    assert probe["nonce"] in path.name and probe["nonce"] in text_of(out), "乱数がパスと出力に入っている"
    assert "pipe-probe" in text_of(out), "確かめ役への指示（呼ぶ相手）が出る"
    assert str(path) in text_of(out) or r.rel(path) in text_of(out), "範囲外のパスが出力に出る"
    assert not path.exists(), "1回目はまだ何も書かない"
    cfg = load_config(tmp_path).for_pipe(r.pipe, own_work_dir=True)
    specs = build_pipe_specs(cfg, pd.load_pipe(r.pipe_dir))
    rel = r.rel(path)
    inside = [name for name, spec in specs.items() if spec.can_write(rel)]
    assert inside == [], f"確かめのパスが書ける範囲に入っている段: {inside}"


def test_d0077_ac08_確かめるたびに乱数が変わる(tmp_path):
    """D0077-AC-08: 確かめが失敗したあとに1回目をもう一度呼ぶと、別の乱数のパスを出す（前の跡を使い回せない）。

    出したあとに続けて呼ぶと「読んで確かめる」になる（AC-10）ので、出し直しは失敗のあとに確かめる（人の承認で直した。D0077）。
    """
    r = started(tmp_path)
    r.ask_probe()
    first = r.state()["chat"]["probe"]["nonce"]
    assert r.cmd("probe")["action"] == "probe_failed", "跡が無いので確かめは失敗する"
    r.ask_probe()
    second = r.state()["chat"]["probe"]["nonce"]
    assert first != second


# ---- AC-09 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("agent_type", ["pipe-probe", "pipe-in:pipe-probe"])
def test_d0077_ac09_そろったときだけ確かめ済みになる(tmp_path, agent_type):
    """D0077-AC-09: 範囲外のファイルが無く、フックの跡に「pipe-probe の agent_type を見て止めた」とあり、乱数が合うときだけ、2回目が「確かめ済み」を記録する。"""
    r = started(tmp_path)
    r.ask_probe()
    path = r.probe_path()
    reason = r.hook("Write", {"file_path": str(path), "content": "probe"}, agent_type)
    assert reason, "確かめ役の範囲外の Write は止まる"
    trace = [json.loads(line) for line in (r.run_dir / "hook" / "trace.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    denied = [t for t in trace if t.get("event") == "probe_denied"]
    assert denied and denied[-1]["as"] == "pipe-probe" and denied[-1]["tool"] == "Write", trace
    assert denied[-1]["agent_type"] == agent_type, "入力の生の値を残す"
    out = r.cmd("probe")
    assert r.code == 0 and out["action"] == "probe_ok", out
    probe = r.state()["chat"]["probe"]
    assert probe["status"] == "verified" and probe.get("verified_at")
    assert not path.exists()
    first = r.next()
    assert first["action"] == "run_stage", "確かめ済みなら最初の段が出る"


# ---- AC-10 ----------------------------------------------------------------------------------


def _file_exists(r: Run) -> None:
    """範囲外のファイルができている（フックの跡もある）。"""
    assert r.hook("Write", {"file_path": str(r.probe_path()), "content": "x"}, PROBE)
    r.probe_path().parent.mkdir(parents=True, exist_ok=True)
    r.probe_path().write_text("書けてしまった", encoding="utf-8")


def _file_without_trace(r: Run) -> None:
    """フックが呼ばれずにファイルができた。"""
    r.probe_path().parent.mkdir(parents=True, exist_ok=True)
    r.probe_path().write_text("書けてしまった", encoding="utf-8")


def _nothing(r: Run) -> None:
    """フックが呼ばれていない（agent_type が来ていない場合も同じ見え方）。"""


def _no_agent_type(r: Run) -> None:
    assert r.hook("Write", {"file_path": str(r.probe_path()), "content": "x"}, None) is None, "会話本体には何もしない"


def _as_stage(r: Run) -> None:
    assert r.hook("Write", {"file_path": str(r.probe_path()), "content": "x"}, "pipe-in:pipe-stage")


def _lookalike(name: str):
    def go(r: Run) -> None:
        r.hook("Write", {"file_path": str(r.probe_path()), "content": "x"}, name)

    return go


def _other_nonce(r: Run) -> None:
    other = r.probe_path().with_name("0123456789abcdef.txt")
    assert r.hook("Write", {"file_path": str(other), "content": "x"}, PROBE)


def _other_tool(r: Run) -> None:
    assert r.hook("Edit", {"file_path": str(r.probe_path()), "old_string": "a", "new_string": "b"}, PROBE)


def _other_target(r: Run) -> None:
    assert r.hook("Write", {"file_path": str(r.project / "src" / "x.txt"), "content": "x"}, PROBE)


# 名前は、範囲外のファイルができている／フックを通らずファイルができた／フックの跡が無い／agent_type が来ていない／
# agent_type が pipe-stage／pipe-probe-x／my-pipe-probe／乱数が違う／道具が Write でない／パスが確かめ用でない
FAIL_CASES = [
    ("file-exists", _file_exists),
    ("file-without-trace", _file_without_trace),
    ("no-trace", _nothing),
    ("no-agent-type", _no_agent_type),
    ("as-pipe-stage", _as_stage),
    ("pipe-probe-x", _lookalike("pipe-probe-x")),
    ("my-pipe-probe", _lookalike("my-pipe-probe")),
    ("other-nonce", _other_nonce),
    ("other-tool", _other_tool),
    ("other-target", _other_target),
]


@pytest.mark.parametrize("name,setup", FAIL_CASES, ids=[n for n, _ in FAIL_CASES])
def test_d0077_ac10_そろわないと確かめ済みにならず理由を伝える(tmp_path, name, setup):
    """D0077-AC-10: 範囲外のファイルができている／フックの跡が無い／乱数が違う／agent_type が pipe-probe でない／道具が違う のどれかなら、
    「確かめ済み」にならず、理由を伝える。段の指示は出ない。"""
    r = started(tmp_path)
    r.ask_probe()
    setup(r)
    out = r.cmd("probe")
    assert out["action"] == "probe_failed", out
    assert out.get("message"), "理由を伝える"
    assert r.state()["chat"]["probe"]["status"] == "failed"
    assert r.state()["chat"]["probe"].get("reason")
    nxt = r.next()
    assert nxt["action"] == "probe", "確かめ済みでないので段の指示は出ない"
    assert r.state()["open"] is None


def test_d0077_ac10_失敗のあとにやり直して確かめ済みになれる(tmp_path):
    """D0077-AC-10: 失敗のあと、1回目からやり直してそろえば、確かめ済みになる。"""
    r = started(tmp_path)
    r.ask_probe()
    assert r.cmd("probe")["action"] == "probe_failed"
    r.verify_probe()
    assert r.state()["chat"]["probe"]["status"] == "verified"
    assert r.next()["action"] == "run_stage"


# ---- AC-11 ----------------------------------------------------------------------------------


def test_d0077_ac11_確かめの印はその実行だけに効く(tmp_path):
    """D0077-AC-11: 確かめ済みの印は、その実行（その state.json）だけに効く。新しい実行を始めると、また確かめが要る。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a")))
    assert r.start()["ok"] is True
    r.verify_probe()
    assert r.state()["chat"]["probe"]["status"] == "verified"
    assert r.start(memo="次の実行")["ok"] is True
    assert r.state()["chat"]["probe"]["status"] == "none", "新しい実行は確かめていない"
    assert r.next()["action"] == "probe"
