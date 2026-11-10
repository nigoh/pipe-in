"""D0078-AC-58：作業台から流せるようになったので、「拡張は子プロセスを起こさない・流さない」と言い切っていた文書を、
決めた形（決まった形の pipe-in 1つだけ・絶対パス・依頼メモは引数）に直してあることを確かめる。

文書の文は細かい言い回しで縛らず、決めた語が出ることと、古い言い切りが消えたことを見る。
読むだけで、ファイルは書かない。置き場所の表の実在・行の長さ・日英の見出しの数は、既存の test_rules.py・test_doc_shape.py・test_english_docs.py が見る（守る）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def head(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[:lines])


def section(text: str, heading: str) -> str | None:
    """`## 見出し` から次の `## ` の前まで。見出しが無ければ None。"""
    m = re.search(rf"^## {re.escape(heading)}\s*$", text, flags=re.M)
    if m is None:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, flags=re.M)
    return rest[: nxt.start()] if nxt else rest


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[。\n]", text) if s.strip()]


def has_sentence_with(text: str, *words: str) -> bool:
    return any(all(w in s for w in words) for s in sentences(text))


# ---- 検査そのもの：文の探し方が、合う文を見つけ、合わない文を見逃す ----------------------------


def test_ac58_checker_finds_a_sentence_with_all_the_words():
    """D0078-AC-58: 検査そのもの：語がそろった文は見つけ、語が別々の文に散っているときは見つけない。"""
    assert has_sentence_with("開発フローは作業台から流せません。端末で貼ります。", "開発フロー", "作業台", "流せ")
    assert has_sentence_with("開発フローです。作業台から流せます。開発フローは作業台からは流せません。", "開発フロー", "作業台", "流せ")
    assert not has_sentence_with("開発フローです。\n作業台です。\n流せます。", "開発フロー", "作業台", "流せ")


def test_ac58_checker_reads_a_section_up_to_the_next_heading():
    """D0078-AC-58: 検査そのもの：節は次の `## ` の前まで。見出しが無ければ None。"""
    text = "## 一\nあ\n## 二\nい\n"
    assert section(text, "一") == "\nあ\n"
    assert section(text, "二") == "\nい\n"
    assert section(text, "三") is None


# ---- vscode/README.md・docs/guide/vscode.md ----------------------------------------------------


@pytest.mark.parametrize("rel", ["vscode/README.md", "docs/guide/vscode.md"])
def test_ac58_vscode_docs_mention_the_setting_and_run(rel):
    """D0078-AC-58: vscode/README.md と docs/guide/vscode.md に、設定 pipe-in.command と「流す」が出る。"""
    text = read(rel)
    assert "pipe-in.command" in text
    assert "「流す」" in text or "『流す』" in text


def test_ac58_vscode_readme_head_names_the_one_exception():
    """D0078-AC-58: vscode/README.md の冒頭は、起こすのが作業台の「流す」の決まった形の pipe-in 1つだけで、実行ファイルは絶対パス・信頼していない場所では動かない、と言う。"""
    top = head(read("vscode/README.md"), 14)
    for word in ("流す", "絶対パス", "信頼"):
        assert word in top, word
    assert "も、読むだけ（子プロセスは起こさない）。" not in top, "別の worktree の文の言い切りが、例外の断りなしに残っている"


def test_ac58_vscode_readme_has_a_run_subsection_under_the_workbench():
    """D0078-AC-58: vscode/README.md の「パイプ作業台」の節に、「流す」の小節（依頼メモ・起こすコマンドの形・流せない理由・実行中）がある。"""
    text = read("vscode/README.md")
    m = re.search(r"^#{2,4} .*流す.*$", text, flags=re.M)
    assert m is not None, "「流す」の見出しが無い"
    body = text[m.end() : m.end() + 3000]
    for word in ("依頼メモ", "実行中"):
        assert word in body, word


def test_ac58_vscode_readme_settings_table_lists_the_command_setting():
    """D0078-AC-58: vscode/README.md の設定の表に pipe-in.command の行があり、絶対パス・ワークスペースの設定が効かない旨が書いてある。"""
    rows = [line for line in read("vscode/README.md").splitlines() if line.startswith("|") and "pipe-in.command" in line]
    assert rows, "設定の表に pipe-in.command の行が無い"
    assert "絶対パス" in rows[0]


def test_ac58_guide_vscode_no_longer_says_there_is_no_run_button():
    """D0078-AC-58: docs/guide/vscode.md に「作業台に『流す』ボタンはありません」と言い切った文が残っていない。"""
    text = read("docs/guide/vscode.md")
    assert "ボタンはありません（流すのは CLI です）" not in text


def test_ac58_guide_vscode_head_mentions_run():
    """D0078-AC-58: docs/guide/vscode.md の冒頭の「記録には何も書きません」の近くに、流す機能の1文がある。"""
    top = head(read("docs/guide/vscode.md"), 16)
    assert "「流す」" in top or "『流す』" in top


def test_ac58_guide_vscode_has_a_run_subsection_with_trust():
    """D0078-AC-58: docs/guide/vscode.md の「パイプ作業台」の節に「流す」の小節があり、設定 pipe-in.command と信頼の扱いが書いてある。"""
    text = read("docs/guide/vscode.md")
    m = re.search(r"^#{2,4} .*流す.*$", text, flags=re.M)
    assert m is not None, "「流す」の見出しが無い"
    body = text[m.end() : m.end() + 3000]
    assert "pipe-in.command" in body
    assert "信頼" in body


# ---- docs/guide/safety.md ------------------------------------------------------------------------


SAFETY_HEADING = "VSCode の拡張から流すときの守り"


def test_ac58_safety_has_the_new_section_between_the_two_neighbours():
    """D0078-AC-58: docs/guide/safety.md に節「VSCode の拡張から流すときの守り」が、「会話の中で流すときの守り」の次、「アーティファクトに送る写し」の前にある。"""
    text = read("docs/guide/safety.md")
    order = [text.find(f"## {h}") for h in ("会話の中で流すときの守り", SAFETY_HEADING, "アーティファクトに送る写し")]
    assert all(i != -1 for i in order), order
    assert order == sorted(order)


@pytest.mark.parametrize("word", ["絶対パス", "決まった形", "依頼メモ", "ユーザーの設定", "信頼していないワークスペース", "シェルを通さ", "D0078-run-from-editor.md"])
def test_ac58_safety_section_names_the_guards(word):
    """D0078-AC-58: 節に、絶対パス・決まった形の引数・依頼メモだけ・ユーザーの設定だけ・信頼していないワークスペース・シェルを通さないの語と、決定の記録への案内が出る。"""
    body = section(read("docs/guide/safety.md"), SAFETY_HEADING)
    assert body is not None, "節が無い"
    assert word in body


# ---- README.md・README.en.md ---------------------------------------------------------------------


def test_ac58_readme_has_the_one_sentence_after_the_workbench_sentence():
    """D0078-AC-58: README.md の「パイプ作業台を開く」の文の次に、「保存したパイプは、作業台の「流す」から流せます。」がある。"""
    text = read("README.md")
    anchor = "「pipe-in: パイプ作業台を開く」では、パイプを組み立てる作業台が開きます。"
    sentence = "保存したパイプは、作業台の「流す」から流せます。"
    assert anchor in text
    assert sentence in text
    assert text.index(anchor) < text.index(sentence) < text.index(anchor) + len(anchor) + 200


def test_ac58_readme_en_has_the_one_sentence_after_the_workbench_sentence():
    """D0078-AC-58: README.en.md の workbench の文の次に、"A saved pipe can be run from the "流す" (Run) section of the workbench." がある。"""
    text = read("README.en.md")
    anchor = '"pipe-in: パイプ作業台を開く" (open the pipe workbench) opens the workbench where you build pipes.'
    sentence = 'A saved pipe can be run from the "流す" (Run) section of the workbench.'
    assert anchor in text
    assert sentence in text
    assert text.index(anchor) < text.index(sentence) < text.index(anchor) + len(anchor) + 200


# ---- 手順「流す」・コマンドを打たない人向けの案内 ---------------------------------------------------


def test_ac58_walkthrough_run_step_no_longer_says_the_extension_does_not_run():
    """D0078-AC-58: vscode/walkthrough/03-run.md から「拡張は流しません」が消え、作業台の「流す」から流せる旨と、開発フローは作業台から流せない旨がある。見本の1行は残る。"""
    text = read("vscode/walkthrough/03-run.md")
    assert "拡張は流しません" not in text
    assert "流す" in text and "作業台" in text
    assert has_sentence_with(text, "開発フロー", "作業台", "流せ")
    assert "pipe-in --project" in text


def test_ac58_walkthrough_run_step_sample_line_is_kept_in_a_code_block():
    """D0078-AC-58: 03-run.md の見本の1行 pipe-in --project … --text … は、コードの塊のまま残る（開発フローの形）。"""
    text = read("vscode/walkthrough/03-run.md")
    assert re.search(r"```bash\n[^`]*pipe-in --project [^\n]* --text [^\n]*\n```", text)


def test_ac58_package_json_run_step_description_matches_the_walkthrough():
    """D0078-AC-58: vscode/package.json の手順「流す」の説明が「端末で1行を貼って流します。」だけでなくなっている（作業台の「流す」にも触れる）。"""
    manifest = json.loads(read("vscode/package.json"))
    steps = {s["id"]: s for s in manifest["contributes"]["walkthroughs"][0]["steps"]}
    description = steps["pipe-in.run"]["description"]
    assert "作業台" in description and "流す" in description


def test_ac58_start_without_commands_no_longer_says_the_extension_cannot_run():
    """D0078-AC-58: docs/guide/start-without-commands.md から「流す機能を持たない」「拡張が子プロセスを起こさない決まりです」が消え、保存したパイプは作業台から流せる旨がある。"""
    text = read("docs/guide/start-without-commands.md")
    assert "流す機能を持たない" not in text
    assert "拡張が子プロセスを起こさない決まりです" not in text
    assert has_sentence_with(text, "作業台", "流す", "保存")


def test_ac58_start_without_commands_keeps_the_dev_flow_line_and_says_what_it_is():
    """D0078-AC-58: 同じ文書に、開発フローは作業台から流せない旨と、見本の1行 pipe-in --project … --text … が残っている。"""
    text = read("docs/guide/start-without-commands.md")
    assert has_sentence_with(text, "開発フロー", "作業台", "流せ")
    assert re.search(r"^pipe-in --project ~/src/myapp --text ", text, flags=re.M)
