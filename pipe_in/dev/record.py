"""pipe-in record：開発フローの記録（state.json・段のログ・まとめ）だけを書く。段は流さない（SDK を呼ばない）。

Claude Code の開発用スキル（/pipe-dev）が、会話の中で進めた段の結果を本体と同じ形で残すために使う。
VSCode の拡張は、本体の記録と同じように図・確認待ち・差し戻しを出せる。
記録には driver = "pipe-dev" を入れ、pipe-in --review がこの記録の続きを流さないようにする。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine import clock
from ..engine.config import Config, load_config
from ..engine.pipeline import EXIT_MESSAGES, INPUT, STATE, SUMMARY, Exit
from ..engine.session import check_token, name_from_memo, normalize_name
from .specs import DESIGN, IMPLEMENTATION, RED, REQUIREMENTS, STAGE_LABELS, STAGES, TEST_REPORT

DRIVER = "pipe-dev"
LOGS = "logs"
ARCHIVE = "archive"
OUTPUTS = {"requirements": REQUIREMENTS, "design": DESIGN, "red": RED, "implement": IMPLEMENTATION, "test": TEST_REPORT}
REVIEWED = ("requirements", "design", "red")
REVIEWS = {"approved": "approved", "approve": "approved", "revise": "revise", "quit": "quit"}
RED_STATUSES = ("red", "blocked")
VERDICTS = ("pass", "fail", "blocked")
FINALS = tuple(e.name for e in Exit if e != Exit.AWAITING_REVIEW)
RECORD_FEEDBACK_LIMIT = 16384  # --feedback-file から読むバイト数の上限（超えたら断る）


class RecordError(Exception):
    """記録に書けない（段の名前の誤り・順番の誤り・途中の記録がある など）。"""


class Recorder:
    def __init__(self, cfg: Config, *, now: Callable[[], datetime] = datetime.now) -> None:
        self.cfg = cfg
        self.now = now

    # ---- 共通 ---------------------------------------------------------

    @property
    def work_dir(self) -> Path:
        return self.cfg.work_dir

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _load(self) -> dict[str, Any]:
        path = self.work_dir / STATE
        if not path.is_file():
            raise RecordError(f"記録がありません（{self.cfg.rel(path)}）。先に pipe-in record start で始めてください")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = self._stamp()
        (self.work_dir / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _stage(stage: str) -> str:
        if stage not in STAGES:
            raise RecordError(f"段の名前が違います（{stage}）。使えるのは {' / '.join(STAGES)}")
        return stage

    @staticmethod
    def _choice(value: str, allowed: Iterable[str], what: str) -> str:
        allowed = tuple(allowed)
        if value not in allowed:
            raise RecordError(f"{what}が違います（{value}）。使えるのは {' / '.join(allowed)}")
        return value

    @staticmethod
    def _open_run(state: dict[str, Any]) -> None:
        if state.get("final") is not None:
            raise RecordError(f"この記録はもう終わっています（{state['final']}）。次は pipe-in record start で始めてください")

    # ---- 始める --------------------------------------------------------

    @staticmethod
    def _token(value: str, what: str) -> str:
        try:
            return check_token(value, what)
        except ValueError as e:
            raise RecordError(str(e)) from e

    def start(self, memo: str, name: str | None = None, session_id: str | None = None) -> None:
        """依頼メモと空の記録を作る。途中の記録があれば断り、終わった記録は archive/<日時>/ に移す。

        name はセッション名（付けなければ依頼メモの最初の行から作る。取れなければ書かない）、
        session_id は Claude Code の会話の ID（付けたときだけ書く）。
        """
        if session_id is not None:
            self._token(session_id, "セッション ID")  # ファイルに触れる前に確かめる
        w = self.work_dir
        old_path = w / STATE
        if old_path.is_file():
            old = json.loads(old_path.read_text(encoding="utf-8"))
            if old.get("final") is None and (old.get("runs") or old.get("open") or old.get("pending_review")):
                raise RecordError(
                    f"途中の記録があります（{self.cfg.rel(old_path)}）。pipe-in record finish で終えるか、"
                    "残さないなら消してから始めてください"
                )
            self._archive(old)
        w.mkdir(parents=True, exist_ok=True)
        (w / INPUT).write_text(memo.strip() + "\n", encoding="utf-8")
        now = self._stamp()
        state: dict[str, Any] = {
            "started_at": now,
            "updated_at": now,
            "pipe": "dev",
        }
        session_name = (normalize_name(name) if name is not None else None) or name_from_memo(memo)
        if session_name is not None:
            state["name"] = session_name
        if session_id is not None:
            state["session_id"] = session_id
        state |= {
            "driver": DRIVER,
            "stages": [
                {"name": n, "label": STAGE_LABELS[n], "output": OUTPUTS[n], "review": n in REVIEWED} for n in STAGES
            ],
            "final": None,
            "total_cost_usd": 0.0,
            "usage_summary": None,
            "pending_review": None,
            "warnings": [],
            "open": None,
            "runs": [],
        }
        self._save(state)

    def _archive(self, old: dict[str, Any]) -> None:
        w = self.work_dir
        stamp = str(old.get("started_at") or self._stamp()).replace("-", "").replace(":", "").replace("T", "-")
        dest = w / ARCHIVE / stamp
        n = 2
        while dest.exists():
            dest = w / ARCHIVE / f"{stamp}-{n}"
            n += 1
        dest.mkdir(parents=True)
        for name in (STATE, INPUT, *OUTPUTS.values(), SUMMARY, LOGS):
            src = w / name
            if src.exists():
                shutil.move(str(src), str(dest / name))

    # ---- 段 -------------------------------------------------------------

    def begin(self, stage: str, attempt: int | None = None, note: str = "", agent: str | None = None) -> None:
        """段を始める。段のログに始まりの行を書き、拡張に「動いている」と出す。agent は受け持ちの名前（付けたときだけ書く）。"""
        if agent is not None:
            self._token(agent, "受け持ち")
        state = self._load()
        self._open_run(state)
        label = STAGE_LABELS[self._stage(stage)]
        if state.get("open"):
            raise RecordError(f"「{STAGE_LABELS[state['open']['stage']]}」の段がまだ閉じていません。先に pipe-in record done で閉じてください")
        if attempt is not None and attempt < 1:
            raise RecordError("attempt は 1 以上にしてください")
        seq = max((r["seq"] for r in state["runs"] if "seq" in r), default=0) + 1
        log = f"{seq:02d}_{stage}" + (f"_{attempt}" if attempt else "") + ".jsonl"
        t = self.now()  # 1回だけ読み、began_at（従来どおりずれなし）と at（ずれつき）に同じ時刻を使う
        now = t.isoformat(timespec="seconds")
        logs = self.work_dir / LOGS
        logs.mkdir(parents=True, exist_ok=True)
        prompt = f"/pipe-dev の{label}" + (f"（{attempt} 回目）" if attempt else "")
        line: dict[str, Any] = {"_type": "Prompt", "stage": stage, "resume": None, "prompt": prompt, "driver": DRIVER}
        if agent is not None:
            line["agent"] = agent
        line["at"] = clock.with_offset(t)
        (logs / log).write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
        state["open"] = {"stage": stage, "seq": seq, "attempt": attempt, "note": note, "log": log, "began_at": now}
        if agent is not None:
            state["open"]["agent"] = agent
        state["pending_review"] = None
        self._save(state)

    def done(self, stage: str, summary: str = "", error: bool = False) -> None:
        """始めた段を閉じ、段の実行として runs に足す。"""
        state = self._load()
        label = STAGE_LABELS[self._stage(stage)]
        o = state.get("open")
        if not o or o["stage"] != stage:
            raise RecordError(f"「{label}」の段は始まっていません。先に pipe-in record begin で始めてください")
        began = datetime.fromisoformat(o["began_at"])
        duration = round(max((self.now() - began).total_seconds(), 0.0), 1)
        lines = []
        if summary:
            lines.append({"_type": "AssistantMessage", "content": [{"text": summary}], "model": DRIVER})
        lines.append({
            "_type": "ResultMessage",
            "subtype": "error" if error else "success",
            "is_error": error,
            "num_turns": 0,
            "duration_ms": int(duration * 1000),
            "total_cost_usd": 0.0,
            "result": summary,
        })
        with (self.work_dir / LOGS / o["log"]).open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        state["runs"].append({
            "stage": stage,
            "session_id": None,
            "is_error": error,
            "subtype": "error" if error else "success",
            "result": summary or None,
            "cost_usd": 0.0,
            "num_turns": 0,
            "duration_sec": duration,
            "denials": [],
            "errors": [summary] if error and summary else [],
            "metrics": {},
            "seq": o["seq"],
            "attempt": o["attempt"],
            "note": o["note"],
        })
        if o.get("agent") is not None:
            state["runs"][-1]["agent"] = o["agent"]
        state["open"] = None
        self._save(state)

    # ---- 人の確認 ----------------------------------------------------------

    def wait(self, stage: str) -> None:
        """人の確認を待っている印（拡張の「確認待ち」）。"""
        state = self._load()
        self._open_run(state)
        self._stage(stage)
        state["pending_review"] = {"stage": stage, "doc": self.cfg.rel(self.work_dir / OUTPUTS[stage]),
            "session_id": None,
            "since": clock.with_offset(self.now()),
        }
        self._save(state)

    def review(self, stage: str, action: str, feedback: str = "") -> None:
        """人の確認の結果（approved・revise・quit）。revise には直してほしい点が要る。"""
        state = self._load()
        self._open_run(state)
        self._stage(stage)
        action = REVIEWS.get(action, action)
        self._choice(action, ("approved", "revise", "quit"), "確認の結果")
        entry: dict[str, Any] = {"stage": stage, "review": action}
        if action == "revise":
            if not feedback.strip():
                raise RecordError("revise には、直してほしい点（feedback）を付けてください")
            entry["feedback"] = feedback.strip()
        state["runs"].append(entry)
        state["pending_review"] = None
        self._save(state)

    # ---- 判定 -------------------------------------------------------------

    def red(self, status: str, summary: str, tests: Sequence[tuple[str, str]] = (), commands: Sequence[str] = ()) -> None:
        """テスト先行の結果（red = 期待どおりに落ちた・blocked = 流せない）。"""
        state = self._load()
        self._open_run(state)
        self._choice(status, RED_STATUSES, "テスト先行の結果")
        state["runs"].append({
            "stage": "red",
            "result": {
                "status": status,
                "summary": summary,
                "tests": [{"criterion": c, "test": t} for c, t in tests],
                "commands": list(commands),
            },
        })
        self._save(state)

    def verdict(
        self, status: str, attempt: int, summary: str, failures: Sequence[tuple[str, str]] = (), commands: Sequence[str] = ()
    ) -> None:
        """検証の判定（pass・fail・blocked）。attempt は何回目の検証か。"""
        state = self._load()
        self._open_run(state)
        self._choice(status, VERDICTS, "判定")
        if attempt < 1:
            raise RecordError("attempt は 1 以上にしてください")
        state["runs"].append({
            "stage": "test",
            "attempt": attempt,
            "verdict": {
                "status": status,
                "summary": summary,
                "failures": [{"criterion": c, "detail": d} for c, d in failures],
                "commands": list(commands),
                "command_check": None,
            },
        })
        self._save(state)

    # ---- 終わり ---------------------------------------------------------

    def finish(self, final: str) -> None:
        """最後の結果と 99_summary.md を書く。"""
        state = self._load()
        self._open_run(state)
        self._choice(final, FINALS, "最後の結果")
        if state.get("open"):
            raise RecordError(f"「{STAGE_LABELS[state['open']['stage']]}」の段がまだ閉じていません。先に pipe-in record done で閉じてください")
        state["final"] = final
        state["pending_review"] = None
        self._save(state)
        (self.work_dir / SUMMARY).write_text(self._summary(state), encoding="utf-8")

    def _summary(self, state: dict[str, Any]) -> str:
        w = self.cfg.rel(self.work_dir)
        lines = [
            "# /pipe-dev のまとめ",
            "",
            f"- 結果: {state['final']}（{EXIT_MESSAGES[Exit[state['final']]]}）",
            f"- 期間: {state['started_at']} 〜 {state['updated_at']}",
            "",
            "## 段の実行",
            "",
        ]
        for r in state["runs"]:
            stage = STAGE_LABELS.get(r["stage"], r["stage"])
            if "seq" in r:
                times = f"（{r['attempt']} 回目）" if r.get("attempt") else ""
                mark = "失敗" if r["is_error"] else "完了"
                lines.append(f"- {stage}{times}：{mark}{' — ' + r['result'] if r.get('result') else ''}")
            elif "review" in r:
                lines.append(f"- {stage}の確認：{r['review']}{' — ' + r['feedback'] if r.get('feedback') else ''}")
            elif "verdict" in r:
                lines.append(f"- 判定（{r['attempt']} 回目）：{r['verdict']['status']} — {r['verdict']['summary']}")
            elif "result" in r:
                lines.append(f"- テスト先行の結果：{r['result']['status']} — {r['result']['summary']}")
        lines += ["", "## 成果物", "", f"- [依頼メモ]({INPUT})"]
        lines += [f"- [{STAGE_LABELS[n]}]({OUTPUTS[n]})" for n in STAGES if (self.work_dir / OUTPUTS[n]).is_file()]
        lines += ["", f"記録: `{w}/{STATE}`", ""]
        return "\n".join(lines)


# ---- コマンド（pipe-in record …） --------------------------------------------------


def _pairs(values: Sequence[str] | None, what: str) -> list[tuple[str, str]]:
    out = []
    for v in values or []:
        key, sep, rest = v.partition("=")
        if not sep or not key.strip() or not rest.strip():
            raise RecordError(f"{what} は <基準>=<中身> の形で渡してください（{v}）")
        out.append((key.strip(), rest.strip()))
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pipe-in record",
        description="開発フローの記録（docs/pipeline/）だけを書く。段は流さない。Claude Code の開発用スキルが使う",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    common.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser("start", parents=[common], help="依頼メモと空の記録を作る")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="依頼メモのファイル")
    src.add_argument("--text", help="依頼メモを直接渡す")
    s.add_argument("--name", help="セッション名（省くと依頼メモの最初の行から作る）")
    s.add_argument("--session-id", dest="session_id", help="Claude Code の会話の ID（拡張の実行の一覧に出る）")

    s = sub.add_parser("begin", parents=[common], help="段を始める（拡張に「動いている」と出る）")
    s.add_argument("stage", help=" / ".join(STAGES))
    s.add_argument("--attempt", type=int, help="実装・検証の何回目か")
    s.add_argument("--note", default="", help="添え書き（例: 指摘を反映）")
    s.add_argument("--agent", help="この段を受け持つエージェントの名前（拡張の時系列に出る）")

    s = sub.add_parser("done", parents=[common], help="始めた段を閉じる")
    s.add_argument("stage")
    s.add_argument("--summary", default="", help="段の結果のひとこと")
    s.add_argument("--error", action="store_true", help="段が失敗した")

    s = sub.add_parser("wait", parents=[common], help="人の確認を待っている印を付ける")
    s.add_argument("stage")

    s = sub.add_parser("review", parents=[common], help="人の確認の結果")
    s.add_argument("stage")
    s.add_argument("result", help="approved / revise / quit")
    s.add_argument("--feedback", default=None, help="revise のときの、直してほしい点")
    s.add_argument(
        "--feedback-file",
        dest="feedback_file",
        type=Path,
        default=None,
        help="直してほしい点を書いたファイル（--feedback とは同時に使えない。UTF-8、16384 バイトまで）",
    )

    s = sub.add_parser("red", parents=[common], help="テスト先行の結果")
    s.add_argument("status", help=" / ".join(RED_STATUSES))
    s.add_argument("--summary", required=True)
    s.add_argument("--test", action="append", help="<基準>=<テスト>（何度でも）")
    s.add_argument("--command", action="append", help="流したコマンド（何度でも）")

    s = sub.add_parser("verdict", parents=[common], help="検証の判定")
    s.add_argument("status", help=" / ".join(VERDICTS))
    s.add_argument("--attempt", type=int, required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--failure", action="append", help="<基準>=<不合格の中身>（何度でも）")
    s.add_argument("--command", action="append", help="流したコマンド（何度でも）")

    s = sub.add_parser("finish", parents=[common], help="最後の結果とまとめを書く")
    s.add_argument("final", help=" / ".join(FINALS))
    return p


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "feedback", None) is not None and getattr(args, "feedback_file", None) is not None:
        parser.error("--feedback と --feedback-file は同時に指定できません")
    return args


def _read_feedback_file(path: Path) -> str:
    """--feedback-file の中身を読む。無い・通常のファイルでない・大きすぎる・UTF-8 でないときは RecordError。"""
    try:
        fd = os.open(os.fspath(path.expanduser()), os.O_RDONLY)
    except OSError as e:
        raise RecordError(f"--feedback-file を開けません（{type(e).__name__}）") from e
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RecordError("--feedback-file は通常のファイルを指定してください")
        raw = b""
        while len(raw) <= RECORD_FEEDBACK_LIMIT:
            chunk = os.read(fd, RECORD_FEEDBACK_LIMIT + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
    except OSError as e:
        raise RecordError(f"--feedback-file を読めません（{type(e).__name__}）") from e
    finally:
        os.close(fd)
    if len(raw) > RECORD_FEEDBACK_LIMIT:
        raise RecordError(f"--feedback-file が大きすぎます（{RECORD_FEEDBACK_LIMIT} バイトまで）")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RecordError("--feedback-file は UTF-8 で書いてください") from e


def main(argv: list[str]) -> int:
    args = _parse(argv)
    r = Recorder(load_config(args.project, args.config))
    try:
        if args.action == "start":
            memo = args.text if args.text is not None else args.input.expanduser().read_text(encoding="utf-8")
            r.start(memo, name=args.name, session_id=args.session_id)
        elif args.action == "begin":
            r.begin(args.stage, attempt=args.attempt, note=args.note, agent=args.agent)
        elif args.action == "done":
            r.done(args.stage, summary=args.summary, error=args.error)
        elif args.action == "wait":
            r.wait(args.stage)
        elif args.action == "review":
            feedback = args.feedback or ""
            if args.feedback_file is not None:
                feedback = _read_feedback_file(args.feedback_file)
            r.review(args.stage, args.result, feedback=feedback)
        elif args.action == "red":
            r.red(args.status, args.summary, tests=_pairs(args.test, "--test"), commands=args.command or [])
        elif args.action == "verdict":
            r.verdict(args.status, args.attempt, args.summary, failures=_pairs(args.failure, "--failure"), commands=args.command or [])
        elif args.action == "finish":
            r.finish(args.final)
    except RecordError as e:
        raise SystemExit(f"pipe-in record: {e}") from e
    print(f"記録しました: {args.action}（{r.cfg.rel(r.work_dir / STATE)}）")
    return 0
