"""D0031（pipe-in live watch）のテストが共有する偽物と補助。テストの補助で、本体には入らない。

- FakeTime  : 偽の単調な時計と眠り。眠った分だけ時計を進め、k 回目の眠りの終わりに「steps[k]」（記録を書き換える関数）を呼ぶ。
              k 回目の steps は、k+1 回目の読みの前に効く。本物の時間は待たない。
- FakeOut   : 行を集める偽の標準出力。行が1つ完成した瞬間に on_line を呼ぶ。write・flush の順番も覚える。
- Rec       : pipe_in.dev.record.Recorder（本体と同じ形で state.json を書く）を、呼ぶたびに偽の時刻を進める形で包んだもの。
- drive     : live_watch.watch を偽の部品で流し、Result を返す。
記録はすべて tmp_path の中に作る。SDK は呼ばない。
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import live_support as ls
from pipe_in.dev.record import Recorder
from pipe_in.engine import live, live_watch
from pipe_in.engine.config import load_config

NOW = ls.NOW
LINE_KEYS = ["event", "seq", "final", "empty"]
MAX_SLEEPS = 5000  # 止まらない実装でテストが終わらなくならないための安全弁


def _no_constant(name: str) -> Any:
    raise AssertionError(f"行に {name} が出ている（厳格な JSON ではない）")


def parse_line(line: str) -> dict[str, Any]:
    return json.loads(line, parse_constant=_no_constant)


class FakeTime:
    """偽の時計・眠り・今。advance(n, s) は n 回目の眠り（s 秒）で時計をどれだけ進めるか（既定は s）。"""

    def __init__(self, steps: dict[int, Callable[[], None]] | None = None, *, start: float = 1000.0,
                 advance: Callable[[int, float], float] | None = None, hook: Callable[[int], None] | None = None) -> None:
        self.t = start
        self.start = start
        self.steps = dict(steps or {})
        self.advance = advance
        self.hook = hook
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def now(self) -> datetime:
        return NOW + timedelta(seconds=self.t - self.start)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        n = len(self.sleeps)
        if n > MAX_SLEEPS:
            raise AssertionError("眠りが多すぎる（止まる条件が働いていない）")
        if self.hook is not None:
            self.hook(n)
        self.t += seconds if self.advance is None else self.advance(n, seconds)
        step = self.steps.get(n)
        if step is not None:
            step()

    @property
    def elapsed(self) -> float:
        return self.t - self.start


class FakeOut:
    """行を集める偽の標準出力。write_error(n)・flush_error(n) は n 回目の write・flush で投げる例外（なければ None）。"""

    def __init__(self, *, on_line: Callable[[str, FakeTime], None] | None = None,
                 write_error: Callable[[int], BaseException | None] | None = None,
                 flush_error: Callable[[int], BaseException | None] | None = None) -> None:
        self.events: list[tuple[str, str]] = []
        self.chunks: list[str] = []
        self.complete: list[str] = []
        self.times: list[float] = []
        self.on_line = on_line
        self.write_error = write_error
        self.flush_error = flush_error
        self.ft: FakeTime | None = None
        self.write_calls = 0
        self.flush_calls = 0
        self._buf = ""

    def write(self, s: str) -> int:
        self.write_calls += 1
        if self.write_error is not None:
            exc = self.write_error(self.write_calls)
            if exc is not None:
                raise exc
        self.events.append(("write", s))
        self.chunks.append(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.complete.append(line)
            self.times.append(self.ft.elapsed if self.ft is not None else 0.0)
            if self.on_line is not None:
                self.on_line(line, self.ft)  # type: ignore[arg-type]
        return len(s)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_error is not None:
            exc = self.flush_error(self.flush_calls)
            if exc is not None:
                raise exc
        self.events.append(("flush", ""))

    @property
    def text(self) -> str:
        return "".join(self.chunks)

    def flushed_after_every_line(self) -> bool:
        """行が完成するたびに、次の write より前に flush が呼ばれている（最後の行のあとも）。"""
        pending = False
        for kind, payload in self.events:
            if kind == "write":
                if pending:
                    return False
                if "\n" in payload:
                    pending = True
            else:
                pending = False
        return not pending


@dataclass
class Result:
    code: int
    out: FakeOut
    err: io.StringIO
    time: FakeTime
    reads: int
    write_attempts: int
    write_ok: int
    lines: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.out.text

    @property
    def errtext(self) -> str:
        return self.err.getvalue()

    @property
    def events(self) -> list[str]:
        return [x["event"] for x in self.lines]

    @property
    def seqs(self) -> list[int]:
        return [x["seq"] for x in self.lines]


def drive(work: Path, out: Path, *, steps: dict[int, Callable[[], None]] | None = None, interval: float = 2.0,
          timeout: float = 600.0, hide: Any = (), advance: Callable[[int, float], float] | None = None,
          sleep_hook: Callable[[int], None] | None = None,
          read_fault: Callable[[int], BaseException | None] | None = None,
          open_fault: Callable[[int], BaseException | None] | None = None,
          write_fault: Callable[[int], BaseException | None] | None = None,
          stdout: FakeOut | None = None) -> Result:
    """live_watch.watch を偽の時計・眠り・標準出力で流す。読みと書きの回数を数える。"""
    ft = FakeTime(steps, advance=advance, hook=sleep_hook)
    so = stdout if stdout is not None else FakeOut()
    so.ft = ft
    se = io.StringIO()
    counts = {"reads": 0, "opens": 0, "attempts": 0, "ok": 0}

    def read_state(w: Path) -> Any:
        counts["reads"] += 1
        exc = read_fault(counts["reads"]) if read_fault else None
        if exc is not None:
            raise exc
        return live.read_state(w)

    def read_open_at(w: Path, state: Any) -> Any:
        counts["opens"] += 1
        exc = open_fault(counts["opens"]) if open_fault else None
        if exc is not None:
            raise exc
        return live.read_open_at(w, state)

    def write(path: Path, data: bytes) -> None:
        counts["attempts"] += 1
        exc = write_fault(counts["attempts"]) if write_fault else None
        if exc is not None:
            raise exc
        live_watch.write_atomic(path, data)
        counts["ok"] += 1

    code = live_watch.watch(
        work, out, interval=interval, timeout=timeout, hide=hide,
        clock=ft.clock, sleep=ft.sleep, now=ft.now,
        read_state=read_state, read_open_at=read_open_at, write=write, stdout=so, stderr=se,
    )
    res = Result(code, so, se, ft, counts["reads"], counts["attempts"], counts["ok"])
    res.lines = [parse_line(x) for x in so.complete]
    return res


class Rec:
    """Recorder を、呼ぶたびに偽の時刻を 60 秒進める形で包む（record の各コマンドと同じ形で state.json を書く）。"""

    def __init__(self, project: Path, t: datetime = datetime(2026, 10, 17, 10, 0, 0)) -> None:
        project.mkdir(parents=True, exist_ok=True)
        self.t = t
        self.r = Recorder(load_config(project), now=lambda: self.t)
        self.work = ls.work_of(project.resolve())

    def __getattr__(self, name: str) -> Callable[..., Any]:
        method = getattr(self.r, name)

        def call(*a: Any, **k: Any) -> Any:
            try:
                return method(*a, **k)
            finally:
                self.t += timedelta(seconds=60)

        return call


def out_path(tmp_path: Path) -> Path:
    d = tmp_path / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d / "live.json"


def expected_bytes(work: Path, now: datetime, hide: Any = ()) -> bytes:
    """同じ記録・同じ「今」で live snapshot が出すバイト列。"""
    state = live.read_state(work)
    return live.dumps(live.build_snapshot(state, live.read_open_at(work, state), now=now, hide=hide)).encode("utf-8")


def tree(root: Path) -> dict[str, tuple[bytes, int] | None]:
    found: dict[str, tuple[bytes, int] | None] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        found[rel] = (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() and not p.is_symlink() else None
    return found


def listing(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())
