"""D0079：確認の段の対話の待ち（pipe_in/engine/checkpoint.py の ask_human と pipe_in/engine/reply.py）。

標準入力と返事のファイルの両方を待ち、先に来た有効な答えで進む。待ちの繰り返しは「行の元の get が時間切れ → 返事のファイルを 1 回確かめる」。
本物の標準入力は読まない。行の元は tests/reply_support.py の偽物（決めた順に 行・時間切れ・EOF を返し、時間切れのたびに操作を差し込める。眠らない）。
ThreadLineSource の単体のテストは、止めておける偽の読みで確かめる。AC-76 だけは子プロセスを使う（pty）。
SDK を呼ばない。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from reply_support import (
    OTHER_ID,
    ROOT,
    STAGE,
    TABLE,
    WAIT_ID,
    BlockingReader,
    Do,
    FlakyRemove,
    ScriptLines,
    invalid_bytes,
    strings_in,
    write_reply,
)

from pipe_in.engine import reply as rp
from pipe_in.engine.checkpoint import Decision, ask_human

LABEL = "要件定義"
# 書きかけかもしれない理由（2 回続けて同じ中身が見えるまで断らない）は AC-17 で確かめる
INCOMPLETE = ("not_json", "not_utf8")


def symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink を作れない環境")


class Wait:
    """1 回の確認の待ちを、偽の行の元で流す。返事のファイルの場所は tmp_path/reply.json。"""

    def __init__(self, tmp_path: Path, script: list[Any], *, stage: str = STAGE, wait_id: str = WAIT_ID, **env_kw: Any) -> None:
        self.doc = tmp_path / "doc.md"
        self.doc.write_text("# 文書\n本文\n", encoding="utf-8")
        self.path = tmp_path / "reply.json"
        self.lines = ScriptLines(script)
        self.said: list[str] = []
        self.env = rp.ReplyEnv(lines=self.lines, say=self.said.append, **env_kw)
        self.stage = stage
        self.wait_id = wait_id

    def run(self) -> Decision:
        reply = rp.ReplyWait(self.path, self.stage, self.wait_id, self.env)
        return ask_human(self.stage, self.doc, label=LABEL, reply=reply)

    def put(self, action: str = "approve", feedback: str | None = None, *, stage: str | None = None, wait_id: str | None = None) -> Do:
        return Do(lambda: write_reply(self.path, action, stage or self.stage, wait_id or self.wait_id, feedback))


# ---- AC-10：返事のファイルが無いとき、今までどおり ---------------------------------------------------------------

ANSWERS = [
    pytest.param([""], Decision("approve"), id="Enter"),
    pytest.param(["y"], Decision("approve"), id="y"),
    pytest.param(["r", "AC-02 を追加", ""], Decision("revise", "AC-02 を追加"), id="r_と指摘"),
    pytest.param(["r", "一行目", "二行目", ""], Decision("revise", "一行目\n二行目"), id="r_と複数行の指摘"),
    pytest.param(["q"], Decision("quit"), id="q"),
]


@pytest.mark.parametrize("lines,want", ANSWERS)
def test_返事のファイルが無いとき_Enter_r_q_は今までどおり_reply_なし(tmp_path: Path, lines, want):
    """D0079-AC-10: reply を渡さない（今までの道）の Enter・r と指摘・q は、承認・修正の依頼・中止になる（今のまま通る。守る）。"""
    doc = tmp_path / "doc.md"
    doc.write_text("# 文書\n", encoding="utf-8")
    it = iter(lines)
    assert ask_human(STAGE, doc, read=lambda prompt: next(it), label=LABEL) == want


@pytest.mark.parametrize("lead", [0, 3], ids=["すぐ答える", "時間切れが続いてから答える"])
@pytest.mark.parametrize("lines,want", ANSWERS)
def test_返事のファイルが無いとき_Enter_r_q_は今までどおり(tmp_path: Path, lines, want, lead):
    """D0079-AC-10: 返事のファイルが無いとき、偽の標準入力の Enter・r と指摘・q が、承認・修正の依頼・中止になる
    （reply を渡した待ちの道でも。時間切れが続いて返事のファイルを確かめても何も起きない）。"""
    w = Wait(tmp_path, [None] * lead + lines)
    assert w.run() == want
    assert w.said == []
    assert not w.path.exists()


# ---- AC-11：標準入力が来ないまま返事のファイルで進む ---------------------------------------------------------------


def test_待ちの間隔は_0_5_秒():
    """D0079-AC-11: 待ちの繰り返しの間隔は 0.5 秒（定数 POLL_SEC。ReplyEnv の既定の interval）。"""
    assert rp.POLL_SEC == 0.5
    assert rp.ReplyEnv().interval == 0.5


@pytest.mark.parametrize(
    "action,feedback,want",
    [
        ("approve", None, Decision("approve")),
        ("revise", "ここを直して", Decision("revise", "ここを直して")),
        ("quit", None, Decision("quit")),
    ],
)
def test_標準入力が来ないまま_有効な返事で_承認_修正の依頼_中止_になり_返事が消える(tmp_path: Path, capsys, action, feedback, want):
    """D0079-AC-11: 標準入力に何も来ないまま、有効な返事のファイルが置かれると、待ちが 承認・修正の依頼（直してほしい点つき）・中止 で終わり、
    返事のファイルが消える。偽の行の元が受け取る待ち時間は全部 0.5（偽の眠りで待ちの繰り返しを進める）。"""
    w = Wait(tmp_path, [None, None, None])
    w.lines.script[1:2] = [w.put(action, feedback)]
    assert w.run() == want
    assert not w.path.exists()
    assert w.lines.timeouts and set(w.lines.timeouts) == {0.5}
    assert len(w.lines.timeouts) == 2, "返事が置かれた確かめで終わっていない"
    assert "返事のファイル" in capsys.readouterr().out, "返事のファイルで進んだことが端末に出ていない"


def test_修正の依頼の指摘を入力している間に有効な返事が来ても返事が勝つ(tmp_path: Path):
    """D0079-AC-11: r を打って直してほしい点を入力している間に有効な返事（中止）が置かれたら、その返事で終わる
    （指摘の入力も同じ待ちの道を通る）。"""
    w = Wait(tmp_path, ["r"])
    w.lines.script += [w.put("quit"), "指摘のつもりの文字"]
    assert w.run() == Decision("quit")
    assert not w.path.exists()
    assert w.lines.script == ["指摘のつもりの文字"], "返事のあとも行を読んでいる"


# ---- AC-12：標準入力と返事の両方・持ち越さない ---------------------------------------------------------------------


def test_標準入力と返事が両方あるときは先の_1_つだけで進み_持ち越さない(tmp_path: Path):
    """D0079-AC-12: 標準入力の答えと有効な返事のファイルが両方あるときは、標準入力（先に見る）の 1 つだけで進み、
    返事のファイルは待ちの終わりに消えて、次の待ちで勝手に使われない（次の待ちは標準入力の q で中止になる）。"""
    w = Wait(tmp_path, [""])
    write_reply(w.path, "quit")
    assert w.run() == Decision("approve")
    assert not w.path.exists(), "使わなかった返事が残っている"
    second = Wait(tmp_path, [None, "q"], wait_id=OTHER_ID)
    assert second.run() == Decision("quit")
    assert second.said == []


def test_待ちの最初に_drain_を呼ぶ(tmp_path: Path):
    """D0079-AC-12: 待ちの最初に（最初の get より前に）行の元の drain を 1 回呼び、待ちの外で届いた行を捨てる。"""
    w = Wait(tmp_path, [None, ""])
    w.run()
    assert w.lines.events[:2] == ["drain", "get"]
    assert w.lines.drained == 1


def test_返事で進んだ待ちの陰で打たれた行は次の待ちで使われない(tmp_path: Path):
    """D0079-AC-12: 返事で進んだ待ちのあと、残っていた読みに Enter が届いても、次の待ちの最初の drain で捨てられ、
    次の待ちの答えにならない（次の待ちは、その最中に届いた q で中止になる）。本物の ThreadLineSource と止めておける偽の読みで確かめる。"""
    reader = BlockingReader()
    try:
        src = rp.ThreadLineSource(reader)
        path = tmp_path / "reply.json"
        doc = tmp_path / "doc.md"
        doc.write_text("# 文書\n", encoding="utf-8")

        def first_read(p: Path) -> rp.FileRead:
            write_reply(p, "approve", wait_id=WAIT_ID)
            return rp.read_reply_file(p)

        env1 = rp.ReplyEnv(lines=src, interval=0.01, read_file=first_read, say=lambda s: None)
        got1 = ask_human(STAGE, doc, label=LABEL, reply=rp.ReplyWait(path, STAGE, WAIT_ID, env1))
        assert got1 == Decision("approve")
        assert reader.wait_calls(1), "返事を待つあいだに読みが頼まれていない"

        reader.put("")  # 返事で進んだあとに打たれた Enter（待ちの外）
        assert reader.settled(1)

        polls = [0]

        def second_read(p: Path) -> rp.FileRead:
            polls[0] += 1
            if polls[0] == 1:
                reader.put("q")  # 次の待ちの最中に打たれた q
            return rp.read_reply_file(p)

        env2 = rp.ReplyEnv(lines=src, interval=0.01, read_file=second_read, say=lambda s: None)
        got2 = ask_human(STAGE, doc, label=LABEL, reply=rp.ReplyWait(path, STAGE, OTHER_ID, env2))
        assert got2 == Decision("quit"), "待ちの外で打たれた Enter が次の待ちの答えになった"
        assert reader.calls == 2, "1 行につき読みは 1 回のはず"
    finally:
        reader.release()


# ---- AC-12：ThreadLineSource（頼まれたときだけ読む） --------------------------------------------------------------


@pytest.fixture
def reader():
    r = BlockingReader()
    yield r
    r.release()


def test_ThreadLineSource_は最初の_get_まで読まない(reader: BlockingReader):
    """D0079-AC-12: ThreadLineSource は作っただけでも drain しただけでも読まない。最初の get で、はじめて 1 回読みを頼む。"""
    src = rp.ThreadLineSource(reader)
    assert not reader.wait_calls(1, 0.1), "作っただけで読み始めた"
    src.drain()
    assert not reader.wait_calls(1, 0.1), "drain で読み始めた"
    assert src.get(0.05) is None
    assert reader.wait_calls(1), "get で読みが頼まれていない"
    assert reader.calls == 1


def test_ThreadLineSource_は_1行につき読みは_1回(reader: BlockingReader):
    """D0079-AC-12: 1 行を返したあとは、次の get まで読まない（読み続けない）。行が先に届いていても 1 回ずつ。"""
    src = rp.ThreadLineSource(reader)
    reader.put("a")
    reader.put("b")
    assert src.get(2.0) == "a"
    assert reader.stays_at(1), "1 行読んだあとも先へ読み続けている"
    assert src.get(2.0) == "b"
    assert reader.calls == 2
    assert reader.stays_at(2), "2 行読んだあとも先へ読み続けている"


def test_ThreadLineSource_は読みが残っているあいだは重ねて読まない(reader: BlockingReader):
    """D0079-AC-12: 時間切れで読みが残っているあいだは、get を何度呼んでも読みを重ねて頼まない。残った読みに届いた行を返す。"""
    src = rp.ThreadLineSource(reader)
    assert src.get(0.05) is None
    assert reader.wait_calls(1)
    assert src.get(0.05) is None
    assert src.get(0.05) is None
    assert reader.stays_at(1), "読みが残っているのに重ねて頼んだ"
    reader.put("x")
    assert src.get(2.0) == "x"
    assert reader.calls == 1


def test_ThreadLineSource_は_drain_で待ちの外の行が捨てられる(reader: BlockingReader):
    """D0079-AC-12: 時間切れで残った読みに、待ちの外で届いた行は、drain で捨てられる（次の get の答えにならない）。
    捨てたあとの get は新しく読みを頼み、そこに届いた行を返す。"""
    src = rp.ThreadLineSource(reader)
    assert src.get(0.05) is None
    assert reader.wait_calls(1)
    reader.put("stray")
    assert reader.settled(1)
    src.drain()
    assert src.get(0.05) is None, "待ちの外で届いた行が捨てられていない"
    assert reader.wait_calls(2), "捨てたあとの get が新しく読みを頼んでいない"
    reader.put("real")
    assert src.get(2.0) == "real"
    assert reader.calls == 2


def test_ThreadLineSource_は_EOF_を覚えて_get_のたびに_EOFError(reader: BlockingReader):
    """D0079-AC-12: EOF（読みが EOFError）を見たあとは、get のたびに EOFError を出し、読みを頼み直さない。
    待ちの外で EOF が届いた場合も、drain で捨てずに残る。"""
    src = rp.ThreadLineSource(reader)
    reader.put(EOFError())
    with pytest.raises(EOFError):
        src.get(2.0)
    with pytest.raises(EOFError):
        src.get(0.05)
    assert reader.calls == 1


def test_ThreadLineSource_は待ちの外で届いた_EOF_を_drain_のあとも残す():
    """D0079-AC-12: 時間切れで残った読みに待ちの外で EOF が届いたら、drain のあとの get は EOFError になる。"""
    reader = BlockingReader()
    try:
        src = rp.ThreadLineSource(reader)
        assert src.get(0.05) is None
        assert reader.wait_calls(1)
        reader.put(EOFError())
        assert reader.wait_returned(1)
        src.drain()
        with pytest.raises(EOFError):
            src.get(0.05)
    finally:
        reader.release()


# ---- AC-13：無効な返事は理由を出して消え、待ちが続く ---------------------------------------------------------------

IMMEDIATE = [r for r in TABLE["invalid"] if r["reason"] not in INCOMPLETE]
VOCABULARY = {"approve", "revise", "quit", "approved", "reply.json", "version", "stage", "id", "action", "feedback"}


@pytest.mark.parametrize("row", IMMEDIATE, ids=[r["name"] for r in IMMEDIATE])
def test_無効な返事は理由が端末に出て消え_待ちが続く(tmp_path: Path, capsys, row):
    """D0079-AC-13: 無効な返事のファイル（表の invalid の行。書きかけかもしれない理由の行は AC-17）が置かれると、決まった理由が端末に出て、
    ファイルが消え、待ちは続く（そのあと標準入力の答えで進む）。理由の文に返事の文字は入らない。"""
    w = Wait(tmp_path, [None])
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [Do(lambda: w.path.write_bytes(invalid_bytes(row))), Do(lambda: seen.append((w.path.exists(), list(w.said)))), ""]
    assert w.run() == Decision("approve")
    assert len(seen) == 1
    exists, said = seen[0]
    assert exists is False, "断った返事が消えていない"
    assert said and any(row["reason"] in s for s in said), f"理由 {row['reason']} が端末に出ていない: {said}"
    out = capsys.readouterr().out + "".join(w.said)
    try:
        values = [s for s in strings_in(json.loads(row["text"])) if len(s) >= 4 and s not in VOCABULARY] if "text" in row else []
    except ValueError:
        values = []
    leaked = [s for s in values if s in out]
    assert leaked == [], f"返事の文字が端末の文に入っている: {leaked}"


@pytest.mark.parametrize("field", ["extra_key", "stage", "id", "action", "feedback"])
def test_理由の文に返事の文字は入らない(tmp_path: Path, capsys, field: str):
    """D0079-AC-13: 返事の中の印の文字（鍵・段・識別子・動作・直してほしい点のどこに入れても）が、端末に出す理由の文に入らない。"""
    marker = "秘密の印ZXQ9"
    body: dict[str, Any] = {"version": 1, "stage": STAGE, "id": WAIT_ID, "action": "approve"}
    if field == "extra_key":
        body[marker] = 1
    elif field == "feedback":
        body["action"] = "revise"
        body["feedback"] = marker + "\u0000"
    else:
        body[field] = marker
    w = Wait(tmp_path, [None])
    w.lines.script = [Do(lambda: w.path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")), Do(lambda: None), ""]
    assert w.run() == Decision("approve")
    assert w.said, "理由が端末に出ていない"
    assert marker not in capsys.readouterr().out + "".join(w.said)
    assert not w.path.exists()


def test_無効な返事のあと有効な返事で進める(tmp_path: Path):
    """D0079-AC-13: 無効な返事が断られたあとに有効な返事が置かれたら、その返事で進む（理由は 1 回だけ出る）。"""
    w = Wait(tmp_path, [None])
    w.lines.script = [Do(lambda: w.path.write_text(json.dumps({"version": 2}), encoding="utf-8")), w.put("quit")]
    assert w.run() == Decision("quit")
    assert len(w.said) == 1
    assert not w.path.exists()


# ---- AC-14：段・識別子が合わない返事 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage,wait_id,reason",
    [
        ("design", WAIT_ID, "stage_mismatch"),
        (STAGE, OTHER_ID, "id_mismatch"),
        ("design", OTHER_ID, "stage_mismatch"),
    ],
    ids=["段が合わない", "識別子が合わない（前の待ち・別の実行）", "両方合わない（段が先）"],
)
def test_段が合わない返事と識別子が合わない返事は別の理由で断る(tmp_path: Path, stage, wait_id, reason):
    """D0079-AC-14: 段が合わない返事（別の段の識別子で作ったもの）と識別子が合わない返事（前の待ちの返事・別の実行の返事）は、
    形が正しくても、別々の理由（stage_mismatch・id_mismatch）で断って消し、待ちは続く（標準入力の答えで進む）。"""
    w = Wait(tmp_path, [None])
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [w.put("quit", stage=stage, wait_id=wait_id), Do(lambda: seen.append((w.path.exists(), list(w.said)))), ""]
    assert w.run() == Decision("approve")
    exists, said = seen[0]
    assert exists is False
    assert len(said) == 1 and reason in said[0]
    other = "id_mismatch" if reason == "stage_mismatch" else "stage_mismatch"
    assert other not in said[0]


# ---- AC-16：返事の場所がリンク ----------------------------------------------------------------------------------


@pytest.mark.parametrize("dangling", [False, True], ids=["有効な返事を指すリンク", "ダングリングリンク"])
def test_返事の場所がリンクなら先を読まずリンクだけを消す(tmp_path: Path, dangling: bool):
    """D0079-AC-16: 返事の場所が、有効な返事（中止）を指すリンクのとき、本体は先を読まず、リンクだけを消して待ちを続ける
    （標準入力の Enter で承認になる）。先のファイルは残り、中身も変わらない。ダングリングリンクも同じ。"""
    w = Wait(tmp_path, [None])
    target = tmp_path / "elsewhere.json"
    if not dangling:
        write_reply(target, "quit")
    before = target.read_bytes() if target.exists() else None
    seen: list[bool] = []

    def make_link() -> None:
        symlink_or_skip(w.path, target)

    w.lines.script = [Do(make_link), Do(lambda: seen.append(os.path.lexists(w.path))), ""]
    assert w.run() == Decision("approve"), "リンクの先の返事で進んでしまった"
    assert seen == [False], "リンクが消えていない"
    assert any("not_regular" in s for s in w.said)
    if dangling:
        assert not target.exists(), "リンクの先に何かが作られた"
    else:
        assert target.read_bytes() == before, "リンクの先の中身が変わった"


# ---- AC-17：書きかけ ------------------------------------------------------------------------------------------


PARTIAL = [
    pytest.param(b'{"version":1,"stage":"requirements","id":"a1b2c3d4e5","act', "not_json", id="途中で切れた_JSON"),
    pytest.param(b"\xff\xfe{", "not_utf8", id="UTF-8_でない"),
]


@pytest.mark.parametrize("partial,reason", PARTIAL)
def test_書きかけは_1回だけなら消さず完成した返事で進む(tmp_path: Path, partial: bytes, reason: str):
    """D0079-AC-17: 解釈できない中身が 1 回だけ見えて、次の確認で完全な有効な返事になっていたら、その返事で進む。
    1 回目のときは消さず、理由も出さない。"""
    w = Wait(tmp_path, [None])
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [
        Do(lambda: w.path.write_bytes(partial)),
        Do(lambda: (seen.append((w.path.exists(), list(w.said))), write_reply(w.path, "quit"))),
    ]
    assert w.run() == Decision("quit")
    assert seen == [(True, [])], "書きかけを 1 回目で消した・理由を出した"
    assert w.said == []
    assert not w.path.exists()


@pytest.mark.parametrize("partial,reason", PARTIAL)
def test_同じ解釈できない中身が_2_回続けて見えたら断って消す(tmp_path: Path, partial: bytes, reason: str):
    """D0079-AC-17: 同じ解釈できない中身が 2 回続けて見えたら、無効として断る（理由を 1 回出す）。ファイルを消して、待ちは続く。"""
    w = Wait(tmp_path, [None])
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [
        Do(lambda: w.path.write_bytes(partial)),
        Do(lambda: seen.append((w.path.exists(), list(w.said)))),
        Do(lambda: seen.append((w.path.exists(), list(w.said)))),
        "",
    ]
    assert w.run() == Decision("approve")
    assert seen[0] == (True, []), "1 回目で断った"
    exists, said = seen[1]
    assert exists is False, "2 回続けて同じ中身なのに消えていない"
    assert len(said) == 1 and reason in said[0]


def test_中身が違う解釈できないものが続いても断らない(tmp_path: Path):
    """D0079-AC-17: 解釈できない中身でも、前の確かめと中身が違うあいだは、覚えるだけで断らず消さない（書いている途中が伸びていく形）。"""
    w = Wait(tmp_path, [None])
    first = b'{"version":1,"stage":"requ'
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [
        Do(lambda: w.path.write_bytes(first)),
        Do(lambda: w.path.write_bytes(first + b'irements","id":"a1b2')),
        Do(lambda: seen.append((w.path.exists(), list(w.said)))),
        "",
    ]
    assert w.run() == Decision("approve")
    assert seen == [(True, [])]


def test_ファイルが無い確かめで書きかけの覚えを忘れる(tmp_path: Path):
    """D0079-AC-17: 書きかけが見えたあとファイルが無くなったら、覚えを忘れる。同じ中身がまた見えても、1 回目として扱って断らない。"""
    w = Wait(tmp_path, [None])
    partial = b'{"version":1,"stage":'
    seen: list[tuple[bool, list[str]]] = []
    w.lines.script = [
        Do(lambda: w.path.write_bytes(partial)),
        Do(lambda: w.path.unlink()),
        Do(lambda: w.path.write_bytes(partial)),
        Do(lambda: seen.append((w.path.exists(), list(w.said)))),
        "",
    ]
    assert w.run() == Decision("approve")
    assert seen == [(True, [])]


# ---- AC-18：EOF ----------------------------------------------------------------------------------------------

EOF_MESSAGE = "入力を読めなかったため中止します（確認を省くなら --yes）。"


def test_標準入力が閉じていて返事も無ければ今までどおり中止になり同じ文が出る_reply_なし(tmp_path: Path, capsys):
    """D0079-AC-18: reply を渡さない今までの道で、標準入力が閉じている（EOF）と中止になり、決まった文が出る（今のまま通る。守る）。"""
    doc = tmp_path / "doc.md"
    doc.write_text("# 文書\n", encoding="utf-8")

    def eof(prompt: str) -> str:
        raise EOFError

    assert ask_human(STAGE, doc, read=eof, label=LABEL) == Decision("quit")
    assert EOF_MESSAGE in capsys.readouterr().out


@pytest.mark.parametrize("lead", [0, 2], ids=["すぐ EOF", "時間切れのあとで EOF"])
def test_標準入力が閉じていて返事も無ければ今までどおり中止になり同じ文が出る(tmp_path: Path, capsys, lead: int):
    """D0079-AC-18: 標準入力が閉じている（EOF）と、返事のファイルが無ければ、今までどおり中止になり、同じ文が出る。"""
    w = Wait(tmp_path, [None] * lead + [EOFError])
    assert w.run() == Decision("quit")
    assert EOF_MESSAGE in capsys.readouterr().out
    assert w.said == []


def test_修正の依頼の指摘の入力中に_EOF_でも中止になる(tmp_path: Path, capsys):
    """D0079-AC-18: r のあと直してほしい点の入力中に EOF になっても、今までどおり中止になる。"""
    w = Wait(tmp_path, ["r", EOFError])
    assert w.run() == Decision("quit")
    assert EOF_MESSAGE in capsys.readouterr().out


# ---- AC-19：消せないとき（待ちの側） --------------------------------------------------------------------------


def test_消せないときは止まらず_照合で断られ_消せるようになったら消える(tmp_path: Path):
    """D0079-AC-19: 残っていた返事のファイルを消せないとき（偽の remove が失敗を返す。Windows で拡張がまだ開いている場合）は、止まらず、
    その返事は読むときの照合で断られ（その返事では進まない）、次の繰り返しで消し直す。消せるようになったら消える。"""
    flaky = FlakyRemove(fail_times=2)
    w = Wait(tmp_path, [None, None, None, ""], remove=flaky)
    write_reply(w.path, "quit", STAGE, OTHER_ID)  # 前の待ちから残っていた返事
    assert w.run() == Decision("approve"), "残っていた返事で進んだ（照合で断られていない）"
    assert not w.path.exists(), "消せるようになったのに消えていない"
    assert flaky.calls >= 3, f"繰り返しのたびに消し直していない（消そうとした回数 {flaky.calls}）"
    assert w.said and all("id_mismatch" in s for s in w.said)


# ---- 端末の読みと環境（AC-75・76 の支え） ----------------------------------------------------------------------


class FakeRaw:
    def __init__(self, data: bytes | BaseException) -> None:
        self.data = data

    def readline(self) -> bytes:
        if isinstance(self.data, BaseException):
            raise self.data
        out, self.data = self.data, b""
        return out


class FakeStdin:
    encoding = "utf-8"

    def __init__(self, data: bytes | BaseException = b"", *, tty: bool = True, raw: bool = True) -> None:
        self.tty = tty
        if raw:
            self.buffer = type("Buffer", (), {"raw": FakeRaw(data)})()

    def isatty(self) -> bool:
        return self.tty


@pytest.mark.parametrize(
    "data,want",
    [(b"hello\n", "hello"), (b"hello\r\n", "hello"), (b"hello", "hello"), (b"\n", ""), ("日本語\n".encode(), "日本語")],
)
def test_端末の読みは生の_readline_で_1_行読み_末尾の改行を_1_つ取る(monkeypatch: pytest.MonkeyPatch, data: bytes, want: str):
    """D0079-AC-76: read_terminal_line は sys.stdin.buffer.raw.readline() で 1 行読み（input() の錠を持たない読み）、末尾の改行を 1 つ取る。"""
    monkeypatch.setattr(sys, "stdin", FakeStdin(data))
    assert rp.read_terminal_line() == want


def test_端末の読みは空なら_EOFError_読めない例外も_EOFError(monkeypatch: pytest.MonkeyPatch):
    """D0079-AC-76: 空（EOF）は EOFError。OSError など読めない例外も EOF と同じ（EOFError）。壊れたバイト列は置き換えて読む。"""
    monkeypatch.setattr(sys, "stdin", FakeStdin(b""))
    with pytest.raises(EOFError):
        rp.read_terminal_line()
    monkeypatch.setattr(sys, "stdin", FakeStdin(OSError("閉じている")))
    with pytest.raises(EOFError):
        rp.read_terminal_line()
    monkeypatch.setattr(sys, "stdin", FakeStdin(b"\xff\xfeabc\n"))
    assert rp.read_terminal_line().endswith("abc")


@pytest.mark.parametrize(
    "stdin,want",
    [
        (FakeStdin(tty=True), True),
        (FakeStdin(tty=False), False),
        (FakeStdin(tty=True, raw=False), False),
        (None, False),
    ],
    ids=["端末", "端末でない", "buffer.raw が無い", "標準入力が無い"],
)
def test_標準入力が端末かの判断(monkeypatch: pytest.MonkeyPatch, stdin, want: bool):
    """D0079-AC-75: stdin_is_terminal は、sys.stdin が有り、isatty() が真で、buffer.raw を持つときだけ真（例外は偽）。"""
    monkeypatch.setattr(sys, "stdin", stdin)
    assert rp.stdin_is_terminal() is want


def test_isatty_が例外を出しても偽(monkeypatch: pytest.MonkeyPatch):
    """D0079-AC-75: isatty() が例外を出しても、stdin_is_terminal は例外を出さず偽。"""

    class Broken(FakeStdin):
        def isatty(self) -> bool:
            raise ValueError("閉じたファイル")

    monkeypatch.setattr(sys, "stdin", Broken())
    assert rp.stdin_is_terminal() is False


def test_ReplyEnv_は行の元が差し替えられていれば使える_なければ標準入力の判断に従う():
    """D0079-AC-75: ReplyEnv.usable() は、行の元（lines）が差し替えられていれば真。そうでなければ interactive() に従う。"""
    assert rp.ReplyEnv(lines=ScriptLines([]), interactive=lambda: False).usable() is True
    assert rp.ReplyEnv(interactive=lambda: False).usable() is False
    assert rp.ReplyEnv(interactive=lambda: True).usable() is True


def test_ReplyEnv_の行の元は最初の使用で作って持ち続ける(reader: BlockingReader):
    """D0079-AC-12: lines を差し替えなければ、最初の line_source() で ThreadLineSource(read_line) を作って持ち、あとは同じものを返す。
    差し替えた lines はそのまま返す。"""
    env = rp.ReplyEnv(read_line=reader)
    first = env.line_source()
    assert isinstance(first, rp.ThreadLineSource)
    assert env.line_source() is first
    assert not reader.wait_calls(1, 0.1), "作っただけで読み始めた"
    fake = ScriptLines([])
    assert rp.ReplyEnv(lines=fake).line_source() is fake


# ---- AC-76：返事で進んだあと端末の読みが残っても、すぐ終わる（子プロセス・pty） ---------------------------------

EXIT_CODE = 7
MARK_PENDING = "READ_PENDING"
CHILD = """\
import sys, threading
sys.path.insert(0, {root!r})
from pipe_in.engine.reply import ThreadLineSource, read_terminal_line

src = ThreadLineSource(read_terminal_line)
got = src.get(0.3)  # 端末には何も届かない：時間切れで、頼んだ読みが残る
assert got is None, "時間切れにならなかった"
alive = [t for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive()]
print({mark!r} if alive else "NO_PENDING_READ", flush=True)
sys.exit({code})
"""


def read_pty(fd: int) -> str:
    import select

    chunks: list[bytes] = []
    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 2.0)
        except (OSError, ValueError):
            break
        if not ready:
            break
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")


@pytest.mark.parametrize("stdout_is_pty", [True, False], ids=["標準入力と標準出力が pty", "標準入力だけ pty"])
def test_返事で進んだあと端末の読みが残っても決まった終了コードですぐ終わる(tmp_path: Path, stdout_is_pty: bool):
    """D0079-AC-76: 子プロセスが本物の既定の読み（ThreadLineSource(read_terminal_line)）で get を 1 回時間切れにし（頼んだ読みが残る）、
    読むスレッドが生きていることを自分で確かめて印を出してから、決めた終了コードで普通に終わる。親は、終了コード・印・Fatal Python error が
    出ないこと・10 秒の中で終わることを見る（終わらなければ kill して落とす）。pty を作れない環境（Windows）では飛ばす。"""
    try:
        import pty
    except ImportError:
        pytest.skip("pty を作れない環境")
    try:
        master, slave = pty.openpty()
    except OSError:
        pytest.skip("pty を作れない環境")
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(root=str(ROOT), mark=MARK_PENDING, code=EXIT_CODE), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=slave,
        stdout=slave if stdout_is_pty else subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
    )
    os.close(slave)
    try:
        try:
            code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("子プロセスが 10 秒たっても終わらない（残った読みで止まっている）")
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        out = read_pty(master) if stdout_is_pty else (proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else "")
    finally:
        os.close(master)
        for pipe in (proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
    assert "Fatal Python error" not in err + out, err + out
    assert code == EXIT_CODE, f"終了コード {code}\n{err}"
    assert MARK_PENDING in out, f"読みが残っている印が出ていない: {out!r}\n{err}"
