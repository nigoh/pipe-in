"""前の名前のコマンド devpipe-gen の入口（0.3 の間だけ。0.4 で消す）。

案内は標準エラーにだけ1行出す。標準出力には何も書かない（guard-hook の JSON を壊さないため）。
古いプラグインのフック（devpipe-gen guard-hook）も、これで同じに動く。
"""

from __future__ import annotations

import sys

NOTICE = "devpipe-gen は名前が pipe-in-gen に変わりました。pipe-in-gen を使ってください（devpipe-gen は 0.4 で無くなります）"


def devpipe_gen_main(argv: list[str] | None = None) -> int:
    from .cli import main

    print(NOTICE, file=sys.stderr)
    return main(argv)
