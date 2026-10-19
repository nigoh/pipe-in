"""調べた結果（docs/research/）の検査。D0018。

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
