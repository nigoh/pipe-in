"""D0038：監査・助言・審査のサブエージェントの定義の maxTurns（回数の上限）と、決定の記録 D0038 の検査。

- 監査（pipe-in-auditor）100・助言（pipe-in-advisor）80・審査（pipe-in-judge）50 が、前置きに1行ずつある
- 文書係と段の4つ（書き込む役）には maxTurns を付けない
- 値は正の整数で、前置きの外（本文）に書いたものは数えない
- 前の版の定義（maxTurns の無い前置き）は、例外でなく「maxTurns が無い」という失敗の文で分かる
- 決定の記録 D0038 があり、索引に行があり、置き換えと解く課題と値の根拠が書いてある

定義と記録は読むだけで、書かない。偽の文は文字列で渡す。SDK も claude も呼ばない。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_headless_audit import section

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"
DECISIONS = ROOT / "docs" / "decisions"
DECISIONS_README = DECISIONS / "README.md"
D0012 = DECISIONS / "D0012-headless-audit.md"
D0015 = DECISIONS / "D0015-rubric-judge.md"
RECORD_GLOB = "D0038-*.md"

LIMITS = {"pipe-in-auditor": 100, "pipe-in-advisor": 80, "pipe-in-judge": 50}
NO_LIMIT = ["pipe-in-documenter", "pipe-in-analyst", "pipe-in-tester", "pipe-in-coder", "pipe-in-verifier"]
ALL_AGENTS = sorted(LIMITS) + NO_LIMIT

MAX_TURNS_LINE = re.compile(r"^maxTurns\s*:(.*)$")
POSITIVE_INT = re.compile(r"[1-9][0-9]*")

# 前の版の定義（maxTurns の無い前置き。D0038-AC-07 の偽の文）
OLD_FRONT = "---\nname: pipe-in-auditor\ndescription: x\ntools: Read, Grep, Glob\ncolor: yellow\n---\n本文\n"


# ---- 補助 ------------------------------------------------------------------------------------


def read(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT).as_posix()} が無い")
    return path.read_text(encoding="utf-8")


def agent_text(name: str) -> str:
    return read(AGENTS / f"{name}.md")


def front_matter(text: str) -> str | None:
    """ファイルの先頭の `---` の行から次の `---` の行までの中身。無ければ None（本文の `---` を前置きと取り違えない）。"""
    m = re.match(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.S)
    return m.group(1) if m else None


def body(text: str) -> str:
    """前置きの後ろ（前置きが無ければ全文）。"""
    m = re.match(r"\A---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.S)
    return text[m.end() :] if m else text


def max_turns_lines(text: str) -> list[str]:
    """前置きの中の maxTurns の行の値（strip したもの）。前置きが無ければ空。"""
    front = front_matter(text)
    if front is None:
        return []
    return [m.group(1).strip() for line in front.splitlines() if (m := MAX_TURNS_LINE.match(line.rstrip("\r")))]


def max_turns_problem(text: str, expected: int | None = None) -> str | None:
    """前置きの maxTurns に問題が無ければ None、あれば失敗の文（例外を出さない）。"""
    if front_matter(text) is None:
        return "前置きが無い"
    values = max_turns_lines(text)
    if not values:
        return "maxTurns が無い"
    if len(values) > 1:
        return "maxTurns が2つ以上ある"
    value = values[0]
    if not POSITIVE_INT.fullmatch(value):
        return f"maxTurns が正の整数でない: {value!r}"
    if expected is not None and int(value) != expected:
        return f"maxTurns が {expected} でない: {value}"
    return None


def record() -> Path:
    records = sorted(DECISIONS.glob(RECORD_GLOB))
    if len(records) != 1:
        pytest.fail(f"D0038 の記録（docs/decisions/{RECORD_GLOB}）がちょうど1つでない: {[p.name for p in records]}")
    return records[0]


# ---- D0038-AC-01〜03：読むだけの3つの maxTurns ------------------------------------------------


@pytest.mark.parametrize(
    "name,limit", list(LIMITS.items()), ids=[f"{n.removeprefix('pipe-in-')}-{v}" for n, v in LIMITS.items()]
)
def test_D0038_AC_01_03_読むだけの3つの前置きにmaxTurnsが1つだけあり値が決めたとおり(name, limit):
    """D0038-AC-01・02・03: pipe-in-auditor は 100、pipe-in-advisor は 80、pipe-in-judge は 50 の maxTurns の行が、前置きにちょうど1つある。"""
    assert max_turns_problem(agent_text(name), limit) is None, f"{name}: {max_turns_problem(agent_text(name), limit)}"


# ---- D0038-AC-04：値の読み方（検査そのものの検査） --------------------------------------------


def _front(*lines: str) -> str:
    return "---\n" + "\n".join(["name: pipe-in-x", "tools: Read", *lines]) + "\n---\n本文\n"


@pytest.mark.parametrize(
    "text,problem",
    [
        (_front("maxTurns: 0"), "maxTurns が正の整数でない: '0'"),
        (_front("maxTurns: -1"), "maxTurns が正の整数でない: '-1'"),
        (_front("maxTurns: abc"), "maxTurns が正の整数でない: 'abc'"),
        (_front("maxTurns:"), "maxTurns が正の整数でない: ''"),
        (_front("maxTurns: 1.5"), "maxTurns が正の整数でない: '1.5'"),
        ("---\nname: pipe-in-x\n---\n本文\nmaxTurns: 100\n", "maxTurns が無い"),
        ("---\nname: pipe-in-x\n---\n本文\n---\nmaxTurns: 100\n---\n", "maxTurns が無い"),
        (_front("maxTurns: 100", "maxTurns: 80"), "maxTurns が2つ以上ある"),
        ("maxTurns: 100\n本文\n", "前置きが無い"),
    ],
    ids=["zero", "negative", "word", "empty", "decimal", "body-only", "body-between-rules", "twice", "no-front"],
)
def test_D0038_AC_04_検査は正の整数でないmaxTurnsと前置きの外のmaxTurnsを見分ける(text, problem):
    """D0038-AC-04: max_turns_problem が、0・-1・abc・空・1.5、本文だけの maxTurns、2つある前置き、前置きの無い文を、それぞれの失敗の文で見分ける。"""
    assert max_turns_problem(text) == problem


@pytest.mark.parametrize(
    "text,expected",
    [
        (_front("maxTurns: 100"), 100),
        (_front("maxTurns:80"), 80),
        (_front("maxTurns: 50").replace("\n", "\r\n"), 50),
    ],
    ids=["space", "no-space", "crlf"],
)
def test_D0038_AC_04_検査は正しいmaxTurnsを通す(text, expected):
    """D0038-AC-04: 正の整数の maxTurns（空白なし・CRLF も）は問題なしと読み、期待と違う値は「<期待> でない」で落とす。"""
    assert max_turns_problem(text) is None
    assert max_turns_problem(text, expected) is None
    assert max_turns_problem(text, expected + 1) == f"maxTurns が {expected + 1} でない: {expected}"


# ---- D0038-AC-05：付けるのは3つだけ -----------------------------------------------------------


def test_D0038_AC_05_maxTurnsが付いているのは監査_助言_審査の3つだけ():
    """D0038-AC-05: .claude/agents/pipe-in-*.md はちょうど8つで、前置きに maxTurns があるのは監査・助言・審査の3つだけ（文書係と段の4つには無い）。"""
    found = {p.stem: p.read_text(encoding="utf-8") for p in sorted(AGENTS.glob("pipe-in-*.md"))}
    assert sorted(found) == sorted(ALL_AGENTS)
    with_limit = {name for name, text in found.items() if max_turns_lines(text)}
    assert with_limit == set(LIMITS), f"足りない={sorted(set(LIMITS) - with_limit)} 余分={sorted(with_limit - set(LIMITS))}"


# ---- D0038-AC-06：ほかの前置きの項目が残る ----------------------------------------------------


def test_D0038_AC_06_審査役の前置きにeffort_highが残る():
    """D0038-AC-06: maxTurns を足したあとも、pipe-in-judge の前置きに effort: high の行が残る（守り続ける検査）。"""
    front = front_matter(agent_text("pipe-in-judge"))
    assert front is not None, "pipe-in-judge に前置きが無い"
    assert "effort: high" in [line.strip() for line in front.splitlines()]


# ---- D0038-AC-07：前の版の定義 ----------------------------------------------------------------


def test_D0038_AC_07_前の版の定義はmaxTurnsが無いと分かり例外で落ちない():
    """D0038-AC-07: maxTurns の無い前の版の前置きを渡すと、例外でなく「maxTurns が無い」が返る（期待の値を渡しても同じ）。"""
    assert max_turns_problem(OLD_FRONT) == "maxTurns が無い"
    assert max_turns_problem(OLD_FRONT, 100) == "maxTurns が無い"


# ---- D0038-AC-08：審査役の本文 ----------------------------------------------------------------


def test_D0038_AC_08_審査役の本文に多くても15件までが残る():
    """D0038-AC-08: pipe-in-judge の本文（前置きの後ろ）に、WebFetch の「多くても 15 件まで」が残っている（守り続ける検査）。"""
    assert "多くても 15 件まで" in body(agent_text("pipe-in-judge"))


# ---- D0038-AC-24〜26：決定の記録 --------------------------------------------------------------


@pytest.mark.parametrize("word", ["D0012 の呼び方の2行を置き換える", "#34", "#35", "D0015", "maxTurns"])
def test_D0038_AC_24_決定の記録に置き換えと解く課題が書いてある(word):
    """D0038-AC-24: docs/decisions/D0038-*.md がちょうど1つあり、「D0012 の呼び方の2行を置き換える」と #34・#35・D0015 の審査役の maxTurns の課題を解くことが書いてある。"""
    assert word in read(record())


def test_D0038_AC_24_索引にD0038の行がある():
    """D0038-AC-24: docs/decisions/README.md に D0038 の行がある。"""
    assert any("D0038" in line for line in read(DECISIONS_README).splitlines())


@pytest.mark.parametrize("path", [D0012, D0015], ids=["D0012", "D0015"])
def test_D0038_AC_25_D0012とD0015の記録にD0038が出てこない(path):
    """D0038-AC-25: D0012・D0015 の記録を書き換えていない（D0038 の語が出てこない。守り続ける検査）。"""
    assert "D0038" not in read(path)


@pytest.mark.parametrize(
    "word",
    ["100", "80", "50", "73 回", "9 回", "15 件", "pipe-in-documenter", "途中で止まると"],
)
def test_D0038_AC_26_決めたことと理由に3つの値と根拠と付けない理由がある(word):
    """D0038-AC-26: D0038 の「決めたことと理由」の節に、3つの値（100・80・50）、根拠（D0008 の 73 回・D0012 の WebFetch 9 回・審査の 15 件）、文書係と段の4つに付けない理由がある。"""
    assert word in section(read(record()), "決めたことと理由")
