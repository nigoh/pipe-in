"""D0056：/pipe-talk（壁打ちのスキル）の検査。

SDK・ネットワーク・git は使わない。SKILL.md・.gitignore・settings.json などの文字を読むだけ。
docs/talk/ は読みも書きもしない（.gitignore の文字だけを読む）。
見出しの切り出しと許可の規則の当たり方は tests/test_skill_tidy.py の関数を使う。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_skill_tidy import front_matter, lacking, need_section, parse_headings, rule_matches

ROOT = Path(__file__).resolve().parents[1]
TALK_SKILL = ROOT / ".claude" / "skills" / "pipe-talk" / "SKILL.md"
HELP_SKILL = ROOT / ".claude" / "skills" / "pipe-help" / "SKILL.md"
SETTINGS = ROOT / ".claude" / "settings.json"
GITIGNORE = ROOT / ".gitignore"
CLAUDE_MD = ROOT / "CLAUDE.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
DECISIONS = ROOT / "docs" / "decisions"
SAMPLE_SUMMARY = "docs/talk/20261030-120000-sample.md"  # 見本のファイル名（文字として使うだけ。作らない）

MUST = "必ず守ること"


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_doc(path: Path) -> str:
    """読む。無ければ「が無い」でそのテストだけを落とす。"""
    if not path.is_file():
        pytest.fail(f"{rel(path)} が無い（まだ作っていない）", pytrace=False)
    return path.read_text(encoding="utf-8")


def talk() -> str:
    return read_doc(TALK_SKILL)


def front_value(fm: str, key: str) -> str | None:
    """前置きの key: の値（1行）。行が無ければ None。"""
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.M)
    return None if m is None else m.group(1).strip()


def must_section(md: str) -> str:
    return need_section(md, MUST, where="pipe-talk の SKILL.md", depth=2)


def permissions() -> dict:
    return json.loads(read_doc(SETTINGS))["permissions"]


def d0054_records() -> list[Path]:
    found = sorted(DECISIONS.glob("D0056-*.md"))
    if not found:
        pytest.fail("docs/decisions/D0056-*.md が無い（まだ作っていない）", pytrace=False)
    return found


# ---- AC-01・02：前置き -----------------------------------------------------------------------------


def test_D0056_AC_01_前置きの名前と説明と引数の案内があり_人が呼んだときだけ動く():
    """D0056-AC-01: SKILL.md があり、前置きの name が pipe-talk、description と argument-hint が空でなく、disable-model-invocation が true。"""
    fm = front_matter(talk())
    assert front_value(fm, "name") == "pipe-talk", fm
    assert front_value(fm, "description"), f"description が空か無い：{fm}"
    assert front_value(fm, "argument-hint"), f"argument-hint が空か無い：{fm}"
    assert front_value(fm, "disable-model-invocation") == "true", fm


def test_D0056_AC_02_前置きにallowed_toolsが無いか_Bashとghとmcpを含まない():
    """D0056-AC-02: 前置きに allowed-tools が無い。あっても Bash・gh・mcp__ を含まない（外へ出す道具を確認なしで通さない）。"""
    fm = front_matter(talk())
    value = front_value(fm, "allowed-tools")
    if value is None:
        return
    assert [w for w in ("Bash", "gh", "mcp__") if w in value] == [], f"allowed-tools：{value}"


# ---- AC-03・04：冒頭の決まりと引数 ---------------------------------------------------------------------


def test_D0056_AC_03_最初の見出しが必ず守ることで_決まりの語がある():
    """D0056-AC-03: # /pipe-talk の次の ## 見出しが「必ず守ること」で、節に「承認」・「gh issue create」・「手元にだけ」・「公開リポジトリとしての注意」・「git check-ignore」がある。"""
    md = talk()
    heads = parse_headings(md)
    tops = [h for h in heads if h.depth == 1]
    assert tops and tops[0].title.startswith("/pipe-talk"), f"# /pipe-talk の見出しが無い：{[h.title for h in tops]}"
    seconds = [h for h in heads if h.depth == 2 and h.start > tops[0].start]
    assert seconds and seconds[0].title == MUST, f"最初の ## 見出し：{seconds[0].title if seconds else None}"
    words = ("承認", "gh issue create", "手元にだけ", "公開リポジトリとしての注意", "git check-ignore")
    assert lacking(must_section(md), words) == []


def test_D0056_AC_04_ARGUMENTSは1回で_必ず守ることより後ろにあり_空なら聞く():
    """D0056-AC-04: $ARGUMENTS が全体で1回、「必ず守ること」の節より後ろにあり、その次の空でない行が「（空なら」で始まる。"""
    md = talk()
    assert md.count("$ARGUMENTS") == 1, f"$ARGUMENTS の数：{md.count('$ARGUMENTS')}"
    body = must_section(md)
    must_end = md.index(body) + len(body)
    pos = md.index("$ARGUMENTS")
    assert pos >= must_end, "$ARGUMENTS が「必ず守ること」の節より前か中にある"
    after = md[md.index("\n", pos) + 1 :] if "\n" in md[pos:] else ""
    nxt = next((line.strip() for line in after.splitlines() if line.strip()), "")
    assert nxt.startswith("（空なら"), f"$ARGUMENTS の次の行：{nxt!r}"


# ---- AC-05〜09：要約 -------------------------------------------------------------------------------


def test_D0056_AC_05_要約の3つの見出しがある():
    """D0056-AC-05: 要約の3つの見出し「決まったこと」「残った問い」「やりたいこと」がある。"""
    assert lacking(talk(), ("決まったこと", "残った問い", "やりたいこと")) == []


def test_D0056_AC_06_要約の置き場所とファイル名の形がある():
    """D0056-AC-06: 要約の置き場所 docs/talk/ と、ファイル名の形 <日時>-<名前>.md と、名前の決まり「英小文字」がある。"""
    assert lacking(talk(), ("docs/talk/", "<日時>-<名前>.md", "英小文字")) == []


GLOB_CHARS = re.compile(r"[*?\[]")


def gitignore_covers(text: str, path: str) -> bool:
    """.gitignore の文字で path が無視されるか（ディレクトリの行だけを見る小さな判定。後ろの行が勝つ）。
    ディレクトリの形（先頭の /・末尾の /・/* ・/**）だけを扱い、ほかのワイルドカードの行は当たらないとみなす（安全側）。"""
    covered = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        for tail in ("/**", "/*"):
            if line.endswith(tail):
                line = line[: -len(tail)]
                break
        line = line.strip("/")
        if not line or GLOB_CHARS.search(line):
            continue
        if path.startswith(line + "/"):
            covered = not negate
    return covered


def test_D0056_AC_07_gitignoreの行が要約の置き場所を覆う():
    """D0056-AC-07: .gitignore に docs/talk/ を覆う行があり、! で戻す行が無い（見本のファイル名で判定）。"""
    text = read_doc(GITIGNORE)
    assert gitignore_covers(text, SAMPLE_SUMMARY), f".gitignore に {SAMPLE_SUMMARY} を覆う行が無い（/docs/talk/ を足す）"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("/docs/talk/\n", True),
        ("docs/talk/\n", True),
        ("/docs/talk\n", True),
        ("/docs/talk/**\n", True),
        ("# /docs/talk/\n/docs/pipeline/\n", False),  # 書いてあるのが説明の行だけ・別の場所の行だけ
        ("", False),
        ("/docs/talk/\n!docs/talk/\n", False),  # 戻す行
        ("/docs/talk/\n!/docs/talk/*.md\n", True),  # ワイルドカードの戻しは当たらないとみなす（判定の限り）
        ("/docs/talks/\n", False),
    ],
)
def test_D0056_AC_07_見本_覆う行と戻す行を見分ける_守る(text, want):
    """D0056-AC-07: 検査そのものの確かめ。覆う行が無い・! で戻す・別の場所の行だけ、は「覆わない」と判定する。（今のまま通る。守る）"""
    assert gitignore_covers(text, SAMPLE_SUMMARY) is want


def test_D0056_AC_08_書く前にgit_check_ignoreで確かめ_無視されていなければ書かずに伝える():
    """D0056-AC-08: 「2. まとめる」の節に git check-ignore・「書かず」・「伝え」がある（古い枝で要約を追跡の候補に出さない）。"""
    body = need_section(talk(), "まとめる", where="pipe-talk の SKILL.md", depth=2)
    assert lacking(body, ("git check-ignore", "書かず", "伝え")) == []


def test_D0056_AC_09_要約のほかには書かず_コミットとpushをしない():
    """D0056-AC-09: 「ほかのファイルには書かない」・「コミット」・「push」がある。"""
    assert lacking(talk(), ("ほかのファイルには書かない", "コミット", "push")) == []


# ---- AC-10〜17：回す先と承認 ---------------------------------------------------------------------------


def test_D0056_AC_10_4つの回す先の語がある():
    """D0056-AC-10: 「issue」・「Design」・「Figma」・/pipe-in・/pipe-plan add がある。"""
    assert lacking(talk(), ("issue", "Design", "Figma", "/pipe-in", "/pipe-plan add")) == []


def test_D0056_AC_11_候補は人が選ぶまで行わない():
    """D0056-AC-11: 「選ぶまで」がある。"""
    assert "選ぶまで" in talk()


def shown_then_approved(body: str) -> bool:
    """「本文」のあとの「見せ」 < その後の「承認」 < gh issue create の最初の位置、の順か。"""
    cmd = body.find("gh issue create")
    honbun = body.find("本文")
    if cmd < 0 or honbun < 0:
        return False
    show = body.find("見せ", honbun)
    if show < 0:
        return False
    ok = body.find("承認", show)
    return 0 <= ok < cmd


def test_D0056_AC_12_issueの節は本文を見せて承認を得てからgh_issue_create():
    """D0056-AC-12: 「issue を作る」の節で、「本文」のあとの「見せ」 < その後の「承認」 < gh issue create の最初の位置。"""
    body = need_section(talk(), "issue を作る", where="pipe-talk の SKILL.md", depth=2)
    assert shown_then_approved(body), body


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("題と本文を作り、全文見せる。人の承認を得てから `gh issue create` で作る。", True),
        ("`gh issue create` で作る。題と本文を作り、全文見せる。人の承認を得る。", False),  # コマンドが先
        ("題と本文を作り、全文見せる。そのまま `gh issue create` で作る。", False),  # 承認が無い
        ("人の承認を得てから `gh issue create` で作る。本文は要約から作る。", False),  # 見せるが無い
        ("本文を作る。人の承認を得る。`gh issue create` で作る。見せる。", False),  # 見せるが後ろ
    ],
)
def test_D0056_AC_12_見本_順番が逆の文を見つける_守る(text, want):
    """D0056-AC-12: 検査そのものの確かめ。gh issue create が先・承認が無い・見せるが無い文は不合格。（今のまま通る。守る）"""
    assert shown_then_approved(text) is want


def test_D0056_AC_13_issueの節にMCPの道も承認を得てからとある():
    """D0056-AC-13: 「issue を作る」の節に「MCP」と「承認」がある。"""
    body = need_section(talk(), "issue を作る", where="pipe-talk の SKILL.md", depth=2)
    assert lacking(body, ("MCP", "承認")) == []


def test_D0056_AC_14_必ず守ることに外へ出す操作の並びと承認がある():
    """D0056-AC-14: 「必ず守ること」に「issue」・「Figma」・「アーティファクト」・「計画ボード」・「承認」がある。"""
    assert lacking(must_section(talk()), ("issue", "Figma", "アーティファクト", "計画ボード", "承認")) == []


def test_D0056_AC_15_入れないものの語がある():
    """D0056-AC-15: 「秘密」・「絶対パス」・「メールアドレス」がある（「公開リポジトリとしての注意」を指すだけでは足りない）。"""
    assert lacking(talk(), ("秘密", "絶対パス", "メールアドレス")) == []


def test_D0056_AC_16_デザインの節は画面か見た目のときだけで_決まりに沿い_道具が無ければ止まる():
    """D0056-AC-16: 「デザインに回す」の節に「画面」か「見た目」・docs/design/README.md・「止ま」がある。"""
    body = need_section(talk(), "デザインに回す", where="pipe-talk の SKILL.md", depth=2)
    assert "画面" in body or "見た目" in body, body
    assert lacking(body, ("docs/design/README.md", "止ま")) == []


def test_D0056_AC_17_pipe_inとpipe_plan_addの節は人が流す行を示す():
    """D0056-AC-17: 「で実装する」の節に「人が」と「/pipe-in 」、「計画ボードに足す」の節に「人が」と /pipe-plan add がある。"""
    md = talk()
    impl = need_section(md, "で実装する", where="pipe-talk の SKILL.md", depth=2)
    board = need_section(md, "計画ボードに足す", where="pipe-talk の SKILL.md", depth=2)
    assert lacking(impl, ("人が", "/pipe-in ")) == [], impl
    assert lacking(board, ("人が", "/pipe-plan add")) == [], board


# ---- AC-18・27：設定 ---------------------------------------------------------------------------------


def test_D0056_AC_18_allowにghのBashの規則が無い_守る():
    """D0056-AC-18: allow のどの規則も gh issue create --title x --body-file y に当たらず、Bash(gh で始まる規則も無い。（今のまま通る。守る）"""
    allow = permissions()["allow"]
    hits = [r for r in allow if rule_matches(r, "gh issue create --title x --body-file y")]
    assert hits == [], hits
    assert [r for r in allow if r.startswith("Bash(gh")] == []


def test_D0056_AC_27_askにgh_issue_createがあり_既存の6つが残る():
    """D0056-AC-27: permissions.ask に Bash(gh issue create:*) があり、既存の6つ（git push・git commit・git merge・npm publish・npx vsce publish・twine upload）が残る。"""
    want = [
        "Bash(gh issue create:*)",
        "Bash(git push:*)",
        "Bash(git commit:*)",
        "Bash(git merge:*)",
        "Bash(npm publish:*)",
        "Bash(npx vsce publish:*)",
        "Bash(twine upload:*)",
    ]
    ask = permissions()["ask"]
    assert lacking(ask, want) == [], f"ask の今の規則：{ask}"


# ---- AC-19：公開してよいか ---------------------------------------------------------------------------

LOCAL_PATHS = ("/home/", "/Users/", "C:\\Users")
FORBIDDEN = (
    (re.compile(r"github\.com/[^/\s]+/[^/\s]+/issues/\d+"), "issue の実際の URL"),
    (re.compile(r"claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]{6,}"), "アーティファクトの実際の URL"),
    (re.compile(r"session_[A-Za-z0-9]{10,}"), "実際のセッション ID"),
)


def test_D0056_AC_19_SKILLと記録に手元のパスと実際のURLとセッションIDが無い():
    """D0056-AC-19: SKILL.md と docs/decisions/D0056-*.md（無ければ落ちる）に、手元のパス・issue やアーティファクトの実際の URL・実際のセッション ID が無い。"""
    problems: list[str] = []
    for path in [TALK_SKILL, *d0054_records()]:
        text = read_doc(path)
        problems += [f"{rel(path)}: {p}" for p in LOCAL_PATHS if p in text]
        problems += [f"{rel(path)}: {why}" for pat, why in FORBIDDEN if pat.search(text)]
    assert problems == []


# ---- AC-20〜23：ほかのファイル -------------------------------------------------------------------------


def test_D0056_AC_20_pipe_helpの表と説明にpipe_talkがある():
    """D0056-AC-20: /pipe-help の SKILL.md の表の行に `/pipe-talk があり、前置きの description に /pipe-talk がある。"""
    md = read_doc(HELP_SKILL)
    rows = [line for line in md.splitlines() if line.lstrip().startswith("|") and "`/pipe-talk" in line]
    assert rows, "/pipe-help の表に `/pipe-talk の行が無い"
    desc = front_value(front_matter(md), "description") or ""
    assert "/pipe-talk" in desc, f"description：{desc}"


def test_D0056_AC_21_CLAUDE_mdにpipe_talkとスキルの置き場所がある():
    """D0056-AC-21: CLAUDE.md に /pipe-talk と .claude/skills/pipe-talk/ がある。"""
    assert lacking(read_doc(CLAUDE_MD), ("/pipe-talk", ".claude/skills/pipe-talk/")) == []


def test_D0056_AC_22_設計の決まりの置き場所の表にpipe_talkがある():
    """D0056-AC-22: docs/development/design.md の表の行（縦棒で始まる行）に .claude/skills/pipe-talk/ がある。"""
    rows = [line for line in read_doc(DESIGN_MD).splitlines() if line.lstrip().startswith("|") and ".claude/skills/pipe-talk/" in line]
    assert rows, "design.md の置き場所の表に .claude/skills/pipe-talk/ が無い"


def test_D0056_AC_23_決定の記録があり_表に載っている():
    """D0056-AC-23: docs/decisions/D0056-*.md があり、docs/decisions/README.md に D0056 がある。"""
    d0054_records()
    assert "D0056" in read_doc(DECISIONS / "README.md"), "docs/decisions/README.md に D0056 が無い"
