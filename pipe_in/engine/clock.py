"""記録に書く時刻の書き方を1か所にする（UTC からのずれつきの ISO 8601、秒まで）。

呼ぶ側は `clock.now_with_offset()` とモジュール経由で呼ぶ（見本の作り直しとテストが差し替えられるように）。
"""

from __future__ import annotations

from datetime import datetime


def with_offset(t: datetime) -> str:
    """時刻を、UTC からのずれつきの文字にする。ずれのない時刻は手元の時刻として扱う。"""
    return t.astimezone().isoformat(timespec="seconds")


def now_with_offset() -> str:
    """今の時刻を、UTC からのずれつきの文字にする。"""
    return with_offset(datetime.now())
