"""会話の中でパイプを流す司会役（D0077）。

段の順番・検査・差し戻し・人の確認・記録を持つ。段そのものは会話（Claude Code）が pipe-stage エージェントに任せるので、
ここは SDK を呼ばず、子プロセスも起こさない（検査の確認用コマンドだけ、引数 shell で流す）。
コマンドは start / probe / next / done / review / status。どれも辞書（JSON にできる返事）を返し、
断るときは ChatError を投げる。記録は本体と同じ形の state.json・logs/・99_summary.md（driver は pipe-chat）。
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine import clock
from ..engine.archive import archive_run
from ..engine.config import Config, load_config
from ..engine.pipeline import CHAT_DRIVER, EXIT_MESSAGES, INPUT, STATE, SUMMARY, Exit, ShellResult, one_line, run_shell
from ..engine.session import check_token, name_from_memo, normalize_name
from ..engine.state import new_state
from . import definition as pd
from .chat_record import (
    HOOK_DIR,
    PROBE_DIR,
    USAGE_UNAVAILABLE,
    chat_specs,
    fingerprint,
    read_trace,
    resolve_pipe_dir,
    same_path,
)
from .pipeline import check_summary_lines, command_outcome, exit_message, stage_checks, verdict_outcome
from .specs import revise_prompt, stage_prompt

LOGS = "logs"
AGENT_STAGE = "pipe-in:pipe-stage"
AGENT_PROBE = "pipe-in:pipe-probe"
REVIEW_ANSWERS = {"approved": "approved", "approve": "approved", "revise": "revise", "quit": "quit"}


class ChatError(Exception):
    """断る（記録は変えない）。文は人に見せる。"""


# ---- 扱えない形・効かない設定 ---------------------------------------------------------------------


def unsupported(pipe: pd.PipeDef, cfg: Config, after: str | None = None) -> list[str]:
    """会話の中では流せない形を、全部集めて返す（空なら流せる）。"""
    out: list[str] = []
    if pipe.kind != "linear":
        out.append(f'kind = "{pipe.kind}" のパイプ（組み込みの開発フロー dev）は、会話の中では流せません')
    if after:
        out.append("--after（前の実行の受け取り）は、会話の中では使えません")
    for s in pipe.stages:
        at = f"段「{s.name}」の"
        if s.group:
            out.append(f"{at}group（並列の段）は、会話の中では流せません")
        if s.routes:
            out.append(f"{at}routes（分岐）は、会話の中では流せません（構造化出力が無いため）")
        if s.check and s.check.judge is not None:
            out.append(f"{at}check.judge（審査）は、会話の中では流せません（構造化出力が無いため）")
        if s.agents:
            out.append(f"{at}agents（段の中のサブエージェント）は、会話の中では流せません")
        if s.mcp:
            out.append(f"{at}mcp（MCP の道具）は、会話の中では流せません")
        if s.mcp_servers:
            out.append(f"{at}mcp_servers（MCP サーバー）は、会話の中では流せません")
        if s.web or s.fetch_domains:
            out.append(f"{at}web（Web の道具）は、会話の中では流せません")
        if s.max_budget_usd is not None:
            out.append(f"{at}max_budget_usd（費用の上限）は、会話の中では守れないので流せません")
    for name, sc in cfg.stages.items():
        if sc.max_budget_usd is not None:
            out.append(f"pipeline.toml の [stages.{name}] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません")
    return out


def ineffective(pipe: pd.PipeDef, cfg: Config) -> list[dict[str, str]]:
    """会話の中では効かない設定（断らず、見せる）。"""
    out: list[dict[str, str]] = []
    for s in pipe.stages:
        for key in ("model", "max_turns", "max_thinking_tokens", "fallback_model", "permission_mode"):
            if getattr(s, key) is not None:
                out.append({"stage": s.name, "key": key, "where": "pipe.toml"})
        if s.add_dirs:
            out.append({"stage": s.name, "key": "add_dirs", "where": "pipe.toml"})
        sc = cfg.stages.get(s.name)
        if sc is not None:
            for key in ("model", "max_turns"):
                if getattr(sc, key) is not None:
                    out.append({"stage": s.name, "key": key, "where": "pipeline.toml"})
    return out


def _ineffective_lines(items: list[dict[str, str]]) -> list[str]:
    return [f"{i['stage']} の {i['key']}（{i['where']}）" for i in items]


def _stage_table(pipe: pd.PipeDef) -> list[dict[str, Any]]:
    return [
        {
            "name": s.name,
            "label": s.label,
            "output": s.output,
            "access": s.access,
            "bash": s.bash,
            "review": s.review,
            "verdict": bool(s.check and s.check.verdict),
            "command": s.check.command if s.check else None,
            "next": s.next,
        }
        for s in pipe.stages
    ]


# ---- 司会役 ---------------------------------------------------------------------------------------


class Chat:
    def __init__(
        self,
        project: Path,
        *,
        pipes_dir: Path | None = None,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
        now: Callable[[], datetime] = datetime.now,
        token: Callable[[], str] = lambda: secrets.token_hex(8),
    ) -> None:
        self.project = project.expanduser().resolve()
        self.base = load_config(self.project)
        self.pipes_dir = pipes_dir
        self.shell = shell
        self.now = now
        self.token = token

    # ---- 共通 -------------------------------------------------------------

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _cfg(self, name: str) -> Config:
        if not pd.is_valid_name(name):
            raise ChatError(f"パイプの名前「{name}」は使えません（英小文字・数字・- だけ）")
        return self.base.for_pipe(name, own_work_dir=True)

    def _save(self, cfg: Config, state: dict[str, Any]) -> None:
        state["updated_at"] = self._stamp()
        (cfg.work_dir / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record(self, name: str) -> tuple[Config, dict[str, Any]]:
        cfg = self._cfg(name)
        path = cfg.work_dir / STATE
        if not path.is_file():
            raise ChatError(f"記録がありません（{cfg.rel(path)}）。先に pipe-in-gen chat start {name} で始めてください")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ChatError(f"記録（{cfg.rel(path)}）を読めません（{type(e).__name__}）") from e
        if not isinstance(state, dict) or state.get("driver") != CHAT_DRIVER or not isinstance(state.get("chat"), dict):
            raise ChatError(
                f"この記録（{cfg.rel(path)}）は会話の道の記録ではありません。会話の中で流すには pipe-in-gen chat start {name} で始めてください"
            )
        return cfg, state

    def _pipe(self, cfg: Config, state: dict[str, Any]) -> pd.PipeDef:
        chat = state["chat"]
        pipe_dir = resolve_pipe_dir(self.project, chat.get("pipe_dir", ""))
        try:
            fp = fingerprint(pipe_dir, self.project)
        except OSError as e:
            raise ChatError(f"パイプの定義（{pipe_dir}）を読めません（{type(e).__name__}）") from e
        if fp != chat.get("fingerprint"):
            raise ChatError(
                "pipe.toml か pipeline.toml が、始めたときから変わっています。"
                "chat review quit で終えるか、最初から（chat start）やり直してください"
            )
        try:
            return pd.load_pipe(pipe_dir)
        except pd.PipeError as e:
            raise ChatError(str(e)) from e

    @staticmethod
    def _out(action: str, message: str, **extra: Any) -> dict[str, Any]:
        return {"ok": True, "action": action, "message": message, **extra}

    def _out_rel(self, cfg: Config, name: str) -> str:
        return f"{cfg.rel(cfg.work_dir)}/{name}"

    # ---- start ------------------------------------------------------------

    def start(
        self,
        pipe_arg: str,
        *,
        memo: str | None = None,
        name: str | None = None,
        session_id: str | None = None,
        after: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        path = pd.find_pipe(pipe_arg, self.pipes_dir, project=self.project)
        if path is None:
            raise ChatError(f"パイプ「{pipe_arg}」が見つかりません（pipe-in-gen list で一覧を出せます）")
        try:
            pipe = pd.load_pipe(path)
        except pd.PipeError as e:
            raise ChatError(str(e)) from e
        errors = pd.check_pipe(pipe, self.project)
        reasons = unsupported(pipe, self.base, after)
        if errors or reasons:
            parts: list[str] = []
            if errors:
                parts.append(f"パイプ「{pipe.name}」に誤りがあります:\n" + "\n".join(f"  - {e}" for e in errors))
            if reasons:
                parts.append("会話の中では流せない形があります:\n" + "\n".join(f"  - {r}" for r in reasons))
            raise ChatError("\n".join(parts))
        memo_text = (memo or "").strip()
        if pipe.input == "required" and not memo_text:
            raise ChatError(f"パイプ「{pipe.name}」には依頼メモが要ります。--memo か --memo-file で渡してください")
        if session_id is not None:
            try:
                check_token(session_id, "セッション ID")
            except ValueError as e:
                raise ChatError(str(e)) from e
        cfg = self._cfg(pipe.name)
        items = ineffective(pipe, self.base)
        table = _stage_table(pipe)
        lines = _ineffective_lines(items)
        old = self._old_state(cfg)
        info = {
            "pipe": pipe.name,
            "stages": table,
            "ineffective": items,
            "message_head": f"パイプ「{pipe.name}」（{len(table)} 段）",
        }
        listing = "効かない設定（会話の中では効きません）: " + ("、".join(lines) if lines else "なし")
        if dry_run:
            return self._out(
                "dry_run",
                f"{info['message_head']}を会話の中で流せます。{listing}。何も書いていません。"
                "続けるなら chat start（--dry-run なし）で始めてください",
                pipe=pipe.name,
                stages=table,
                ineffective=items,
            )

        if old is not None:
            names = [STATE, INPUT, SUMMARY, LOGS, HOOK_DIR, PROBE_DIR]
            names += [s.output for s in pipe.stages]
            names += [s.get("output") for s in old.get("stages", []) if isinstance(s, dict) and isinstance(s.get("output"), str)]
            archive_run(cfg.work_dir, old.get("started_at"), dict.fromkeys(names), self._stamp())
        cfg.work_dir.mkdir(parents=True, exist_ok=True)
        if memo_text:
            (cfg.work_dir / INPUT).write_text(memo_text + "\n", encoding="utf-8")
        now = self._stamp()
        session_name = (normalize_name(name) if name is not None else None) or (name_from_memo(memo_text) if memo_text else None)
        checks = stage_checks(pipe)
        state = new_state(
            CHAT_DRIVER,
            started_at=now,
            updated_at=now,
            pipe=pipe.name,
            name=session_name,
            session_id=session_id,
            stages=[
                {"name": s.name, "label": s.label, "output": s.output, "review": s.review, **({"check": checks[s.name]} if s.name in checks else {})}
                for s in pipe.stages
            ],
            warnings=[f"効かない設定: {line}" for line in lines],
            runs=[],
            with_open=True,
            unavailable_reason=USAGE_UNAVAILABLE["reason"],
        )
        state |= {
            "chat": {
                "pipe_dir": cfg.rel(path),
                "fingerprint": fingerprint(path, self.project),
                "probe": {"status": "none", "nonce": None, "path": None, "asked_at": None, "verified_at": None, "reason": None},
                "steps": 0,
                "retries": {},
                "notes": {},
                "next_stage": None,
                "revise": None,
            },
        }
        self._save(cfg, state)
        return self._out(
            "started",
            f"{info['message_head']}の記録を作りました。{listing}。次は chat probe で、守りが効いているかを確かめてください",
            pipe=pipe.name,
            stages=table,
            ineffective=items,
            work_dir=cfg.rel(cfg.work_dir),
            next="chat probe",
        )

    def _old_state(self, cfg: Config) -> dict[str, Any] | None:
        """今ある記録。途中の記録なら断る。無ければ None。"""
        path = cfg.work_dir / STATE
        if not path.is_file():
            return None
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ChatError(f"今ある記録（{cfg.rel(path)}）を読めません。残さないなら消してから始めてください") from e
        if not isinstance(old, dict):
            raise ChatError(f"今ある記録（{cfg.rel(path)}）の形が読めません。残さないなら消してから始めてください")
        if old.get("final") is None and (old.get("runs") or old.get("open") or old.get("pending_review")):
            raise ChatError(
                f"途中の記録があります（{cfg.rel(path)}）。chat next で続けるか、chat review quit で終えるか、"
                "残さないなら消してから始めてください"
            )
        return old

    # ---- probe ------------------------------------------------------------

    def probe(self, name: str) -> dict[str, Any]:
        cfg, state = self._record(name)
        self._pipe(cfg, state)
        probe = state["chat"]["probe"]
        if probe.get("status") == "asked":
            return self._probe_verify(cfg, state)
        if probe.get("status") == "verified":
            return self._out("probe_ok", "守りの確かめはもう済んでいます。chat next で進めてください")
        nonce = self.token()
        path = cfg.work_dir / PROBE_DIR / f"{nonce}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        state["chat"]["probe"] = {
            "status": "asked",
            "nonce": nonce,
            "path": cfg.rel(path),
            "asked_at": clock.now_with_offset(),
            "verified_at": None,
            "reason": None,
        }
        self._save(cfg, state)
        prompt = (
            f"守りの確かめです。次のパスに「probe」と書く Write を、1回だけ試してください。\n\n{path}\n\n"
            "このパスは書けない場所にしてあるので、フックに止められるはずです。止められたら「止められました」とだけ返してください。"
            "書けてしまったら「書けてしまった」と返してください。別のパスや、ほかの道具は試さないでください。"
        )
        return self._out(
            "probe_ask",
            f"確かめ役 {AGENT_PROBE} を1回呼んでください（agent_prompt をそのまま渡す）。返ってきたら、もう一度 chat probe を呼びます",
            agent=AGENT_PROBE,
            agent_prompt=prompt,
            path=str(path),
            nonce=nonce,
            then="chat probe をもう一度呼ぶ",
        )

    def _probe_verify(self, cfg: Config, state: dict[str, Any]) -> dict[str, Any]:
        probe = state["chat"]["probe"]
        path = resolve_pipe_dir(self.project, probe.get("path", ""))
        reason: str | None = None
        rows = read_trace(cfg.work_dir)
        denied = [r for r in rows if r.get("event") == "probe_denied"]
        if path.exists():
            reason = "範囲外のファイルができています（確かめ役が書けてしまいました。守りは効いていません）"
        elif not denied:
            reason = "フックの跡がありません（フックが確かめ役の呼び出しを見ていません。プラグインのフックが入っていないか、効いていません）"
        else:
            mine = [r for r in denied if same_path(r.get("target"), str(path))]
            if not mine:
                reason = "フックの跡の書き込み先が、確かめ用のパス（乱数入り）と合いません"
            elif not any(r.get("as") == "pipe-probe" and r.get("tool") == "Write" for r in mine):
                reason = "フックの跡が、確かめ役（pipe-probe）の Write を止めたものではありません"
        if reason is not None:
            probe["status"] = "failed"
            probe["reason"] = reason
            self._save(cfg, state)
            return self._out("probe_failed", f"守りを確かめられませんでした：{reason}。守りなしでは流しません", reason=reason, ok_to_run=False)
        probe["status"] = "verified"
        probe["verified_at"] = clock.now_with_offset()
        probe["reason"] = None
        self._save(cfg, state)
        return self._out("probe_ok", "守りが効いていることを確かめました。chat next で進めてください")

    # ---- next -------------------------------------------------------------

    def next(self, name: str) -> dict[str, Any]:
        cfg, state = self._record(name)
        chat = state["chat"]
        if state.get("final"):
            return self._finished(cfg, state)
        pipe = self._pipe(cfg, state)
        if chat["probe"].get("status") != "verified":
            return self._out("probe", "先に chat probe で、守りが効いていることを確かめてください")
        if state.get("pending_review"):
            return self._await_review(cfg, state)
        if state.get("open"):
            return self._run_reply(cfg, pipe, state, resumed=True)
        if chat.get("next_stage") == "end":
            self._finish(cfg, state, Exit.PASSED)
            return self._finished(cfg, state)

        names = [s.name for s in pipe.stages]
        revise = chat.get("revise")
        feedback: str | None = None
        failure: str | None = None
        if revise:
            stage, kind, feedback = revise["stage"], "revise", revise["feedback"]
            chat["revise"] = None
        else:
            if chat.get("steps", 0) + 1 > pipe.max_steps:
                state["warnings"].append(f"段を流した回数が max_steps（{pipe.max_steps}）を超えたため止めました")
                self._finish(cfg, state, Exit.STAGE_ERROR)
                return self._finished(cfg, state)
            chat["steps"] = chat.get("steps", 0) + 1
            stage = chat.get("next_stage") or names[0]
            failure = chat["notes"].pop(stage, None)
            kind = "retry" if failure else "stage"
        if stage not in names:
            raise ChatError(f"次の段「{stage}」が定義にありません")
        label = next(s.label for s in pipe.stages if s.name == stage)
        seq = max((r["seq"] for r in state["runs"] if "seq" in r), default=0) + 1
        log = f"{seq:02d}_{stage}.jsonl"
        t = self.now()
        logs = cfg.work_dir / LOGS
        logs.mkdir(parents=True, exist_ok=True)
        line = {
            "_type": "Prompt",
            "stage": stage,
            "resume": None,
            "prompt": f"/pipe-in:pipe-run の{label}",
            "driver": CHAT_DRIVER,
            "at": clock.with_offset(t),
        }
        (logs / log).write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
        opened: dict[str, Any] = {
            "stage": stage,
            "seq": seq,
            "attempt": None,
            "note": {"revise": "指摘を反映", "retry": "検証の指摘を反映"}.get(kind, ""),
            "log": log,
            "began_at": t.isoformat(timespec="seconds"),
            "kind": kind,
        }
        if failure:
            opened["failure"] = failure
        if feedback:
            opened["feedback"] = feedback
        state["open"] = opened
        state["pending_review"] = None
        chat["next_stage"] = stage
        self._save(cfg, state)
        return self._run_reply(cfg, pipe, state, resumed=False)

    def _run_reply(self, cfg: Config, pipe: pd.PipeDef, state: dict[str, Any], *, resumed: bool) -> dict[str, Any]:
        o = state["open"]
        stage = o["stage"]
        names = [s.name for s in pipe.stages]
        if stage not in names:
            raise ChatError(f"開いている段「{stage}」が定義にありません")
        index = names.index(stage)
        ps = pipe.stages[index]
        spec = chat_specs(cfg, pipe)[stage]
        kind = o.get("kind", "stage")
        verdict = bool(ps.check and ps.check.verdict)
        parts = [
            spec.system_append.strip(),
            "",
            stage_prompt(cfg, pipe, index, failure_note=o.get("failure") if kind == "retry" else None, structured=False),
            "",
            "## 書ける範囲",
            "",
            f"書けるのは {spec.write_scope_hint} だけです。範囲外への書き込みは止められます。回避せず、できなかったことは成果物に書いてください。",
        ]
        if not spec.allow_bash:
            parts.append("この段では Bash を使えません。")
        if kind == "revise":
            parts += ["", revise_prompt(cfg, pipe, stage, o.get("feedback", ""))]
        parts += ["", "## 返し方", ""]
        if verdict:
            parts.append(
                "返事の先頭に `STATUS: pass` か `STATUS: fail` を書き、fail なら直す点を `PROBLEM: …` で1行ずつ書いてください。"
                "そのあとに、変えたファイルと要点を3行以内で書いてください。"
            )
        else:
            parts.append("最後に、変えたファイルと要点を3行以内で返してください。")
        runs = sum(1 for r in state["runs"] if "seq" in r and r.get("stage") == stage) + 1
        return self._out(
            "run_stage",
            f"「{ps.label}」を {AGENT_STAGE} に任せてください（agent_prompt を変えずにそのまま渡す）。返事の要点を --summary にして chat done を呼びます",
            stage=stage,
            label=ps.label,
            seq=o["seq"],
            run=runs,
            kind=kind,
            resumed=resumed,
            agent=AGENT_STAGE,
            agent_prompt="\n".join(parts),
            output=self._out_rel(cfg, ps.output),
            scope={"access": ps.access, "bash": spec.allow_bash, "hint": spec.write_scope_hint},
            verdict=verdict,
            then=f"pipe-stage の返事の要点を --summary にして chat done --stage {stage} を呼ぶ",
        )

    def _await_review(self, cfg: Config, state: dict[str, Any]) -> dict[str, Any]:
        p = state["pending_review"]
        return self._out(
            "await_review",
            f"人の確認を待っています（{p['stage']}）。成果物 {p['doc']} を人に見せて、"
            "承認なら chat review approved、直す点があれば chat review revise --feedback …、中止なら chat review quit を呼んでください",
            stage=p["stage"],
            doc=p["doc"],
        )

    def _finished(self, cfg: Config, state: dict[str, Any]) -> dict[str, Any]:
        final = state.get("final")
        summary = self._out_rel(cfg, SUMMARY)
        msg = EXIT_MESSAGES.get(Exit[final], str(final)) if final in Exit.__members__ else str(final)
        return self._out("finished", f"終わっています：{final}（{msg}）。まとめ: {summary}", final=final, summary=summary)

    # ---- done -------------------------------------------------------------

    def done(
        self,
        name: str,
        stage: str,
        summary: str = "",
        *,
        status: str | None = None,
        problems: list[str] | None = None,
        error: bool = False,
    ) -> dict[str, Any]:
        cfg, state = self._record(name)
        pipe = self._pipe(cfg, state)
        o = state.get("open")
        if not o or o.get("stage") != stage:
            raise ChatError(f"「{stage}」の段は開いていません。先に chat next で始めてください")
        ps = next((s for s in pipe.stages if s.name == stage), None)
        if ps is None:
            raise ChatError(f"段「{stage}」が定義にありません")
        verdict = bool(ps.check and ps.check.verdict)
        if verdict and not error and status not in ("pass", "fail"):
            raise ChatError(f"段「{stage}」は判定のある段です。--status に pass か fail を付けてください")
        if not verdict and status is not None:
            raise ChatError(f"段「{stage}」は判定のある段ではないので、--status は付けられません")

        chat = state["chat"]
        began = datetime.fromisoformat(o["began_at"])
        duration = round(max((self.now() - began).total_seconds(), 0.0), 1)
        denials = [
            f"{r.get('tool')}: {one_line(str(r.get('reason', '')))}"
            for r in read_trace(cfg.work_dir)
            if r.get("event") in ("stage_denied", "agent_denied") and r.get("seq") == o["seq"]
        ]
        lines: list[dict[str, Any]] = []
        if summary:
            lines.append({"_type": "AssistantMessage", "content": [{"text": summary}], "model": CHAT_DRIVER})
        lines.append(
            {
                "_type": "ResultMessage",
                "subtype": "error" if error else "success",
                "is_error": error,
                "num_turns": 0,
                "duration_ms": int(duration * 1000),
                "total_cost_usd": None,
                "result": summary,
            }
        )
        with (cfg.work_dir / LOGS / o["log"]).open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        state["runs"].append(
            {
                "stage": stage,
                "session_id": None,
                "is_error": error,
                "subtype": "error" if error else "success",
                "result": summary or None,
                "cost_usd": None,
                "num_turns": 0,
                "duration_sec": duration,
                "denials": denials,
                "errors": [summary] if error and summary else [],
                "seq": o["seq"],
                "attempt": o.get("attempt"),
                "note": o.get("note", ""),
            }
        )
        state["open"] = None

        out = (cfg.work_dir / ps.output)
        if error or not (out.is_file() and out.read_text(encoding="utf-8").strip()):
            self._finish(cfg, state, Exit.STAGE_ERROR)
            return self._closed(cfg, state, stage, "error", "成果物が作れなかったか、段が失敗したので、ここで終えました")

        c = ps.check
        if c is not None:
            found: list[str] = []
            record: dict[str, Any] = {}
            if c.verdict:
                f1, r1 = verdict_outcome({"status": status, "summary": summary, "problems": list(problems or [])})
                found += f1
                record.update(r1)
            if c.command:
                f2, r2 = command_outcome(c.command, self.project, c.timeout_sec, self.shell)
                found += f2
                record.update(r2)
            attempt = sum(1 for h in state["runs"] if h.get("stage") == stage and "check" in h) + 1
            result = "fail" if found else "pass"
            state["runs"].append({"stage": stage, "check": {"attempt": attempt, "status": result, "problems": found, **record}})
            if found:
                used = chat["retries"].get(stage, 0)
                if used >= c.max_retries:
                    self._finish(cfg, state, Exit.TEST_FAILED)
                    return self._closed(cfg, state, stage, "fail", "差し戻しの上限まで検証に通らなかったので、ここで終えました")
                chat["retries"][stage] = used + 1
                target = c.on_fail or stage
                chat["notes"][target] = "\n".join(f"- {p}" for p in found)
                chat["next_stage"] = target
                self._save(cfg, state)
                return self._closed(cfg, state, stage, "fail", f"検証に通りませんでした。{target} をやり直します（chat next）")

        names = [s.name for s in pipe.stages]
        if ps.next is not None:
            nxt = ps.next
        else:
            i = names.index(stage) + 1
            nxt = names[i] if i < len(names) else pd.END
        if ps.review:
            state["pending_review"] = {
                "stage": stage,
                "doc": self._out_rel(cfg, ps.output),
                "session_id": None,
                "next": nxt,
                "since": clock.now_with_offset(),
            }
            self._save(cfg, state)
            return self._closed(cfg, state, stage, "pass", "人の確認を待ちます（chat next で確認の案内が出ます）")
        if nxt == pd.END:
            self._finish(cfg, state, Exit.PASSED)
            return self._closed(cfg, state, stage, "pass", "最後の段まで終わりました")
        chat["next_stage"] = nxt
        self._save(cfg, state)
        return self._closed(cfg, state, stage, "pass", "次は chat next を呼んでください")

    def _closed(self, cfg: Config, state: dict[str, Any], stage: str, result: str, message: str) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if state.get("final"):
            extra = {"final": state["final"], "summary": self._out_rel(cfg, SUMMARY)}
        return self._out("closed", f"「{stage}」を閉じました（{result}）。{message}", stage=stage, result=result, **extra)

    # ---- review -----------------------------------------------------------

    def review(self, name: str, answer: str, feedback: str | None = None) -> dict[str, Any]:
        cfg, state = self._record(name)
        pending = state.get("pending_review")
        if not pending:
            raise ChatError("確認待ちではありません（chat next で今の様子を確かめてください）")
        action = REVIEW_ANSWERS.get(answer)
        if action is None:
            raise ChatError(f"答えは approved / revise / quit のどれかです（{answer}）")
        stage = pending["stage"]
        chat = state["chat"]
        entry: dict[str, Any] = {"stage": stage, "review": action}
        if action == "revise":
            fb = (feedback or "").strip()
            if not fb:
                raise ChatError("revise には、直してほしい点（--feedback）が要ります")
            entry["feedback"] = fb
        entry["at"] = clock.now_with_offset()
        state["runs"].append(entry)
        state["pending_review"] = None
        message = ""
        if action == "approved":
            chat["next_stage"] = pending.get("next")
            message = "承認しました"
            if chat["next_stage"] == pd.END:
                self._finish(cfg, state, Exit.PASSED)
                message += "。最後の段まで終わりました"
            else:
                self._save(cfg, state)
                message += "。次は chat next を呼んでください"
        elif action == "revise":
            chat["revise"] = {"stage": stage, "feedback": entry["feedback"]}
            chat["next_stage"] = stage
            self._save(cfg, state)
            message = f"「{stage}」を直してやり直します。chat next を呼んでください"
        else:
            self._finish(cfg, state, Exit.STOPPED_BY_HUMAN)
            message = "中止しました"
        extra = {"final": state["final"]} if state.get("final") else {}
        return self._out("reviewed", message, stage=stage, answer=action, **extra)

    # ---- status -----------------------------------------------------------

    def status(self, name: str) -> dict[str, Any]:
        cfg, state = self._record(name)
        chat = state["chat"]
        labels = {s["name"]: s.get("label", s["name"]) for s in state.get("stages", []) if isinstance(s, dict) and "name" in s}
        o = state.get("open")
        p = state.get("pending_review")
        if state.get("final"):
            where = f"終わっています（{state['final']}）"
        elif p:
            where = f"「{labels.get(p['stage'], p['stage'])}」の人の確認を待っています"
        elif o:
            n = sum(1 for r in state["runs"] if "seq" in r and r.get("stage") == o["stage"]) + 1
            where = f"「{labels.get(o['stage'], o['stage'])}」を {n} 回目で実行中です（{o.get('kind', 'stage')}）"
        else:
            where = f"次に流す段は {chat.get('next_stage') or '最初の段'} です"
        probe = chat.get("probe", {}).get("status")
        message = f"{where}。守りの確かめ: {probe}・段を流した回数: {chat.get('steps', 0)}"
        return self._out(
            "status",
            message,
            pipe=name,
            final=state.get("final"),
            open=o,
            pending_review=p,
            probe=probe,
            steps=chat.get("steps", 0),
            retries=chat.get("retries", {}),
        )

    # ---- 終わり -----------------------------------------------------------

    def _finish(self, cfg: Config, state: dict[str, Any], final: Exit) -> None:
        state["final"] = final.name
        state["pending_review"] = None
        state["open"] = None
        self._save(cfg, state)
        (cfg.work_dir / SUMMARY).write_text(self._summary(cfg, state, final), encoding="utf-8")

    def _summary(self, cfg: Config, state: dict[str, Any], final: Exit) -> str:
        w = cfg.rel(cfg.work_dir)
        stages = [s for s in state.get("stages", []) if isinstance(s, dict)]
        labels = {s["name"]: s.get("label", s["name"]) for s in stages}
        lines = [
            "# パイプラインの結果",
            "",
            f"- 結果: **{exit_message(final)}**",
            f"- パイプ: {state.get('pipe')}",
            f"- 開始: {state.get('started_at')}",
            "- 使用量は取れません（会話の中で流したため）",
            "",
            "## 成果物",
            "",
        ]
        artifacts = [(INPUT, "依頼メモ")] + [(s["output"], s.get("label", s["name"])) for s in stages]
        for fname, title in artifacts:
            p = cfg.work_dir / fname
            if p.is_file() and p.read_text(encoding="utf-8").strip():
                lines.append(f"- {title}: `{w}/{fname}`")
        warnings = state.get("warnings") or []
        if warnings:
            lines += ["", "## 注意", ""] + [f"- ⚠ {x}" for x in warnings] + [""]
        lines += ["", "## 実行の記録", "", "| # | 段 | 回 | 結果 | 時間 |", "|---|---|---|---|---|"]
        seen: dict[str, int] = {}
        for h in state["runs"]:
            if "seq" in h:
                seen[h["stage"]] = seen.get(h["stage"], 0) + 1
                ok = "失敗" if h.get("is_error") else "完了"
                note = ("・" + h["note"]) if h.get("note") else ""
                lines.append(f"| {h['seq']} | {labels.get(h['stage'], h['stage'])}{note} | {seen[h['stage']]} | {ok} | {h.get('duration_sec')}s |")
        lines += check_summary_lines(state["runs"], labels)
        denials = [d for h in state["runs"] for d in h.get("denials", [])]
        if denials:
            lines += ["", "## 止めた操作", ""] + [f"- {d}" for d in denials]
        return "\n".join(lines) + "\n"
