"""D0017：パイプの段のログの Prompt 行に、段の始まりの時刻 at（UTC からのずれつき）を書く。SDK は呼ばない。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from pipe_in.engine import runner

OFFSET_TEXT = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)"


def test_d0017_ac03_prompt_line_has_at_with_offset():
    """D0017-AC-03: prompt_line の JSON 1行に _type・stage・resume・prompt・at が入り、at はオフセットつき。"""
    line = runner.prompt_line("design", "s-1", "設計して", "2026-10-17T10:00:00+09:00")
    assert "\n" not in line
    data = json.loads(line)
    assert data == {
        "_type": "Prompt",
        "stage": "design",
        "resume": "s-1",
        "prompt": "設計して",
        "at": "2026-10-17T10:00:00+09:00",
    }
    assert re.fullmatch(OFFSET_TEXT, data["at"])


def test_d0017_ac03_prompt_line_keeps_japanese_and_none_resume():
    """D0017-AC-03: 日本語はそのまま（ensure_ascii でない）、resume が None なら null。"""
    line = runner.prompt_line("red", None, "テストを書く", "2026-10-17T10:00:00+00:00")
    assert "テストを書く" in line
    assert json.loads(line)["resume"] is None


def test_d0017_ac03_with_offset_gives_offset_for_aware_time():
    """D0017-AC-03: clock.with_offset は、オフセットつきの時刻をそのまま同じ瞬間の文字にする（秒まで）。"""
    from pipe_in.engine import clock

    t = datetime(2026, 10, 17, 10, 0, 0, 123456, tzinfo=timezone(timedelta(hours=9)))
    text = clock.with_offset(t)
    assert re.fullmatch(OFFSET_TEXT, text), text
    assert datetime.fromisoformat(text) == t.replace(microsecond=0)


def test_d0017_ac03_with_offset_treats_naive_time_as_local():
    """D0017-AC-03: clock.with_offset は、オフセットなしの時刻を手元の時刻として扱い、オフセットを付ける。"""
    from pipe_in.engine import clock

    t = datetime(2026, 10, 17, 10, 0, 0)
    text = clock.with_offset(t)
    assert re.fullmatch(OFFSET_TEXT, text), text
    assert datetime.fromisoformat(text) == t.astimezone()


def test_d0017_ac03_now_with_offset_is_now():
    """D0017-AC-03: clock.now_with_offset は今の時刻をオフセットつきで返す。"""
    from pipe_in.engine import clock

    before = datetime.now().astimezone().replace(microsecond=0)
    text = clock.now_with_offset()
    after = datetime.now().astimezone()
    assert re.fullmatch(OFFSET_TEXT, text), text
    assert before <= datetime.fromisoformat(text) <= after
