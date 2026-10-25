"""D0027：コマンド pipe-in live（snapshot・page）。引数の解釈・出力先・終了コード・何も書かないこと。

入口は pipe_in/engine/live_cmd.py の main(argv, *, now=None)。argv は「live」の後ろ（["snapshot", …]）。pipe_in/cli.py の `live` の分岐が
それを呼ぶ（`pipe-in record` と同じ作り）。時計は引数 now で差し替える。SDK は呼ばない。記録は tmp_path の中に作る。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import live_support as ls
from pipe_in import cli
from pipe_in.engine import live, live_cmd, live_page

ROOT = Path(__file__).resolve().parents[1]
NOW = ls.NOW
SEP = chr(92)
EMPTY_KEYS = ["schema", "generated_at", "empty", "name", "final", "stages", "review"]


def run_live(argv, cap, *, now=NOW):
    """live_cmd.main を呼ぶ。SystemExit（argparse の使い方の誤り）も終了コードとして返す。"""
    try:
        code = live_cmd.main(list(argv), now=now)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    out, err = cap.readouterr()
    return code, out, err


def run_cli(argv, cap):
    try:
        code = cli.main(list(argv))
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    out, err = cap.readouterr()
    return code, out, err


def parse(out: bytes) -> dict:
    assert out, "標準出力が空（写しを出していない）"
    text = out.decode("utf-8")
    assert text.endswith("\n") and "\r" not in text
    return json.loads(text)


def tree(root: Path) -> dict[str, tuple[bytes, int] | None]:
    found: dict[str, tuple[bytes, int] | None] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        found[rel] = (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
    return found


def midway(tmp_path: Path) -> Path:
    return ls.dev_record_midway(tmp_path)


# ---- AC-22・23 記録なしでも終了コード 0 ------------------------------------------------------------------


def test_d0027_ac22_missing_state_exits_zero(tmp_path, capfdbinary):
    """D0027-AC-22: state.json が無い（フォルダはある）とき、記録なしの形を標準出力に出して終了コード 0。"""
    work = tmp_path / "w"
    work.mkdir()
    code, out, err = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    assert code == 0 and err == b""
    s = parse(out)
    assert list(s) == EMPTY_KEYS and s["empty"] is True and s["stages"] == [] and s["name"] is None and s["final"] is None
    assert s["generated_at"] == "2026-10-17T12:00:00+00:00"


def test_d0027_ac23_missing_dir_exits_zero(tmp_path, capfdbinary):
    """D0027-AC-23: 読み先のフォルダ自体が無くても、記録なしの形で終了コード 0（フォルダは作らない）。"""
    code, out, _err = run_live(["snapshot", "--work-dir", str(tmp_path / "nope" / "deeper")], capfdbinary)
    assert code == 0 and parse(out)["empty"] is True
    assert not (tmp_path / "nope").exists()


# ---- AC-63 読み先・出力先 ---------------------------------------------------------------------------------


def test_d0027_ac63_work_dir_argument_reads_pipe_records(tmp_path, capfdbinary):
    """D0027-AC-63: --work-dir に、パイプの記録のフォルダ（docs/pipeline/<パイプ名>）を渡して読める。"""
    work = tmp_path / "docs" / "pipeline" / "diagram"
    state = ls.base_state(pipe="diagram", name="図のパイプ", stages=[ls.stage_entry("collect", "集める"), ls.stage_entry("draw", "描く")],
                          runs=[ls.run("collect", seq=1)])
    ls.write_state(work, state)
    code, out, _ = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    s = parse(out)
    assert code == 0 and s["name"] == "図のパイプ"
    assert [(x["name"], x["label"], x["status"]) for x in s["stages"]] == [("collect", "集める", "done"), ("draw", "描く", "waiting")]


def test_d0027_ac63_relative_work_dir_is_read_from_the_current_folder(tmp_path, monkeypatch, capfdbinary):
    """D0027-AC-63: --work-dir が相対なら、今のフォルダから読む。"""
    ls.write_state(tmp_path / "docs" / "pipeline" / "run-1", ls.base_state(name="相対"))
    monkeypatch.chdir(tmp_path)
    for given in ("docs/pipeline/run-1", "./docs/pipeline/run-1", "docs/pipeline/../pipeline/run-1"):
        code, out, _ = run_live(["snapshot", "--work-dir", given], capfdbinary)
        assert code == 0 and parse(out)["name"] == "相対", given


def test_d0027_ac63_default_work_dir_is_the_project_work_dir(tmp_path, capfdbinary):
    """D0027-AC-63: --work-dir を省くと、--project の work_dir（開発フローの docs/pipeline/）を読む。"""
    midway(tmp_path)
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path)], capfdbinary)
    s = parse(out)
    assert code == 0 and s["name"] == "途中のセッション"
    assert [x["status"] for x in s["stages"]] == ["done", "running", "waiting", "waiting", "waiting"]
    assert s["stages"][1]["started_at"] is not None


def test_d0027_ac63_default_project_is_the_current_folder(tmp_path, monkeypatch, capfdbinary):
    """D0027-AC-63: --project も省くと、今のフォルダのプロジェクトを読む（record と同じ）。"""
    midway(tmp_path)
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_live(["snapshot"], capfdbinary)
    assert code == 0 and parse(out)["name"] == "途中のセッション"


def test_d0027_ac63_work_dir_follows_pipeline_toml_and_config(tmp_path, capfdbinary):
    """D0027-AC-63: pipeline.toml の work_dir（--config で渡したものも）に従う。"""
    ls.write_state(tmp_path / "custom" / "run", ls.base_state(name="設定の先"))
    (tmp_path / "pipeline.toml").write_text('[pipeline]\nwork_dir = "custom/run"\n', encoding="utf-8")
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path)], capfdbinary)
    assert code == 0 and parse(out)["name"] == "設定の先"
    other = tmp_path / "other.toml"
    other.write_text('[pipeline]\nwork_dir = "elsewhere"\n', encoding="utf-8")
    ls.write_state(tmp_path / "elsewhere", ls.base_state(name="別の設定"))
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path), "--config", str(other)], capfdbinary)
    assert code == 0 and parse(out)["name"] == "別の設定"


def test_d0027_ac63_explicit_work_dir_beats_the_project_work_dir(tmp_path, capfdbinary):
    """D0027-AC-63: --work-dir を渡したら、--project の work_dir は読まない。"""
    midway(tmp_path)
    ls.write_state(tmp_path / "pick", ls.base_state(name="こちら"))
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path), "--work-dir", str(tmp_path / "pick")], capfdbinary)
    assert code == 0 and parse(out)["name"] == "こちら"


def test_d0027_ac63_writes_to_stdout_or_out_file(tmp_path, capfdbinary):
    """D0027-AC-63: 標準出力か --out のファイルに、同じバイト列（UTF-8・\\n 固定）で出す。ファイルのときは標準出力に何も出さない。"""
    work = midway(tmp_path)
    state = live.read_state(work)
    expected = live.dumps(live.build_snapshot(state, live.read_open_at(work, state), now=NOW)).encode("utf-8")
    code, out, _ = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    assert code == 0 and out == expected and out.endswith(b"\n") and b"\r" not in out
    target = tmp_path / "out" / "snap.json"
    target.parent.mkdir()
    code, out2, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(target)], capfdbinary)
    assert code == 0 and out2 == b"" and target.read_bytes() == expected


def test_d0027_ac63_output_is_ascii_json_even_for_japanese_names(tmp_path, capfdbinary):
    """D0027-AC-63: 日本語の名前でも出力は ASCII だけの JSON（\\u エスケープ）で、読み直せる。"""
    ls.write_state(tmp_path / "w", ls.base_state(name="日本語の名前 😀"))
    code, out, _ = run_live(["snapshot", "--work-dir", str(tmp_path / "w")], capfdbinary)
    assert code == 0 and out.isascii() and parse(out)["name"] == "日本語の名前 😀"


def test_d0027_ac63_now_default_is_the_real_clock(tmp_path, capfdbinary):
    """D0027-AC-21: now を渡さないと、実際の今（UTC）を generated_at に使う。"""
    (tmp_path / "w").mkdir()
    before = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        code = live_cmd.main(["snapshot", "--work-dir", str(tmp_path / "w")])
    except SystemExit as e:
        code = e.code
    out, _ = capfdbinary.readouterr()
    after = datetime.now(timezone.utc)
    assert code == 0
    stamp = datetime.fromisoformat(parse(out)["generated_at"])
    assert stamp.utcoffset() == timedelta(0) and before - timedelta(seconds=1) <= stamp <= after + timedelta(seconds=1)


@pytest.mark.parametrize("now", [NOW, datetime(2026, 10, 17, 21, 0, 0, tzinfo=ls.JST), datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)], ids=["utc", "jst", "later"])
def test_d0027_ac63_now_argument_is_used_for_generated_at(tmp_path, capfdbinary, now):
    """D0027-AC-21: 引数 now が generated_at になる（UTC に直して秒まで）。"""
    (tmp_path / "w").mkdir()
    code, out, _ = run_live(["snapshot", "--work-dir", str(tmp_path / "w")], capfdbinary, now=now)
    assert code == 0 and parse(out)["generated_at"] == now.astimezone(timezone.utc).isoformat(timespec="seconds")


def test_d0027_ac63_snapshot_hides_the_read_path(tmp_path, capfdbinary):
    """D0027-AC-13: 読み先のパス（与えられた形・resolve した形・/ 形・\\ 形）が、名前に混じっていても出力に出ない。親の名前（pipeline）は消さない。"""
    work = tmp_path / "docs" / "pipeline"
    ls.write_state(work, ls.base_state(name=f"pipeline status at {work} and {work.resolve()}", stages=[ls.stage_entry("a", str(work).replace("/", SEP) + SEP + "x")]))
    code, out, _ = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    s = parse(out)
    values = [s["name"], *[x["label"] for x in s["stages"]], *[x["name"] for x in s["stages"]]]
    assert code == 0
    for form in (str(work), str(work.resolve()), str(work).replace("/", SEP)):
        assert not any(form in v for v in values), form
    assert s["name"].startswith("pipeline status at")


def test_d0027_ac63_snapshot_hides_the_symlink_and_resolved_forms(tmp_path, capfdbinary):
    """D0027-AC-13: シンボリックリンク経由で読んでも、リンクの形と本当の場所の形、どちらも出力に出ない。"""
    real = tmp_path / "real" / "rec"
    ls.write_state(real, ls.base_state(name=f"a {real} b {tmp_path / 'link' / 'rec'}"))
    try:
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    code, out, _ = run_live(["snapshot", "--work-dir", str(tmp_path / "link" / "rec")], capfdbinary)
    text = out.decode("utf-8")
    assert code == 0 and parse(out)["empty"] is False
    assert str(real) not in text and str(tmp_path / "link" / "rec") not in text


# ---- AC-64 書き出しの守り -----------------------------------------------------------------------------------


def test_d0027_ac64_out_leaves_state_json_bytes_unchanged(tmp_path, capfdbinary):
    """D0027-AC-64: --out で書いても、読み先の記録（state.json・ログ・ほかのファイル）のバイト列も更新時刻も変わらない。"""
    work = midway(tmp_path)
    before = tree(work)
    target = tmp_path / "out" / "snap.json"
    target.parent.mkdir()
    code, out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(target)], capfdbinary)
    assert code == 0 and target.is_file() and parse(target.read_bytes() or b"")["name"] == "途中のセッション"
    assert tree(work) == before


@pytest.mark.parametrize("where", ["snap.json", "logs/snap.json", "state.json", "00_input.md", "../{work}/snap.json", "./snap.json", "sub/snap.json"],
                         ids=["inside", "in_logs", "over_state", "over_input", "dotdot_back_in", "dot", "missing_sub"])
def test_d0027_ac64_out_inside_the_work_dir_is_refused(tmp_path, capfdbinary, where):
    """D0027-AC-64: --out が読み先のフォルダの中を指すときは、書かずに使い方の誤り（終了コード 2）。記録は何も変わらない。"""
    work = midway(tmp_path)
    before = tree(work)
    target = str(work / where.format(work=work.name))
    code, out, err = run_live(["snapshot", "--work-dir", str(work), "--out", target], capfdbinary)
    assert code == 2 and out == b"" and err
    assert tree(work) == before


def test_d0027_ac64_out_through_a_symlinked_folder_into_the_work_dir_is_refused(tmp_path, capfdbinary):
    """D0027-AC-64: 外のシンボリックリンクのフォルダ経由で、読み先の中に書こうとしても断る（resolve した場所で見る）。"""
    work = midway(tmp_path)
    before = tree(work)
    try:
        (tmp_path / "shortcut").symlink_to(work, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    code, _out, _err = run_live(["snapshot", "--work-dir", str(work), "--out", str(tmp_path / "shortcut" / "snap.json")], capfdbinary)
    assert code == 2 and tree(work) == before


def test_d0027_ac64_out_symlink_is_refused(tmp_path, capfdbinary):
    """D0027-AC-64: --out がシンボリックリンクのときは、書かずに終了コード 2。リンク先も変わらない。"""
    work = midway(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("守る", encoding="utf-8")
    link = tmp_path / "out.json"
    try:
        link.symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    code, _out, _err = run_live(["snapshot", "--work-dir", str(work), "--out", str(link)], capfdbinary)
    assert code == 2 and victim.read_text(encoding="utf-8") == "守る" and link.is_symlink()


def test_d0027_ac64_out_dangling_symlink_is_refused(tmp_path, capfdbinary):
    """D0027-AC-64: リンク先の無い（切れた）シンボリックリンクも断る。リンク先を作らない。"""
    work = midway(tmp_path)
    link = tmp_path / "out.json"
    try:
        link.symlink_to(tmp_path / "ghost.json")
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    code, _out, _err = run_live(["snapshot", "--work-dir", str(work), "--out", str(link)], capfdbinary)
    assert code == 2 and not (tmp_path / "ghost.json").exists()


def test_d0027_ac64_out_with_missing_parent_is_refused(tmp_path, capfdbinary):
    """D0027-AC-64: --out の親のフォルダが無いときは、フォルダを作らず終了コード 2。"""
    work = midway(tmp_path)
    code, out, err = run_live(["snapshot", "--work-dir", str(work), "--out", str(tmp_path / "no" / "such" / "snap.json")], capfdbinary)
    assert code == 2 and out == b"" and err
    assert not (tmp_path / "no").exists()


def test_d0027_ac64_out_that_cannot_be_written_exits_one(tmp_path, capfdbinary):
    """D0027-AC-64: 書けなかった（--out がフォルダなど。OSError）ときは、短い文を出して終了コード 1。例外の長い表示を出さない。"""
    work = midway(tmp_path)
    folder = tmp_path / "isafolder"
    folder.mkdir()
    code, out, err = run_live(["snapshot", "--work-dir", str(work), "--out", str(folder)], capfdbinary)
    assert code == 1 and out == b""
    assert err.strip() and b"Traceback" not in err and err.count(b"\n") <= 3


def test_d0027_ac64_out_overwrites_the_old_file_completely(tmp_path, capfdbinary):
    """D0027-AC-64: 既にあるファイルは、古い中身が残らないよう置き換える（長い古い中身の尻尾が残らない）。"""
    work = midway(tmp_path)
    target = tmp_path / "snap.json"
    target.write_bytes(b"x" * 100000)
    code, _out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(target)], capfdbinary)
    data = target.read_bytes()
    assert code == 0 and len(data) < 100000 and json.loads(data.decode("utf-8"))["schema"] == 1


def test_d0027_ac64_out_leaves_no_other_files_behind(tmp_path, capfdbinary):
    """D0027-AC-64: 出力先のフォルダに、--out のファイル以外（一時ファイルなど）を残さない。"""
    work = midway(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, _out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(out_dir / "snap.json")], capfdbinary)
    assert code == 0 and sorted(p.name for p in out_dir.iterdir()) == ["snap.json"]


def test_d0027_ac64_out_next_to_but_outside_the_work_dir_is_allowed(tmp_path, capfdbinary):
    """D0027-AC-64: 読み先の隣（同じ親のフォルダ）や、名前の頭だけが同じフォルダには書ける（頭の文字の比較で誤って断らない）。"""
    work = midway(tmp_path)
    twin = work.parent / (work.name + "-copy")
    twin.mkdir()
    code, _out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(twin / "snap.json")], capfdbinary)
    assert code == 0 and (twin / "snap.json").is_file()
    code, _out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(work.parent / "next.json")], capfdbinary)
    assert code == 0 and (work.parent / "next.json").is_file()


def test_d0027_ac64_out_in_the_work_dir_is_refused_even_when_the_dir_is_missing_state(tmp_path, capfdbinary):
    """D0027-AC-64: 読み先に state.json が無くても、読み先の中への書き出しは断る。"""
    work = tmp_path / "w"
    work.mkdir()
    code, _out, _ = run_live(["snapshot", "--work-dir", str(work), "--out", str(work / "snap.json")], capfdbinary)
    assert code == 2 and list(work.iterdir()) == []


# ---- AC-65 ページ -----------------------------------------------------------------------------------------


def test_d0027_ac65_page_writes_to_stdout_or_out_file(tmp_path, capfdbinary):
    """D0027-AC-65: page は、標準出力か --out のファイルに、build_page() と同じ HTML（UTF-8）を出す。"""
    expected = live_page.build_page().encode("utf-8")
    assert expected.lower().startswith(b"<!doctype html>"), "ページがまだ無い"
    code, out, _ = run_live(["page"], capfdbinary)
    assert code == 0 and out == expected
    target = tmp_path / "page.html"
    code, out2, _ = run_live(["page", "--out", str(target)], capfdbinary)
    assert code == 0 and out2 == b"" and target.read_bytes() == expected


def test_d0027_ac65_page_does_not_read_any_record(tmp_path, monkeypatch, capfdbinary):
    """D0027-AC-65: page は記録を読まない（記録の無いフォルダでも、壊れた記録のあるフォルダでも同じ HTML）。"""
    expected = live_page.build_page().encode("utf-8")
    assert expected
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "pipeline").mkdir(parents=True)
    (tmp_path / "docs" / "pipeline" / "state.json").write_text("{broken", encoding="utf-8")
    code, out, _ = run_live(["page"], capfdbinary)
    assert code == 0 and out == expected


def test_d0027_ac65_page_out_overwrites_the_old_file(tmp_path, capfdbinary):
    """D0027-AC-65: page --out は、古い中身を残さず置き換える。"""
    target = tmp_path / "page.html"
    target.write_bytes(b"x" * 200000)
    code, _out, _ = run_live(["page", "--out", str(target)], capfdbinary)
    assert code == 0 and target.read_bytes() == live_page.build_page().encode("utf-8") != b""


def test_d0027_ac65_page_out_with_missing_parent_or_folder_fails_cleanly(tmp_path, capfdbinary):
    """D0027-AC-65: page --out が書けない（親が無い・フォルダ）ときは、例外の長い表示でなく、使い方の誤りか短い文の失敗にする。"""
    expected = live_page.build_page()
    assert expected
    code, _out, err = run_live(["page", "--out", str(tmp_path / "no" / "page.html")], capfdbinary)
    assert code in (1, 2) and b"Traceback" not in err and err.strip()
    (tmp_path / "folder").mkdir()
    code, _out, err = run_live(["page", "--out", str(tmp_path / "folder")], capfdbinary)
    assert code in (1, 2) and b"Traceback" not in err and err.strip()


# ---- AC-66 SDK・子プロセス ---------------------------------------------------------------------------------


SDK_PROBE = """
import sys
sys.path.insert(0, {root!r})
def sdk():
    return sorted(m for m in sys.modules if m.split('.')[0] in ('claude_agent_sdk', 'anyio', 'mcp'))
import pipe_in.engine.live, pipe_in.engine.live_page, pipe_in.engine.live_cmd
direct = sdk()
from pipe_in import cli
before = sdk()
rc = cli.main({argv!r})
after = sdk()
print(repr((direct, before, after, rc)))
"""


@pytest.mark.parametrize("argv", [["live", "page"], ["live", "snapshot", "--work-dir", "nothing-here"]], ids=["page", "snapshot"])
def test_d0027_ac66_live_commands_do_not_import_the_sdk(tmp_path, argv):
    """D0027-AC-66: live の部品を読み込んでも、live のコマンドを流しても、claude_agent_sdk（と、それが引き込むもの）が sys.modules に増えない。"""
    proc = subprocess.run([sys.executable, "-I", "-c", SDK_PROBE.format(root=str(ROOT), argv=argv)], capture_output=True, cwd=tmp_path, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    direct, before, after, rc = eval(proc.stdout.decode("utf-8").strip().splitlines()[-1])
    assert direct == [], f"live の部品の import で SDK 側が入った: {direct}"
    assert after == before, f"live の実行で SDK 側が増えた: {set(after) - set(before)}"
    assert rc == 0


def test_d0027_ac66_live_commands_start_no_child_process(tmp_path, monkeypatch, capfdbinary):
    """D0027-AC-66: live は子プロセスを起こさない（git も node も呼ばない）。"""
    def boom(*a, **k):
        raise AssertionError("子プロセスを起こそうとした")

    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(os, "system", boom)
    midway(tmp_path)
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path)], capfdbinary)
    assert code == 0 and parse(out)["name"] == "途中のセッション"
    code, out, _ = run_live(["page"], capfdbinary)
    assert code == 0 and out


# ---- AC-67 どちらの呼び方でも ---------------------------------------------------------------------------------


def test_d0027_ac67_runs_through_cli_main(tmp_path, capfdbinary):
    """D0027-AC-67: pipe_in.cli.main(["live", …]) から呼べる（pipe-in live … の通り道）。"""
    work = midway(tmp_path)
    code, out, _ = run_cli(["live", "page"], capfdbinary)
    assert code == 0 and out == live_page.build_page().encode("utf-8") != b""
    code, out, _ = run_cli(["live", "snapshot", "--work-dir", str(work)], capfdbinary)
    assert code == 0 and parse(out)["name"] == "途中のセッション"


def test_d0027_ac67_cli_live_errors_exit_two(capfdbinary):
    """D0027-AC-67: cli.main(["live"]) と、知らない下位コマンドは、使い方を出して終了コード 2。"""
    for argv, words in ((["live"], (b"snapshot", b"page")), (["live", "nope"], (b"snapshot", b"page")), (["live", "snapshot", "--bogus"], (b"snapshot",))):
        code, _out, err = run_cli(argv, capfdbinary)
        assert code == 2 and b"usage" in err.lower(), argv
        assert all(w in err for w in words), (argv, err)  # live の使い方（下位コマンド）を出す。本体の使い方ではない


def test_d0027_ac67_runs_through_python_dash_m(tmp_path):
    """D0027-AC-67: python -m pipe_in live … からも呼べる。標準出力は同じバイト列で、終了コード 0。"""
    work = midway(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    page = subprocess.run([sys.executable, "-m", "pipe_in", "live", "page"], capture_output=True, cwd=tmp_path, env=env, timeout=120)
    assert page.returncode == 0 and page.stdout == live_page.build_page().encode("utf-8") != b""
    snap = subprocess.run([sys.executable, "-m", "pipe_in", "live", "snapshot", "--work-dir", str(work)], capture_output=True, cwd=tmp_path, env=env, timeout=120)
    assert snap.returncode == 0 and json.loads(snap.stdout.decode("utf-8"))["name"] == "途中のセッション"
    bad = subprocess.run([sys.executable, "-m", "pipe_in", "live"], capture_output=True, cwd=tmp_path, env=env, timeout=120)
    assert bad.returncode == 2 and b"usage" in bad.stderr.lower()


def test_d0027_ac67_console_script_points_at_cli_main():
    """D0027-AC-67: pipe-in コマンドは pipe_in.cli:main（live の分岐を持つ入口）を指す。"""
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["pipe-in"] == "pipe_in.cli:main"


# ---- AC-68 引数の誤りは 2、記録の問題は 0 ----------------------------------------------------------------------

ARG_ERRORS = [
    [], ["nope"], ["snapshot", "--bogus"], ["snapshot", "--work-dir"], ["snapshot", "--out"], ["snapshot", "--project"], ["snapshot", "--config"],
    ["snapshot", "extra"], ["snapshot", "--work-dir", "a", "extra"], ["page", "--work-dir", "x"], ["page", "--project", "x"], ["page", "--config", "x"],
    ["page", "--out"], ["page", "extra"], ["page", "--bogus"], ["--bogus"], ["snapshot", "--work-dir", "a", "--bogus", "b"], ["Snapshot"], ["snapshot,page"],
]


@pytest.mark.parametrize("argv", ARG_ERRORS, ids=lambda a: " ".join(a) or "(none)")
def test_d0027_ac68_argument_errors_exit_two(tmp_path, monkeypatch, capfdbinary, argv):
    """D0027-AC-68: 引数の誤り（下位コマンドが無い・知らない引数・値の欠け・page に snapshot の引数）は、使い方を出して終了コード 2。標準出力には何も出さない。"""
    monkeypatch.chdir(tmp_path)
    code, out, err = run_live(argv, capfdbinary)
    assert code == 2, (code, err)
    assert out == b"" and b"usage" in err.lower()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [b"", b"{", b"[]", b"null", b"\xff\xfe\x00", b"\xef\xbb\xbf{}", b"[" * 100000, b'{"stages": 5}', b'{"stages": [1, null]}', b"NaN"],
    ids=["empty", "cut", "array", "null", "bytes", "bom", "deep", "stages_number", "stages_junk", "nan"],
)
def test_d0027_ac68_broken_record_exits_zero(tmp_path, capfdbinary, raw):
    """D0027-AC-68: 記録の中身の問題（壊れた JSON・配列・BOM・深すぎる入れ子など）では、終了コード 0 で、決まった形の写しを出す。"""
    work = tmp_path / "w"
    work.mkdir()
    (work / "state.json").write_bytes(raw)
    code, out, err = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    assert code == 0 and b"Traceback" not in err
    s = parse(out)
    assert list(s) == EMPTY_KEYS and isinstance(s["stages"], list)


def test_d0027_ac68_state_json_as_a_folder_exits_zero(tmp_path, capfdbinary):
    """D0027-AC-68: state.json という名前のフォルダでも、終了コード 0 で記録なしの形。"""
    (tmp_path / "w" / "state.json").mkdir(parents=True)
    code, out, _ = run_live(["snapshot", "--work-dir", str(tmp_path / "w")], capfdbinary)
    assert code == 0 and parse(out)["empty"] is True


def test_d0027_ac68_work_dir_that_is_a_file_exits_zero(tmp_path, capfdbinary):
    """D0027-AC-68: 読み先がファイルでも、終了コード 0 で記録なしの形。"""
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    code, out, _ = run_live(["snapshot", "--work-dir", str(f)], capfdbinary)
    assert code == 0 and parse(out)["empty"] is True


def test_d0027_ac68_broken_log_exits_zero(tmp_path, capfdbinary):
    """D0027-AC-68: ログが壊れていても、終了コード 0 で、started_at だけが null の写しを出す。"""
    work = tmp_path / "w"
    ls.write_state(work, ls.base_state(open=ls.opened("design", seq=2)))
    (work / "logs").mkdir()
    (work / "logs" / "02_design.jsonl").write_bytes(b"\xff\xff garbage\n{{{\n")
    code, out, _ = run_live(["snapshot", "--work-dir", str(work)], capfdbinary)
    s = parse(out)
    assert code == 0 and s["empty"] is False
    assert [x["status"] for x in s["stages"]][1] == "running" and s["stages"][1]["started_at"] is None


# ---- AC-69 記録に何も書かない・record は変わらない -----------------------------------------------------------------


def test_d0027_ac69_live_writes_nothing_to_the_record(tmp_path, capfdbinary):
    """D0027-AC-69: live snapshot / page は、記録のあるプロジェクトの中のファイル（内容・更新時刻・ファイルの一覧）を何も変えない。"""
    midway(tmp_path)
    before = tree(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-out")
    outside.mkdir()
    try:
        for argv in (["snapshot", "--project", str(tmp_path)], ["snapshot", "--work-dir", str(ls.work_of(tmp_path))], ["page"],
                     ["snapshot", "--project", str(tmp_path), "--out", str(outside / "s.json")], ["page", "--out", str(outside / "p.html")]):
            code, _out, _err = run_live(argv, capfdbinary)
            assert code == 0, argv
        assert tree(tmp_path) == before
        assert (outside / "s.json").is_file() and (outside / "p.html").is_file() and (outside / "s.json").stat().st_size > 50
    finally:
        for p in outside.iterdir():
            p.unlink()
        outside.rmdir()


def test_d0027_ac69_snapshot_goes_to_stdout_and_it_is_the_record_snapshot(tmp_path, capfdbinary):
    """D0027-AC-69: 何も書かない代わりに、写しは標準出力に出る（上のテストが「何も出さない」だけで通らないように）。"""
    midway(tmp_path)
    code, out, _ = run_live(["snapshot", "--project", str(tmp_path)], capfdbinary)
    assert code == 0 and parse(out)["name"] == "途中のセッション"


def test_d0027_ac69_record_commands_are_unchanged(tmp_path, capfdbinary):
    """D0027-AC-69: live を挟んでも、pipe-in record の動き（出力・state.json・ログ・終了コード）は変わらない。"""
    proj = str(tmp_path)
    steps = [
        ["record", "start", "--project", proj, "--text", "メモ", "--name", "記録の続き"],
        ["record", "begin", "--project", proj, "requirements"],
    ]
    for argv in steps:
        code, _out, _err = run_cli(argv, capfdbinary)
        assert code == 0, argv
    live_code, live_out, _ = run_cli(["live", "snapshot", "--project", proj], capfdbinary)
    assert live_code == 0 and parse(live_out)["stages"][0]["status"] == "running"
    for argv in (["record", "done", "--project", proj, "requirements", "--summary", "書いた"], ["record", "wait", "--project", proj, "requirements"],
                 ["record", "review", "--project", proj, "requirements", "approved"], ["record", "finish", "--project", proj, "STOPPED_BY_HUMAN"]):
        code, out, _err = run_cli(argv, capfdbinary)
        assert code == 0 and "記録しました" in out.decode("utf-8"), argv
    state = json.loads((ls.work_of(tmp_path) / "state.json").read_text(encoding="utf-8"))
    assert state["final"] == "STOPPED_BY_HUMAN" and state["name"] == "記録の続き"
    assert [r.get("review") or r.get("stage") for r in state["runs"]] == ["requirements", "approved"]
    after, _, _ = run_cli(["live", "snapshot", "--project", proj], capfdbinary)
    assert after == 0


# ---- AC-71 依存を足さない ----------------------------------------------------------------------------------------


def test_d0027_ac71_dependencies_are_unchanged():
    """D0027-AC-71: 外部のパッケージの依存を足さない（pyproject.toml の dependencies が claude-agent-sdk だけ）。今のままで通る検査（守り続ける）。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["claude-agent-sdk>=0.2.159,<0.3"]
    assert set(project.get("optional-dependencies", {})) == {"dev"}


def test_d0027_ac71_new_modules_are_in_an_installed_package():
    """D0027-AC-71: 新しい .py は pipe_in.engine の中（packages に載っている）。package-data を増やさない。"""
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    assert "pipe_in.engine" in cfg["packages"]
    assert not any("live" in str(v) for v in cfg.get("package-data", {}).values())
    for name in ("live.py", "live_page.py", "live_cmd.py"):
        assert (ROOT / "pipe_in" / "engine" / name).is_file()
