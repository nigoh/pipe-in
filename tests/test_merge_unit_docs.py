"""D0074：夜のまとめ実行と機能の merge の単位。CLAUDE.md・設定・スキル・文書の文字の検査。

読むだけで書かない（偽の文は文字列で組み立てる）。SDK は呼ばない。判定の道具（rule_matches・ask_hits・permissions など）は tests/test_skill_tidy.py、
文書の読み方の道具と無人の実行の検査は tests/test_unattended_run.py にある（新しい判定の知識は足さない。D0073 と同じ形）。

- 検査は、「問題の一覧を返す関数」と、実物を読む検査と、設計の文案で関数を確かめる見本（今のまま通る。守る）の 3 つ組にしてある。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
- 実機・手で確かめる AC（AC-23 の手の部分・AC-30・AC-31）は、ここにテストを足さない（03_red_tests.md に書く）。
- 字数（AC-24）は tests/test_skill_tidy.py の D0039-AC-11（SKILL.md は 12,300 字以下・補助ファイルは 1 つずつ 3,500 字以下）が見る。
- decision_number.py の挙動は tests/test_decision_number.py、worktree の挙動は tests/test_worktree_origin.py が見る。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from test_skill_tidy import (
    ROOT,
    ask_hits,
    line_with,
    permissions,
    read_doc,
    rule_matches,
    section_text,
    skill,
)
from test_unattended_run import (
    CLAUDE_MD,
    DESIGN_MD,
    DEVELOP_MD,
    HELP_SKILL,
    STOP_ALL,
    WORKFLOW_MD,
    check,
    commit_item,
    finish_problems,
    forbidden_words,
    missing_words,
    unattended_text,
)

README_GUIDE = ROOT / "docs" / "guide" / "README.md"
DECISION_NUMBER = ROOT / "pipe_in" / "dev" / "decision_number.py"


# ======== AC-19：CLAUDE.md の無人の実行の範囲 ==================================================================================

NIGHT_ITEM_WORDS = (
    "`night/<名前>`",
    "名指し",
    "早送り",
    "1本",
    "`night/` 以外",
    "`feat/`・`fix/`・`docs/`・`night/`",
    "main",
    "強制",
    "削除",
    "今までどおりしない",
)


def night_item_problems(item: str) -> list[str]:
    """コミットの項目に、まとめの枝の名指し・その枝への早送りの push の承認・その 1 本だけに効くこと・それ以外は今までどおりしないこと、がある問題の一覧。"""
    return missing_words(item, NIGHT_ITEM_WORDS, "コミットの項目")


# 設計 2.5 の文案（CLAUDE.md の 58 行目の書き換えと、その下の入れ子の 1 行）
SAMPLE_NIGHT_ITEM = (
    "- 1つの機能を1つのコミットにする。無人の実行でしてよいのは、その実行が切った枝（`feat/`・`fix/`・`docs/`・`night/`）への commit・"
    "`git push -u origin <その枝>`・PR の作成だけ。承認は名指しした操作だけで、開始の指示では範囲を広げられない。\n"
    "  - 夜のまとめ実行（D0074）だけ、範囲をもう1つ広げる。開始の指示が、まとめの枝 `night/<名前>` を名指しして、その枝への早送りの push を承認しているときは、"
    "その枝1本にだけ、`git push origin <子の枝>:night/<名前>`（子の枝の中なら `git push origin HEAD:night/<名前>`）の形の push をしてよい（`git -C` を付けない）。"
    "承認は名指しした枝だけに効く。`night/` 以外の枝・名指しされていない `night/` の枝・main・強制・削除・`--all`・`--mirror` への push は、今までどおりしない。"
    "まとめの枝の作成（origin の main から切り、`git push -u origin night/<名前>`）と、main 向けの PR の作成は、親が開始の指示の承認に沿ってする。"
    "main に入れること（merge）は人が朝にする。\n"
)


def test_D0074_AC_19_CLAUDE_mdにまとめの枝の名指しと早送りのpushの承認と1本だけに効くことがある() -> None:
    """D0074-AC-19: CLAUDE.md のコミットの項目に、まとめの枝 `night/<名前>` の名指し・その枝への早送りの push の承認・その 1 本だけに効くこと・
    `night/` 以外と main と強制と削除は今までどおりしないこと、があり、無人の実行が切った枝の並びが `feat/`・`fix/`・`docs/`・`night/` になっている。
    ほかの項目の文（無人の実行の見分け方・親が起こす子の実行）は、範囲を変えずに写す決まりのまま（D0073-AC-07〜14 の既存のテストが見る）。"""
    _, item = commit_item(read_doc(CLAUDE_MD))
    check(night_item_problems(item))


def test_D0074_AC_19_見本_設計の文案は検査に通り_語が欠けた形を見つける_守る() -> None:
    """D0074-AC-19: 検査そのものの確かめ。設計の文案は検査に通り、語を 1 つ消した文は、その語だけを欠けとして返す。（今のまま通る。守る）"""
    assert night_item_problems(SAMPLE_NIGHT_ITEM) == []
    for word in NIGHT_ITEM_WORDS:
        problems = night_item_problems(SAMPLE_NIGHT_ITEM.replace(word, "□"))
        assert problems == [f"コミットの項目に「{word}」が無い"], (word, problems)
    assert night_item_problems("- 1つの機能を1つのコミットにする。")  # 何も書いていなければ問題が出る


# ======== AC-20・21：settings.json の ask と allow ==============================================================================

# 夜の形（設計 4 の N1〜N4）と、止める形（M1〜M5）と、M ごとに当たる ask の規則
NIGHT_PUSHES = [
    ("N1", "git push origin HEAD:night/2026-11-04"),
    ("N2", "git push origin feat/merge-unit:night/2026-11-04"),
    ("N3", "git push -u origin night/2026-11-04"),
    ("N4", "git push origin HEAD:night/2026-11-04-2"),
]
STOPPED_PUSHES = [
    ("M1", "git push origin HEAD:main", "Bash(git push *:main)"),
    ("M2", "git push origin feat/x:main", "Bash(git push *:main)"),
    ("M3", "git push origin HEAD:refs/heads/main", "Bash(git push */main)"),
    ("M4", "git push --force origin HEAD:night/x", "Bash(git push *--force*)"),
    ("M5", "git push origin :night/x", "Bash(git push * :**)"),
]


@pytest.mark.parametrize("command", [pytest.param(c, id=n) for n, c in NIGHT_PUSHES])
def test_D0074_AC_20_夜のpushの形はaskのどの規則にも当たらない_守る(command: str) -> None:
    """D0074-AC-20: 夜の push の形（N1〜N4。まとめの枝へ、HEAD または子の枝から。同じ日の 2 回目は -2）は、ask のどの規則にも当たらない
    （確認で止まらない。設定は変えない）。（今のまま通る。守る）"""
    hits = ask_hits(permissions()["ask"], command)
    assert hits == [], f"「{command}」に当たる ask の規則がある：{hits}"


@pytest.mark.parametrize("command,rule", [pytest.param(c, r, id=n) for n, c, r in STOPPED_PUSHES])
def test_D0074_AC_20_main_強制_削除の形は今までどおりaskに当たる_守る(command: str, rule: str) -> None:
    """D0074-AC-20: main へ届きうる形（M1〜M3）・強制（M4）・削除（M5）は、今までどおり ask に当たる（狭めない）。当たる規則は設計の表のとおり。
    （今のまま通る。守る）"""
    hits = ask_hits(permissions()["ask"], command)
    assert rule in hits, f"「{command}」が {rule} に当たらない（当たった規則：{hits}）"


def test_D0074_AC_20_見本_判定の道具は夜の形とmainの形を分ける_守る() -> None:
    """D0074-AC-20: 検査そのものの確かめ。判定の道具が、night/ の枝への push と main への push を取り違えない
    （*:main は :main で終わる形だけ・* :** は空白の直後の : だけ）。（今のまま通る。守る）"""
    assert rule_matches("Bash(git push *:main)", "git push origin HEAD:main")
    assert not rule_matches("Bash(git push *:main)", "git push origin HEAD:night/2026-11-04")
    assert rule_matches("Bash(git push * :**)", "git push origin :night/x")
    assert not rule_matches("Bash(git push * :**)", "git push origin HEAD:night/x")


def test_D0074_AC_21_allowに夜のpushの規則を足さず_git_pushに当たる規則も無い_守る() -> None:
    """D0074-AC-21: allow のどの規則も夜の push の形（N1〜N3）に当たらず、git push の規則（Bash(git push…)）を持たない（足さない。Q3）。
    足す規則があれば、git push origin <枝>:night/<名前> の形だけで、ask に当たる形（M1〜M5 と、D0073 の止める形すべて）に当たらない。（今のまま通る。守る）"""
    allow = permissions()["allow"]
    ask = permissions()["ask"]
    for name, command in NIGHT_PUSHES[:3]:
        assert ask_hits(allow, command) == [], f"{name} に当たる allow の規則がある"
    push_rules = [r for r in allow if r.startswith("Bash(git push")]
    # 足す規則があるなら：ask に当たる形のどれにも当たらない（ask と重ならない）
    stop_commands = [c for _, c in STOP_ALL if any(rule_matches(r, c) for r in ask)] + [c for _, c, _ in STOPPED_PUSHES]
    overlapping = {r: [c for c in stop_commands if rule_matches(r, c)] for r in push_rules}
    assert {r: cs for r, cs in overlapping.items() if cs} == {}
    assert push_rules == [], f"allow に git push の規則を足している（足さない決まり。Q3）：{push_rules}"


# ======== AC-22・23：unattended.md ==============================================================================================

NIGHT_CHILD_WORDS = (
    "--base night/",
    "decision-number --branch night/",
    "git push origin HEAD:night/",
    "早送り",
    "worktree sync --base night/",
    "もう 1 回だけ",
    "record finish BLOCKED",
    "push せず",
    "PR も作らない",
)


def night_child_problems(text: str) -> list[str]:
    """unattended.md に、まとめの枝へ積む子の手順（枝の切り方・番号の取り方・早送りの push・載せ直しと 1 回だけの再 push・BLOCKED・件ごとの枝は push せず PR も作らない）がある問題。"""
    return missing_words(text, NIGHT_CHILD_WORDS, "unattended.md")


# 設計 2.5 の文案（補助ファイルの「仕上げ」の下に足す形）
SAMPLE_NIGHT_CHILD = """**夜のまとめの子（まとめの枝へ積む）。** 親の開始の指示が、まとめの枝 `night/<名前>` を名指しして、その枝への早送りの push を承認しているときの、子の手順。上の「仕上げ」の 2〜4 を、次に替える。

- 枝は `python -m pipe_in skill worktree new <件の名前> --base night/<名前>` で、まとめの枝の最新から切る。決定の記録の番号は、始めに `python -m pipe_in skill decision-number --branch night/<名前>` で取る（前の件が積んだ番号の次になる）。
- 検証が通ったら、自分の変更を 1 コミットにする（commit の前に `git diff --cached`）。件ごとの枝は push せず、PR も作らない。
- `git push origin HEAD:night/<名前>` で、まとめの枝へ早送りだけで push する（強制はしない。`git -C` を付けない。名指しされた枝のほかへは push しない）。
- 早送りでなく断られたら（ほかの子が先に積んだ）、`python -m pipe_in skill worktree sync --base night/<名前>` で載せ直し、テストを流し直して、もう 1 回だけ push する。それでも断られたら `record finish BLOCKED` で止め、変更は commit のまま残して終わりの報告に書く。
- `BLOCKED`・`TEST_FAILED` で止まった子は、まとめの枝に積まれない。終わりの報告に、止まった理由と、積まなかったことを書く。
"""


def test_D0074_AC_22_unattended_mdにまとめの枝へ積む子の手順がある() -> None:
    """D0074-AC-22: unattended.md に、まとめの枝へ積む子の手順（--base night/ での枝の切り方・decision-number --branch night/・git push origin HEAD:night/ の早送りの push・
    断られたときの worktree sync --base night/ での載せ直しと「もう 1 回だけ」の再 push・record finish BLOCKED）と、件ごとの枝は push せず PR も作らないこと、がある。
    形（# の見出し 1 つ）は D0073-AC-42、目印の 3 語が無いことは D0073-AC-14 が見る（既存）。"""
    check(night_child_problems(unattended_text()))


def test_D0074_AC_22_見本_設計の文案は検査に通り_語が欠けた形を見つける_守る() -> None:
    """D0074-AC-22: 検査そのものの確かめ。設計の文案は検査に通り、語を 1 つ消した文は、その語を欠けとして返す
    （「--base night/」は「worktree sync --base night/」の一部でもあるので、両方が欠けとして出てよい）。（今のまま通る。守る）"""
    assert night_child_problems(SAMPLE_NIGHT_CHILD) == []
    for word in NIGHT_CHILD_WORDS:
        problems = night_child_problems(SAMPLE_NIGHT_CHILD.replace(word, "□"))
        assert f"unattended.mdに「{word}」が無い" in problems, (word, problems)
    assert forbidden_words(SAMPLE_NIGHT_CHILD, ("承認にならない", "名指しの無い", "サブエージェントの返事"), "文案") == []


def test_D0074_AC_23_仕上げの手順は変わらずその枝へのpushとPRの作成を書く_守る() -> None:
    """D0074-AC-23（機械の補助。本体は手で、unattended.md の「仕上げ」の 1〜5 が今回の diff で変わっていないことを git diff で見る）：
    まとめの枝を使わない今までの無人の実行の手順（その実行が切った feat/ の枝へ commit し、git push -u origin <その枝> で push し、PR を作る）の語が残る。
    （今のまま通る。守る）"""
    text = unattended_text()
    check(finish_problems(text))
    check(missing_words(text, ("`git push -u origin <その枝>`", "`feat/`・`fix/`・`docs/`", "PR を作る（`gh pr create`"), "unattended.md"))


# ======== AC-24・25：SKILL.md ===================================================================================================


def test_D0074_AC_24_SKILLの入れるよう言われたらの項目にff_onlyが無くPRとCIとsyncとcleanがある() -> None:
    """D0074-AC-24: SKILL.md の「main に入れるよう言われたら」に git merge --ff-only が無く（SKILL.md のどこにも無い）、worktree sync での載せ直し・PR の CI・
    GitHub の PR で入れること（gh pr merge は確認が出る）・worktree clean での片付けが書かれている（ExitWorktree・keep は残る）。字数の上限は D0039-AC-11 が見る。"""
    md = skill()
    line = line_with(md, "main に入れるよう言われたら", "SKILL.md")
    problems = missing_words(line, ("worktree sync", "CI", "PR", "gh pr merge", "worktree clean", "ExitWorktree", "keep"), "「main に入れるよう言われたら」の項目")
    problems += forbidden_words(md, ("git merge --ff-only",), "SKILL.md ")
    problems += forbidden_words(line, ("stash",), "「main に入れるよう言われたら」の項目")
    check(problems)


def test_D0074_AC_25_SKILLの始めの手順にmainから切って積まないこととdecision_numberがある() -> None:
    """D0074-AC-25: SKILL.md の始めの手順（枝を切る所）に、origin の main から切ってほかの機能の枝の上に積まないことが、決定の記録の番号を決める所に、
    python -m pipe_in skill decision-number で取ること（origin の main の次の番号）が書かれている。"""
    md = skill()
    cut = line_with(md, "skill worktree new <名前>", "SKILL.md")
    number = line_with(md, "skill decision-number", "SKILL.md")
    check(
        missing_words(cut, ("origin の main", "積まない"), "枝を切る所")
        + missing_words(number, ("python -m pipe_in skill decision-number", "Dnnnn", "origin の main"), "決定の記録の番号の所")
    )


# ======== AC-26：docs/guide/develop.md の夜のまとめ実行 ========================================================================

NIGHT_GUIDE_WORDS = (
    "night/<日付>",
    "名指し",
    "早送りの push",
    "worktree new <日付> --kind night",
    "git push -u origin night/<日付>",
    "順に",
    "並列にしない",
    "完了の返事",
    "BLOCKED",
    "TEST_FAILED",
    "飛ばして",
    "PR",
    "本文",
    "積んだ件",
    "止まった件",
    "merge commit",
)


def night_guide_problems(md: str) -> list[str]:
    """develop.md に、夜のまとめ実行（親の進め方）の節があり、6 点（開始の指示・子の作り方・待ち方・止まったとき・まとめ・朝の入れ方）の語がある問題。"""
    body = section_text(md, "夜のまとめ実行", depth=3)
    if body is None:
        return ["develop.md に「### 夜のまとめ実行（親の進め方）」の節が無い"]
    return missing_words(body, NIGHT_GUIDE_WORDS, "夜のまとめ実行の節")


SAMPLE_GUIDE = """### 無人の実行の始め方

本文。

### 夜のまとめ実行（親の進め方）

1. 開始の指示に、まとめの枝 `night/<日付>` を名指しして、その枝への早送りの push を承認する文を書く。
2. 親は `python -m pipe_in worktree new <日付> --kind night` で切り、`git push -u origin night/<日付>` で出す。子は件ごとに 1 つ、順に起こす（並列にしない）。
3. 子の完了の返事を待つ。
4. `BLOCKED`・`TEST_FAILED` の件は積まず、飛ばして次へ。
5. 親が main 向けの PR を 1 つ作る。本文に、積んだ件と止まった件を書く。
6. 朝は人が CI を見て、merge commit で入れる。
"""


def test_D0074_AC_26_developに夜のまとめ実行の親の進め方の6点があり目次から辿れる() -> None:
    """D0074-AC-26: docs/guide/develop.md に「夜のまとめ実行（親の進め方）」の節があり、6 点（開始の指示の文・件ごとに順に・待ち方・BLOCKED/TEST_FAILED は積まず飛ばす・
    PR の本文・朝の merge commit）が書かれ、docs/guide/README.md の目次の行（pipe-in を開発する）から辿れる（「夜のまとめ実行」）。
    目印の 3 語が無いことは D0073-AC-14 が見る（既存）。"""
    problems = night_guide_problems(read_doc(DEVELOP_MD))
    row = line_with(read_doc(README_GUIDE), "[pipe-in を開発する](develop.md)", "docs/guide/README.md")
    problems += missing_words(row, ("夜のまとめ実行",), "目次の行")
    check(problems)


def test_D0074_AC_26_見本_設計の文案は検査に通り_節や語が欠けた形を見つける_守る() -> None:
    """D0074-AC-26: 検査そのものの確かめ。節があり 6 点の語がそろう形は通り、節が無い形・語が欠けた形は見つける。（今のまま通る。守る）"""
    assert night_guide_problems(SAMPLE_GUIDE) == []
    assert night_guide_problems("### 無人の実行の始め方\n\n本文。\n") == ["develop.md に「### 夜のまとめ実行（親の進め方）」の節が無い"]
    assert night_guide_problems(SAMPLE_GUIDE.replace("merge commit", "マージ")) == ["夜のまとめ実行の節に「merge commit」が無い"]


# ======== AC-27：workflow.md と design.md ======================================================================================


def workflow_problems(md: str) -> list[str]:
    """workflow.md：「1. 始める」に origin から取ること・--no-fetch・まとめの枝・積み重ねないこと、「3. 載せ直す」に origin/main と --no-fetch、
    「5. 終える」に PR と CI で入れる形（手元の git merge --ff-only・stash の段落は無い）と night/ の push の範囲がある問題。"""
    problems: list[str] = []
    start = section_text(md, "1. 始める", depth=2)
    again = section_text(md, "3. 載せ直す", depth=2)
    finish = section_text(md, "5. 終える", depth=2)
    for name, body in (("1. 始める", start), ("3. 載せ直す", again), ("5. 終える", finish)):
        if body is None:
            problems.append(f"workflow.md に「## {name}」の節が無い")
    if start is not None:
        problems += missing_words(start, ("origin の main", "--no-fetch", "--kind night", "night/", "積み重ね"), "「1. 始める」")
        problems += forbidden_words(start, ("`git fetch` してから `--base origin/main` を付けます",), "「1. 始める」")
    if again is not None:
        problems += missing_words(again, ("origin/main", "--no-fetch"), "「3. 載せ直す」")
        problems += forbidden_words(again, ("HEAD..main",), "「3. 載せ直す」")
    if finish is not None:
        problems += missing_words(finish, ("worktree clean", "PR", "CI", "night/"), "「5. 終える」")
        problems += forbidden_words(finish, ("git merge --ff-only", "stash"), "「5. 終える」")
    return problems


def test_D0074_AC_27_workflowにoriginから取ること_no_fetch_まとめの枝がある() -> None:
    """D0074-AC-27: workflow.md の「1. 始める」に、origin から取ること・取れなければ止まること・--no-fetch・--kind night・単独の機能は main から切って積み重ねないこと、
    「3. 載せ直す」に origin/main と --no-fetch、「5. 終える」に PR と CI で入れる形（手元の git merge --ff-only と stash の段落は外れる）と night/ の push の範囲が書かれている。
    「ブランチの保護」の節の git merge --ff-only は残る（D0073-AC-25・tests/test_rules.py が見る）。"""
    check(workflow_problems(read_doc(WORKFLOW_MD)))


def test_D0074_AC_27_見本_検査は語が欠けた形と古い文が残った形を見つける_守る() -> None:
    """D0074-AC-27: 検査そのものの確かめ。節が無い形・古い文（git fetch してから --base origin/main・HEAD..main・git merge --ff-only・stash）が残った形を見つける。
    （今のまま通る。守る）"""
    good = (
        "## 1. 始める\n\norigin の main から切る。--no-fetch。--kind night。night/ のまとめの枝。積み重ねない。\n\n"
        "## 3. 載せ直す\n\norigin/main に載せる。--no-fetch。\n\n"
        "## 5. 終える\n\nPR の CI を見て入れる。worktree clean。night/ の早送りの push。\n\n"
        "## 6. CI\n\nブランチの保護：git merge --ff-only は使えない。\n"
    )
    assert workflow_problems(good) == []
    assert workflow_problems("## 1. 始める\n\n本文。\n")  # 語が欠け、ほかの節も無い
    stale = good.replace("origin/main に載せる。", "HEAD..main を見る。").replace("入れる。worktree clean。", "git merge --ff-only で入れる。stash しない。worktree clean。")
    problems = workflow_problems(stale)
    assert "「3. 載せ直す」に「origin/main」が無い" in problems
    assert "「3. 載せ直す」に「HEAD..main」がある" in problems
    assert "「5. 終える」に「git merge --ff-only」がある" in problems and "「5. 終える」に「stash」がある" in problems


def test_D0074_AC_27_designの置き場所の表のdev行にdecision_numberが入る() -> None:
    """D0074-AC-27: docs/development/design.md の置き場所の表で、pipe_in/dev/worktree.py の行に decision-number（決定の記録の次の番号を出す。D0074）と
    パス pipe_in/dev/decision_number.py が入り、skill 入口（skill_cmd.py）の行にも decision-number が入る。行は足さず、既存の 2 行を直す。"""
    md = read_doc(DESIGN_MD)
    worktree_row = line_with(md, "`pipe_in/dev/worktree.py`", "design.md")
    skill_row = line_with(md, "`pipe_in/dev/skill_cmd.py`", "design.md")
    check(
        missing_words(worktree_row, ("decision-number", "D0074", "pipe_in/dev/decision_number.py"), "worktree.py の行")
        + missing_words(skill_row, ("decision-number",), "skill_cmd.py の行")
    )


# ======== AC-28：/pipe-help ======================================================================================================


def help_problems(text: str) -> list[str]:
    """/pipe-help の worktree と --auto の行が新しい形（--no-fetch・night・decision-number。夜のまとめ実行は develop.md を指す）とそろっている問題。"""
    problems = missing_words(text, ("--no-fetch", "night", "decision-number"), "/pipe-help")
    auto = next((line for line in text.splitlines() if line.startswith("| `/pipe-in --auto")), None)
    if auto is None:
        return problems + ["/pipe-help に「/pipe-in --auto」の行が無い"]
    return problems + missing_words(auto, ("夜のまとめ実行", "docs/guide/develop.md", "無人の実行だけ例外"), "「/pipe-in --auto」の行")


def test_D0074_AC_28_pipe_helpの行がno_fetch_night_decision_numberとそろう() -> None:
    """D0074-AC-28: /pipe-help の /pipe-in の行（始めは origin の main から切り、取れなければ止まる。--no-fetch で手元の main。番号は decision-number）と
    --auto の行（夜のまとめ実行は docs/guide/develop.md。コミットは言われるまでしない・無人の実行だけ例外は残る。D0073-AC-29）が新しい形になっている。"""
    check(help_problems(read_doc(HELP_SKILL)))


def test_D0074_AC_28_見本_検査は語が欠けた形を見つける_守る() -> None:
    """D0074-AC-28: 検査そのものの確かめ。そろった形は通り、--auto の行に指しが無い形・語が欠けた形を見つける。（今のまま通る。守る）"""
    good = (
        "| `/pipe-in <要件メモ>` | origin の main から切る（`--no-fetch` で手元の main）。番号は `pipe-in skill decision-number` |\n"
        "| `/pipe-in --auto <要件メモ>` | 夜のまとめ実行（night/）は docs/guide/develop.md。コミットは言われるまでしない（無人の実行だけ例外。CLAUDE.md） |\n"
    )
    assert help_problems(good) == []
    assert help_problems(good.replace("docs/guide/develop.md", "どこか"))
    assert help_problems(good.replace("--no-fetch", "旗"))


# ======== AC-29：decision_number.py の置き場所と依存の向き ====================================================================


def import_problems(source: str) -> list[str]:
    """pipe_in/dev/decision_number.py の import：標準ライブラリと pipe_in.dev の中（同じ層の相対 import か pipe_in.dev.…）だけ。
    pipe_in.pipe・pipe_in.engine・generator・ほかのパッケージは読まない（依存の向きを破らない）。"""
    problems: list[str] = []
    stdlib = sys.stdlib_module_names
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in stdlib:
                    problems.append(f"標準ライブラリでない import：{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1:
                continue  # 同じ層（pipe_in.dev）の中
            if node.level >= 2:
                problems.append(f"上の層への相対 import：{'.' * node.level}{module}")
            elif module.split(".")[0] not in stdlib and not (module == "pipe_in.dev" or module.startswith("pipe_in.dev.")):
                problems.append(f"標準ライブラリでも pipe_in.dev でもない import：{module}")
    return problems


def test_D0074_AC_29_decision_numberはpipe_in_devの中にあり依存の向きを破らない() -> None:
    """D0074-AC-29: pipe_in/dev/decision_number.py があり、import が標準ライブラリと pipe_in.dev の中だけ（pipe_in.pipe・pipe_in.engine・generator を読まない）。
    tests/test_rules.py・tests/test_architecture.py が通ることは、既存のテストが見る。"""
    if not DECISION_NUMBER.is_file():
        pytest.fail("pipe_in/dev/decision_number.py が無い（まだ作っていない）", pytrace=False)
    check(import_problems(DECISION_NUMBER.read_text(encoding="utf-8")))


def test_D0074_AC_29_見本_検査は依存の向きを破る_importを見つける_守る() -> None:
    """D0074-AC-29: 検査そのものの確かめ。標準ライブラリ・同じ層の相対 import は通り、pipe_in.pipe・pipe_in.engine・generator・上の層への相対 import は見つける。
    （今のまま通る。守る）"""
    ok = "from __future__ import annotations\nimport re\nimport subprocess\nfrom pathlib import Path\nfrom . import worktree\nfrom pipe_in.dev import worktree as w\n"
    assert import_problems(ok) == []
    assert import_problems("from pipe_in.pipe import x\n") == ["標準ライブラリでも pipe_in.dev でもない import：pipe_in.pipe"]
    assert import_problems("from pipe_in.engine import guard\n") == ["標準ライブラリでも pipe_in.dev でもない import：pipe_in.engine"]
    assert import_problems("import pipe_in_generator\n") == ["標準ライブラリでない import：pipe_in_generator"]
    assert import_problems("from ..engine import guard\n") == ["上の層への相対 import：..engine"]
