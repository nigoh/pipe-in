"""D0082-AC-01〜03・07・08・10：会話の道の能力表（pipe_in/pipe/capability.py）の検査。

表に全項目が載っていること・載っている鍵が実在すること・検査そのものが働くこと・断る/黙る項目に理由があること・
docs/guide/pipes.md の2つの表と同じ集合であること・chat.py に項目名で分ける条件が残らないこと。
SDK は呼ばない。リポジトリの実物には書かない（読むだけ。偽の dataclass・偽の表・偽の chat.py は tmp_path の中）。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from pipe_in.engine.config import Config, StageConfig
from pipe_in.pipe import capability
from pipe_in.pipe.capability import Row
from pipe_in.pipe.definition import AgentDef, JudgeItem, McpServerDef, PipeDef, PipeStage, StageCheck, StageJudge

ROOT = Path(__file__).resolve().parent.parent

REAL_CLASSES = (PipeDef, PipeStage, StageCheck, StageJudge, JudgeItem, AgentDef, McpServerDef, StageConfig, Config)


# ---- AC-01・02：実物の表と全項目の突き合わせ -----------------------------------------------------


def test_d0082_ac01_全項目が表にある():
    """D0082-AC-01: PipeDef・PipeStage・StageCheck・StageJudge・JudgeItem・AgentDef・McpServerDef・StageConfig・Config の fields() で集めた
    全項目が表にある（check_table が「表に無い」を1件も返さない）。表が空のままではいけない。"""
    assert capability.TABLE, "能力表が空（まだ項目を載せていない）"
    problems = capability.check_table(capability.TABLE, REAL_CLASSES)
    missing = [p for p in problems if p.startswith("表に無い")]
    assert missing == []


def test_d0082_ac02_表の鍵はすべて実在する():
    """D0082-AC-02: 表の鍵は、すべて実在する項目か --after（check_table が「実在しない」を1件も返さない）。--after は表に必ずある。"""
    assert capability.TABLE, "能力表が空（まだ項目を載せていない）"
    problems = capability.check_table(capability.TABLE, REAL_CLASSES, extra_keys=("--after",))
    ghosts = [p for p in problems if p.startswith("実在しない")]
    assert ghosts == []
    assert "--after" in {r.key for r in capability.TABLE}


def test_d0082_ac01_実物の表は内部の整合の問題も無い():
    """D0082-AC-01: 実物の表は check_table の問題が空（動きの種類・理由・断る文・親子の食い違いなど、表の整合も満たす）。"""
    assert capability.TABLE, "能力表が空（まだ項目を載せていない）"
    assert capability.check_table(capability.TABLE, REAL_CLASSES) == []


# ---- AC-03：検査そのものの確かめ -----------------------------------------------------------------


@dataclass
class FakeThing:
    a: int = 0
    b: int = 0


def fake_table(*rows: Row) -> tuple[Row, ...]:
    return tuple(rows)


def works(key: str) -> Row:
    return Row(key, capability.WORKS, capability.WORKS)


def test_d0082_ac03_項目を足した偽のdataclassは表に無いと報告する():
    """D0082-AC-03: 表が a だけを載せているとき、b を持つ偽の dataclass を渡すと「表に無い: FakeThing.b」と報告する。"""
    problems = capability.check_table(fake_table(works("FakeThing.a")), (FakeThing,), extra_keys=())
    assert "表に無い: FakeThing.b" in problems
    assert not [p for p in problems if "FakeThing.a" in p]


def test_d0082_ac03_全項目を載せた偽の表は問題なしと返す():
    """D0082-AC-03: 全項目を載せた偽の表では、問題が空（検査が何でも報告するのではないこと）。"""
    assert capability.check_table(fake_table(works("FakeThing.a"), works("FakeThing.b")), (FakeThing,), extra_keys=()) == []


def test_d0082_ac03_実在しない鍵の偽の表は実在しないと報告する():
    """D0082-AC-03: 実在しない鍵（FakeThing.zzz）を足した表は「実在しない: FakeThing.zzz」と報告する。"""
    table = fake_table(works("FakeThing.a"), works("FakeThing.b"), works("FakeThing.zzz"))
    assert "実在しない: FakeThing.zzz" in capability.check_table(table, (FakeThing,), extra_keys=())


def test_d0082_ac03_extra_keysの鍵は実在するものとして扱う():
    """D0082-AC-03: extra_keys に挙げた鍵（--after）は、型の項目でなくても実在しない扱いにならない。挙げなければ「実在しない」になる。"""
    table = fake_table(works("FakeThing.a"), works("FakeThing.b"), works("--after"))
    assert capability.check_table(table, (FakeThing,), extra_keys=("--after",)) == []
    assert "実在しない: --after" in capability.check_table(table, (FakeThing,), extra_keys=())


# ---- AC-07：理由 -----------------------------------------------------------------------------------


def test_d0082_ac07_断る項目と黙る項目は理由を持つ():
    """D0082-AC-07: 実物の表で、sdk か chat が「断る」「黙る」の行は、すべて空でない理由の文を持つ。"""
    assert capability.TABLE, "能力表が空（まだ項目を載せていない）"
    need = [r for r in capability.TABLE if capability.REFUSE in (r.chat, r.sdk) or capability.SILENT in (r.chat, r.sdk)]
    assert need, "断る・黙る行が1つも無い"
    assert [r.key for r in need if not r.reason.strip()] == []
    # 黙る項目は設計どおり setting_sources・auto_approve
    assert {"Config.setting_sources", "Config.auto_approve"} <= {r.key for r in need if r.chat == capability.SILENT}


def test_d0082_ac07_理由が空の断る行は検査が報告する():
    """D0082-AC-07: 検査そのものの確かめ。理由が空の「断る」「黙る」の行を持つ偽の表では、check_table がその鍵を挙げて報告する。"""
    refuse = Row(
        "FakeThing.a", capability.WORKS, capability.REFUSE, reason="", scope="pipe", path=("a",), sentence="a は断ります"
    )
    silent = Row("FakeThing.b", capability.WORKS, capability.SILENT, reason="")
    problems = capability.check_table(fake_table(refuse, silent), (FakeThing,), extra_keys=())
    assert any("FakeThing.a" in p for p in problems), problems
    assert any("FakeThing.b" in p for p in problems), problems
    # 理由を書けば問題は無くなる
    ok = (
        Row("FakeThing.a", capability.WORKS, capability.REFUSE, reason="理由", scope="pipe", path=("a",), sentence="a は断ります"),
        Row("FakeThing.b", capability.WORKS, capability.SILENT, reason="理由"),
    )
    assert capability.check_table(ok, (FakeThing,), extra_keys=()) == []


# ---- AC-08：docs/guide/pipes.md の2つの表 ----------------------------------------------------------

DOC_NAME = {"StageCheck.judge": "check.judge"}


def doc_tables(text: str) -> tuple[set[str], set[str]]:
    """「会話の中で流すとき」の節の、断る表（| 形 | 理由 |）と効かない設定の表（| 設定 | 場所 |）の1列目の項目名の集合。"""
    m = re.search(r"^## 会話の中で流すとき\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, "「会話の中で流すとき」の節を読めない"
    section = m.group(1)

    def first_column(header: str) -> set[str]:
        lines = section.splitlines()
        starts = [i for i, ln in enumerate(lines) if ln.replace(" ", "").startswith(header.replace(" ", ""))]
        assert starts, f"表（{header}）を読めない"
        names: set[str] = set()
        for ln in lines[starts[0] + 2 :]:
            if not ln.startswith("|"):
                break
            cell = ln.split("|")[1]
            cell = re.sub(r"（[^）]*）|\([^)]*\)", "", cell)
            for token in re.findall(r"`([^`]*)`", cell):
                names.add(token.split("=")[0].strip())
        assert names, f"表（{header}）の行を読めない"
        return names

    return first_column("| 形 | 理由 |"), first_column("| 設定 | 場所 |")


def table_names(action: str) -> set[str]:
    keys = set(capability.keys_with(action))
    parents = [r for r in capability.TABLE if r.key in keys and not r.via]
    return {DOC_NAME.get(r.key, r.key.split(".", 1)[-1]) for r in parents}


def test_d0082_ac08_pipes_mdの表と能力表が同じ集合():
    """D0082-AC-08: docs/guide/pipes.md の「扱えない形」の表の項目が能力表の「断る」と、「効かない設定」の表の項目が「一覧に出す」と、同じ集合（親の行だけ）。"""
    text = (ROOT / "docs" / "guide" / "pipes.md").read_text(encoding="utf-8")
    doc_refuse, doc_list = doc_tables(text)
    assert capability.TABLE, "能力表が空（まだ項目を載せていない）"
    cap_refuse, cap_list = table_names(capability.REFUSE), table_names(capability.LIST)
    assert (doc_refuse - cap_refuse, cap_refuse - doc_refuse) == (set(), set()), "断る: (文書だけにある, 表だけにある)"
    assert (doc_list - cap_list, cap_list - doc_list) == (set(), set()), "一覧に出す: (文書だけにある, 表だけにある)"


def test_d0082_ac08_文書の表の読み方が項目名を取り出す():
    """D0082-AC-08: 検査そのものの確かめ。表の1列目から、括弧の中を消し、= の前の語を取り、複数の語を全部取る。表が読めなければ落ちる。"""
    text = (
        "## 会話の中で流すとき\n\n| 形 | 理由 |\n| --- | --- |\n"
        '| `kind = "dev"`（組み込み） | x |\n| `--after`（前の） | x |\n| `mcp`・`mcp_servers`（MCP） | x |\n'
        "| `web`（`true` でもドメインの一覧でも） | x |\n\n"
        "| 設定 | 場所 |\n| --- | --- |\n| `model`・`max_turns` | `pipe.toml` |\n\n## 次の節\n\n| 形 | 理由 |\n| --- | --- |\n| `zzz` | x |\n"
    )
    refuse, listed = doc_tables(text)
    assert refuse == {"kind", "--after", "mcp", "mcp_servers", "web"}
    assert listed == {"model", "max_turns"}


# ---- AC-10：chat.py に項目名で分ける条件が残らない -------------------------------------------------

CONTAINERS = {"check"}  # ("check", "judge") の途中の入れ物の名前。段の検証の表示など、別の用途でも chat.py が読むので除く


def item_names() -> set[str]:
    """判断の行（scope のある行）の path の項目名。表から取る（書き写さない）。"""
    return {n for r in capability.TABLE if r.scope for n in r.path} - CONTAINERS


def names_in_source(source: str, names: set[str]) -> list[str]:
    """属性（s.group）・getattr/hasattr の2つ目の文字列・文字列の並び（("model", "max_turns")）に現れる項目名。"""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in names:
            found.append(f".{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr", "setattr"):
            arg = node.args[1] if len(node.args) > 1 else None
            if isinstance(arg, ast.Constant) and arg.value in names:
                found.append(f"{node.func.id}(..., {arg.value!r})")
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            found += [f"{e.value!r}" for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value in names]
    return found


def test_d0082_ac10_chat_pyに項目名で分ける条件が残らない():
    """D0082-AC-10: pipe_in/pipe/chat.py に、判断の行の項目名（group・routes・agents・model など）を属性・getattr・文字列の並びで読む所が無い。
    項目名を並べるのは表だけ。"""
    names = item_names()
    assert {"group", "routes", "agents", "model", "add_dirs", "max_budget_usd"} <= names, f"表から項目名を取れない: {sorted(names)}"
    source = (ROOT / "pipe_in" / "pipe" / "chat.py").read_text(encoding="utf-8")
    assert names_in_source(source, names) == []


def test_d0082_ac10_検査そのものが項目名を見つける():
    """D0082-AC-10: 検査そのものの確かめ。偽の chat.py の文字列（s.group・getattr(s, "model")・("max_turns", ...)）から、項目名を1件以上見つける。
    関係の無い属性・文字列は見つけない。"""
    names = {"group", "model", "max_turns", "web"}
    bad = 'def f(s):\n    if s.group:\n        pass\n    x = getattr(s, "model")\n    for k in ("max_turns", "other"):\n        pass\n'
    found = names_in_source(bad, names)
    assert found == [".group", "getattr(..., 'model')", "'max_turns'"], found
    assert names_in_source('def f(s):\n    return s.name, {"model": 1}, ("a", "b")\n', names) == []
