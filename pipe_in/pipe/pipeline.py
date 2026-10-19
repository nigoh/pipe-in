"""パイプ（kind = "linear"）の流れ。

段を定義の順に流すのを基本に、次のことができる。
- 検証（[stages.check]）：判定やコマンドで確かめ、不合格なら on_fail の段へ戻す（max_retries まで）
- 分岐（[stages.routes]）と飛び先（next）：段が選んだ先・決めた先へ進む。"end" で終わる
- 並列（group）：同じ group の続いた段を同時に流す
人の確認（review）は、検証に通ってから取る。段を流す回数は max_steps までに限る。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine import clock
from ..engine.checkpoint import Decision
from ..engine.config import Config
from ..engine.pipeline import EXIT_MESSAGES, INPUT, BasePipeline, Exit, ShellResult, one_line, run_shell
from ..engine.runner import StageRun, StageRunner, run_stage_sdk
from . import specs as ps
from .definition import END, PipeDef, PipeStage


@dataclass
class _Step:
    """1つの段を流した結果。"""

    exit: Exit | None = None  # 止まるとき（失敗・中止・確認待ち）
    next: int | None = None  # 次に流す段（None は終わり）
    failure: str | None = None  # 検証に通らなかったときの、直す点


class _BadRoute(Exception):
    pass


def _structured(run: StageRun) -> dict[str, Any] | None:
    data = run.structured
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


class LinearPipeline(BasePipeline):
    def __init__(
        self,
        cfg: Config,
        pipe: PipeDef,
        *,
        runner: StageRunner = run_stage_sdk,
        ask: Callable[[str, Path], Decision] | None = None,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
    ) -> None:
        super().__init__(cfg, ps.build_pipe_specs(cfg, pipe), runner=runner, ask=ask, shell=shell)
        self.pipe = pipe
        self.index = {s.name: i for i, s in enumerate(pipe.stages)}

    def _revise_prompt(self, stage: str, feedback: str) -> str:
        return ps.revise_prompt(self.cfg, self.pipe, stage, feedback)

    def _artifacts(self) -> list[tuple[str, str]]:
        return [(INPUT, "依頼メモ")] + [(s.output, s.label) for s in self.pipe.stages]

    def _exit_message(self, result: Exit) -> str:
        if result == Exit.TEST_FAILED:
            return "差し戻しの上限まで検証に通りませんでした"
        return EXIT_MESSAGES[result]

    def _summary_extra(self) -> list[str]:
        checks = [h for h in self.history if "check" in h]
        if not checks:
            return []
        lines = ["", "## 検証", ""]
        for h in checks:
            c = h["check"]
            mark = "✓" if c["status"] == "pass" else "✗"
            detail = c.get("summary") or "; ".join(c.get("problems", [])[:2])
            lines.append(f"- {mark} {self.labels.get(h['stage'], h['stage'])}: {c['status']}{' — ' + one_line(detail) if detail else ''}")
        return lines

    # ---- 入口 ---------------------------------------------------------

    async def run(self, input_text: str | None, from_stage: str | None = None) -> Exit:
        names = self.stage_order
        start_name = from_stage or names[0]
        if start_name not in names:
            raise SystemExit(f"--from には {', '.join(names)} のどれかを指定してください")
        start = names.index(start_name)
        if input_text is None and self.pipe.input == "required" and not self._doc_ready(INPUT):
            raise SystemExit(f"パイプ「{self.pipe.name}」には依頼メモが要ります。--input か --text で渡してください")
        missing = [
            self.cfg.rel(self.doc(s.output))
            for s in self.pipe.stages[:start]
            if not self._doc_ready(s.output) and not s.routes and s.next is None and not s.group
        ]
        if missing:
            raise SystemExit(f"{self.labels[start_name]}から始めるには次のファイルが必要です: {', '.join(missing)}")
        self.cfg.work_dir.mkdir(parents=True, exist_ok=True)
        if input_text is not None:
            self.doc(INPUT).write_text(input_text.strip() + "\n", encoding="utf-8")
        return self._finish(await self._flow(start))

    async def review(self, decision: Decision) -> Exit:
        """確認で止まった実行に答えて、続きを流す。承認なら、止まったときに決まっていた次の段から。"""
        pending = self._load_pending()
        stage = pending["stage"]
        self.pending = None
        if decision.action == "approve":
            self.history.append({"stage": stage, "review": "approved"})
            self._save_state()
            nxt = pending.get("next")
            if nxt is None:  # next を残す前の記録：定義の次の段へ
                i = self.index[stage] + 1
                nxt = self.stage_order[i] if i < len(self.stage_order) else END
            result = Exit.PASSED if nxt == END else await self._flow(self.index[nxt])
        elif decision.action == "revise":
            self.history.append({"stage": stage, "review": "revise", "feedback": decision.feedback})
            first = (self._revise_prompt(stage, decision.feedback), pending["session_id"])
            result = await self._flow(self.index[stage], first=first)
        else:
            self.history.append({"stage": stage, "review": "quit"})
            result = Exit.STOPPED_BY_HUMAN
        return self._finish(result)

    async def _stages_from(self, start: int, *, first: tuple[str, str] | None = None) -> Exit:
        return await self._flow(start, first=first)

    # ---- 流れ ---------------------------------------------------------

    async def _flow(self, start: int, *, first: tuple[str, str] | None = None) -> Exit:
        stages = self.pipe.stages
        steps = 0
        retries: dict[str, int] = {}
        notes: dict[str, str] = {}
        i: int | None = start
        while i is not None:
            s = stages[i]
            if s.group:
                members = self._group_members(i)
                steps += len(members)
                if steps > self.pipe.max_steps:
                    return self._too_many_steps()
                results = await asyncio.gather(*(self._member(j) for j in members))
                for r in results:
                    if r is not None:
                        return r
                after = members[-1] + 1
                i = after if after < len(stages) else None
                continue

            steps += 1
            if steps > self.pipe.max_steps:
                return self._too_many_steps()
            step = await self._step(i, first=first if i == start else None, note=notes.pop(s.name, None))
            first = None
            if step.failure is not None:
                assert s.check is not None
                used = retries.get(s.name, 0)
                if used >= s.check.max_retries:
                    print(f"  ✗ {s.label}: 差し戻しの上限（{s.check.max_retries} 回）まで検証に通りませんでした")
                    return Exit.TEST_FAILED
                retries[s.name] = used + 1
                target = s.check.on_fail or s.name
                notes[target] = step.failure
                print(f"  ↩ {self.labels[target]}へ戻します（残り {s.check.max_retries - used - 1} 回）", flush=True)
                i = self.index[target]
                continue
            if step.exit is not None:
                return step.exit
            i = step.next
        return Exit.PASSED

    def _group_members(self, i: int) -> list[int]:
        g = self.pipe.stages[i].group
        j = i
        while j < len(self.pipe.stages) and self.pipe.stages[j].group == g:
            j += 1
        return list(range(i, j))

    async def _member(self, i: int) -> Exit | None:
        """グループの段：検証に通らなければ、自分だけをやり直す。"""
        s = self.pipe.stages[i]
        tries = 0
        note: str | None = None
        while True:
            step = await self._step(i, note=note)
            if step.failure is None:
                return step.exit
            assert s.check is not None
            if tries >= s.check.max_retries:
                print(f"  ✗ {s.label}: 差し戻しの上限（{s.check.max_retries} 回）まで検証に通りませんでした")
                return Exit.TEST_FAILED
            tries += 1
            note = step.failure

    def _too_many_steps(self) -> Exit:
        print(f"  ✗ 段を流した回数が max_steps（{self.pipe.max_steps}）を超えました。飛び先や差し戻しが回り続けていないか見てください")
        self.warnings.append(f"段を流した回数が max_steps（{self.pipe.max_steps}）を超えたため止めました")
        return Exit.STAGE_ERROR

    async def _step(self, i: int, *, first: tuple[str, str] | None = None, note: str | None = None) -> _Step:
        s = self.pipe.stages[i]
        if first is not None:
            run = await self._run(s.name, first[0], resume=first[1], note="指摘を反映")
        else:
            prompt = ps.stage_prompt(self.cfg, self.pipe, i, failure_note=note)
            run = await self._run(s.name, prompt, note="検証の指摘を反映" if note else "")
        while True:
            if run.is_error or not self._doc_ready(s.output):
                print(f"  ✗ {s.label}の成果物 {self.cfg.rel(self.doc(s.output))} を作れませんでした")
                return _Step(exit=Exit.STAGE_ERROR)
            failure = self._check(s, run)
            if failure is not None:
                return _Step(failure=failure)
            try:
                nxt = self._next_of(i, run)
            except _BadRoute as e:
                print(f"  ✗ {s.label}: {e}")
                return _Step(exit=Exit.STAGE_ERROR)
            if not s.review or self.cfg.auto_approve:
                return _Step(next=nxt)
            if self.cfg.pause_for_review:
                self.pending = {
                    "stage": s.name,
                    "doc": self.cfg.rel(self.doc(s.output)),
                    "session_id": run.session_id,
                    "next": END if nxt is None else self.stage_order[nxt],
                    "since": clock.now_with_offset(),
                }
                return _Step(exit=Exit.AWAITING_REVIEW)
            decision = self.ask(s.name, self.doc(s.output))
            if decision.action == "approve":
                self.history.append({"stage": s.name, "review": "approved"})
                self._save_state()
                return _Step(next=nxt)
            if decision.action == "quit":
                self.history.append({"stage": s.name, "review": "quit"})
                return _Step(exit=Exit.STOPPED_BY_HUMAN)
            self.history.append({"stage": s.name, "review": "revise", "feedback": decision.feedback})
            run = await self._run(s.name, self._revise_prompt(s.name, decision.feedback), resume=run.session_id, note="指摘を反映")

    def _check(self, s: PipeStage, run: StageRun) -> str | None:
        """検証して、不合格なら直す点（箇条書きの文）を返す。検証がなければ None。"""
        c = s.check
        if c is None:
            return None
        problems: list[str] = []
        record: dict[str, Any] = {}
        if c.verdict:
            data = _structured(run)
            if data is None or data.get("status") not in ("pass", "fail"):
                problems.append("判定（status: pass / fail）が返りませんでした")
            else:
                record["summary"] = str(data.get("summary", ""))
                if data["status"] == "fail":
                    found = [str(p) for p in data.get("problems", []) if str(p).strip()]
                    problems += found or [record["summary"] or "判定が fail でした"]
        if c.command:
            print(f"  確認用コマンドを実行: {c.command}", flush=True)
            res = self.shell(c.command, self.cfg.project_dir, c.timeout_sec)
            record.update({"command": c.command, "returncode": res.returncode})
            if res.returncode != 0:
                problems.append(
                    f"確認用コマンド `{c.command}` が失敗しました（終了コード {res.returncode}）\n```\n{res.output_tail[-2000:]}\n```"
                )
        status = "fail" if problems else "pass"
        self.history.append({"stage": s.name, "check": {"status": status, "problems": problems, **record}})
        self._save_state()
        mark = "✓ 検証に合格" if status == "pass" else "✗ 検証に不合格"
        print(f"  {mark}: {one_line(record.get('summary') or '; '.join(problems))}", flush=True)
        return "\n".join(f"- {p}" for p in problems) if problems else None

    def _next_of(self, i: int, run: StageRun) -> int | None:
        s = self.pipe.stages[i]
        if s.routes:
            data = _structured(run) or {}
            choice = data.get("choice")
            if choice not in s.routes:
                raise _BadRoute(f"次に進む先（choice）が返りませんでした（{' / '.join(s.routes)} のどれか。返った値: {choice!r}）")
            target = s.routes[choice]
            self.history.append({"stage": s.name, "route": choice, "next": target})
            self._save_state()
            print(f"  → {choice}: {'終わり' if target == END else self.labels[target]}へ", flush=True)
            return None if target == END else self.index[target]
        if s.next is not None:
            return None if s.next == END else self.index[s.next]
        return i + 1 if i + 1 < len(self.pipe.stages) else None
