"""`pipe_in/dev/spec_check.py` の置き場所の検査（D0085）。

標準ライブラリだけを読む・書き込みも子プロセスも使わない・コードに具体的な ID を書かない。
共有の部品は tests/test_architecture.py から借りる（そこの末尾には足さない。D0075）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from test_architecture import _imports, _outside_stdlib

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "pipe_in" / "dev" / "spec_check.py"
MODULE = "pipe_in.dev.spec_check"

FORBIDDEN_MODULES = {"subprocess", "socket", "shutil", "tempfile", "urllib", "http", "multiprocessing", "ctypes", "asyncio", "os"}
WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "touch", "unlink", "rename", "replace", "rmdir", "symlink_to", "write", "writelines", "system", "popen"}
CONCRETE_ID = re.compile(r"\b(UR|FR|NFR|DS)-\d")


def effect_problems(source: str) -> list[str]:
    """書き込み・子プロセス・ネットワークにつながる import と呼び出しを数える。"""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in FORBIDDEN_MODULES:
            found.append(f"from {node.module} import …")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS:
                found.append(f".{func.attr}(…)")
            if isinstance(func, ast.Name) and func.id in {"open", "exec", "eval", "__import__"}:
                mode = ""
                if func.id == "open" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                if func.id != "open" or set(mode) & set("wax+"):
                    found.append(f"{func.id}(…)")
    return sorted(set(found))


def test_D0085_AC_21_spec_checkは標準ライブラリだけを読む():
    """D0085-AC-21: pipe_in/dev/spec_check.py は標準ライブラリだけを import し、pipe_in の他の部品（engine・pipe・cli など）も読まない。
    部品の空の形はすでに標準ライブラリだけなので、今の作りでも通る（守り続けるための検査）。"""
    assert PATH.is_file()
    assert _outside_stdlib(PATH, MODULE) == []
    own = sorted({t for t in _imports(PATH, MODULE) if t.split(".")[0] == "pipe_in"})
    assert own == [], "pipe_in.dev の中で完結する（engine も pipe も読まない）"


def test_D0085_AC_21_spec_checkは書き込みと子プロセスを使わない():
    """D0085-AC-21: spec_check.py のソースに、書き込み・子プロセス・ネットワークの import も呼び出しも無い（読むだけ）。今の作りでも通る。"""
    assert effect_problems(PATH.read_text(encoding="utf-8")) == []


def test_D0085_AC_21_検査そのものが書き込みと子プロセスと外の部品の読み込みを見つける_守る(tmp_path):
    """D0085-AC-21: 上の検査が、違反を見つけられる（書き込み・子プロセス・標準ライブラリの外の import・具体的な ID）。"""
    bad = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def f(p):\n"
        "    Path(p).write_text('x')\n"
        "    open(p, 'w')\n"
        "    subprocess.run(['ls'])\n"
    )
    found = effect_problems(bad)
    assert "import subprocess" in found
    assert ".write_text(…)" in found
    assert "open(…)" in found
    assert effect_problems("from pathlib import Path\ndef f(p):\n    return open(p, 'r', encoding='utf-8').read()\n") == []

    outside = tmp_path / "outside.py"
    outside.write_text("import requests\nfrom pipe_in.engine import guard\n", encoding="utf-8")
    assert "requests" in _outside_stdlib(outside, "pipe_in.dev.outside")
    assert CONCRETE_ID.search('x = "UR-01"')
    assert not CONCRETE_ID.search(r're.compile(r"UR-\d{2,}")')


def test_D0085_AC_21_コードに具体的なIDを書かない():
    """D0085-AC-21: spec_check.py に UR・FR・NFR・DS の具体的な ID（`UR-01` の形）を書かない。正規表現の形（`\\d`）だけにする。今の作りでも通る。"""
    source = PATH.read_text(encoding="utf-8")
    assert CONCRETE_ID.search(source) is None
