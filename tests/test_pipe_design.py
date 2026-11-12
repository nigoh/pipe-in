"""D0093：/pipe-design（画面の見本を触って比べて決めるスキル）と、調べ係 pipe-in-ux-researcher の検査。

SDK・ネットワーク・git は使わない。SKILL.md・補助ファイル・エージェントの定義・文書の文字を読み、
フック（.claude/hooks/pipe_in_guard.py）の decide に偽の入力を渡すだけ。どこにも書かない。
見出しの切り出しは tests/test_skill_tidy.py の関数を使う。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from test_skill_tidy import front_matter, lacking, need_section, parse_headings

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "pipe-design"
SKILL = SKILL_DIR / "SKILL.md"
MOCK = SKILL_DIR / "mock.md"
FAVS = SKILL_DIR / "favs.md"
AGENT = ROOT / ".claude" / "agents" / "pipe-in-ux-researcher.md"
HOOK = ROOT / ".claude" / "hooks" / "pipe_in_guard.py"
HELP_SKILL = ROOT / ".claude" / "skills" / "pipe-help" / "SKILL.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
DECISIONS = ROOT / "docs" / "decisions"
RESEARCHER = "pipe-in-ux-researcher"

MUST = "必ず守ること"
STEPS = ("1. 不満を言葉にする", "2. 見本を作る", "3. 良さの条件を調べる", "4. ★ を読んで決める", "5. まとめて残す")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_doc(path: Path) -> str:
    """読む。無ければ「が無い」でそのテストだけを落とす。"""
    if not path.is_file():
        pytest.fail(f"{rel(path)} が無い（まだ作っていない）", pytrace=False)
    return path.read_text(encoding="utf-8")


def skill() -> str:
    return read_doc(SKILL)


def front_value(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.M)
    return None if m is None else m.group(1).strip()


def step(title: str) -> str:
    return need_section(skill(), title, where="pipe-design の SKILL.md", depth=2, exact=True)


def load_guard():
    spec = importlib.util.spec_from_file_location("pipe_in_guard_d0093", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def decide(agent: str, tool: str, tool_input: dict, tmp_path: Path) -> str | None:
    guard = load_guard()
    return guard.decide({"agent_type": agent, "tool_name": tool, "tool_input": tool_input}, root=str(tmp_path))


# ---- AC-01〜04：前置きと冒頭の決まり ------------------------------------------------------------


def test_D0093_AC_01_前置きの名前と説明と引数の案内があり_人が呼んだときだけ動く():
    """D0093-AC-01: SKILL.md があり、前置きの name が pipe-design、description と argument-hint が空でなく、disable-model-invocation が true。"""
    fm = front_matter(skill())
    assert front_value(fm, "name") == "pipe-design", fm
    assert front_value(fm, "description"), f"description が空か無い：{fm}"
    assert front_value(fm, "argument-hint"), f"argument-hint が空か無い：{fm}"
    assert front_value(fm, "disable-model-invocation") == "true", fm


def test_D0093_AC_02_前置きにallowed_toolsが無いか_Bashとghとmcpを含まない():
    """D0093-AC-02: 前置きに allowed-tools が無い。あっても Bash・gh・mcp__ を含まない（外へ出す道具を確認なしで通さない）。"""
    value = front_value(front_matter(skill()), "allowed-tools")
    if value is None:
        return
    assert [w for w in ("Bash", "gh", "mcp__") if w in value] == [], f"allowed-tools：{value}"


def test_D0093_AC_03_最初の見出しが必ず守ることで_決まりの語がある():
    """D0093-AC-03: # /pipe-design の次の ## 見出しが「必ず守ること」で、節に「全文」・「承認」・「質問欄」・「明るい画面と暗い画面」・「公開リポジトリとしての注意」がある。"""
    md = skill()
    heads = parse_headings(md)
    tops = [h for h in heads if h.depth == 1]
    assert tops and tops[0].title.startswith("/pipe-design"), f"# /pipe-design の見出しが無い：{[h.title for h in tops]}"
    seconds = [h for h in heads if h.depth == 2 and h.start > tops[0].start]
    assert seconds and seconds[0].title == MUST, f"最初の ## 見出し：{seconds[0].title if seconds else None}"
    body = need_section(md, MUST, where="pipe-design の SKILL.md", depth=2)
    assert lacking(body, ("全文", "承認", "質問欄", "明るい画面と暗い画面", "公開リポジトリとしての注意")) == []


def test_D0093_AC_04_ARGUMENTSは1回で_必ず守ることより後ろにあり_空なら聞く():
    """D0093-AC-04: $ARGUMENTS が全体で1回、「必ず守ること」の節より後ろにあり、その次の空でない行が「（空なら」で始まる。"""
    md = skill()
    assert md.count("$ARGUMENTS") == 1, f"$ARGUMENTS の数：{md.count('$ARGUMENTS')}"
    body = need_section(md, MUST, where="pipe-design の SKILL.md", depth=2)
    pos = md.index("$ARGUMENTS")
    assert pos >= md.index(body) + len(body), "$ARGUMENTS が「必ず守ること」の節より前か中にある"
    after = md[md.index("\n", pos) + 1 :]
    nxt = next((line.strip() for line in after.splitlines() if line.strip()), "")
    assert nxt.startswith("（空なら"), f"$ARGUMENTS の次の行：{nxt!r}"


# ---- AC-05〜11：流れ ----------------------------------------------------------------------------


def test_D0093_AC_05_流れの5つの節がこの順にある():
    """D0093-AC-05: ## の見出しに「1. 不満を言葉にする」〜「5. まとめて残す」の5つが、この順にある。"""
    titles = [h.title for h in parse_headings(skill()) if h.depth == 2]
    found = [t for t in titles if t in STEPS]
    assert found == list(STEPS), f"見出し：{titles}"


def test_D0093_AC_06_見本の作り方の補助ファイルに_つまみと一覧と番号と明暗がある():
    """D0093-AC-06: mock.md があり、「つまみ」・「縮図」・「おすすめ」・「1本ずつ」・「番号」・「prefers-color-scheme」がある。SKILL.md の「2. 見本を作る」が mock.md を指す。"""
    assert lacking(read_doc(MOCK), ("つまみ", "縮図", "おすすめ", "1本ずつ", "番号", "prefers-color-scheme")) == []
    assert "mock.md" in step("2. 見本を作る")


def test_D0093_AC_07_星の補助ファイルに_保存先と読み方と使えないときがある():
    """D0093-AC-07: favs.md があり、「db」・「favs」・「ArtifactData」・「localStorage」がある。SKILL.md の「4. ★ を読んで決める」が favs.md を指す。"""
    assert lacking(read_doc(FAVS), ("db", "favs", "ArtifactData", "localStorage")) == []
    assert "favs.md" in step("4. ★ を読んで決める")


def test_D0093_AC_08_良さの条件は調べ係に任せ_確かめた出典だけで_印を付ける():
    """D0093-AC-08: 「3. 良さの条件を調べる」に、pipe-in-ux-researcher・「開いて確かめた」・○・△・× がある。"""
    assert lacking(step("3. 良さの条件を調べる"), (RESEARCHER, "開いて確かめた", "○", "△", "×")) == []


def test_D0093_AC_09_星を数えて_割れた所と外れる所だけを質問欄で聞く():
    """D0093-AC-09: 「4. ★ を読んで決める」に、「割れた」・「外れる」・「質問欄」がある。"""
    assert lacking(step("4. ★ を読んで決める"), ("割れた", "外れる", "質問欄")) == []


def test_D0093_AC_10_まとめて残す節に_見本の置き場所と要約と承認がある():
    """D0093-AC-10: 「5. まとめて残す」に、「docs/design/」・「docs/talk/」・「git check-ignore」・「承認」・「issue」がある。"""
    assert lacking(step("5. まとめて残す"), ("docs/design/", "docs/talk/", "git check-ignore", "承認", "issue")) == []


def test_D0093_AC_11_SKILLと補助ファイルに手元の事情と実際のURLが無い():
    """D0093-AC-11: SKILL.md・mock.md・favs.md・調べ係の定義に、ユーザー名の入った絶対パス・アーティファクトの実際の URL・メールアドレスが無い。"""
    bad = re.compile(r"/home/[a-z]|C:\\Users|/Users/[a-z]|claude\.ai/artifact/[A-Za-z0-9]|[\w.+-]+@[\w-]+\.[a-z]{2,}")
    found = {rel(p): bad.findall(read_doc(p)) for p in (SKILL, MOCK, FAVS, AGENT)}
    assert {k: v for k, v in found.items() if v} == {}


# ---- AC-12〜18：調べ係とフック ------------------------------------------------------------------


def test_D0093_AC_12_調べ係の前置き_道具は読むとWebだけで軽いモデルと回数の上限():
    """D0093-AC-12: 調べ係の定義があり、name が pipe-in-ux-researcher、tools がちょうど Read・Grep・Glob・WebFetch・WebSearch、model が sonnet、maxTurns が 60。"""
    fm = front_matter(read_doc(AGENT))
    assert front_value(fm, "name") == RESEARCHER
    tools = sorted(t.strip() for t in (front_value(fm, "tools") or "").split(","))
    assert tools == sorted(["Read", "Grep", "Glob", "WebFetch", "WebSearch"]), tools
    assert front_value(fm, "model") == "sonnet"
    assert front_value(fm, "maxTurns") == "60"


def test_D0093_AC_13_調べ係はどこにも書けず_Bashも使えない(tmp_path):
    """D0093-AC-13: フックが、調べ係の Write・Edit（リポジトリの中でも）と Bash を止め、Read・Grep を通す。"""
    inside = str(tmp_path / "docs" / "x.md")
    assert decide(RESEARCHER, "Write", {"file_path": inside, "content": "x"}, tmp_path)
    assert decide(RESEARCHER, "Edit", {"file_path": inside, "old_string": "a", "new_string": "b"}, tmp_path)
    assert decide(RESEARCHER, "Bash", {"command": "pytest -q"}, tmp_path)
    assert decide(RESEARCHER, "Read", {"file_path": inside}, tmp_path) is None
    assert decide(RESEARCHER, "Grep", {"pattern": "x"}, tmp_path) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.nngroup.com/articles/response-times-3-important-limits/",
        "https://design.digital.go.jp/dads/foundations/typography/",
        "https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html",
        "https://developer.mozilla.org/en-US/docs/Web/CSS/font-variant-numeric",
        "https://lawsofux.com/doherty-threshold/",
    ],
)
def test_D0093_AC_14_調べ係のWebFetchはUXの出典の場所を通す(url, tmp_path):
    """D0093-AC-14: 調べ係の WebFetch は、UX の出典の場所（UX_HOSTS）の https:// の URL を通す。"""
    assert decide(RESEARCHER, "WebFetch", {"url": url, "prompt": "x"}, tmp_path) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://www.nngroup.com/articles/x/",
        "https://www.nngroup.com:8443/articles/x/",
        "https://user" + "@www.nngroup.com/articles/x/",  # 分けて書く：つなげるとメールアドレスに見え、tests/test_rules.py の検査に掛かる
        "https://www.nngroup.com.evil.example/x",
        "https://www.nngroup.com/articles/%2e%2e/x",
        "https://code.claude.com/docs/en/overview",
        "https://github.com/anthropics/claude-code",
        "",
        None,
    ],
)
def test_D0093_AC_15_調べ係のWebFetchはほかの場所と見せかけを止める(url, tmp_path):
    """D0093-AC-15: 調べ係の WebFetch は、UX の出典の場所でない URL・http・ポート・ユーザー情報・似せたホスト・道の正規化・空を止める（公式の文書の場所も、この役には開けない）。"""
    assert decide(RESEARCHER, "WebFetch", {"url": url, "prompt": "x"}, tmp_path)


def test_D0093_AC_16_調べ係のWebSearchはUXの出典の場所だけに絞ったときだけ通す(tmp_path):
    """D0093-AC-16: 調べ係の WebSearch は、allowed_domains が空でなく、すべて UX_HOSTS のときだけ通す。無い・空・ほかの場所が混じると止める。"""
    ok = {"query": "x", "allowed_domains": ["www.nngroup.com", "design.digital.go.jp"]}
    assert decide(RESEARCHER, "WebSearch", ok, tmp_path) is None
    for bad in ({"query": "x"}, {"query": "x", "allowed_domains": []}, {"query": "x", "allowed_domains": ["www.nngroup.com", "example.com"]}):
        assert decide(RESEARCHER, "WebSearch", bad, tmp_path), bad


def test_D0093_AC_17_助言と審査には_UXの出典の場所を開かない(tmp_path):
    """D0093-AC-17: 助言（pipe-in-advisor）と審査（pipe-in-judge）の WebFetch は、UX の出典の場所の URL を今までどおり止め、公式の文書の URL は通す（広げるのは調べ係だけ）。"""
    url = "https://www.nngroup.com/articles/x/"
    for agent in ("pipe-in-advisor", "pipe-in-judge"):
        assert decide(agent, "WebFetch", {"url": url, "prompt": "x"}, tmp_path), agent
        assert decide(agent, "WebFetch", {"url": "https://code.claude.com/docs/en/hooks", "prompt": "x"}, tmp_path) is None, agent
    assert decide("pipe-in-advisor", "WebSearch", {"query": "x", "allowed_domains": ["www.nngroup.com"]}, tmp_path)


def test_D0093_AC_18_調べ係の定義はフックのUXの出典の場所を写す():
    """D0093-AC-18: フックに UX_HOSTS があり、その全部のホストが調べ係の定義の本文にある。"""
    guard = load_guard()
    hosts = getattr(guard, "UX_HOSTS", None)
    assert hosts, "フックに UX_HOSTS が無い"
    assert lacking(read_doc(AGENT), hosts) == []


# ---- AC-19〜22：文書 ----------------------------------------------------------------------------


def test_D0093_AC_19_pipe_helpの表と説明にpipe_designがある():
    """D0093-AC-19: /pipe-help の SKILL.md の表と、前置きの description に /pipe-design がある。"""
    md = read_doc(HELP_SKILL)
    assert "/pipe-design" in (front_value(front_matter(md), "description") or "")
    assert any(line.startswith("| `/pipe-design") for line in md.splitlines()), "表に /pipe-design の行が無い"


def test_D0093_AC_20_CLAUDE_mdにpipe_designと置き場所と調べ係がある():
    """D0093-AC-20: CLAUDE.md に /pipe-design・.claude/skills/pipe-design/・pipe-in-ux-researcher がある。"""
    assert lacking(read_doc(CLAUDE_MD), ("/pipe-design", ".claude/skills/pipe-design/", RESEARCHER)) == []


def test_D0093_AC_21_置き場所の表にpipe_designがある():
    """D0093-AC-21: docs/development/design.md の置き場所の表に .claude/skills/pipe-design/ がある。"""
    md = read_doc(DESIGN_MD)
    assert any(line.startswith("|") and ".claude/skills/pipe-design/" in line for line in md.splitlines())


def test_D0093_AC_22_この記録があり_一覧に載っている():
    """D0093-AC-22: docs/decisions/D0093-*.md があり、docs/decisions/README.md の表に D0093 の行がある。"""
    assert sorted(DECISIONS.glob("D0093-*.md")), "docs/decisions/D0093-*.md が無い"
    assert "[D0093](" in read_doc(DECISIONS / "README.md")
