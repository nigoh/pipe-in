"""pipe-in-gen quorum：引数・終了コード・入力の誤り・出力の形（D0076）。

generator/cli.py の main を通して呼ぶ（--project は取らない）。SDK は呼ばない。ファイルはすべて tmp_path の中に作る。
まだ quorum が無いときは cli が「知らないコマンド」で終わるので、終了コード 2 を期待するテストも、
標準エラーに quorum の入力の誤りの文（「quorum: 入力を受け取れません」）があることまで見る（別の理由の 2 で通らないように）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ERR_PREFIX = "quorum: 入力を受け取れません"
SPEC_TEXT = "# 貸出仕様\n\n## 2.1 冊数\n\n利用者は、本を最大5冊まで借りられる。\n\n## 2.2 期限\n\n返却期限は、貸出日から14日とする。\n"
QUOTE_1 = "利用者は、本を最大5冊まで借りられる。"
QUOTE_2 = "返却期限は、貸出日から14日とする。"


def finding(n: int = 1, section: str = "2.1", quote: str = QUOTE_1, source: str = "SRC-001", **override) -> dict:
    f = {
        "id": f"F-{n:03d}",
        "role": "quality",
        "location": {"source": source, "section": section, "quote": quote},
        "kind": "ambiguous",
        "statement": "冊数の数え方が分からない。",
        "rationale": "続き物の扱いが決まっていない。",
        "sources": [source],
        "guess": False,
        "confidence": "high",
        "severity": "minor",
        "status": "open",
    }
    f.update(override)
    return f


def write(path: Path, findings: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 1, "findings": findings}, ensure_ascii=False), encoding="utf-8")
    return path


def call(capsys, *argv):
    from pipe_in_generator import cli

    capsys.readouterr()
    try:
        code = cli.main(["quorum", *[str(a) for a in argv]])
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def last_line(out: str) -> str:
    return [ln for ln in out.splitlines() if ln.strip()][-1]


def two_files(tmp_path: Path, a: list, b: list):
    return write(tmp_path / "a.json", a), write(tmp_path / "b.json", b)


def secs(*names: str) -> list:
    return [finding(i + 1, s) for i, s in enumerate(names)]


# ---- AC-05: 終了コード --------------------------------------------------------------------------


def test_d0076_ac05_exit_codes_0_3_2(tmp_path, capsys):
    """D0076-AC-05: 書いて3体目が要らない＝0、書いて3体目が要る＝3、入力を受け取れない＝2。"""
    a, b = two_files(tmp_path, secs("1", "2", "3", "4"), secs("1", "2", "3", "4", "5"))
    code, out, _ = call(capsys, a, b, "--out", tmp_path / "ok.json")
    assert code == 0 and (tmp_path / "ok.json").is_file()
    assert last_line(out).startswith("3体目は要りません")

    a2, b2 = two_files(tmp_path, secs("1", "2", "3"), secs("1", "2", "3", "4"))
    code, out, _ = call(capsys, a2, b2, "--out", tmp_path / "third.json")
    assert code == 3 and (tmp_path / "third.json").is_file()
    assert last_line(out).startswith("3体目が要ります")

    code, _, err = call(capsys, tmp_path / "nope.json", b2, "--out", tmp_path / "none.json")
    assert code == 2 and ERR_PREFIX in err
    assert not (tmp_path / "none.json").exists()


def test_d0076_ac05_no_third_exits_0_and_last_line(tmp_path, capsys):
    """D0076-AC-05: --no-third のときは、3体目が要る場合も終了コード 0 で、最後の行が「3体目は流さず、共通部分だけを書きました」になり、節の一致の値が付く。"""
    a, b = two_files(tmp_path, secs("1", "2", "3"), secs("1", "2", "3", "4"))
    code, out, _ = call(capsys, a, b, "--no-third", "--out", tmp_path / "c.json")
    assert code == 0
    assert last_line(out).startswith("3体目は流さず、共通部分だけを書きました")
    assert "0.75" in last_line(out)
    assert "3体目が要ります" not in out


def test_d0076_ac05_no_third_when_not_needed_keeps_not_needed(tmp_path, capsys):
    """D0076-AC-05: --no-third でも、もともと要らないときは「3体目は要りません」のまま。"""
    a, b = two_files(tmp_path, secs("1", "2"), secs("1", "2"))
    code, out, _ = call(capsys, a, b, "--no-third", "--out", tmp_path / "c.json")
    assert code == 0 and last_line(out).startswith("3体目は要りません")


def test_d0076_ac05_three_files_exit_0(tmp_path, capsys):
    """D0076-AC-05: 3つ渡したときは判定せず、終了コード 0。最後の行は「3体目は要りません」で、使った体の数（3体）が出る。"""
    a = write(tmp_path / "a.json", secs("1", "2"))
    b = write(tmp_path / "b.json", secs("1", "9"))
    c = write(tmp_path / "c.json", secs("7", "8"))
    code, out, _ = call(capsys, a, b, c, "--out", tmp_path / "c3.json")
    assert code == 0
    assert last_line(out).startswith("3体目は要りません")
    assert "使った体は3体" in out
    doc = json.loads((tmp_path / "c3.json").read_text(encoding="utf-8"))
    assert [f["location"]["section"] for f in doc["findings"]] == ["1"]


def test_d0076_ac04_threshold_option_on_cli(tmp_path, capsys):
    """D0076-AC-04: --threshold 0.9 を付けると基準が変わる（4/5 = 0.8 は 0.9 では要る＝終了コード 3）。付けなければ 0。"""
    a, b = two_files(tmp_path, secs("1", "2", "3", "4"), secs("1", "2", "3", "4", "5"))
    code, _, _ = call(capsys, a, b, "--out", tmp_path / "x.json")
    assert code == 0
    code, out, _ = call(capsys, a, b, "--threshold", "0.9", "--out", tmp_path / "y.json")
    assert code == 3 and last_line(out).startswith("3体目が要ります")


# ---- AC-06: 標準出力 ----------------------------------------------------------------------------


def test_d0076_ac06_stdout_counts_and_jaccard(tmp_path, capsys):
    """D0076-AC-06: 標準出力に、残した件数・各体の件数・Jaccard（小数2けた）が出る。"""
    a, b = two_files(tmp_path, secs("1", "2", "3"), secs("1", "2", "3", "4"))
    code, out, _ = call(capsys, a, b, "--no-third", "--out", tmp_path / "c.json")
    assert code == 0
    assert re.search(r"共通部分\s*3\s*件", out), out
    assert re.search(r"3\s*件・\s*4\s*件", out), out
    assert "0.75" in out


def test_d0076_ac06_jaccard_has_two_decimals(tmp_path, capsys):
    """D0076-AC-06: Jaccard は小数2けた（2/3 は 0.67）。"""
    a, b = two_files(tmp_path, secs("1", "2"), secs("1", "2", "3"))
    _, out, _ = call(capsys, a, b, "--no-third", "--out", tmp_path / "c.json")
    assert "0.67" in out and "0.666" not in out


# ---- AC-07: 受け取れない入力 -------------------------------------------------------------------


def snapshot(root: Path) -> dict:
    """root の下の全部のファイルとフォルダ（ファイルは中身）。何も書かないことの確かめ用。"""
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None) for p in root.rglob("*")}


def bad_case(name: str, tmp_path: Path):
    """(argv の入力のファイル, 書かないことを確かめる --out) を返す。入力は tmp_path の中に作る。"""
    good = write(tmp_path / "good.json", secs("1", "2"))
    out = tmp_path / "out" / "common.json"
    raw = tmp_path / "raw.json"

    def doc(findings=None, **top):
        d = {"v": 1, "findings": findings if findings is not None else secs("1")}
        d.update(top)
        return d

    def put(obj) -> Path:
        raw.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return raw

    def bad_location(loc) -> Path:
        f = finding(1)
        f["location"] = loc
        return put(doc([f]))

    if name == "missing-file":
        return [good, tmp_path / "nope.json"], out
    if name == "not-json":
        raw.write_text("{ ここは JSON ではない", encoding="utf-8")
        return [good, raw], out
    if name == "not-utf8":
        raw.write_bytes(b"\x80\x81\x82")
        return [good, raw], out
    if name == "top-is-list":
        return [good, put([1, 2])], out
    if name == "no-v":
        return [good, put({"findings": []})], out
    if name == "v-is-2":
        return [good, put(doc(v=2))], out
    if name == "v-is-string":
        return [good, put(doc(v="1"))], out
    if name == "findings-not-list":
        return [good, put({"v": 1, "findings": {"a": 1}})], out
    if name == "source-not-string":
        f = finding(1)
        f["location"]["source"] = 1
        return [good, put(doc([f]))], out
    if name == "section-not-string":
        f = finding(1)
        f["location"]["section"] = None
        return [good, put(doc([f]))], out
    if name == "location-not-dict":
        return [good, bad_location("2.1")], out
    if name == "finding-not-dict":
        return [good, put(doc(["F-001"]))], out
    if name == "one-file":
        return [good], out
    if name == "four-files":
        files = [write(tmp_path / f"f{i}.json", secs("1")) for i in range(4)]
        return files, out
    if name == "out-is-input":
        other = write(tmp_path / "other.json", secs("1"))
        return [good, other], good  # --out が入力のどれかと同じ
    if name == "out-is-input-other-spelling":
        other = write(tmp_path / "other.json", secs("1"))
        sub = tmp_path / "sub"
        sub.mkdir()
        return [good, other], sub / ".." / "other.json"  # 同じファイルを別の書き方で指す
    raise AssertionError(name)


BAD_CASES = [
    "missing-file", "not-json", "not-utf8", "top-is-list", "no-v", "v-is-2", "v-is-string", "findings-not-list",
    "source-not-string", "section-not-string", "location-not-dict", "finding-not-dict", "one-file", "four-files",
    "out-is-input", "out-is-input-other-spelling",
]


@pytest.mark.parametrize("name", BAD_CASES)
def test_d0076_ac07_bad_input_exits_2_and_writes_nothing(tmp_path, capsys, name):
    """D0076-AC-07: 受け取れない入力は終了コード 2、理由を標準エラーに出し、何も書かない（入力も書き換えない）。"""
    inputs, out = bad_case(name, tmp_path)
    before = snapshot(tmp_path)
    code, stdout, err = call(capsys, *inputs, "--out", out)
    assert code == 2, (code, err)
    assert ERR_PREFIX in err
    assert stdout.strip() == ""
    assert snapshot(tmp_path) == before, "ファイルやフォルダが増えたか、入力が変わった"


def test_d0076_ac07_bom_allowed(tmp_path, capsys):
    """D0076-AC-07: BOM 付きの UTF-8 の入力は読める。"""
    a = tmp_path / "a.json"
    a.write_bytes(b"\xef\xbb\xbf" + json.dumps({"v": 1, "findings": secs("1")}, ensure_ascii=False).encode("utf-8"))
    b = write(tmp_path / "b.json", secs("1"))
    code, _, err = call(capsys, a, b, "--out", tmp_path / "c.json")
    assert code == 0, err
    assert len(json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))["findings"]) == 1


# ---- AC-08: 入力は書き換えず、--out だけを書く --------------------------------------------------


def test_d0076_ac08_inputs_untouched(tmp_path, capsys):
    """D0076-AC-08: 入力のファイルは書き換えない（バイト列が同じ）。tmp_path に増えるのは --out だけ。"""
    a, b = two_files(tmp_path, secs("1", "2"), secs("2", "3"))
    before = {a: a.read_bytes(), b: b.read_bytes()}
    names_before = {p.name for p in tmp_path.iterdir()}
    code, _, _ = call(capsys, a, b, "--out", tmp_path / "c.json")
    assert code in (0, 3)
    assert {a: a.read_bytes(), b: b.read_bytes()} == before
    assert {p.name for p in tmp_path.iterdir()} - names_before == {"c.json"}


def test_d0076_ac08_out_parent_created_utf8_no_bom_no_escape(tmp_path, capsys):
    """D0076-AC-08: --out の親のフォルダが無ければ作る。書いたファイルは UTF-8（BOM なし）で、日本語は \\u に直さない。"""
    a, b = two_files(tmp_path, [finding(1, "2.1", statement="冊数の数え方")], [finding(1, "2.1")])
    out = tmp_path / "deep" / "er" / "common.json"
    code, _, _ = call(capsys, a, b, "--out", out)
    assert code == 0
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "冊数の数え方" in text and "\\u" not in text


# ---- AC-09: findings-check に通る ------------------------------------------------------------------


def test_d0076_ac09_common_passes_findings_check(tmp_path, capsys):
    """D0076-AC-09: 元の入力が findings-check に通っていれば、共通部分のファイルも同じ台帳と仕様書で findings-check に通る（id は振り直し済み）。"""
    from pipe_in_generator import findings_check

    spec = tmp_path / "spec.md"
    spec.write_text(SPEC_TEXT, encoding="utf-8")
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            {"v": 1, "sources": [{"id": "SRC-001", "kind": "spec", "title": "貸出仕様", "version": "1.0", "where": "全体", "file": "spec.md"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    a = write(tmp_path / "a.json", [finding(1, "2.1", QUOTE_1), finding(2, "2.2", QUOTE_2)])
    b = write(tmp_path / "b.json", [finding(1, "2.2", QUOTE_2), finding(2, "2.1", QUOTE_1)])
    assert findings_check.run(a, sources, [spec])[0] == 0 and findings_check.run(b, sources, [spec])[0] == 0
    out = tmp_path / "common.json"
    code, _, err = call(capsys, a, b, "--out", out)
    assert code in (0, 3), err
    assert findings_check.run(out, sources, [spec])[0] == 0
    assert [f["id"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]] == ["F-001", "F-002"]


# ---- AC-16: 古い形 -------------------------------------------------------------------------------


def test_d0076_ac16_quorum_rejects_v2(tmp_path, capsys):
    """D0076-AC-16: 指摘の形 v1 は変えない。v が 1 でないファイルは quorum が終了コード 2（何も書かない）。"""
    a = write(tmp_path / "a.json", secs("1"))
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"v": 2, "findings": secs("1")}, ensure_ascii=False), encoding="utf-8")
    code, _, err = call(capsys, a, b, "--out", tmp_path / "c.json")
    assert code == 2 and ERR_PREFIX in err
    assert not (tmp_path / "c.json").exists()


def test_d0076_ac16_findings_check_still_rejects_v2(tmp_path, capsys):
    """D0076-AC-16: 今の作りのままで通る。守る。findings-check は v が 1 でないファイルを今までどおり終了コード 2 にする。"""
    from pipe_in_generator import cli

    f = tmp_path / "f.json"
    f.write_text(json.dumps({"v": 2, "findings": []}), encoding="utf-8")
    s = tmp_path / "s.json"
    s.write_text(json.dumps({"v": 1, "sources": []}), encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["findings-check", str(f), "--sources", str(s)]) == 2
    assert "findings-check: 入力を受け取れません" in capsys.readouterr().err
