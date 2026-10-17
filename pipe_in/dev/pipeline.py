"""開発フローの流れ：要件定義 → 設計 → テスト先行 → 実装 → 検証。テストが通らなければ実装へ差し戻す。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..engine.checkpoint import Decision
from ..engine.config import Config
from ..engine.pipeline import EXIT_MESSAGES, BasePipeline, Exit, ShellResult, one_line, run_shell
from ..engine.runner import StageRun, StageRunner, run_stage_sdk
from . import specs as st
from .specs import STAGE_LABELS, STAGES


@dataclass
class Verdict:
    status: str  # pass / fail / blocked
    summary: str
    failures: list[dict[str, str]] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    command_check: dict[str, Any] | None = None


def parse_verdict(run: StageRun) -> Verdict:
    data = run.structured
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict) and data.get("status") in ("pass", "fail", "blocked"):
        return Verdict(
            status=data["status"],
            summary=str(data.get("summary", "")),
            failures=[f for f in data.get("failures", []) if isinstance(f, dict)],
            commands=[str(c) for c in data.get("commands", [])],
        )
    reason = "テストの段から判定が返りませんでした"
    if run.is_error:
        reason += f"（{run.subtype}: {'; '.join(run.errors) or 'エラー'}）"
    return Verdict(status="blocked", summary=reason)


AC_ID = re.compile(r"\bAC-\d+\b")


def parse_red(run: StageRun) -> dict[str, Any] | None:
    data = run.structured
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict) and data.get("status") in ("red", "blocked"):
        return data
    return None


def failure_note(v: Verdict) -> str:
    lines = [f"- 判定: {v.status}", f"- 要約: {v.summary}"]
    for f in v.failures:
        lines.append(f"- {f.get('criterion', '?')}: {f.get('detail', '')}")
    if v.command_check and v.command_check.get("returncode") != 0:
        lines.append(f"- 確認用コマンド `{v.command_check['command']}` が失敗しました（終了コード {v.command_check['returncode']}）")
        lines.append("```\n" + v.command_check["output_tail"][-2000:] + "\n```")
    return "\n".join(lines)


class DevPipeline(BasePipeline):
    def __init__(
        self,
        cfg: Config,
        *,
        runner: StageRunner = run_stage_sdk,
        ask: Callable[[str, Path], Decision] | None = None,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
    ) -> None:
        super().__init__(cfg, st.build_specs(cfg), runner=runner, ask=ask, shell=shell)

    def _revise_prompt(self, stage: str, feedback: str) -> str:
        return st.revise_prompt(self.cfg, stage, feedback)

    def _exit_message(self, result: Exit) -> str:
        return "テストまで合格しました" if result == Exit.PASSED else EXIT_MESSAGES[result]

    def _artifacts(self) -> list[tuple[str, str]]:
        return [
            (st.INPUT, "要件メモ"),
            (st.REQUIREMENTS, "要件定義書"),
            (st.DESIGN, "設計書"),
            (st.RED, "テスト先行の記録"),
            (st.IMPLEMENTATION, "実装の記録"),
            (st.TEST_REPORT, "テスト報告"),
        ]

    def _summary_extra(self) -> list[str]:
        verdicts = [h for h in self.history if "verdict" in h]
        if not verdicts:
            return []
        lines = ["", "## テストの判定", ""]
        for h in verdicts:
            v = h["verdict"]
            lines.append(f"- {h['attempt']} 回目: {v['status']} — {v['summary']}")
        return lines

    # ---- テスト先行（TDD の赤） -----------------------------------------

    def _required_acs(self) -> list[str]:
        if not self._doc_ready(st.REQUIREMENTS):
            return []
        text = self.doc(st.REQUIREMENTS).read_text(encoding="utf-8")
        return list(dict.fromkeys(AC_ID.findall(text)))

    def _check_red_command(self) -> None:
        if not self.cfg.test_command:
            return
        print(f"  確認用コマンドを実行（落ちることの確認）: {self.cfg.test_command}", flush=True)
        res = self.shell(self.cfg.test_command, self.cfg.project_dir, self.cfg.test_timeout_sec)
        self.history.append({"stage": "red", "command_check": {"command": self.cfg.test_command, "returncode": res.returncode}})
        if res.returncode == 0:
            msg = "テスト先行のあと、確認用コマンドが通りました。テストが赤になっていません（実装前から満たされているか、テストが何も確かめていない可能性）"
            self.warnings.append(msg)
            print(f"  ⚠ {msg}", flush=True)
        self._save_state()

    async def _red_stage(self, prompt: str | None = None, *, resume: str | None = None, note: str = "") -> Exit | None:
        run = await self._run("red", prompt or st.red_prompt(self.cfg), resume=resume, note=note)
        asked_missing = False
        while True:
            result = parse_red(run)
            if run.is_error or result is None or not self._doc_ready(st.RED):
                print(f"  ✗ テスト先行の記録 {self.cfg.rel(self.doc(st.RED))} か結果を受け取れませんでした")
                return Exit.STAGE_ERROR
            self.history.append({"stage": "red", "result": result})
            self._save_state()
            if result["status"] == "blocked":
                print(f"  ■ 実行できず: {result.get('summary', '')}")
                return Exit.BLOCKED
            covered = {str(t.get("criterion")) for t in result.get("tests", []) if isinstance(t, dict)}
            missing = [ac for ac in self._required_acs() if ac not in covered]
            if missing:
                if asked_missing:
                    print(f"  ✗ テストのない受け入れ基準が残りました: {', '.join(missing)}")
                    return Exit.STAGE_ERROR
                asked_missing = True
                run = await self._run(
                    "red", st.red_missing_prompt(self.cfg, missing), resume=run.session_id, note="抜けた受け入れ基準を補う"
                )
                continue
            print(f"  ● 赤: {result.get('summary', '')}")
            self._check_red_command()
            if self.cfg.auto_approve:
                return None
            if self.cfg.pause_for_review:
                return self._pause("red", st.RED, run)
            decision = self.ask("red", self.doc(st.RED))
            if decision.action == "approve":
                self.history.append({"stage": "red", "review": "approved"})
                self._save_state()
                return None
            if decision.action == "quit":
                self.history.append({"stage": "red", "review": "quit"})
                return Exit.STOPPED_BY_HUMAN
            self.history.append({"stage": "red", "review": "revise", "feedback": decision.feedback})
            asked_missing = False
            run = await self._run(
                "red", st.revise_prompt(self.cfg, "red", decision.feedback), resume=run.session_id, note="指摘を反映"
            )

    # ---- 実装とテスト（差し戻しつき） -----------------------------------

    async def _test(self, attempt: int) -> Verdict:
        run = await self._run("test", st.test_prompt(self.cfg, attempt), attempt=attempt)
        verdict = parse_verdict(run)
        if self.cfg.test_command and verdict.status != "blocked":
            print(f"  確認用コマンドを実行: {self.cfg.test_command}", flush=True)
            res = self.shell(self.cfg.test_command, self.cfg.project_dir, self.cfg.test_timeout_sec)
            verdict.command_check = {
                "command": self.cfg.test_command,
                "returncode": res.returncode,
                "output_tail": res.output_tail,
            }
            if res.returncode != 0 and verdict.status == "pass":
                verdict.status = "fail"
                verdict.summary += "（ただし確認用コマンドが失敗）"
        mark = {"pass": "✓ 合格", "fail": "✗ 不合格", "blocked": "■ 実行できず"}[verdict.status]
        print(f"  {mark}: {verdict.summary}")
        for f in verdict.failures[:5]:
            print(f"    - {f.get('criterion', '?')}: {one_line(f.get('detail', ''))}")
        self.history.append({"stage": "test", "attempt": attempt, "verdict": asdict(verdict)})
        self._save_state()
        return verdict

    async def _build_and_test(self, skip_first_impl: bool) -> Exit:
        note: str | None = None
        last_attempt = self.cfg.max_retries + 1
        for attempt in range(1, last_attempt + 1):
            if not (skip_first_impl and attempt == 1):
                impl = await self._run("implement", st.implement_prompt(self.cfg, attempt, note), attempt=attempt)
                if impl.is_error:
                    return Exit.STAGE_ERROR
            verdict = await self._test(attempt)
            if verdict.status == "pass":
                return Exit.PASSED
            if verdict.status == "blocked":
                return Exit.BLOCKED
            if attempt == last_attempt:
                return Exit.TEST_FAILED
            note = failure_note(verdict)
            print(f"  ↩ 実装へ差し戻します（残り {last_attempt - attempt} 回）", flush=True)
        return Exit.TEST_FAILED

    # ---- 全体 ---------------------------------------------------------

    def _check_prereq(self, from_stage: str) -> None:
        need = {
            "requirements": [st.INPUT],
            "design": [st.REQUIREMENTS],
            "red": [st.REQUIREMENTS, st.DESIGN],
            "implement": [st.REQUIREMENTS, st.DESIGN, st.RED],
            "test": [st.REQUIREMENTS, st.DESIGN, st.RED],
        }[from_stage]
        missing = [self.cfg.rel(self.doc(n)) for n in need if not self._doc_ready(n)]
        if missing:
            raise SystemExit(f"{STAGE_LABELS[from_stage]}から始めるには次のファイルが必要です: {', '.join(missing)}")

    async def run(self, input_text: str | None, from_stage: str = "requirements") -> Exit:
        if from_stage not in STAGES:
            raise SystemExit(f"--from には {', '.join(STAGES)} のどれかを指定してください")
        self.cfg.work_dir.mkdir(parents=True, exist_ok=True)
        if input_text is not None:
            self.doc(st.INPUT).write_text(input_text.strip() + "\n", encoding="utf-8")
        self._check_prereq(from_stage)

        result = await self._stages_from(STAGES.index(from_stage), skip_first_impl=(from_stage == "test"))
        return self._finish(result)

    async def _stages_from(
        self, start: int, *, first: tuple[str, str] | None = None, skip_first_impl: bool = False
    ) -> Exit:
        """start 番目の段から最後まで。first を渡すと、最初の段をその指示と会話の続きで動かす（修正の依頼）。"""

        def opts(i: int, prompt: str) -> dict[str, Any]:
            if first is not None and i == start:
                return {"prompt": first[0], "resume": first[1], "note": "指摘を反映"}
            return {"prompt": prompt}

        result: Exit | None = None
        if start <= 0:
            o = opts(0, st.requirements_prompt(self.cfg))
            result = await self._doc_stage("requirements", o.pop("prompt"), st.REQUIREMENTS, **o)
        if result is None and start <= 1:
            o = opts(1, st.design_prompt(self.cfg))
            result = await self._doc_stage("design", o.pop("prompt"), st.DESIGN, **o)
        if result is None and start <= 2:
            o = opts(2, st.red_prompt(self.cfg))
            result = await self._red_stage(o.pop("prompt"), **o)
        if result is None:
            result = await self._build_and_test(skip_first_impl=skip_first_impl)
        return result
