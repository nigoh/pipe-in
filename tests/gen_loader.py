"""テストが、いつも作業フォルダの generator/ を pipe_in_generator として読むための補助（D0086）。

開発用の入れ込み（pip install -e）が別の checkout を指していても、そちらは使わない。
入れ込み先を import してしまうと、worktree で generator/ を直しても、テストは直す前のコードを見る。

- load(gen_dir)：gen_dir（作業フォルダの generator/）から pipe_in_generator を作って sys.modules に入れる。
- verify(gen_dir)：読み込み済みの pipe_in_generator とそのサブモジュールが gen_dir の下かを確かめ、違えば落とす。
- CHILD_PRELUDE：子プロセスのスクリプトの頭に付ける文字。python [-I] -c <CHILD_PRELUDE + 本体> <LOADER_PATH> <gen_dir> の形で起こす。

標準ライブラリだけ。標準出力には何も書かない（子プロセスの出力を読むテストがあるため）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

NAME = "pipe_in_generator"
LOADER_PATH = Path(__file__)

# 子プロセスの頭：sys.argv[1] の補助をパスで読み、sys.argv[2]（generator/ のフォルダ）を読み込む。-I（隔離）でも動く
CHILD_PRELUDE = (
    "import importlib.util as _u, sys as _s\n"
    "_sp = _u.spec_from_file_location('gen_loader', _s.argv[1])\n"
    "_gl = _u.module_from_spec(_sp); _s.modules['gen_loader'] = _gl; _sp.loader.exec_module(_gl)\n"
    "_gl.load(_s.argv[2])\n"
)


def _under(file: str | None, base: Path) -> bool:
    if not file:
        return False
    try:
        Path(file).resolve().relative_to(base)
    except (OSError, ValueError):
        return False
    return True


def verify(gen_dir: str | Path) -> None:
    """読み込み済みの pipe_in_generator が gen_dir のものかを確かめる。違えば RuntimeError。"""
    base = Path(gen_dir).resolve()
    module = sys.modules.get(NAME)
    actual = getattr(module, "__file__", None) if module is not None else None
    fix = (
        "直し方：この作業フォルダで pip install -e '.[dev]' をし直すか、"
        "tests/gen_loader.py の load() で読み込んでください。"
    )
    if module is None or not _under(actual, base):
        raise RuntimeError(
            f"テストが読んでいる {NAME} は、この作業フォルダの generator/ ではありません。"
            f"実際の場所: {actual}／期待した場所: {base}。{fix}"
        )
    for name, sub in list(sys.modules.items()):
        if not name.startswith(NAME + "."):
            continue
        sub_file = getattr(sub, "__file__", None)
        if sub_file and not _under(sub_file, base):
            raise RuntimeError(
                f"テストが読んでいる {name} は、この作業フォルダの generator/ ではありません。"
                f"実際の場所: {sub_file}／期待した場所: {base}。{fix}"
            )


def load(gen_dir: str | Path) -> None:
    """gen_dir（generator/）を pipe_in_generator として読み込む。先に別の場所のものが入っていたら、外して作り直す。"""
    base = Path(gen_dir).resolve()
    root = str(base.parent)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)  # generator/ が読む pipe_in も、同じ作業フォルダのものにする
    current = sys.modules.get(NAME)
    if current is None or not _under(getattr(current, "__file__", None), base):
        for name in [n for n in sys.modules if n == NAME or n.startswith(NAME + ".")]:
            del sys.modules[name]
        spec = importlib.util.spec_from_file_location("pipe_in_generator", base / "__init__.py", submodule_search_locations=[str(base)])
        if spec is None or spec.loader is None:
            raise RuntimeError(f"{base} から {NAME} を読めません（__init__.py がありません）")
        module = importlib.util.module_from_spec(spec)
        sys.modules[NAME] = module
        spec.loader.exec_module(module)
    verify(base)
