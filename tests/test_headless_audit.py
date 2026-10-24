"""D0012（会話を開かずに /pipe-audit・/pipe-advise を流す呼び方）と、文書・SKILL.md の食い違いの検査。

- /pipe-help とガイドの開発の文書（docs/guide/develop.md。D0014 で README から移した）に、同じ `claude -p "/pipe-audit …"`・`claude -p "/pipe-advise …"` の呼び方の例がある
- 例は読むだけに絞られ（--tools で組み込みの道具そのものを絞り、--allowedTools は確認なしで通す許可）、--bare などを付けていない
- 助言の行の WebFetch の行き先が、.claude/hooks/pipe_in_guard.py の DOC_HOSTS・GITHUB_HOSTS と同じ
- 報告で止まること・開かれなかったときの見分け方が、それぞれの節の中に書いてある
- 検査そのものが、ずれた書き方を見つけられる（偽の文は文字列で渡す）
- D0038：呼び方の行に --disallowedTools "mcp__*" があり、節に MCP を断る説明と maxTurns（サブエージェントの回数の上限）の説明がある

文書と SKILL.md は読むだけで、書かない。SDK も claude も呼ばない。
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "pipe_in_guard.py"
SKILLS = ROOT / ".claude" / "skills"
HELP = SKILLS / "pipe-help" / "SKILL.md"
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "guide"
DEVELOP = GUIDE / "develop.md"
DECISIONS = ROOT / "docs" / "decisions"
RECORD = DECISIONS / "D0012-headless-audit.md"
D0008 = DECISIONS / "D0008-audit-advisor.md"
DECISIONS_README = DECISIONS / "README.md"

AUDIT_START = 'claude -p "/pipe-audit'
ADVISE_START = 'claude -p "/pipe-advise'
SKILL_NAMES = ["pipe-audit", "pipe-advise"]

# 呼び方に付けてはいけないもの（名前）
NO_SKILL_OPTIONS = ["--bare", "--disable-slash-commands"]
# 読むだけに絞るため、呼び方に入れてはいけないもの
WRITE_WORDS = [
    "--dangerously-skip-permissions",
    "--allow-dangerously-skip-permissions",
    "bypassPermissions",
    "acceptEdits",
    "Bash",
    "PowerShell",
    "Write",
    "Edit",
]
# --allowedTools に書いてよい道具（WebSearch は助言の行だけ。監査の行は別に検査する）
ALLOWED_TOOL = re.compile(r"^(Agent\([\w-]+\)|Read|Grep|Glob|WebSearch|WebFetch\(domain:[\w.\-]+\))$")
# --tools に書いてよい組み込みの道具
TOOLS_OK = {"Agent", "Read", "Grep", "Glob", "WebFetch", "WebSearch"}
WEB_TOOLS = {"WebFetch", "WebSearch"}
# 人が承認した呼び方の2行（<範囲>・<テーマ> はそのまま）。D0038 で --disallowedTools "mcp__*" を足した
EXPECTED_AUDIT = (
    'claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob" --disallowedTools "mcp__*" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob'
)
EXPECTED_ADVISE = (
    'claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --disallowedTools "mcp__*" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch '
    '"WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" '
    '"WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"'
)
# D0012 の前の版の2行（D0038-AC-15 の偽の文。--disallowedTools が無い）
OLD_AUDIT_D0012 = (
    'claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob'
)
OLD_ADVISE_D0012 = (
    'claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch '
    '"WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" '
    '"WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"'
)
# D0038：断る MCP の道具（全部）、節に残っていてはいけない前の言い方、D0038 の記録
MCP_ALL = "mcp__*"
OLD_MCP_WORDS = ["`--tools` では消えませんが", "`dontAsk` で許可に無ければ断られます"]
D0038_RECORD_GLOB = "D0038-*.md"
ADVISE_WEBFETCH = [
    "WebFetch(domain:code.claude.com)",
    "WebFetch(domain:docs.claude.com)",
    "WebFetch(domain:docs.anthropic.com)",
    "WebFetch(domain:platform.claude.com)",
    "WebFetch(domain:github.com)",
    "WebFetch(domain:raw.githubusercontent.com)",
]
# 説明を探す節（文書の名前: (ファイル, 見出しの語)）
SECTION_OF = {
    "pipe-help": (HELP, "会話を開かずに流す"),
    "develop": (DEVELOP, "Claude Code で開発するとき"),
}


# ---- 補助 ------------------------------------------------------------------------------------


def read(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT)} が無い")
    return path.read_text(encoding="utf-8")


def call_lines(text: str) -> list[str]:
    """`claude -p "` で始まる行（コードブロックの中の呼び方）を集める。本文の説明の行は対象にしない。"""
    return [line.strip() for line in text.splitlines() if line.strip().startswith('claude -p "')]


def squash(line: str) -> str:
    return " ".join(line.split())


def call_for(text: str, start: str) -> str:
    found = [squash(line) for line in call_lines(text) if line.startswith(start)]
    if not found:
        pytest.fail(f"{start} で始まる呼び方の行が無い")
    return found[0]


def frontmatter(text: str) -> list[str]:
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    return m.group(1).splitlines() if m else []


def allowed_tools(line: str) -> list[str]:
    """--allowedTools のあと、次の -- のオプションまでの語。"""
    tokens = shlex.split(line)
    if "--allowedTools" not in tokens:
        return []
    out: list[str] = []
    for tok in tokens[tokens.index("--allowedTools") + 1 :]:
        if tok.startswith("--"):
            break
        out.append(tok)
    return out


def option_words(line: str, option: str) -> list[str] | None:
    """option のあと、次の -- のオプションまでの語（空の文字は除く）。option が無ければ None。"""
    tokens = shlex.split(line)
    if option not in tokens:
        return None
    out: list[str] = []
    for tok in tokens[tokens.index(option) + 1 :]:
        if tok.startswith("--"):
            break
        if tok:
            out.append(tok)
    return out


def tools_option(line: str) -> list[str] | None:
    """--tools の値（カンマ区切り）。無ければ None。"""
    tokens = shlex.split(line)
    if "--tools" not in tokens:
        return None
    i = tokens.index("--tools") + 1
    return [t for t in tokens[i].split(",") if t] if i < len(tokens) else []


def webfetch_domains(line: str) -> set[str]:
    return {m for t in allowed_tools(line) for m in re.findall(r"^WebFetch\(domain:([^)]+)\)$", t)}


def guard_hosts(text: str) -> set[str]:
    """pipe_in_guard.py の DOC_HOSTS と GITHUB_HOSTS の中の文字列を集める（import せず文字として読む）。"""
    hosts: set[str] = set()
    for name in ("DOC_HOSTS", "GITHUB_HOSTS"):
        m = re.search(rf"^{name}\s*=\s*\(([^)]*)\)", text, re.MULTILINE)
        if not m:
            pytest.fail(f"{name} が見つからない")
        hosts |= set(re.findall(r'"([^"]+)"', m.group(1)))
    return hosts


def section(text: str, heading: str) -> str:
    """見出し（`### …` など）の行から、同じかより上の階層の次の見出しの前まで。見出しが無ければ失敗。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"(#+)\s+(.*)", line)
        if m and heading in m.group(2):
            level = len(m.group(1))
            out = [line]
            for nxt in lines[i + 1 :]:
                n = re.match(r"(#+)\s", nxt)
                if n and len(n.group(1)) <= level:
                    break
                out.append(nxt)
            return "\n".join(out)
    pytest.fail(f"見出し「{heading}」が無い")


def doc_section(doc: str) -> str:
    path, heading = SECTION_OF[doc]
    return section(read(path), heading)


def has_word(line: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", line) is not None


def doc_calls() -> list[tuple[str, str]]:
    """(文書の名前, 呼び方の行) を、pipe-help とガイドの開発の文書から集める。"""
    out: list[tuple[str, str]] = []
    for name, path in (("pipe-help", HELP), ("develop", DEVELOP)):
        out += [(name, squash(line)) for line in call_lines(read(path))]
    return out


# ---- D0012-AC-01：SKILL.md の frontmatter ----------------------------------------------------


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_スキルの設定は人が呼ぶだけでモデルが勝手に呼べない形を保つ(name):
    """D0012-AC-01: SKILL.md の frontmatter に disable-model-invocation: true があり、user-invocable: false は無い（守り続ける検査）。"""
    lines = frontmatter(read(SKILLS / name / "SKILL.md"))
    assert "disable-model-invocation: true" in lines
    assert not any(re.match(r"user-invocable:\s*false", line) for line in lines)


# ---- D0012-AC-02・03：呼び方の例 -------------------------------------------------------------


@pytest.mark.parametrize("start", [AUDIT_START, ADVISE_START])
def test_pipe_helpに会話を開かない呼び方の例がある(start):
    """D0012-AC-02: /pipe-help の SKILL.md に、claude -p "/pipe-audit と claude -p "/pipe-advise で始まる呼び方の行がある。"""
    call_for(read(HELP), start)


@pytest.mark.parametrize("start", [AUDIT_START, ADVISE_START])
def test_D0014_AC_30_ガイドの開発の文書に会話を開かない呼び方の例がある(start):
    """D0014-AC-30: docs/guide/develop.md に、同じ2つの呼び方の行がある（D0012-AC-03 の README を、移した先に付け直した）。"""
    call_for(read(DEVELOP), start)


@pytest.mark.parametrize("start", [AUDIT_START, ADVISE_START])
def test_D0014_AC_30_ガイドとpipe_helpの呼び方が空白をそろえて同じ(start):
    """D0014-AC-30: docs/guide/develop.md の呼び方の行（文字列とオプション）が、/pipe-help のものと一致する。"""
    assert call_for(read(DEVELOP), start) == call_for(read(HELP), start)


def test_D0014_AC_30_呼び方の行はpipe_helpと開発の文書の2か所だけ():
    """D0014-AC-30: README.md・ガイドのほかの文書・D0014 の記録に `claude -p "` で始まる呼び方の行が無い。"""
    others = [README] + sorted(p for p in GUIDE.glob("*.md") if p != DEVELOP) + sorted(DECISIONS.glob("D0014-*.md"))
    found = [p.relative_to(ROOT).as_posix() for p in others if call_lines(read(p))]
    assert found == []


# ---- D0012-AC-04：付けないオプション ---------------------------------------------------------


@pytest.mark.parametrize("option", NO_SKILL_OPTIONS)
@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
def test_呼び方の例にスキルを無効にするオプションを付けていない(doc, option):
    """D0012-AC-04・D0014-AC-30: /pipe-help・docs/guide/develop.md の呼び方の行に --bare・--disable-slash-commands が無い。"""
    path = {"pipe-help": HELP, "develop": DEVELOP}[doc]
    lines = call_lines(read(path))
    assert lines, "呼び方の行が1つも無い（検査が空振りしないように）"
    assert not [line for line in lines if has_word(line, option)]


def test_D0012に呼び方の行を書かない():
    """D0012-AC-04: D0012 に `claude -p "` で始まる呼び方の行を書かない（文書の呼び方は pipe-help と docs/guide/develop.md に1か所ずつ）。"""
    assert call_lines(read(RECORD)) == []


# ---- D0012-AC-05：読むだけ -------------------------------------------------------------------


def test_呼び方は確認なしで断るモードと許す道具の一覧を付けている():
    """D0012-AC-05・D0014-AC-30: /pipe-help・docs/guide/develop.md の呼び方の行すべてに --permission-mode dontAsk と --allowedTools がある。"""
    calls = doc_calls()
    assert {n for n, _ in calls} == {"pipe-help", "develop"}, "どちらの文書にも呼び方の行が要る"
    for name, line in calls:
        assert "--permission-mode dontAsk" in line, f"{name}: {line}"
        assert allowed_tools(line), f"{name}: --allowedTools が無い: {line}"


@pytest.mark.parametrize("word", WRITE_WORDS)
def test_呼び方に書き込みやコマンド実行を許す語が無い(word):
    """D0012-AC-05・D0014-AC-30: /pipe-help・docs/guide/develop.md の呼び方の行に、書き込み・Bash・PowerShell を許す語が無い。"""
    calls = doc_calls()
    assert calls, "呼び方の行が1つも無い（検査が空振りしないように）"
    assert not [(n, line) for n, line in calls if has_word(line, word)]


def test_許す道具は読む道具と公式の文書の取得だけ():
    """D0012-AC-05・D0014-AC-30: --allowedTools に書いた道具が Agent(…)・Read・Grep・Glob・WebSearch・WebFetch(domain:…) だけ。"""
    calls = doc_calls()
    assert calls, "呼び方の行が1つも無い（検査が空振りしないように）"
    for name, line in calls:
        tools = allowed_tools(line)
        assert tools, f"{name}: --allowedTools が無い"
        assert [t for t in tools if not ALLOWED_TOOL.match(t)] == [], f"{name}: {line}"


@pytest.mark.parametrize("skill,start", [("pipe-audit", AUDIT_START), ("pipe-advise", ADVISE_START)])
def test_呼び方で許すサブエージェントがスキルのallowed_toolsと一致する(skill, start):
    """D0012-AC-05・D0014-AC-30: 呼び方の Agent(…) が、SKILL.md の allowed-tools の Agent(…) と一致する。"""
    declared = [
        line.split(":", 1)[1].strip()
        for line in frontmatter(read(SKILLS / skill / "SKILL.md"))
        if line.startswith("allowed-tools:")
    ]
    assert len(declared) == 1
    for text in (read(HELP), read(DEVELOP)):
        agents = [t for t in allowed_tools(call_for(text, start)) if t.startswith("Agent(")]
        assert agents == [declared[0]]


def test_呼び方の行は承認された2行と同じ():
    """D0038-AC-11・D0012-AC-05・D0014-AC-30: pipe-help・docs/guide/develop.md の呼び方の行が、承認された監査・助言の2行（空白をそろえて。D0038 で --disallowedTools "mcp__*" を足した）と一致する。"""
    for text in (read(HELP), read(DEVELOP)):
        assert call_for(text, AUDIT_START) == EXPECTED_AUDIT
        assert call_for(text, ADVISE_START) == EXPECTED_ADVISE


@pytest.mark.parametrize("start", [AUDIT_START, ADVISE_START])
def test_呼び方にtoolsで組み込みの道具を絞る指定がある(start):
    """D0012-AC-05・D0014-AC-30: 呼び方の行に --tools があり、値（カンマ区切り）が Agent・Read・Grep・Glob・WebFetch・WebSearch の中だけ（Bash・Write・Edit などが入れば落ちる）。"""
    for name, text in (("pipe-help", read(HELP)), ("develop", read(DEVELOP))):
        tools = tools_option(call_for(text, start))
        assert tools, f"{name}: --tools が無い"
        assert set(tools) <= TOOLS_OK, f"{name}: {tools}"


def test_監査の呼び方にはWebの道具を付けない():
    """D0012-AC-05・D0014-AC-30: 監査の行の --tools にも --allowedTools にも WebFetch・WebSearch が無い。"""
    for name, text in (("pipe-help", read(HELP)), ("develop", read(DEVELOP))):
        line = call_for(text, AUDIT_START)
        tools = tools_option(line)
        assert tools, f"{name}: --tools が無い"
        assert not set(tools) & WEB_TOOLS, name
        assert not [t for t in allowed_tools(line) if t.split("(")[0] in WEB_TOOLS], name


def test_助言の呼び方のWebFetchの行き先がガードの公式の場所と同じ():
    """D0012-AC-05・D0014-AC-30: 助言の行の WebFetch(domain:…) の集合が、pipe_in_guard.py の DOC_HOSTS と GITHUB_HOSTS を合わせた集合とちょうど同じ。"""
    expected = guard_hosts(read(GUARD))
    for name, text in (("pipe-help", read(HELP)), ("develop", read(DEVELOP))):
        got = webfetch_domains(call_for(text, ADVISE_START))
        assert got == expected, f"{name}: 足りない={sorted(expected - got)} 余分={sorted(got - expected)}"


# ---- D0012-AC-06・07：書いておくべき説明（それぞれの節の中だけを見る） -------------------------


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
@pytest.mark.parametrize("word", ["報告", "止まり", "承認", "会話"], ids=["report", "stop", "approve", "chat"])
def test_非対話では報告で止まり直すのは承認のあと会話でと書いてある(doc, word):
    """D0012-AC-06・D0014-AC-30: /pipe-help の「会話を開かずに流す」の節と docs/guide/develop.md の「Claude Code で開発するとき」の節の中に、報告を出して止まること、直すのは承認のあと会話でと書いてある。"""
    text = doc_section(doc)
    assert call_lines(text), "その節に呼び方の例が無い"
    assert word in text


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
@pytest.mark.parametrize("word", ["slash_commands", "system/init", "--output-format stream-json --verbose"])
def test_開かれなかったときの見分け方が書いてある(doc, word):
    """D0012-AC-07・D0014-AC-30: 上と同じ節の中に、system/init の slash_commands で開かれたかを見分ける方法が書いてある。"""
    text = doc_section(doc)
    assert call_lines(text), "その節に呼び方の例が無い"
    assert word in text


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
def test_見分け方は助言のpipe_adviseも確かめると書いてある(doc):
    """D0012-AC-07・D0014-AC-30: 同じ節に、slash_commands で `pipe-audit`（/pipe-advise のときは `pipe-advise`）も確かめると書いてある。"""
    text = doc_section(doc)
    assert "slash_commands" in text
    assert "`pipe-audit`" in text and "`pipe-advise`" in text


# ---- D0012-AC-12・FR-08：決定の記録 ----------------------------------------------------------


def test_D0008の記録はD0012に触れずそのまま():
    """D0012-AC-12: D0008 の記録に D0012 が出てこない（守り続ける検査）。"""
    assert "D0012" not in read(D0008)


def test_D0012は残った課題を解くと書く():
    """D0012-AC-12: D0012 に「D0008 の残った課題を解く」がある。"""
    assert "D0008 の残った課題を解く" in read(RECORD)


def test_決定の記録D0012があり索引に行がある():
    """D0012-AC-12: docs/decisions/D0012-headless-audit.md があり、docs/decisions/README.md に D0012 の行がある（FR-08）。"""
    assert read(RECORD).strip()
    assert any("D0012" in line for line in read(DECISIONS_README).splitlines())


# ---- 検査そのものの検査 ----------------------------------------------------------------------

GOOD_AUDIT = (
    'claude -p "/pipe-audit docs/" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob'
)


def test_検査は禁止語を付けた呼び方を見つけ説明の文は見逃す():
    """D0012-AC-04/05: call_lines と禁止語の検査が、--bare・acceptEdits を付けた呼び方を見つけ、コードブロック外の説明は対象にしない。"""
    text = "\n".join(
        [
            "`--bare` は付けません。",
            "```",
            GOOD_AUDIT,
            GOOD_AUDIT + " --bare",
            'claude -p "/pipe-audit x" --permission-mode acceptEdits --allowedTools Read Bash',
            "```",
        ]
    )
    lines = call_lines(text)
    assert len(lines) == 3  # 説明の行は入らない
    assert [has_word(line, "--bare") for line in lines] == [False, True, False]
    assert [has_word(line, "acceptEdits") for line in lines] == [False, False, True]
    assert has_word(lines[2], "Bash") and not has_word(lines[0], "Bash")
    assert not has_word("--bare-ish", "--bare")


def test_検査は許さない道具と抜けたallowedToolsを見つける():
    """D0012-AC-05: allowed_tools と ALLOWED_TOOL が、許す一覧に無い道具と --allowedTools の無い呼び方を見つける。"""
    assert allowed_tools(GOOD_AUDIT) == ["Agent(pipe-in-auditor)", "Read", "Grep", "Glob"]
    assert all(ALLOWED_TOOL.match(t) for t in allowed_tools(GOOD_AUDIT))
    assert allowed_tools('claude -p "/pipe-audit x" --permission-mode dontAsk') == []
    bad = allowed_tools('claude -p "/pipe-audit x" --allowedTools Read Bash "Edit"')
    assert [t for t in bad if not ALLOWED_TOOL.match(t)] == ["Bash", "Edit"]
    assert ALLOWED_TOOL.match("WebFetch(domain:code.claude.com)")
    assert not ALLOWED_TOOL.match("WebFetch")
    assert ALLOWED_TOOL.match("WebSearch")
    assert not ALLOWED_TOOL.match("Bash(ls)")


def test_検査はtoolsに入った許さない道具を見つける():
    """D0012-AC-05: tools_option が --tools の値を読み、Bash・Write・Edit・PowerShell が入れば許す一覧からはみ出す。Web の道具は監査の検査で見つかる。"""
    assert tools_option(GOOD_AUDIT) == ["Agent", "Read", "Grep", "Glob"]
    assert set(tools_option(GOOD_AUDIT) or []) <= TOOLS_OK
    assert tools_option('claude -p "/pipe-audit x" --allowedTools Read') is None
    for bad in ("Bash", "Write", "Edit", "PowerShell"):
        got = tools_option(f'claude -p "/pipe-audit x" --tools "Agent,Read,{bad}"')
        assert not set(got or []) <= TOOLS_OK, bad
    web = tools_option('claude -p "/pipe-audit x" --tools "Agent,WebSearch"')
    assert set(web or []) & WEB_TOOLS


def test_検査はWebFetchの行き先の過不足を見つける():
    """D0012-AC-05: guard_hosts がガードの文字を読み、webfetch_domains との集合の違いで過不足が見える。"""
    guard = 'DOC_HOSTS = ("a.example", "b.example")\n# メモ\nGITHUB_HOSTS = ("g.example",)\n'
    assert guard_hosts(guard) == {"a.example", "b.example", "g.example"}
    line = 'claude -p "/pipe-advise x" --allowedTools Read "WebFetch(domain:a.example)" "WebFetch(domain:z.example)"'
    got = webfetch_domains(line)
    assert got == {"a.example", "z.example"}
    assert guard_hosts(guard) - got == {"b.example", "g.example"}  # 不足
    assert got - guard_hosts(guard) == {"z.example"}  # 余分
    assert len(guard_hosts(read(GUARD))) >= 6  # 本物のガードからも取れる（空振りしない）


def test_検査は節の外の語を数えない():
    """D0012-AC-06/07: section が見出しの節だけを返し、前後の節の語や、見出しが無い場合は数えない。"""
    text = "## 上\n外の語 slash_commands\n### 対象\n中の語\n#### 孫\n孫の語\n### 次\n次の語 報告\n## 別\n別の語\n"
    body = section(text, "対象")
    assert "中の語" in body and "孫の語" in body
    assert "slash_commands" not in body and "報告" not in body and "別の語" not in body
    with pytest.raises(pytest.fail.Exception):
        section(text, "無い見出し")


def test_検査はfrontmatterの欠けを見つける():
    """D0012-AC-01: frontmatter の読み方が、設定の無いファイルでは空になる。"""
    assert frontmatter("本文だけ") == []
    assert "disable-model-invocation: true" in frontmatter("---\ndisable-model-invocation: true\n---\n本文")


# ---- D0038：呼び方で MCP の道具を断る ---------------------------------------------------------


def test_D0038_AC_12_呼び方の行のdisallowedToolsはちょうどmcpの全部():
    """D0038-AC-12: /pipe-help・docs/guide/develop.md の呼び方の行すべてに --disallowedTools があり、値がちょうど mcp__* の1つ。"""
    calls = doc_calls()
    assert {n for n, _ in calls} == {"pipe-help", "develop"}, "どちらの文書にも呼び方の行が要る"
    bad = [(n, option_words(line, "--disallowedTools")) for n, line in calls if option_words(line, "--disallowedTools") != [MCP_ALL]]
    assert bad == [], f"--disallowedTools が無いか、値が mcp__* でない: {bad}"


@pytest.mark.parametrize(
    "line,expected",
    [
        ('claude -p "/pipe-audit x" --tools "Agent,Read" --allowedTools Read', None),
        ('claude -p "/pipe-audit x" --tools "Agent,Read" --disallowedTools "mcp__x__*" --allowedTools Read', ["mcp__x__*"]),
        ('claude -p "/pipe-audit x" --tools "Agent,Read" --disallowedTools --allowedTools Read', []),
        ('claude -p "/pipe-audit x" --tools "Agent,Read" --disallowedTools "" --allowedTools Read', []),
        ('claude -p "/pipe-audit x" --tools "Agent,Read" --disallowedTools "mcp__*" --allowedTools Read', ["mcp__*"]),
    ],
    ids=["missing", "narrow", "empty-next-option", "empty-string", "good"],
)
def test_D0038_AC_12_検査はdisallowedToolsの抜けと狭い値と空の値を見つける(line, expected):
    """D0038-AC-12: option_words が --disallowedTools の無い行（None）・狭い値・空の値を読み分け、正しい行だけが [mcp__*] になる。"""
    got = option_words(line, "--disallowedTools")
    assert got == expected
    assert (got == [MCP_ALL]) == (expected == [MCP_ALL])


def test_D0038_AC_13_disallowedToolsを足してもallowedToolsの語が変わらない():
    """D0038-AC-13: 承認された2行と、/pipe-help・docs/guide/develop.md の行の --allowedTools の語が今までどおりで、mcp__* が混ざらない。"""
    want_audit = ["Agent(pipe-in-auditor)", "Read", "Grep", "Glob"]
    want_advise = ["Agent(pipe-in-advisor)", "Read", "Grep", "Glob", "WebSearch"] + ADVISE_WEBFETCH
    assert allowed_tools(EXPECTED_AUDIT) == want_audit
    assert allowed_tools(EXPECTED_ADVISE) == want_advise
    for name, text in (("pipe-help", read(HELP)), ("develop", read(DEVELOP))):
        assert allowed_tools(call_for(text, AUDIT_START)) == want_audit, name
        assert allowed_tools(call_for(text, ADVISE_START)) == want_advise, name


def test_D0038_AC_14_allowedToolsにmcpで始まる語が無い():
    """D0038-AC-14: /pipe-help・docs/guide/develop.md の呼び方の行の --allowedTools に、mcp__ で始まる語が無い（MCP を許していない）。"""
    calls = doc_calls()
    assert calls, "呼び方の行が1つも無い（検査が空振りしないように）"
    assert [(n, t) for n, line in calls for t in allowed_tools(line) if t.startswith("mcp__")] == []


def test_D0038_AC_14_検査はallowedToolsに混ざったmcpの語を見つける():
    """D0038-AC-14: 偽の行 `--allowedTools Read mcp__x__y` で、mcp__ で始まる語が見つかり、許す道具の一覧にも当たらない。"""
    line = 'claude -p "/pipe-audit x" --allowedTools Read mcp__x__y'
    assert [t for t in allowed_tools(line) if t.startswith("mcp__")] == ["mcp__x__y"]
    assert not ALLOWED_TOOL.match("mcp__x__y")


@pytest.mark.parametrize(
    "old,new", [(OLD_AUDIT_D0012, EXPECTED_AUDIT), (OLD_ADVISE_D0012, EXPECTED_ADVISE)], ids=["audit", "advise"]
)
def test_D0038_AC_15_前の版の呼び方の行は新しい検査で落ちる(old, new):
    """D0038-AC-15: D0012 の前の版の行は、承認された新しい行と違い（AC-11 で落ちる）、--disallowedTools が無い（AC-12 で落ちる）。"""
    assert squash(old) != new
    assert option_words(old, "--disallowedTools") is None
    assert option_words(new, "--disallowedTools") == [MCP_ALL]


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
@pytest.mark.parametrize(
    "word",
    ["--disallowedTools", MCP_ALL, ".mcp.json", "`--allowedTools` は省かない"],
    ids=["disallowedTools", "mcp-all", "mcp-json", "keep-allowedTools"],
)
def test_D0038_AC_16_節にMCPを断る説明がある(doc, word):
    """D0038-AC-16: /pipe-help の「会話を開かずに流す」の節と docs/guide/develop.md の「Claude Code で開発するとき」の節の中に、--disallowedTools と mcp__* の説明があり、.mcp.json・--allowedTools は省かない、の説明が残っている。"""
    text = doc_section(doc)
    # 呼び方の行（コードブロック）を除いた説明の文だけを見る
    prose = "\n".join(line for line in text.splitlines() if not line.strip().startswith('claude -p "'))
    assert word in prose


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
@pytest.mark.parametrize("word", OLD_MCP_WORDS, ids=["tools-not-removed", "dontask-refuses"])
def test_D0038_AC_16_節に前の言い方が残っていない(doc, word):
    """D0038-AC-16: 同じ節の中に、「`--tools` では消えませんが、`dontAsk` で許可に無ければ断られます」という前の言い方が残っていない。"""
    assert word not in doc_section(doc)


@pytest.mark.parametrize("doc", ["pipe-help", "develop"])
@pytest.mark.parametrize("word", ["maxTurns", "--max-turns", "狭め"], ids=["maxTurns", "max-turns", "narrow"])
def test_D0038_AC_17_節にmaxTurnsと狭めて流し直す説明がある(doc, word):
    """D0038-AC-17: 同じ節の中に、サブエージェントの回数の上限 maxTurns と、それとは別の --max-turns と、上限で止まったら範囲を狭めて流し直すことが書いてある。"""
    assert word in doc_section(doc)


def test_D0038_AC_18_D0038の記録に呼び方の行を書かない():
    """D0038-AC-18: D0038 の記録がちょうど1つあり、`claude -p "` で始まる呼び方の行が無い（呼び方の行は pipe-help と docs/guide/develop.md の2か所だけ）。"""
    records = sorted(DECISIONS.glob(D0038_RECORD_GLOB))
    assert len(records) == 1, f"D0038 の記録がちょうど1つでない: {[p.name for p in records]}"
    assert call_lines(read(records[0])) == []
