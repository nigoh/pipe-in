"""終わった記録を archive/<日時>/ へ移す（開発フローの記録と、会話の中で流した記録が共有する）。"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

ARCHIVE = "archive"


def archive_run(work_dir: Path, started_at: object, names: Iterable[str], fallback_stamp: str) -> Path:
    """work_dir の中の names（ファイルかフォルダ。あるものだけ）を archive/<日時>/ へ移し、移した先を返す。

    日時は記録の開始時刻（started_at）から作る。無いときは fallback_stamp を使う。同じ名前があれば -2、-3 … を付ける。
    """
    stamp = str(started_at or fallback_stamp).replace("-", "").replace(":", "").replace("T", "-")
    dest = work_dir / ARCHIVE / stamp
    n = 2
    while dest.exists():
        dest = work_dir / ARCHIVE / f"{stamp}-{n}"
        n += 1
    dest.mkdir(parents=True)
    for name in names:
        src = work_dir / name
        if src.exists():
            shutil.move(str(src), str(dest / name))
    return dest
