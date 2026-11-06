"""2体の共通部分（generator/quorum.py = pipe-in-gen quorum）の判断（D0076）。

指摘の形 v1（D0043）のファイル2つか3つから、location.source と location.section の組が合う指摘を残す。
LLM も SDK も呼ばない。ファイルは tmp_path の中だけに作る。
新しい部品（generator/quorum.py）はテストの中で読み込む（落ちる理由が「まだ無い」だと読めるように）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def q():
    from pipe_in_generator import quorum

    return quorum


def finding(n: int = 1, section: str = "2.1", source: str = "SRC-001", **override) -> dict:
    f = {
        "id": f"F-{n:03d}",
        "role": "quality",
        "location": {"source": source, "section": section, "quote": f"{section} の原文"},
        "kind": "ambiguous",
        "statement": f"{section} の説明が分からない。",
        "rationale": "決まっていない。",
        "sources": [source],
        "guess": False,
        "confidence": "high",
        "severity": "minor",
        "status": "open",
    }
    f.update(override)
    return f


def write_findings(path: Path, findings: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 1, "findings": findings}, ensure_ascii=False), encoding="utf-8")
    return path


def run_files(tmp_path: Path, *docs: list, threshold: float = 0.8, no_third: bool = False):
    """docs を a.json・b.json・c.json に書いて run を呼ぶ。(終了コード, 標準出力の行, 書いた指摘の一覧) を返す。"""
    paths = [write_findings(tmp_path / f"{'abc'[i]}.json", d) for i, d in enumerate(docs)]
    out = tmp_path / "out" / "common.json"
    code, lines = q().run(paths, out, threshold, no_third)
    written = json.loads(out.read_text(encoding="utf-8"))["findings"] if out.is_file() else None
    return code, lines, written


def sections(findings: list) -> list[str]:
    return [f["location"]["section"] for f in findings]


# ---- AC-01: 1つ目のうち、キーが2つ目にもあるものを残す -----------------------------------------------


def test_d0076_ac01_keeps_findings_whose_key_is_in_second(tmp_path):
    """D0076-AC-01: 1つ目の指摘のうち、source と section の組が2つ目にもあるものだけが残り、順は1つ目の中の順。2つ目にしかないものは入らない。"""
    a = [finding(1, "1.1"), finding(2, "1.2"), finding(3, "1.3"), finding(4, "1.4")]
    b = [finding(1, "1.4"), finding(2, "9.9"), finding(3, "1.2")]
    _, _, written = run_files(tmp_path, a, b)
    assert sections(written) == ["1.2", "1.4"]


def test_d0076_ac01_output_shape_and_renumbered_ids(tmp_path):
    """D0076-AC-01: 書かれたファイルは {"v": 1, "findings": [...]} で、id は F-001 から順に振り直される。"""
    a = [finding(7, "1.1"), finding(9, "1.2"), finding(12, "1.3")]
    b = [finding(1, "1.1"), finding(2, "1.3")]
    paths = [write_findings(tmp_path / "a.json", a), write_findings(tmp_path / "b.json", b)]
    out = tmp_path / "common.json"
    q().run(paths, out, 0.8, False)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert list(doc) == ["v", "findings"] and doc["v"] == 1
    assert [f["id"] for f in doc["findings"]] == ["F-001", "F-002"]
    assert sections(doc["findings"]) == ["1.1", "1.3"]


def test_d0076_ac01_other_fields_unchanged(tmp_path):
    """D0076-AC-01: id のほかの欄は入力のまま（欄が増えも減りも、値が変わりもしない）。"""
    a = [finding(5, "1.1", status="confirmed", links={"requirements": ["FR-01"], "acceptance": ["AC-01"]})]
    b = [finding(1, "1.1")]
    _, _, written = run_files(tmp_path, a, b)
    expected = dict(a[0], id="F-001")
    assert written == [expected]


# ---- AC-02: キーは normalize を通して比べる -------------------------------------------------------


@pytest.mark.parametrize(
    "first,second",
    [
        ("3.2 認証", "3.2認証"),  # 空白の有無
        ("3.2 認証", "３.２ 認証"),  # 全角数字
        ("3.2\n認証", "3.2 認証"),  # 改行
        ("3.2　認証", "3.2 認証"),  # 全角空白
        ("Section 3", "Ｓｅｃｔｉｏｎ　３"),  # 全角英数字
    ],
    ids=["no-space", "fullwidth-digits", "newline", "ideographic-space", "fullwidth-alnum"],
)
def test_d0076_ac02_key_is_normalized(tmp_path, first, second):
    """D0076-AC-02: 全角・半角、空白、改行の違いだけの節は同じとみなされ、残る。"""
    _, _, written = run_files(tmp_path, [finding(1, first)], [finding(1, second)])
    assert written is not None and len(written) == 1


def test_d0076_ac02_source_is_normalized_too(tmp_path):
    """D0076-AC-02: source も normalize を通して比べる（全角の SRC-001 と半角の SRC-001 は同じ）。"""
    _, _, written = run_files(tmp_path, [finding(1, "1.1", source="SRC-001")], [finding(1, "1.1", source="ＳＲＣ－００１")])
    assert written is not None and len(written) == 1


def test_d0076_ac02_different_section_not_kept(tmp_path):
    """D0076-AC-02: 節が違えば、kind も statement も同じでも残らない。source が違うときも残らない。"""
    same = dict(kind="missing", statement="同じ文")
    _, _, written = run_files(tmp_path, [finding(1, "1.1", **same)], [finding(1, "1.2", **same)])
    assert written == []
    _, _, written = run_files(tmp_path, [finding(1, "1.1", source="SRC-001", **same)], [finding(1, "1.1", source="SRC-002", **same)])
    assert written == []


def test_d0076_ac02_kind_and_quote_ignored(tmp_path):
    """D0076-AC-02: 節が同じなら、kind・statement・quote が違っても残る（1つ目の指摘がそのまま残る）。"""
    a = [finding(1, "1.1", kind="missing", statement="A の文")]
    a[0]["location"]["quote"] = "A の引用"
    b = [finding(1, "1.1", kind="risk", statement="B の文")]
    b[0]["location"]["quote"] = "B の引用"
    _, _, written = run_files(tmp_path, a, b)
    assert len(written) == 1
    assert written[0]["kind"] == "missing" and written[0]["location"]["quote"] == "A の引用"


# ---- AC-03: 3つのとき、2つ以上のファイルにあるキーを残す ---------------------------------------------


def test_d0076_ac03_three_files_keep_keys_in_two_or_more(tmp_path):
    """D0076-AC-03: 3つのとき、キーが2つ以上のファイルにある指摘が残る（どの2つの組でもよい）。残す順はファイルの順 → ファイルの中の順。"""
    a = [finding(1, "1.1"), finding(2, "1.2")]
    b = [finding(1, "1.2"), finding(2, "1.3")]
    c = [finding(1, "1.3"), finding(2, "1.1")]
    _, _, written = run_files(tmp_path, a, b, c)
    # 1.1 は a・c、1.2 は a・b、1.3 は b・c。最前のファイルの指摘を使うので a の 1.1, 1.2、次に b の 1.3
    assert sections(written) == ["1.1", "1.2", "1.3"]


def test_d0076_ac03_key_in_one_file_dropped(tmp_path):
    """D0076-AC-03: 1つのファイルにしかないキーは落ちる。"""
    a = [finding(1, "1.1"), finding(2, "only-a")]
    b = [finding(1, "1.1"), finding(2, "only-b")]
    c = [finding(1, "only-c")]
    _, _, written = run_files(tmp_path, a, b, c)
    assert sections(written) == ["1.1"]


def test_d0076_ac03_earliest_file_used(tmp_path):
    """D0076-AC-03: 同じキーが複数のファイルにあるときは、いちばん前のファイルの指摘を使う。"""
    a = [finding(1, "9.9"), finding(2, "other")]
    b = [finding(1, "1.1", statement="b の文")]
    c = [finding(1, "1.1", statement="c の文"), finding(2, "9.9", statement="c の 9.9")]
    _, _, written = run_files(tmp_path, a, b, c)
    by_section = {f["location"]["section"]: f["statement"] for f in written}
    assert by_section["1.1"] == "b の文"
    assert by_section["9.9"] != "c の 9.9"  # a の指摘を使う
    assert sections(written) == ["9.9", "1.1"]  # 残す順はファイルの順 → ファイルの中の順


def test_d0076_ac03_duplicate_key_in_one_file_counts_once(tmp_path):
    """D0076-AC-03: 同じキーが1つのファイルに複数あっても、そのファイルの1票。ほかのファイルに無ければ落ちる。"""
    a = [finding(1, "1.1"), finding(2, "1.1", statement="同じ節の2件目")]
    b = [finding(1, "x")]
    c = [finding(1, "y")]
    _, _, written = run_files(tmp_path, a, b, c)
    assert written == []


def test_d0076_ac03_duplicates_in_first_file_all_kept(tmp_path):
    """D0076-AC-01・03: 1つ目に同じ節の指摘が2件あり、2つ目にその節があれば、2件とも残る（ファイルの中の順）。"""
    a = [finding(1, "1.1", statement="一件目"), finding(2, "1.1", statement="二件目")]
    b = [finding(1, "1.1")]
    _, _, written = run_files(tmp_path, a, b)
    assert [f["statement"] for f in written] == ["一件目", "二件目"]
    assert [f["id"] for f in written] == ["F-001", "F-002"]


# ---- AC-04: 3体目が要るかの判定（Jaccard） ----------------------------------------------------------


def test_d0076_ac04_jaccard_values():
    """D0076-AC-04: Jaccard は 共通 ÷ 和。両方空なら 1.0。"""
    j = q().jaccard
    assert j({("a", "1"), ("a", "2")}, {("a", "2"), ("a", "3")}) == pytest.approx(1 / 3)
    assert j({("a", "1")}, {("a", "1")}) == 1.0
    assert j({("a", "1")}, {("a", "2")}) == 0.0
    assert j(set(), set()) == 1.0
    assert j(set(), {("a", "1")}) == 0.0


def keyed(*secs: str) -> list:
    return [finding(i + 1, s) for i, s in enumerate(secs)]


def test_d0076_ac04_jaccard_below_threshold_needs_third(tmp_path):
    """D0076-AC-04: 2つのとき、Jaccard が 0.8 未満（3/4 = 0.75）なら終了コード 3 で「3体目が要ります」。"""
    code, lines, written = run_files(tmp_path, keyed("1", "2", "3"), keyed("1", "2", "3", "4"))
    assert code == 3
    assert lines[-1].startswith("3体目が要ります")
    assert written is not None  # 書いてはある


def test_d0076_ac04_exactly_threshold_not_needed(tmp_path):
    """D0076-AC-04: ちょうど 0.8（4/5）は要らない。終了コード 0 で「3体目は要りません」。"""
    code, lines, _ = run_files(tmp_path, keyed("1", "2", "3", "4"), keyed("1", "2", "3", "4", "5"))
    assert code == 0
    assert lines[-1].startswith("3体目は要りません")


def test_d0076_ac04_threshold_option(tmp_path):
    """D0076-AC-04: --threshold 相当の引数で基準が変わる。0.8 では要らない 4/5 が、0.9 では要る。"""
    docs = (keyed("1", "2", "3", "4"), keyed("1", "2", "3", "4", "5"))
    code, lines, _ = run_files(tmp_path, *docs, threshold=0.9)
    assert code == 3 and lines[-1].startswith("3体目が要ります")


def test_d0076_ac04_both_empty_is_one_and_writes_empty(tmp_path):
    """D0076-AC-04: 両方とも指摘が 0 件なら Jaccard は 1.0（3体目は要りません）、残る指摘は 0 件で、ファイルは書く。"""
    code, lines, written = run_files(tmp_path, [], [])
    assert code == 0 and written == []
    assert lines[-1].startswith("3体目は要りません")
    assert "1.00" in "\n".join(lines)


def test_d0076_ac04_jaccard_uses_keys_not_findings(tmp_path):
    """D0076-AC-04: Jaccard は指摘の件数でなく、キーの集合で数える（同じ節の2件は1つのキー）。"""
    a = [finding(1, "1.1"), finding(2, "1.1"), finding(3, "1.2")]
    b = [finding(1, "1.1"), finding(2, "1.2")]
    code, _, _ = run_files(tmp_path, a, b)
    assert code == 0  # キーの集合は同じ（Jaccard 1.0）


# ---- 部品の確かめ ----------------------------------------------------------------------------------


def test_d0076_ac01_renumber_does_not_change_input():
    """D0076-AC-01: renumber は入力の指摘を書き換えず（コピーして）、F-001 から振り直す。"""
    src = [finding(5, "1.1"), finding(9, "1.2")]
    before = json.dumps(src, ensure_ascii=False)
    out = q().renumber(src)
    assert [f["id"] for f in out] == ["F-001", "F-002"]
    assert json.dumps(src, ensure_ascii=False) == before
