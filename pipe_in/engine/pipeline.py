"""どのパイプにも共通の流れ：段の実行と記録（state.json）、人の確認、--pause / --review、まとめ（99_summary.md）。

段の並びと、どう流すか（差し戻しの有無など）は子のクラスが決める。
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from ..usage.metrics import summarize_runs
from ..usage.report import usage_sections
from . import clock
from .checkpoint import Decision, ask_human
from .config import Config
from .runner import StageRun, StageRunner, run_stage_sdk
from .spec import StageSpec

# どのパイプでも本体が書くファイル
INPUT = "00_input.md"
SUMMARY = "99_summary.md"
STATE = "state.json"


class Exit(IntEnum):
    PASSED = 0
    TEST_FAILED = 1
    STOPPED_BY_HUMAN = 2
    STAGE_ERROR = 3
    BLOCKED = 4
    AWAITING_REVIEW = 5


EXIT_MESSAGES = {
    Exit.PASSED: "最後の段まで終わりました",
    Exit.TEST_FAILED: "差し戻しの上限までテストが通りませんでした",
    Exit.STOPPED_BY_HUMAN: "確認の段階で中止しました",
    Exit.STAGE_ERROR: "段の実行が途中で失敗しました",
    Exit.BLOCKED: "テストを実行できませんでした（環境などの問題）",
    Exit.AWAITING_REVIEW: "人の確認を待っています",
}


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


def one_line(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class BasePipeline:
    def __init__(
        self,
        cfg: Config,
        specs: dict[str, StageSpec],
        *,
        runner: StageRunner = run_stage_sdk,
        ask: Callable[[str, Path], Decision] | None = None,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
    ) -> None:
        self.cfg = cfg
        self.specs = specs
        # 段の並びと表示名は specs の順と label から取る
        self.stage_order: list[str] = list(specs)
        self.labels: dict[str, str] = {name: spec.label for name, spec in specs.items()}
        self.runner = runner
        self.ask = ask or (lambda stage, doc: ask_human(stage, doc, label=self.labels[stage]))
        self.shell = shell
        self.history: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.seq = 0
        # 確認で止まっているときの {段・文書・会話の ID}。--review で続きから再開する。
        self.pending: dict[str, Any] | None = None
        self.started_at = datetime.now().isoformat(timespec="seconds")

    # ---- 子が決めること ---------------------------------------------------

    async def _stages_from(self, start: int, *, first: tuple[str, str] | None = None) -> Exit:
        """start 番目の段から最後まで。first を渡すと、最初の段をその指示と会話の続きで動かす（修正の依頼）。"""
        raise NotImplementedError

    def _revise_prompt(self, stage: str, feedback: str) -> str:
        raise NotImplementedError

    def _artifacts(self) -> list[tuple[str, str]]:
        """まとめに載せる成果物（ファイル名, 見出し）。"""
        return [(INPUT, "依頼メモ")]

    def _exit_message(self, result: Exit) -> str:
        return EXIT_MESSAGES[result]

    def _summary_extra(self) -> list[str]:
        """まとめに足す節（開発フローのテストの判定など）。"""
        return []

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
            "pipe": self.cfg.pipe,
            "stages": [
                {"name": n, "label": s.label, "output": s.output, "review": s.review} for n, s in self.specs.items()
            ],
            # 確認待ちは終わりではないので final は空のまま（pending_review を見る）
            "final": final.name if final is not None and final != Exit.AWAITING_REVIEW else None,
            "total_cost_usd": self.total_cost,
            "usage_summary": summarize_runs([h.get("metrics") for h in self.history if "seq" in h]),
            "pending_review": self.pending,
            "warnings": self.warnings,
            "runs": self.history,
        }
        self.doc(STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _run(self, stage: str, prompt: str, *, resume: str | None = None, attempt: int | None = None, note: str = "") -> StageRun:
        self.seq += 1
        label = self.labels[stage]
        suffix = f"（{attempt} 回目）" if attempt else ""
        print(f"\n▶ {label}{suffix}{' ' + note if note else ''}", flush=True)
        log_name = f"{self.seq:02d}_{stage}" + (f"_{attempt}" if attempt else "")
        run = await self.runner(self.specs[stage], prompt, self.cfg, resume=resume, log_name=log_name)
        entry = {k: v for k, v in asdict(run).items() if k not in ("structured",)}
        entry.update({"seq": self.seq, "attempt": attempt, "note": note, "metrics": run.metrics.to_dict()})
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

    # ---- 文書を書く段（人の確認つき） -------------------------------------

    def _pause(self, stage: str, doc_name: str, run: StageRun) -> Exit:
        self.pending = {
            "stage": stage,
            "doc": self.cfg.rel(self.doc(doc_name)),
            "session_id": run.session_id,
            "since": clock.now_with_offset(),
        }
        return Exit.AWAITING_REVIEW

    async def _doc_stage(
        self, stage: str, prompt: str, doc_name: str, *, resume: str | None = None, note: str = "", review: bool = True
    ) -> Exit | None:
        run = await self._run(stage, prompt, resume=resume, note=note)
        while True:
            if run.is_error or not self._doc_ready(doc_name):
                print(f"  ✗ {self.labels[stage]}の文書 {self.cfg.rel(self.doc(doc_name))} を作れませんでした")
                return Exit.STAGE_ERROR
            if not review or self.cfg.auto_approve:
                return None
            if self.cfg.pause_for_review:
                return self._pause(stage, doc_name, run)
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
                stage, self._revise_prompt(stage, decision.feedback), resume=run.session_id, note="指摘を反映"
            )

    # ---- 確認待ちからの再開 ---------------------------------------------

    async def review(self, decision: Decision) -> Exit:
        """確認で止まった実行に答えて、続きを流す（--pause で止めたあとの --review）。"""
        pending = self._load_pending()
        stage = pending["stage"]
        self.pending = None
        start = self.stage_order.index(stage)
        if decision.action == "approve":
            self.history.append({"stage": stage, "review": "approved"})
            self._save_state()
            result = await self._stages_from(start + 1)
        elif decision.action == "revise":
            self.history.append({"stage": stage, "review": "revise", "feedback": decision.feedback})
            first = (self._revise_prompt(stage, decision.feedback), pending["session_id"])
            result = await self._stages_from(start, first=first)
        else:
            self.history.append({"stage": stage, "review": "quit"})
            result = Exit.STOPPED_BY_HUMAN
        return self._finish(result)

    def _load_pending(self) -> dict[str, Any]:
        path = self.doc(STATE)
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if data.get("driver") is not None:
            # 開発用スキル（pipe-in record）の記録には会話の続きがないので、ここから SDK で流さない。
            # 値は見ない（前の版の "pipe-in" も、この先名前が変わっても漏れないように）
            raise SystemExit(
                f"この記録（{self.cfg.rel(path)}）は Claude Code の開発用スキル（/pipe-dev）が書いたものです。"
                "続きはその会話で進めてください（pipe-in --review では流せません）"
            )
        pending = data.get("pending_review")
        if not pending:
            raise SystemExit(f"確認待ちの実行がありません（{self.cfg.rel(path)}）。--pause で流したあとに --review を使ってください")
        self.history = list(data.get("runs", []))
        self.warnings = list(data.get("warnings", []))
        self.started_at = data.get("started_at", self.started_at)
        self.seq = max((h["seq"] for h in self.history if "seq" in h), default=0)
        return pending

    # ---- 終わり ---------------------------------------------------------

    def _finish(self, result: Exit) -> Exit:
        self._save_state(result)
        self._write_summary(result)
        print(f"\n■ {self._exit_message(result)}（合計 ${self.total_cost:.3f}）")
        if result == Exit.AWAITING_REVIEW and self.pending:
            print(f"  確認する文書: {self.pending['doc']}")
            print('  続き: --review approve ／ --review revise --feedback "直してほしい点" ／ --review quit')
        print(f"  まとめ: {self.cfg.rel(self.doc(SUMMARY))}")
        return result

    def _write_summary(self, result: Exit) -> None:
        w = self.cfg.rel(self.cfg.work_dir)
        lines = [
            "# パイプラインの結果",
            "",
            f"- 結果: **{self._exit_message(result)}**",
            f"- パイプ: {self.cfg.pipe}",
            f"- 開始: {self.started_at}",
            f"- 合計（概算）: ${self.total_cost:.3f}",
            "",
            "## 成果物",
            "",
        ]
        for name, title in self._artifacts():
            if self._doc_ready(name):
                lines.append(f"- {title}: `{w}/{name}`")
        if self.warnings:
            lines += ["## 注意", ""] + [f"- ⚠ {w}" for w in self.warnings] + [""]
        lines += ["", "## 実行の記録", "", "| # | 段 | 回 | 結果 | ターン | 費用 | 時間 |", "|---|---|---|---|---|---|---|"]
        for h in self.history:
            if "seq" in h:
                ok = "失敗" if h["is_error"] else "完了"
                lines.append(
                    f"| {h['seq']} | {self.labels.get(h['stage'], h['stage'])}{('・' + h['note']) if h.get('note') else ''} | "
                    f"{h.get('attempt') or ''} | {ok} | {h['num_turns']} | ${h['cost_usd']:.3f} | {h['duration_sec']}s |"
                )
        lines += self._summary_extra()
        lines += usage_sections(self.history, self.labels)
        denials = [d for h in self.history for d in h.get("denials", [])]
        denials += [
            f"{tool}: 許可されずに止まりました"
            for h in self.history
            for tool in (h.get("metrics") or {}).get("permission_denials", [])
        ]
        if denials:
            lines += ["", "## 止めた操作", ""] + [f"- {d}" for d in denials]
        self.doc(SUMMARY).write_text("\n".join(lines) + "\n", encoding="utf-8")
