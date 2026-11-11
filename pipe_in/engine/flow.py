"""記録の flow（流した回数と段ごとの戻した回数）の読み方（D0081・D0090）。

SDK の道（pipe_in.pipe.pipeline）も会話の道（pipe_in.pipe.chat）もここで読む。標準ライブラリだけを使う。
"""

from __future__ import annotations

from typing import Any


def read_flow(raw: Any) -> tuple[int, dict[str, int]]:
    """記録の flow を読む。返すのは (流した回数, 段の名前 → 戻した回数)。
    形が違う部分・負の数・小数・真偽値は 0 として読む（落ちない。読めない記録で続きを止めない）。"""

    def count(v: Any) -> int:
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0

    if not isinstance(raw, dict):
        return 0, {}
    retries_raw = raw.get("retries")
    retries = {k: count(v) for k, v in retries_raw.items() if isinstance(k, str)} if isinstance(retries_raw, dict) else {}
    return count(raw.get("steps")), retries
