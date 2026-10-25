"""pipe-in-gen findings-check：引数・終了コード・入力の誤り・出力の形（D0043）。

generator/cli.py の main を通して呼ぶ。SDK は呼ばない。ファイルはすべて tmp_path の中に作る。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SPEC_A = "利用者は、本を最大5冊まで借りられる。\nLibrary Card を提示する。\n"
SPEC_B = "返却期限は、貸出日から14日とする。\n"
QA = "利用者は、本を最大5冊まで借りられる。"
QB = "返却期限は、貸出日から14日とする。"
MISSING = object()


def finding(n: int = 1, quote: str = QA, source: str = "SRC-001", **override) -> dict:
    f = {
        "id": f"F-{n:03d}",
        "role": "quality",
        "location": {"source": source, "section": "2.1", "quote": quote},
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


def spec_entry(n: int = 1, file="spec.md") -> dict:
    e = {"id": f"SRC-{n:03d}", "kind": "spec", "title": "貸出仕様", "version": "1.0", "where": "全体"}
    if file is not MISSING:
        e["file"] = file
    return e


def write_case(tmp_path: Path, findings: list, sources: list, spec_text: str = SPEC_A, crlf: bool = False, spec_name: str = "spec.md"):
    """ファイルを書いて (指摘, 台帳, 仕様書) のパスを返す。crlf=True は仕様書を \\r\\n のバイト列で書く。"""
    f = tmp_path / "findings.json"
    s = tmp_path / "sources.json"
    sp = tmp_path / spec_name
    f.write_text(json.dumps({"v": 1, "findings": findings}, ensure_ascii=False), encoding="utf-8")
    s.write_text(json.dumps({"v": 1, "sources": sources}, ensure_ascii=False), encoding="utf-8")
    body = spec_text.replace("\n", "\r\n") if crlf else spec_text
    sp.write_bytes(body.encode("utf-8"))
    return f, s, sp


def call(capsys, *argv):
    from pipe_in_generator import cli

    try:
        code = cli.main(["findings-check", *[str(a) for a in argv]])
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def clean(tmp_path: Path, **kw):
    return write_case(tmp_path, [finding()], [spec_entry()], **kw)


# ---- AC-15: --spec と台帳の結び --------------------------------------------------------------


def test_multiple_spec_files_are_matched_by_name(tmp_path, capsys):
    """D0043-AC-15: --spec を複数回書け、台帳の file と同じ名前のものと結ばれて、引用が両方の本文と照らされる。"""
    (tmp_path / "a").mkdir()
    a = tmp_path / "a" / "a.md"
    b = tmp_path / "b.md"
    a.write_text(SPEC_A, encoding="utf-8")
    b.write_text(SPEC_B, encoding="utf-8")
    sources = [spec_entry(1, "a.md"), spec_entry(7, "b.md")]
    good = [finding(1, QA, "SRC-001"), finding(2, QB, "SRC-007")]
    f, s, _ = write_case(tmp_path, good, sources)
    code, out, err = call(capsys, f, "--sources", s, "--spec", a, "--spec", b)
    assert code == 0, out + err
    # 取り違えた引用（b の文を a の出典で引く）は落ちる = 名前で結んでいる
    swapped = [finding(1, QB, "SRC-001")]
    f2, s2, _ = write_case(tmp_path, swapped, sources)
    code, out, err = call(capsys, f2, "--sources", s2, "--spec", a, "--spec", b)
    assert code == 1, out + err
    assert "location.quote" in out


@pytest.mark.parametrize("case", ["no-matching-name", "duplicate-name", "no-spec-flag", "no-file-field", "slash-in-file"])
def test_spec_exit2_cases(tmp_path, capsys, case):
    """D0043-AC-15: 結べない spec の件・同じ名前が複数・--spec なし・file が無い・file に / がある、は理由に台帳の id を添えて終了コード 2。"""
    spec_args: list = []
    entry = spec_entry()
    other = tmp_path / "other.md"
    other.write_text(SPEC_A, encoding="utf-8")
    if case == "no-matching-name":
        spec_args = ["--spec", other]
    elif case == "duplicate-name":
        for d in ("x", "y"):
            (tmp_path / d).mkdir()
            (tmp_path / d / "spec.md").write_text(SPEC_A, encoding="utf-8")
        spec_args = ["--spec", tmp_path / "x" / "spec.md", "--spec", tmp_path / "y" / "spec.md"]
    elif case == "no-spec-flag":
        spec_args = []
    elif case == "no-file-field":
        entry = spec_entry(file=MISSING)
        spec_args = ["--spec", other]
    elif case == "slash-in-file":
        entry = spec_entry(file="sub/spec.md")
        spec_args = ["--spec", other]
    f, s, _ = write_case(tmp_path, [finding()], [entry])
    code, out, err = call(capsys, f, "--sources", s, *spec_args)
    assert code == 2, out + err
    assert "SRC-001" in err
    assert out == "" and "Traceback" not in err


def test_unused_spec_is_ignored(tmp_path, capsys):
    """D0043-AC-15: 使われない --spec は黙って許す（開きもしないので、存在しなくてもよい）。"""
    f, s, sp = clean(tmp_path)
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp, "--spec", tmp_path / "nowhere" / "unused.md")
    assert code == 0, out + err


def test_windows_style_spec_path_matches_by_name():
    """D0043-AC-15: Windows の書き方（C:\\tmp\\spec.md）の --spec も、名前だけで台帳の file と結べる。"""
    from pipe_in_generator import findings_check as fc

    got = fc.resolve_specs([spec_entry()], [("C:\\tmp\\spec.md", SPEC_A)])
    assert got == {"SRC-001": SPEC_A}


# ---- AC-16: 出力と終了コード -----------------------------------------------------------------


def test_clean_case_prints_no_errors_and_exits_0(tmp_path, capsys):
    """D0043-AC-16: 誤りの無い見本は、標準出力に「誤りなし」を出して終了コード 0。"""
    f, s, sp = clean(tmp_path)
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 0, out + err
    assert "誤りなし" in out


def three_errors(tmp_path):
    findings = [
        finding(1, kind="typo"),
        finding(2, severity="blocker"),
        finding(3, confidence="certain"),
    ]
    return write_case(tmp_path, findings, [spec_entry()])


def test_error_lines_have_three_parts_and_count(tmp_path, capsys):
    """D0043-AC-16: 誤り3件の見本は「<id>: <欄>: <理由>」の行が3つ、最後に「誤り 3 件」、終了コード 1。"""
    f, s, sp = three_errors(tmp_path)
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 1, out + err
    lines = out.splitlines()
    assert lines[-1] == "誤り 3 件", out
    body = lines[:-1]
    assert len(body) == 3, out
    pats = [r"F-001: kind: .+", r"F-002: severity: .+", r"F-003: confidence: .+"]
    for line, pat in zip(body, pats):
        assert re.fullmatch(pat, line), line


def test_output_is_deterministic(tmp_path, capsys):
    """D0043-AC-16: 同じ入力で2回流すと、出力の並びが同じ。"""
    f, s, sp = three_errors(tmp_path)
    first = call(capsys, f, "--sources", s, "--spec", sp)
    second = call(capsys, f, "--sources", s, "--spec", sp)
    assert first == second
    assert first[0] == 1


# ---- AC-17: 入力を受け取れない -----------------------------------------------------------------


def _break(case: str, f: Path, s: Path, sp: Path) -> None:
    if case == "findings-missing":
        f.unlink()
    elif case == "sources-missing":
        s.unlink()
    elif case == "findings-not-json":
        f.write_text("{ not json", encoding="utf-8")
    elif case == "sources-not-json":
        s.write_text("", encoding="utf-8")
    elif case == "findings-not-utf8":
        f.write_bytes(b'{"v": 1, "findings": ["\xff\xfe"]}')
    elif case == "findings-top-array":
        f.write_text("[]", encoding="utf-8")
    elif case == "sources-top-array":
        s.write_text("[]", encoding="utf-8")
    elif case == "spec-not-utf8":
        sp.write_bytes(b"\xff\xfe\x00bad")
    else:  # pragma: no cover
        raise AssertionError(case)


@pytest.mark.parametrize(
    "case",
    [
        "findings-missing",
        "sources-missing",
        "findings-not-json",
        "sources-not-json",
        "findings-not-utf8",
        "findings-top-array",
        "sources-top-array",
        "spec-not-utf8",
    ],
)
def test_unreadable_input_exits_2(tmp_path, capsys, case):
    """D0043-AC-17: ファイルが無い・JSON でない・UTF-8 でない・一番上が辞書でない・仕様書が読めない、は終了コード 2。理由を標準エラーに出し、例外の記録は出さない。"""
    f, s, sp = clean(tmp_path)
    _break(case, f, s, sp)
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 2, out + err
    assert "入力を受け取れません" in err
    assert "Traceback" not in err
    assert out == ""


def test_bom_is_allowed(tmp_path, capsys):
    """D0043-AC-17: UTF-8 の BOM つきの指摘・台帳・仕様書は通る。"""
    f, s, sp = clean(tmp_path)
    for p in (f, s, sp):
        p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 0, out + err


def test_missing_argument_exits_2(tmp_path, capsys):
    """D0043-AC-17: 引数が足りない（--sources なし）と、終了コード 2（argparse の誤り）で、足りない引数の名前が出る。"""
    f, _, sp = clean(tmp_path)
    code, out, err = call(capsys, f, "--spec", sp)
    assert code == 2
    assert "--sources" in err


# ---- AC-18: 版 --------------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["findings", "sources"])
@pytest.mark.parametrize("value", [MISSING, 2, "1", True, None, 1.0])
def test_unknown_version_exits_2(tmp_path, capsys, which, value):
    """D0043-AC-18: v が無い・2・"1"・true・null・1.0 のファイル（指摘も台帳も）は、版が分かりませんで終了コード 2。"""
    f, s, sp = clean(tmp_path)
    path = f if which == "findings" else s
    doc = json.loads(path.read_text(encoding="utf-8"))
    if value is MISSING:
        doc.pop("v")
    else:
        doc["v"] = value
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 2, out + err
    assert "版が分かりません" in err
    assert "Traceback" not in err


# ---- AC-08（実機に近い形） ----------------------------------------------------------------------


def test_crlf_spec_file_passes_through_cli(tmp_path, capsys):
    """D0043-AC-08: 仕様書を CRLF のバイト列で保存し、引用の空白を全角にしても、CLI は終了コード 0。"""
    f, s, sp = write_case(
        tmp_path,
        [finding(1, quote="Library\u3000Card\u3000を提示する。")],
        [spec_entry()],
        crlf=True,
    )
    assert b"\r\n" in sp.read_bytes()
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 0, out + err


# ---- AC-20・22: SDK を呼ばない・呼び分け ---------------------------------------------------------


def test_findings_check_does_not_import_sdk(tmp_path, capsys):
    """D0043-AC-20: findings-check を流しても SDK が読み込まれない（流して成功した上で sys.modules を見る）。"""
    before = "claude_agent_sdk" in sys.modules
    f, s, sp = clean(tmp_path)
    code, out, err = call(capsys, f, "--sources", s, "--spec", sp)
    assert code == 0, out + err
    assert before or "claude_agent_sdk" not in sys.modules


def test_cases_write_only_under_tmp_path(tmp_path):
    """D0043-AC-20: 見本のファイルはすべて tmp_path の中に作る（リポジトリの実物には書かない）。"""
    paths = clean(tmp_path)
    for p in paths:
        assert tmp_path in p.resolve().parents


def test_cli_dispatches_findings_check(tmp_path, capsys):
    """D0043-AC-22: pipe-in-gen findings-check は、--project の検めを経ずに findings_check.main へ渡り、終了コードを返す。"""
    from pipe_in_generator import cli

    f, s, sp = clean(tmp_path)
    code = cli.main(["findings-check", str(f), "--sources", str(s), "--spec", str(sp)])
    assert code == 0
    assert "誤りなし" in capsys.readouterr().out


def test_help_lists_findings_check(capsys):
    """D0043-AC-22: pipe-in-gen --help の一覧に findings-check がある（古い pipe-in-gen と見分けられる）。"""
    from pipe_in_generator import cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "findings-check" in capsys.readouterr().out
