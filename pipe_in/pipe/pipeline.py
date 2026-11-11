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
from ..engine.flow import read_flow
from ..engine.pipeline import EXIT_MESSAGES, INPUT, BasePipeline, Exit, ShellResult, one_line, run_shell
from ..engine.runner import StageRun, StageRunner, run_stage_sdk
from . import after, judge
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


def _judge_line(j: dict[str, Any]) -> str:
    """99_summary.md の審査の1行。"""
    if not j.get("valid", True):
        return "  - 審査: 返りが決まりに合いませんでした"
    overall = j.get("overall")
    line = f"  - 審査: 平均 {'なし' if overall is None else overall} / しきい値 {j.get('threshold')} → {j.get('status')}"
    must = j.get("must") or {}
    violated = [n for n, m in must.items() if m.get("violated") is True]
    unchecked = [n for n, m in must.items() if m.get("violated") is None]
    parts = ([f"must の違反: {'、'.join(violated)}"] if violated else []) + ([f"確かめられず: {'、'.join(unchecked)}"] if unchecked else [])
    return line + (f"（{'、'.join(parts)}）" if parts else "")


def verdict_outcome(data: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    """判定（status・summary・problems）の読み。返すのは (直す点の一覧, 記録に足す項目)。合格なら直す点は空。"""
    if data is None or data.get("status") not in ("pass", "fail"):
        return ["判定（status: pass / fail）が返りませんでした"], {}
    record: dict[str, Any] = {"summary": str(data.get("summary", ""))}
    problems: list[str] = []
    if data["status"] == "fail":
        found = [str(p) for p in data.get("problems", []) if str(p).strip()]
        problems = found or [record["summary"] or "判定が fail でした"]
    return problems, record


def command_outcome(
    command: str, cwd: Path, timeout: int, shell: Callable[[str, Path, int], ShellResult]
) -> tuple[list[str], dict[str, Any]]:
    """確認用コマンドを流した結果。返すのは (直す点の一覧, 記録に足す項目)。終了コード 0 なら直す点は空。"""
    res = shell(command, cwd, timeout)
    record: dict[str, Any] = {"command": command, "returncode": res.returncode}
    problems: list[str] = []
    if res.returncode != 0:
        problems.append(f"確認用コマンド `{command}` が失敗しました（終了コード {res.returncode}）\n```\n{res.output_tail[-2000:]}\n```")
    return problems, record


def stage_checks(pipe: PipeDef) -> dict[str, dict[str, Any]]:
    """判定のある段の設定（記録の stages[].check）。自分をやり直すときの on_fail は None。"""
    return {
        s.name: {"on_fail": s.check.on_fail if s.check.on_fail not in (None, "", s.name) else None, "max_retries": s.check.max_retries}
        for s in pipe.stages
        if s.check
    }


def exit_message(result: Exit) -> str:
    """パイプ（linear）の終了の文。"""
    if result == Exit.TEST_FAILED:
        return "差し戻しの上限まで検証に通りませんでした"
    return EXIT_MESSAGES[result]


def check_summary_lines(history: list[dict[str, Any]], labels: dict[str, str]) -> list[str]:
    """99_summary.md の「検証」の節。検証の記録が無ければ空。"""
    checks = [h for h in history if "check" in h]
    if not checks:
        return []
    lines = ["", "## 検証", ""]
    for h in checks:
        c = h["check"]
        mark = "✓" if c["status"] == "pass" else "✗"
        detail = c.get("summary") or "; ".join(c.get("problems", [])[:2])
        lines.append(f"- {mark} {labels.get(h['stage'], h['stage'])}: {c['status']}{' — ' + one_line(detail) if detail else ''}")
        if c.get("judge"):
            lines.append(_judge_line(c["judge"]))
    return lines


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
        # 流した回数と、段ごとに戻した回数。確認をはさんでも引き継ぐので、記録（flow）に書く
        self.flow_steps = 0
        self.flow_retries: dict[str, int] = {}

    def receive(self, record: dict[str, Any] | None) -> None:
        """前のパイプの記録を受ける（--after）。受けた元で、後ろの段の書けない所（前の記録）を作り直す（D0069-FR-15）。
        読めない形の受けた元は、守りを外して流さないよう止める。"""
        if record is not None:
            problem = after.check_received(record)
            if problem is not None:
                raise SystemExit(f"state.json の received_from が読めません（{problem}）。前のパイプからの受け渡しを、流し直してください")
        self.received = record
        previous = None if record is None else after.guard_for(record, self.cfg.rel(self.cfg.work_dir.parent))
        self.specs = ps.build_pipe_specs(self.cfg, self.pipe, previous=previous)

    def _revise_prompt(self, stage: str, feedback: str) -> str:
        return ps.revise_prompt(self.cfg, self.pipe, stage, feedback)

    def _artifacts(self) -> list[tuple[str, str]]:
        return [(INPUT, "依頼メモ")] + [(s.output, s.label) for s in self.pipe.stages]

    def _exit_message(self, result: Exit) -> str:
        return exit_message(result)

    def _stage_checks(self) -> dict[str, dict[str, Any]]:
        """判定のある段の設定（記録の stages[].check）。"""
        return stage_checks(self.pipe)

    def _stage_groups(self) -> dict[str, str]:
        """枠（並列の束）の中の段の枠の名前（記録の stages[].group）。"""
        return {s.name: s.group for s in self.pipe.stages if s.group}

    def _flow_record(self) -> dict[str, Any] | None:
        return {"steps": self.flow_steps, "retries": dict(self.flow_retries)}

    def _next_attempt(self, stage: str) -> int:
        """この段の検証が何回目か。記録（review の再開で戻した分も含む）の check の数 + 1。"""
        return sum(1 for h in self.history if h.get("stage") == stage and "check" in h) + 1

    def _summary_extra(self) -> list[str]:
        return check_summary_lines(self.history, self.labels)

    # ---- 入口 ---------------------------------------------------------

    async def run(self, input_text: str | None, from_stage: str | None = None) -> Exit:
        names = self.stage_order
        start_name = from_stage or names[0]
        if start_name not in names:
            raise SystemExit(f"--from には {', '.join(names)} のどれかを指定してください")
        start = names.index(start_name)
        # 回数は 0 から数える（--from も同じ。前の記録の flow は読まない）
        self.flow_steps = 0
        self.flow_retries = {}
        if from_stage is not None:
            # 途中の段からの再開は、この記録の受けた元をそのまま使う（前の記録は読み直さない。D0069-FR-11）
            self.receive(self._state_data().get("received_from"))
            self._resume_note()
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
        self._clear_reply(mark=True)
        if input_text is not None:
            self.doc(INPUT).write_text(input_text.strip() + "\n", encoding="utf-8")
        self._settle_name(input_text)
        return self._finish(await self._flow(start))

    async def review(self, decision: Decision) -> Exit:
        """確認で止まった実行に答えて、続きを流す。承認なら、止まったときに決まっていた次の段から。"""
        pending = self._load_pending()
        # 止まる前までの回数を記録から引き継ぐ（無い・壊れた部分は 0）
        self.flow_steps, self.flow_retries = read_flow(self._state_data().get("flow"))
        self._clear_reply(mark=True)
        self._resume_note()
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
        notes: dict[str, str] = {}
        i: int | None = start
        while i is not None:
            s = stages[i]
            if s.group:
                members = self._group_members(i)
                self.flow_steps += len(members)
                if self.flow_steps > self.pipe.max_steps:
                    return self._too_many_steps()
                results = await asyncio.gather(*(self._member(j) for j in members))
                for r in results:
                    if r is not None:
                        return r
                after = members[-1] + 1
                i = after if after < len(stages) else None
                continue

            # 人の revise で流し直す1回（first）は、数えず上限も見ない
            if first is None:
                self.flow_steps += 1
                if self.flow_steps > self.pipe.max_steps:
                    return self._too_many_steps()
            step = await self._step(i, first=first if i == start else None, note=notes.pop(s.name, None))
            first = None
            if step.failure is not None:
                assert s.check is not None
                used = self.flow_retries.get(s.name, 0)
                if used >= s.check.max_retries:
                    print(f"  ✗ {s.label}: 差し戻しの上限（{s.check.max_retries} 回）まで検証に通りませんでした")
                    return Exit.TEST_FAILED
                self.flow_retries[s.name] = used + 1
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
            prompt = ps.stage_prompt(self.cfg, self.pipe, i, failure_note=note, received=self.received)
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
            decision = self._confirm(s.name, self.doc(s.output))
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
            found, extra = verdict_outcome(_structured(run))
            problems += found
            record.update(extra)
        if c.judge:
            data = _structured(run)
            outcome = judge.evaluate(
                data.get("judge") if data else None,
                [i.name for i in c.judge.criteria],
                [i.name for i in c.judge.must],
                c.judge.threshold,
            )
            problems += outcome.problems
            record["judge"] = outcome.to_record()
        if c.command:
            print(f"  確認用コマンドを実行: {c.command}", flush=True)
            found, extra = command_outcome(c.command, self.cfg.project_dir, c.timeout_sec, self.shell)
            problems += found
            record.update(extra)
        status = "fail" if problems else "pass"
        attempt = self._next_attempt(s.name)
        self.history.append({"stage": s.name, "check": {"attempt": attempt, "status": status, "problems": problems, **record}})
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
