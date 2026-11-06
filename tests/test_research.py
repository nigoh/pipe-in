"""調べた結果（docs/research/）の検査。D0018。D0053（harness-compare の中身と目次の行）も見る。

- 目次 docs/research/README.md が、すべての調査のフォルダを指す
- eval と審査の比較（docs/research/eval-vs-judge/）の本文に決めた節があり、集計の結果と数が合う
- 実験の eval（evalcheck.py）が、決まりの違反を数えて見つける（SDK は呼ばない）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research"
EVJ = RESEARCH / "eval-vs-judge"


def test_d0018_ac01_index_links_every_study():
    """D0018-AC-01: 目次があり、docs/research/ の下のフォルダをすべて表から指す。"""
    index = RESEARCH / "README.md"
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    dirs = sorted(p.name for p in RESEARCH.iterdir() if p.is_dir() and not p.name.startswith((".", "__")))
    assert dirs, "調査のフォルダが無い"
    linked = set(re.findall(r"\]\(([a-z0-9-]+)/(?:README\.md)?\)", text))
    assert [d for d in dirs if d not in linked] == []


def test_d0018_ac02_study_has_sections():
    """D0018-AC-02: 本文に、問い・結論・方法・結果・限界・pipe-in への示唆・やり直し方の節がある。"""
    text = (EVJ / "README.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", text, re.M)
    for want in ["問い", "結論", "方法", "結果", "限界", "pipe-in への示唆", "やり直し方"]:
        assert any(h.startswith(want) for h in heads), want


def test_d0018_ac03_summary_matches_design():
    """D0018-AC-03: 集計の結果は 4条件×50本＝200試行で、本文の合格の数と同じ。"""
    s = json.loads((EVJ / "summary.json").read_text(encoding="utf-8"))
    assert s["n_total"] == 200
    assert {c: v["n"] for c, v in s["conds"].items()} == {"A": 50, "B": 50, "C": 50, "D": 50}
    text = (EVJ / "README.md").read_text(encoding="utf-8")
    for c in "ABCD":
        assert f"{s['conds'][c]['eval_pass']}/50" in text, c


@pytest.fixture()
def evalcheck():
    sys.path.insert(0, str(EVJ))
    try:
        import evalcheck as mod  # noqa: PLC0415  （docs の下の実験のスクリプト）
        yield mod
    finally:
        sys.path.remove(str(EVJ))
        for name in ["evalcheck", "topics"]:
            sys.modules.pop(name, None)


GOOD = (
    "pipe-inは要件メモから要件定義と設計とテスト先行を経て検証まで流す道具だ。"
    "検証で不合格なら実装へ差し戻し、既定で最大3回まで実装を自動でやり直させる仕組みだ。"
    "段ごとに書ける範囲を決め、進み具合と使用量はVSCodeで図にして見られる。"
)


def test_d0018_ac04_eval_counts_rules(evalcheck):
    """D0018-AC-04: 決まりを守った文は全部合格し、「の」・字数・数字・英字の違反はそれぞれ見つかる。"""
    ok = evalcheck.run_eval("pipein", GOOD, "nono")
    assert ok["all_ok"], [c for c in ok["checks"] if not c["ok"]]

    def failed(text):
        r = evalcheck.run_eval("pipein", text, "nono")
        return {c["check"] for c in r["checks"] if not c["ok"]}

    assert "「の」を使わない" in failed(GOOD.replace("流す道具だ", "流すための道具だ"))
    assert any(k.startswith("文字数") for k in failed(GOOD.replace("既定で", "")))
    assert any(k.startswith("数字") for k in failed(GOOD.replace("最大3回", "最大4回")))
    assert any(k.startswith("英字") for k in failed(GOOD.replace("VSCodeで", "VSCodeやWebで")))


# ---- D0053: 段の組み方（ハーネス）の比較（docs/research/harness-compare/） ----

HARNESS = RESEARCH / "harness-compare"
STUDY_SECTIONS = ["問い", "結論", "方法", "結果", "限界", "pipe-in への示唆", "やり直し方"]
# 今あるフォルダに、この機能で足す harness-compare を加える（まだ無くても、無いことで赤になるように）
STUDIES = sorted({p.name for p in RESEARCH.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))} | {"harness-compare"})


@pytest.mark.parametrize("study", STUDIES)
def test_d0053_ac21_every_study_has_sections(study):
    """D0053-AC-21: docs/research/ の下のどの調査の本文（README.md）にも、問い・結論・方法・結果・限界・pipe-in への示唆・やり直し方の節がある。"""
    path = RESEARCH / study / "README.md"
    assert path.is_file(), f"{study}/README.md が無い"
    heads = re.findall(r"^## (.+)$", path.read_text(encoding="utf-8"), re.M)
    missing = [w for w in STUDY_SECTIONS if not any(h.startswith(w) for h in heads)]
    assert missing == []


def _harness_text() -> str:
    path = HARNESS / "README.md"
    assert path.is_file(), "docs/research/harness-compare/README.md が無い"
    return path.read_text(encoding="utf-8")


# （pytest の id, 探す言葉）。実験のあらまし・重ねがけの比べ方の基準・スクリプトが外にあること
D0053_HARNESS_FACTS = [
    ("haiku", "Haiku"),
    ("tasks-20-30", "20〜30"),
    ("holm", "Holm"),
    ("vote-5-runs", "同じ課題を5回解かせ"),
    ("vote-4-or-more", "4回以上出た指摘を残す"),
    ("outside", "pipe-in の外"),
]


@pytest.mark.parametrize("word", [w for _, w in D0053_HARNESS_FACTS], ids=[i for i, _ in D0053_HARNESS_FACTS])
def test_d0053_ac21_harness_compare_facts(word):
    """D0053-AC-21: 比較実験の本文に、実験のあらまし（Haiku・20〜30 課題・Holm の補正）、重ねがけの比べ方の基準（同じ課題を5回解かせ、4回以上出た指摘を残す）、
    実験のスクリプトが pipe-in の外にあることが書いてある。"""
    assert word in _harness_text()


def test_d0053_ac21_harness_compare_marks_unbuilt():
    """D0053-AC-21・D0076-AC-17: 比較実験の本文で、6（複数の実装）と 8（教訓のメモ）について「仕組みが無い」と書いてある（2回以上）。
    結論 4（票）は D0076 で 2体の共通部分の仕組みができたので、4 の行には「仕組みが無い」がなく、6・8 の行にある。"""
    text = _harness_text()
    assert text.count("仕組みが無い") >= 2
    lines = text.splitlines()
    conclusion = {m.group(1): ln for ln in lines if (m := re.match(r"^(\d+)\. ", ln))}
    assert "仕組みが無い" not in conclusion["4"], "結論 4 に「仕組みが無い」が残っている"
    assert "仕組みが無い" in conclusion["6"] and "仕組みが無い" in conclusion["8"]


def test_d0053_ac21_index_row_for_harness_compare():
    """D0053-AC-21: 目次 docs/research/README.md の表に harness-compare の行があり、日付は「2026年10月」（実験を行った月）。"""
    rows = [line for line in (RESEARCH / "README.md").read_text(encoding="utf-8").splitlines() if "](harness-compare/README.md)" in line]
    assert len(rows) == 1, "目次の表に harness-compare/README.md を指す行が無い"
    assert "2026年10月" in rows[0]


# ---- D0076: 比較実験の続き（R7〜R14）と 2体の共通部分 ----

# （pytest の id, R7〜R14 の節に入っているべき文字）。AC-15 の数字。表記は要件定義のまま（マイナスは U+2212）
D0076_R_NUMBERS = [
    ("f1-diff-60", "+0.003 [−0.008, +0.015]"),
    ("cost-69-80", "69〜80%"),
    ("vs-single", "+0.087 [+0.069, +0.106]"),
    ("wins", "47勝2敗"),
    ("sonnet-common", "−0.019 [−0.036, −0.001]"),
    ("haiku2-vs-sonnet1-diff", "0.009"),
    ("haiku2-vs-sonnet1-range", "−0.027〜+0.007"),
    ("haiku2-vs-sonnet1-cost", "22%"),
    ("varied-readings", "−0.021 [−0.040, −0.006]"),
    ("arbitration-2-3x", "2.3 倍"),
    ("citation-stop-all-20", "20 課題すべて"),
    ("r7-single-f1", "0.996"),
    ("r10-impl", "0.941 → 0.991"),
    ("r10-saving", "17%"),
    ("r12-diff", "+0.064"),
    ("r12-holm", "p=0.043"),
]


def _r_section(text: str) -> str:
    """見出し（# で始まる行）に「R7」を含む節の本文。次の同じか上の階層の見出しの手前まで。無ければ空。"""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(#+) .*R7", ln)
        if m:
            level = len(m.group(1))
            body = []
            for nxt in lines[i + 1 :]:
                h = re.match(r"^(#+) ", nxt)
                if h and len(h.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return ""


def test_d0076_ac15_has_r7_to_r14_section():
    """D0076-AC-15: 調査の本文の見出しに R7〜R14 の節があり、R7 と R14 の両方の名前が出る。"""
    text = _harness_text()
    heads = [ln for ln in text.splitlines() if ln.startswith("#")]
    assert any("R7" in h and "R14" in h for h in heads), f"R7〜R14 の節の見出しが無い: {heads}"
    assert _r_section(text), "R7〜R14 の節の本文が空"


@pytest.mark.parametrize("word", [w for _, w in D0076_R_NUMBERS], ids=[i for i, _ in D0076_R_NUMBERS])
def test_d0076_ac15_r7_to_r14_numbers(word):
    """D0076-AC-15: R7〜R14 の節に、60 課題での F1 の差・費用・1体との差・Sonnet の共通部分・Haiku 2体と Sonnet 1体・読み方を変えた2体・裁定・引用照合で止める型・R7・R10・R12 の数字がそろっている。"""
    section = _r_section(_harness_text())
    assert section, "R7〜R14 の節が無い"
    found = word in section  # 節の本文を assert の失敗の表示に出さない
    assert found, f"R7〜R14 の節に {word} が無い"


# （pytest の id, 本文のどこかに入っているべき言葉）
D0076_LIMIT_WORDS = [
    ("post-hoc", "事後の解析"),
    ("haiku-centered", "Haiku 中心"),
    ("generator-tasks", "生成器の課題"),
    ("few-third", "3体目まで流れたのは数本"),
    ("no-impl-mechanism", "複数案を並べる仕組みは無い"),
]


@pytest.mark.parametrize("word", [w for _, w in D0076_LIMIT_WORDS], ids=[i for i, _ in D0076_LIMIT_WORDS])
def test_d0076_ac15_limits_and_no_mechanism_note(word):
    """D0076-AC-15: 本文に「60 課題をまとめたのは事後の解析」「Haiku 中心」「生成器の課題」「3体目まで流れたのは数本」と、実装の複数案を並べる仕組みは無く調査に書くだけ、がある。"""
    found = word in _harness_text()
    assert found, f"本文に {word} が無い"


def test_d0076_ac15_conclusion_4_points_to_quorum():
    """D0076-AC-15・FR-10: 結論 4 が、2体の共通部分を pipe-in-gen quorum で足したことと、票を数える型を置き換えることを書いている。"""
    text = _harness_text()
    conclusion4 = next((ln for ln in text.splitlines() if ln.startswith("4. ")), "")
    assert "pipe-in-gen quorum" in conclusion4 and "2体の共通部分" in conclusion4
    assert "置き換え" in conclusion4
