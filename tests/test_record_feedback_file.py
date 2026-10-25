"""D0039：`pipe-in record review <段> revise --feedback-file FILE`。

直してほしい点（外から来た文字）を、シェルのコマンド行に入れずに記録へ渡すための口。--feedback と同時には使えず、
ファイルは通常のファイルだけ、16384 バイトまで（超えたら断る）、UTF-8 で読む。断るときは記録を変えない。
既存の --feedback の動きは変えない。SDK は呼ばない。記録は tmp_path の中に作る。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import live_support as ls
from pipe_in import cli
from pipe_in.dev import record

LIMIT = 16384
OK_LINE = "記録しました: review（docs/pipeline/state.json）"


def project(tmp_path: Path, name: str = "p", stage: str = "requirements") -> Path:
    root = tmp_path / name
    root.mkdir()
    ls.pending_project(root, stage)
    return root


def state_bytes(root: Path) -> bytes:
    return (root / "docs" / "pipeline" / "state.json").read_bytes()


def state_of(root: Path) -> dict:
    return json.loads(state_bytes(root).decode("utf-8"))


def review_argv(root: Path, result: str, *extra: str, stage: str = "requirements") -> list[str]:
    return ["review", stage, result, "--project", str(root), *extra]


def run(argv: list[str]) -> int:
    return record.main(argv)


def refuses(argv, root: Path, capsys, *, code=None):
    """記録が変わらず、SystemExit で断ること。(SystemExit の code) を返す。"""
    before = state_bytes(root)
    with pytest.raises(SystemExit) as e:
        run(argv)
    assert state_bytes(root) == before, "断ったのに記録が変わった"
    capsys.readouterr()
    if code is not None:
        assert e.value.code == code
    return e.value.code


def write(path: Path, data: bytes | str) -> Path:
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


# ---- 引数の形 --------------------------------------------------------------------------------------------


def test_d0039_ac30_parser_is_built_by_a_function_and_parse_uses_it():
    """D0039-AC-30: 引数の読み取りは _build_parser()（ArgumentParser を返す）と _parse(argv)（それで読むだけ）に分かれる。AC-45 のテストが引数の一覧を取る。"""
    parser = record._build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    argv = ["review", "requirements", "revise", "--feedback-file", "x.txt", "--project", "p"]
    assert record._parse(argv) == parser.parse_args(argv)


def test_d0039_ac30_review_options_include_feedback_file_and_default_feedback_is_none():
    """D0039-AC-30: review の引数に --feedback-file が増え、--feedback の既定は None（同時指定を見分けるため）。ほかの引数の名前は変わらない。"""
    parser = record._build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices["review"]
    options = {o for a in sub._actions for o in a.option_strings}
    assert {"--feedback", "--feedback-file", "--project", "--config"} <= options
    args = record._build_parser().parse_args(["review", "design", "revise"])
    assert args.feedback is None and args.feedback_file is None
    args = record._build_parser().parse_args(["review", "design", "revise", "--feedback-file", "f.txt"])
    assert str(args.feedback_file) == "f.txt" and args.feedback is None
    args = record._build_parser().parse_args(["review", "design", "revise", "--feedback", "x"])
    assert args.feedback == "x" and args.feedback_file is None


def test_d0039_ac30_other_subcommands_are_unchanged_by_the_split():
    """D0039-AC-30: _parse の分け方で、ほかのコマンド（start・begin・done・wait・red・verdict・finish）の引数の読み方は変わらない。今のままで通る（守り続ける検査）。"""
    args = record._parse(["begin", "design", "--attempt", "2", "--note", "n", "--agent", "a"])
    assert (args.action, args.stage, args.attempt, args.note, args.agent) == ("begin", "design", 2, "n", "a")
    args = record._parse(["start", "--text", "memo", "--name", "N"])
    assert (args.action, args.text, args.name) == ("start", "memo", "N")
    args = record._parse(["red", "red", "--summary", "s", "--test", "AC-01=t", "--command", "c"])
    assert (args.status, args.summary, args.test, args.command) == ("red", "s", ["AC-01=t"], ["c"])
    args = record._parse(["verdict", "pass", "--attempt", "1", "--summary", "s"])
    assert (args.status, args.attempt) == ("pass", 1)
    assert record._parse(["finish", "PASSED"]).final == "PASSED"
    with pytest.raises(SystemExit) as e:
        record._parse(["review", "design"])
    assert e.value.code == 2


# ---- 通る ----------------------------------------------------------------------------------------------------


FEEDBACKS = [
    "ここを直してください",
    "1行目\n2行目\n\n4行目",
    "日本語 English 😀🎉 é 全角　空白",
    "  前後に空白  \n",
    "\n\n本文\n\n",
    "tab\tinside",
    "<script>alert(1)</script>",
    "`rm -rf /` $(whoami) ; a && b | c > d",
    '"quoted" \'single\' \\ backslash',
    "x" * 1000,
    "100%",
]


@pytest.mark.parametrize("feedback", FEEDBACKS, ids=lambda s: ascii(s)[:40])
def test_d0039_ac30_feedback_file_gives_the_same_record_as_feedback(tmp_path, capsys, feedback):
    """D0039-AC-30: --feedback-file の中身が、--feedback と同じ結果で記録に入る（前後の空白を取った直してほしい点・差し戻しの行・確認待ちが消える）。"""
    a, b = project(tmp_path, "a"), project(tmp_path, "b")
    assert run(review_argv(a, "revise", "--feedback", feedback)) == 0
    out_a = capsys.readouterr().out
    f = write(tmp_path / "fb.txt", feedback)
    assert run(review_argv(b, "revise", "--feedback-file", str(f))) == 0
    out_b = capsys.readouterr().out
    sa, sb = state_of(a), state_of(b)
    assert sa["runs"][-1] == sb["runs"][-1] == {"stage": "requirements", "review": "revise", "feedback": feedback.strip()}
    assert sa["pending_review"] is None and sb["pending_review"] is None
    assert [r for r in sa["runs"] if "review" in r] == [r for r in sb["runs"] if "review" in r]
    assert out_a == out_b == OK_LINE + "\n"
    assert f.read_bytes() == feedback.encode("utf-8"), "読むだけで、ファイルは変えない"


def test_d0039_ac30_feedback_file_of_exactly_the_limit_is_accepted(tmp_path, capsys):
    """D0039-AC-30: 16384 バイトちょうどのファイルは読める（日本語の3バイト文字でも、バイトで数える）。"""
    root = project(tmp_path)
    body = "あ" * 5461 + "a"  # 16383 + 1 = 16384 バイト
    assert len(body.encode("utf-8")) == LIMIT
    f = write(tmp_path / "fb.txt", body)
    assert run(review_argv(root, "revise", "--feedback-file", str(f))) == 0
    assert state_of(root)["runs"][-1]["feedback"] == body
    capsys.readouterr()


def test_d0039_ac30_relative_path_is_read_from_the_current_folder(tmp_path, monkeypatch, capsys):
    """D0039-AC-30: 相対のパスは、今のフォルダから読む。"""
    root = project(tmp_path)
    write(tmp_path / "fb.txt", "相対の指摘")
    monkeypatch.chdir(tmp_path)
    assert run(review_argv(root, "revise", "--feedback-file", "fb.txt")) == 0
    assert state_of(root)["runs"][-1]["feedback"] == "相対の指摘"
    capsys.readouterr()


# ---- 断る（記録を変えない） ---------------------------------------------------------------------------------------


def test_d0039_ac30_both_options_exit_2(tmp_path, capsys):
    """D0039-AC-30: --feedback と --feedback-file を同時に付けたら、使い方の誤り（終了コード 2）。記録は変わらない。空の --feedback でも同じ。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", "指摘")
    control = project(tmp_path, "control")  # 対にする確認：--feedback-file だけなら通る（未対応の引数で 2 になっているだけ、にならないように）
    assert run(review_argv(control, "revise", "--feedback-file", str(f))) == 0
    capsys.readouterr()
    for first in (["--feedback", "x"], ["--feedback", ""], ["--feedback", "指摘"]):
        code = refuses(review_argv(root, "revise", *first, "--feedback-file", str(f)), root, capsys)
        assert code == 2
        code = refuses(review_argv(root, "revise", "--feedback-file", str(f), *first), root, capsys)
        assert code == 2
    assert state_of(root)["pending_review"] is not None


def test_d0039_ac30_both_options_exit_2_for_other_results_too(tmp_path, capsys):
    """D0039-AC-30: 同時指定は、approved・quit でも使い方の誤り（付けた組み合わせ自体が誤り）。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", "指摘")
    control = project(tmp_path, "control")
    assert run(review_argv(control, "approved", "--feedback-file", str(f))) == 0
    capsys.readouterr()
    for result in ("approved", "quit"):
        assert refuses(review_argv(root, result, "--feedback", "x", "--feedback-file", str(f)), root, capsys) == 2


def test_d0039_ac30_missing_file_is_refused_and_the_record_is_unchanged(tmp_path, capsys):
    """D0039-AC-30: ファイルが無い（親のフォルダも無い）ときは、断る（SystemExit の文は pipe-in record: で始まる。終了コード 1）。記録は変わらない。"""
    root = project(tmp_path)
    for path in (tmp_path / "nope.txt", tmp_path / "no" / "such" / "dir" / "fb.txt"):
        code = refuses(review_argv(root, "revise", "--feedback-file", str(path)), root, capsys)
        assert isinstance(code, str) and code.startswith("pipe-in record: ")


def test_d0039_ac30_directory_is_refused_and_the_record_is_unchanged(tmp_path, capsys):
    """D0039-AC-30: フォルダを渡したときは断る（通常のファイルだけ読む）。"""
    root = project(tmp_path)
    folder = tmp_path / "folder"
    folder.mkdir()
    code = refuses(review_argv(root, "revise", "--feedback-file", str(folder)), root, capsys)
    assert isinstance(code, str) and code.startswith("pipe-in record: ")


@pytest.mark.parametrize("size", [LIMIT + 1, LIMIT + 2, LIMIT * 4, 1 << 20])
def test_d0039_ac30_huge_file_is_refused_and_the_record_is_unchanged(tmp_path, capsys, size):
    """D0039-AC-30: 16384 バイトを超えるファイルは断る（境目の +1 から）。全部は読まない。記録は変わらない。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", b"a" * size)
    code = refuses(review_argv(root, "revise", "--feedback-file", str(f)), root, capsys)
    assert isinstance(code, str) and code.startswith("pipe-in record: ")


@pytest.mark.parametrize("data", [b"\xff\xfe\xfd", b"\x80", b"abc\xc3", "あ".encode("utf-16"), b"\xed\xa0\x80", b"ok \xe3\x81"], ids=lambda b: repr(b)[:20])
def test_d0039_ac30_non_utf8_file_is_refused_and_the_record_is_unchanged(tmp_path, capsys, data):
    """D0039-AC-30: UTF-8 でないファイルは断る。記録は変わらない。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", data)
    code = refuses(review_argv(root, "revise", "--feedback-file", str(f)), root, capsys)
    assert isinstance(code, str) and code.startswith("pipe-in record: ")


@pytest.mark.parametrize("data", [b"", b" ", b"\n", b"  \n\t\n", "　".encode(), " \n".encode(), b"\r\n"], ids=lambda b: repr(b)[:20])
def test_d0039_ac30_empty_or_blank_file_is_refused_and_the_record_is_unchanged(tmp_path, capsys, data):
    """D0039-AC-30: 空（空白だけ）のファイルは、revise には直してほしい点が要るので断る（今の review の断りと同じ）。記録は変わらない。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", data)
    code = refuses(review_argv(root, "revise", "--feedback-file", str(f)), root, capsys)
    assert isinstance(code, str) and "revise" in code and code.startswith("pipe-in record: ")


def test_d0039_ac30_missing_file_message_does_not_become_a_traceback(tmp_path, capsys):
    """D0039-AC-30: 断りは SystemExit の短い文で、Python の例外（FileNotFoundError など）をそのまま出さない。"""
    root = project(tmp_path)
    before = state_bytes(root)
    try:
        run(review_argv(root, "revise", "--feedback-file", str(tmp_path / "nope.txt")))
    except SystemExit as e:
        assert isinstance(e.code, str) and "Traceback" not in e.code
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"例外がそのまま出た: {type(e).__name__}")
    else:
        pytest.fail("断らなかった")
    assert state_bytes(root) == before


@pytest.mark.parametrize("result", ["approved", "approve", "quit"])
def test_d0039_ac30_other_results_also_refuse_an_unreadable_file(tmp_path, capsys, result):
    """D0039-AC-30: approved・quit に付けたときも、読めなければ断る（付けた以上は読む）。記録は変わらない。"""
    root = project(tmp_path)
    (tmp_path / "dir").mkdir()
    write(tmp_path / "huge.txt", b"a" * (LIMIT + 1))
    write(tmp_path / "bad.txt", b"\xff\xfe")
    for bad in (tmp_path / "nope.txt", tmp_path / "huge.txt", tmp_path / "bad.txt", tmp_path / "dir"):
        code = refuses(review_argv(root, result, "--feedback-file", str(bad)), root, capsys)
        assert isinstance(code, str) and code.startswith("pipe-in record: ")


@pytest.mark.parametrize("result,expected", [("approved", "approved"), ("approve", "approved"), ("quit", "quit")])
def test_d0039_ac30_other_results_with_a_readable_file_ignore_its_text(tmp_path, capsys, result, expected):
    """D0039-AC-30: approved・quit にファイルを付けて読めるときは、今の --feedback と同じく、文は記録に入らない（確認の行だけ）。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", "入らない指摘")
    assert run(review_argv(root, result, "--feedback-file", str(f))) == 0
    entry = state_of(root)["runs"][-1]
    assert entry == {"stage": "requirements", "review": expected}
    assert state_of(root)["pending_review"] is None
    capsys.readouterr()


# ---- 今の --feedback は変わらない（今のままで通る。守り続ける検査） -----------------------------------------------------


def test_d0039_ac30_feedback_option_alone_is_unchanged(tmp_path, capsys):
    """D0039-AC-30: --feedback だけのときの動きと出力は変わらない（前後の空白を取って記録し、確認待ちが消え、同じ出力）。今のままで通る。"""
    root = project(tmp_path)
    assert run(review_argv(root, "revise", "--feedback", "  直して  ")) == 0
    assert capsys.readouterr().out == OK_LINE + "\n"
    s = state_of(root)
    assert s["runs"][-1] == {"stage": "requirements", "review": "revise", "feedback": "直して"} and s["pending_review"] is None


def test_d0039_ac30_revise_without_any_feedback_is_still_refused(tmp_path, capsys):
    """D0039-AC-30: revise に直してほしい点が無ければ、今までどおり断る（--feedback も --feedback-file も無い）。記録は変わらない。今のままで通る。"""
    root = project(tmp_path)
    code = refuses(review_argv(root, "revise"), root, capsys)
    assert isinstance(code, str) and "revise には" in code
    code = refuses(review_argv(root, "revise", "--feedback", "  "), root, capsys)
    assert isinstance(code, str) and "revise には" in code


@pytest.mark.parametrize("result", ["approved", "quit"])
def test_d0039_ac30_feedback_option_is_ignored_for_other_results_as_before(tmp_path, capsys, result):
    """D0039-AC-30: approved・quit に付けた --feedback は、今までどおり無視される。今のままで通る。"""
    root = project(tmp_path)
    assert run(review_argv(root, result, "--feedback", "無視される")) == 0
    assert state_of(root)["runs"][-1] == {"stage": "requirements", "review": result}
    capsys.readouterr()


def test_d0039_ac30_feedback_option_with_a_dash_value_still_works(tmp_path, capsys):
    """D0039-AC-30: --feedback の値が - で始まっても（--feedback=-x の形）、今までどおり読める。今のままで通る。"""
    root = project(tmp_path)
    assert run(review_argv(root, "revise", "--feedback=-x を直して")) == 0
    assert state_of(root)["runs"][-1]["feedback"] == "-x を直して"
    capsys.readouterr()


def test_d0039_ac30_through_cli_main(tmp_path, capsys):
    """D0039-AC-30: pipe-in record 経由（cli.main）でも --feedback-file が使える（record の分岐の中で解決される）。"""
    root = project(tmp_path)
    f = write(tmp_path / "fb.txt", "cli からの指摘")
    assert cli.main(["record", *review_argv(root, "revise", "--feedback-file", str(f))]) == 0
    assert state_of(root)["runs"][-1]["feedback"] == "cli からの指摘"
    capsys.readouterr()


def test_d0039_ac30_other_records_are_not_touched(tmp_path, capsys):
    """D0039-AC-30: 読んだあと、記録のほかのキー（runs の前の行・name・started_at）は変わらない。"""
    root = project(tmp_path)
    before = state_of(root)
    f = write(tmp_path / "fb.txt", "指摘")
    run(review_argv(root, "revise", "--feedback-file", str(f)))
    after = state_of(root)
    assert after["runs"][:-1] == before["runs"]
    for key in ("name", "started_at", "stages", "driver", "session_id", "pipe"):
        assert after.get(key) == before.get(key), key
    capsys.readouterr()
