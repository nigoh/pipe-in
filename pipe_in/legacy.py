"""前の名前のコマンド devpipe の入口（0.3 の間だけ。0.4 で消す）。

標準エラーに案内を1行出してから、pipe-in と同じ中身を流す。終わり方と標準出力は pipe-in と同じ。
"""

from __future__ import annotations

import sys

NOTICE = "devpipe は名前が pipe-in に変わりました。pipe-in を使ってください（devpipe は 0.4 で無くなります）"


def devpipe_main(argv: list[str] | None = None) -> int:
    from .cli import main

    print(NOTICE, file=sys.stderr)
    return main(argv)
