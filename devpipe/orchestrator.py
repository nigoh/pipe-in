"""段の順番、人の確認、テスト失敗時の差し戻しを管理する。"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from . import stages as st
from .checkpoint import Decision, ask_human
from .config import STAGE_LABELS, STAGES, Config
from .runner import StageRun, StageRunner, run_stage_sdk


class Exit(IntEnum):
    PASSED = 0
    TEST_FAILED = 1
    STOPPED_BY_HUMAN = 2
    STAGE_ERROR = 3
    BLOCKED = 4


EXIT_MESSAGES = {
    Exit.PASSED: "テストまで合格しました",
    Exit.TEST_FAILED: "差し戻しの上限までテストが通りませんでした",
    Exit.STOPPED_BY_HUMAN: "確認の段階で中止しました",
    Exit.STAGE_ERROR: "段の実行が途中で失敗しました",
    Exit.BLOCKED: "テストを実行できませんでした（環境などの問題）",
}


@dataclass
class Verdict:
    status: str  # pass / fail / blocked
    summary: str
    failures: list[dict[str, str]] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    command_check: dict[str, Any] | None = None


@dataclass
class ShellResult:
    returncode: int | None
    output_tail: str


def run_shell(command: str, cwd: Path, timeout: int) -> ShellResult:
    try:
        p = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return ShellResult(p.returncode, out[-4000:])
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return ShellResult(None, f"{timeout} 秒でタイムアウトしました\n{out[-3000:]}")


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


class Pipeline:
    def __init__(
        self,
        cfg: Config,
        *,
        runner: StageRunner = run_stage_sdk,
        ask: Callable[[str, Path], Decision] = ask_human,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
    ) -> None:
        self.cfg = cfg
        self.runner = runner
        self.ask = ask
        self.shell = shell
        self.specs = st.build_specs(cfg)
        self.history: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.seq = 0
        self.started_at = datetime.now().isoformat(timespec="seconds")

    # ---- 共通 ---------------------------------------------------------

    def doc(self, name: str) -> Path:
        return self.cfg.work_dir / name

    @property
    def total_cost(self) -> float:
        return round(sum(h.get("cost_usd", 0.0) for h in self.history), 4)

    def _save_state(self, final: Exit | None = None) -> None:
        state = {
            "started_at": self.started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "final": final.name if final is not None else None,
            "total_cost_usd": self.total_cost,
            "runs": self.history,
        }
        self.doc(st.STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _run(self, stage: str, prompt: str, *, resume: str | None = None, attempt: int | None = None, note: str = "") -> StageRun:
        self.seq += 1
        label = STAGE_LABELS[stage]
        suffix = f"（{attempt} 回目）" if attempt else ""
        print(f"\n▶ {label}{suffix}{' ' + note if note else ''}", flush=True)
        log_name = f"{self.seq:02d}_{stage}" + (f"_{attempt}" if attempt else "")
        run = await self.runner(self.specs[stage], prompt, self.cfg, resume=resume, log_name=log_name)
        entry = {k: v for k, v in asdict(run).items() if k not in ("structured",)}
        entry.update({"seq": self.seq, "attempt": attempt, "note": note})
        self.history.append(entry)
        self._save_state()
        status = "失敗" if run.is_error else "完了"
        print(f"  {label}{suffix} {status}・{run.num_turns} ターン・${run.cost_usd:.3f}・{run.duration_sec}s", flush=True)
        if run.result and not run.is_error:
            for line in run.result.strip().splitlines()[:3]:
                print(f"    » {line}")
        return run

    def _doc_ready(self, name: str) -> bool:
        p = self.doc(name)
        return p.is_file() and p.read_text(encoding="utf-8").strip() != ""

    # ---- 要件定義・設計（人の確認つき） ---------------------------------

    async def _doc_stage(self, stage: str, prompt: str, doc_name: str) -> Exit | None:
        run = await self._run(stage, prompt)
        while True:
            if run.is_error or not self._doc_ready(doc_name):
                print(f"  ✗ {STAGE_LABELS[stage]}の文書 {self.cfg.rel(self.doc(doc_name))} を作れませんでした")
                return Exit.STAGE_ERROR
            if self.cfg.auto_approve:
                return None
            decision = self.ask(stage, self.doc(doc_name))
            if decision.action == "approve":
                self.history.append({"stage": stage, "review": "approved"})
                self._save_state()
                return None
            if decision.action == "quit":
                self.history.append({"stage": stage, "review": "quit"})
                return Exit.STOPPED_BY_HUMAN
            self.history.append({"stage": stage, "review": "revise", "feedback": decision.feedback})
            run = await self._run(
                stage, st.revise_prompt(self.cfg, stage, decision.feedback), resume=run.session_id, note="指摘を反映"
            )

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

    async def _red_stage(self) -> Exit | None:
        run = await self._run("red", st.red_prompt(self.cfg))
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
            print(f"    - {f.get('criterion', '?')}: {_one_line(f.get('detail', ''))}")
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

        start = STAGES.index(from_stage)
        result: Exit | None = None
        if start <= 0:
            result = await self._doc_stage("requirements", st.requirements_prompt(self.cfg), st.REQUIREMENTS)
        if result is None and start <= 1:
            result = await self._doc_stage("design", st.design_prompt(self.cfg), st.DESIGN)
        if result is None and start <= 2:
            result = await self._red_stage()
        if result is None:
            result = await self._build_and_test(skip_first_impl=(from_stage == "test"))

        self._save_state(result)
        self._write_summary(result)
        print(f"\n■ {EXIT_MESSAGES[result]}（合計 ${self.total_cost:.3f}）")
        print(f"  まとめ: {self.cfg.rel(self.doc(st.SUMMARY))}")
        return result

    def _write_summary(self, result: Exit) -> None:
        w = self.cfg.rel(self.cfg.work_dir)
        lines = [
            "# パイプラインの結果",
            "",
            f"- 結果: **{EXIT_MESSAGES[result]}**",
            f"- 開始: {self.started_at}",
            f"- 合計（概算）: ${self.total_cost:.3f}",
            "",
            "## 成果物",
            "",
        ]
        for name, title in [
            (st.INPUT, "要件メモ"),
            (st.REQUIREMENTS, "要件定義書"),
            (st.DESIGN, "設計書"),
            (st.RED, "テスト先行の記録"),
            (st.IMPLEMENTATION, "実装の記録"),
            (st.TEST_REPORT, "テスト報告"),
        ]:
            if self._doc_ready(name):
                lines.append(f"- {title}: `{w}/{name}`")
        if self.warnings:
            lines += ["## 注意", ""] + [f"- ⚠ {w}" for w in self.warnings] + [""]
        lines += ["", "## 実行の記録", "", "| # | 段 | 回 | 結果 | ターン | 費用 | 時間 |", "|---|---|---|---|---|---|---|"]
        for h in self.history:
            if "seq" in h:
                ok = "失敗" if h["is_error"] else "完了"
                lines.append(
                    f"| {h['seq']} | {STAGE_LABELS[h['stage']]}{('・' + h['note']) if h.get('note') else ''} | "
                    f"{h.get('attempt') or ''} | {ok} | {h['num_turns']} | ${h['cost_usd']:.3f} | {h['duration_sec']}s |"
                )
        verdicts = [h for h in self.history if "verdict" in h]
        if verdicts:
            lines += ["", "## テストの判定", ""]
            for h in verdicts:
                v = h["verdict"]
                lines.append(f"- {h['attempt']} 回目: {v['status']} — {v['summary']}")
        denials = [d for h in self.history for d in h.get("denials", [])]
        if denials:
            lines += ["", "## 止めた操作", ""] + [f"- {d}" for d in denials]
        self.doc(st.SUMMARY).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _one_line(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
