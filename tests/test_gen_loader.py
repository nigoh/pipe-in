"""D0086: テストはいつも、流している作業フォルダの generator/ を pipe_in_generator として読む。

補助 tests/gen_loader.py（load・verify・CHILD_PRELUDE・LOADER_PATH）を確かめる。
入れ込みが主の checkout にある状態は、tmp_path に偽の2つの置き場所を作って、-I の子プロセスで再現する
（本当の pip install -e はしない。sys.modules の差し替えが親のテスト全体に漏れないため）。
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def _gl():
    """補助を遅く読む（補助がまだ無いときは、このテストだけが ModuleNotFoundError で落ちる）。"""
    return importlib.import_module("gen_loader")


def _make_places(base: Path) -> tuple[Path, Path]:
    """入れ込み先の役（main_checkout）と、作業フォルダの役（work）を作る。"""
    base = base.resolve()
    main_pkg = base / "main_checkout" / "pipe_in_generator"
    main_pkg.mkdir(parents=True)
    (main_pkg / "__init__.py").write_text('WHERE = "main"\n', encoding="utf-8")
    (main_pkg / "cli.py").write_text('MARK = "main"\n', encoding="utf-8")
    work_gen = base / "work" / "generator"
    work_gen.mkdir(parents=True)
    (work_gen / "__init__.py").write_text('WHERE = "work"\n', encoding="utf-8")
    (work_gen / "cli.py").write_text('MARK = "work"\n', encoding="utf-8")
    (work_gen / "only_here.py").write_text("VALUE = 42\n", encoding="utf-8")
    return base / "main_checkout", work_gen


def _run_child(code: str, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-c", code, *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=60,
    )


_REPORT = """
import json, sys
import pipe_in_generator, pipe_in_generator.cli
from pipe_in_generator import only_here
print(json.dumps({
    "file": pipe_in_generator.__file__,
    "where": pipe_in_generator.WHERE,
    "cli_mark": pipe_in_generator.cli.MARK,
    "cli_file": pipe_in_generator.cli.__file__,
    "only_here": only_here.VALUE,
}))
"""


def test_d0086_ac01_入れ込みが別の場所でも作業フォルダのgeneratorを読む(tmp_path):
    """D0086-AC-01: 入れ込み先（主の checkout の役）を先に読んだ状態で load() を呼ぶと、作業フォルダの generator/ になる。"""
    main_checkout, work_gen = _make_places(tmp_path)
    loader = _gl()
    pre = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[3])\n"
        "import pipe_in_generator, pipe_in_generator.cli\n"  # 入れ込み先を先に読んだ状態
        "assert pipe_in_generator.WHERE == 'main'\n"
    )
    code = pre + loader.CHILD_PRELUDE + _REPORT
    r = _run_child(code, str(loader.LOADER_PATH), str(work_gen), str(main_checkout), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert Path(got["file"]).resolve() == (work_gen / "__init__.py").resolve()
    assert got["where"] == "work"
    assert got["cli_mark"] == "work"
    assert Path(got["cli_file"]).resolve().is_relative_to(work_gen.resolve())
    assert got["only_here"] == 42


def test_d0086_ac02_入れ込みが無くても作業フォルダから読めてcliが通る(tmp_path):
    """D0086-AC-02: 入れ込み先が無い状態でも load() は作業フォルダの generator/ から作り、pipe_in_generator.cli などが通る。"""
    _, work_gen = _make_places(tmp_path)
    loader = _gl()
    code = loader.CHILD_PRELUDE + _REPORT
    r = _run_child(code, str(loader.LOADER_PATH), str(work_gen), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert Path(got["file"]).resolve() == (work_gen / "__init__.py").resolve()
    assert got["cli_mark"] == "work"
    assert got["only_here"] == 42


def test_d0086_ac03_子プロセスの補助は隔離のiでも効く(tmp_path):
    """D0086-AC-03: -I（cwd も PYTHONPATH も sys.path に入らない）の子でも、CHILD_PRELUDE がパスで補助を読んで load() できる。"""
    _, work_gen = _make_places(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    loader = _gl()
    assert Path(loader.LOADER_PATH).resolve() == (TESTS / "gen_loader.py").resolve()
    code = loader.CHILD_PRELUDE + "import pipe_in_generator, json, sys\nprint(json.dumps(pipe_in_generator.__file__))\n"
    r = _run_child(code, str(loader.LOADER_PATH), str(work_gen), cwd=elsewhere)
    assert r.returncode == 0, r.stderr
    assert Path(json.loads(r.stdout.strip().splitlines()[-1])).resolve() == (work_gen / "__init__.py").resolve()


def _fake_module(name: str, file: Path):
    import types

    m = types.ModuleType(name)
    m.__file__ = str(file)
    return m


def _isolate_modules(monkeypatch) -> None:
    """親の sys.modules にある pipe_in_generator.* を（テストの間だけ）外す。monkeypatch が戻す。"""
    for key in [k for k in sys.modules if k == "pipe_in_generator" or k.startswith("pipe_in_generator.")]:
        monkeypatch.delitem(sys.modules, key)


def test_d0086_ac05_場所が違うと実際の場所と期待した場所と直し方の文で落ちる(tmp_path, monkeypatch):
    """D0086-AC-05: 別の場所の pipe_in_generator が読まれているとき、verify は実際の場所・期待した場所・直し方の入った文で RuntimeError。"""
    main_checkout, work_gen = _make_places(tmp_path)
    loader = _gl()
    _isolate_modules(monkeypatch)
    other = main_checkout / "pipe_in_generator"
    monkeypatch.setitem(sys.modules, "pipe_in_generator", _fake_module("pipe_in_generator", other / "__init__.py"))
    with pytest.raises(RuntimeError) as exc:
        loader.verify(work_gen)
    msg = str(exc.value)
    assert str(other) in msg  # 実際の場所
    assert str(work_gen) in msg  # 期待した場所
    assert "pip install -e" in msg  # 直し方
    assert "load" in msg


def test_d0086_ac05_サブモジュールだけ別の場所でも落ちる(tmp_path, monkeypatch):
    """D0086-AC-05: pipe_in_generator 本体は合っていても、pipe_in_generator.cli が作業フォルダの外から読まれていれば落ちる。"""
    main_checkout, work_gen = _make_places(tmp_path)
    loader = _gl()
    _isolate_modules(monkeypatch)
    monkeypatch.setitem(sys.modules, "pipe_in_generator", _fake_module("pipe_in_generator", work_gen / "__init__.py"))
    stray = main_checkout / "pipe_in_generator" / "cli.py"
    monkeypatch.setitem(sys.modules, "pipe_in_generator.cli", _fake_module("pipe_in_generator.cli", stray))
    with pytest.raises(RuntimeError) as exc:
        loader.verify(work_gen)
    assert str(stray) in str(exc.value)


def test_d0086_ac05_同じ場所なら落ちない(tmp_path, monkeypatch):
    """D0086-AC-05: 読まれている場所が作業フォルダの generator/ と同じなら、verify は何も言わない。"""
    _, work_gen = _make_places(tmp_path)
    loader = _gl()
    _isolate_modules(monkeypatch)
    monkeypatch.setitem(sys.modules, "pipe_in_generator", _fake_module("pipe_in_generator", work_gen / "__init__.py"))
    monkeypatch.setitem(sys.modules, "pipe_in_generator.cli", _fake_module("pipe_in_generator.cli", work_gen / "cli.py"))
    assert loader.verify(work_gen) is None


# 同じ try: import pipe_in_generator / except ImportError の写し
_COPY = re.compile(r"import pipe_in_generator(?![.\w])[\s\S]{0,200}?except ImportError")
_SPEC = re.compile(r"""spec_from_file_location\(\s*["']pipe_in_generator["']""")
_COPIES = ("conftest.py", "test_guard_hook_input.py", "test_architecture_chat.py")


@pytest.mark.parametrize("name", _COPIES)
def test_d0086_ac06_importの写しが3つのファイルに残らない(name):
    """D0086-AC-06: try: import pipe_in_generator / except ImportError の組と、名前を決めた明示の読み込みが、補助以外に残らない。"""
    src = (TESTS / name).read_text(encoding="utf-8")
    assert not _COPY.search(src), f"{name} に import pipe_in_generator / except ImportError の写しが残っています"
    assert not _SPEC.search(src), f"{name} に pipe_in_generator の明示の読み込みの写しが残っています"


def test_d0086_ac06_読み込みの手順は補助の1か所だけ():
    """D0086-AC-06: 明示の読み込み（spec_from_file_location）は tests/gen_loader.py にだけある。"""
    helper = TESTS / "gen_loader.py"
    assert helper.is_file(), "tests/gen_loader.py がありません"
    assert _SPEC.search(helper.read_text(encoding="utf-8"))


def test_d0086_ac07_補助はtestsの中だけでgeneratorとpipe_inに入れない():
    """D0086-AC-07: 補助は tests/ にあり、generator/・pipe_in/ のソースは補助を知らない。"""
    assert (TESTS / "gen_loader.py").is_file(), "tests/gen_loader.py がありません"
    for base in (ROOT / "generator", ROOT / "pipe_in"):
        for p in base.rglob("*.py"):
            assert "gen_loader" not in p.read_text(encoding="utf-8"), f"{p.relative_to(ROOT)} が gen_loader に触れています"
    assert not (ROOT / "generator" / "gen_loader.py").exists()
    assert not (ROOT / "pipe_in" / "gen_loader.py").exists()


def test_d0086_ac08_develop_mdにgeneratorの読まれ方がある():
    """D0086-AC-08: docs/guide/develop.md に、テストは作業フォルダの generator/ を読むこと・pipe-in-gen は入れ込み先を動かすことがある。"""
    text = (ROOT / "docs" / "guide" / "develop.md").read_text(encoding="utf-8")
    assert "作業フォルダの `generator/`" in text
    assert "入れ込み先" in text
    assert "pipe-in-gen" in text
