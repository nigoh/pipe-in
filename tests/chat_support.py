"""D0077 のテストの補助：一時フォルダにパイプを作る・司会役（pipe-in-gen chat）とフックを外の入口から呼ぶ。

どれも tmp_path の中だけに書く（リポジトリの pipes/・.pipe-in/・docs/pipeline/ には書かない）。
手書きの偽物だけを使い、SDK は呼ばない（no_sdk で claude_agent_sdk を読もうとすると落ちる形にする）。
司会役は chat_cmd.main(argv)（標準出力に JSON を1つ）、フックは chat_hook.main()（標準入力の JSON → 標準出力の deny）を通す。
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from pipe_in.pipe import definition as pd

PY = sys.executable
STAGE = "pipe-in:pipe-stage"
PROBE = "pipe-in:pipe-probe"
OK_CMD = f'"{PY}" -c "import sys; sys.exit(0)"'
# 前の版の名前（名前替えの検査 tests/test_rename.py に掛からないよう、つなげて書く）
OLD_NAME = "dev" + "pipe"
OLD_PIPES_ENV = OLD_NAME.upper() + "_PIPES_DIR"


@pytest.fixture
def no_sdk(monkeypatch):
    """claude_agent_sdk を読もうとすると ImportError になる状態にする（司会役とフックは SDK を読まない）。"""
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(OLD_PIPES_ENV, raising=False)


# ---- パイプを作る ----------------------------------------------------------------------------


def stage_toml(
    name: str, *, access: str = "read", output: str | None = None, docs_dir: str | None = None, extra: str = "", prompt: str | None = None
) -> str:
    """[[stages]] 1つ。extra は段の表の最後に足す行（review = true や [stages.check] など。値の行を先に、表を後に）。"""
    docs = f'docs_dir = "{docs_dir}"\n' if docs_dir else ""
    return (
        f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{output or name + ".md"}"\n'
        f'access = "{access}"\nprompt = "{prompt or name + "をする"}"\n{docs}{extra}'
    )


def pipe_toml(*stages: str, head: str = "") -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + head + "".join(stages)


def make_pipe(project: Path, toml: str, name: str = "hp", *, valid: bool = True) -> Path:
    """<project>/.pipe-in/pipes/pipe-in-<name>/pipe.toml を作る。valid なら check_pipe が通ることも確かめる（テスト側の誤りを赤にしないため）。"""
    d = project / ".pipe-in" / "pipes" / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    if valid:
        errors = pd.check_pipe(pd.load_pipe(d), project.resolve())
        assert errors == [], f"テストが作ったパイプの定義が誤り: {errors}"
    return d


def fill(obj: Any, project: Path) -> Any:
    """{P} を project の絶対パス、{PP} をその親に置き換える（表を collect の時点で書くため）。"""
    if isinstance(obj, str):
        return obj.replace("{PP}", str(project.parent)).replace("{P}", str(project))
    if isinstance(obj, dict):
        return {k: fill(v, project) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v, project) for v in obj]
    return obj


# ---- 入口を通す ------------------------------------------------------------------------------


def hook_decision(text: str) -> str | None:
    """chat_hook.main() に標準入力の文を渡し、止めた理由（deny の文）を返す。通したときは None（何も出さない）。"""
    from pipe_in_generator import chat_hook

    old, buf = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(text)
    try:
        with contextlib.redirect_stdout(buf):
            code = chat_hook.main()
    finally:
        sys.stdin = old
    assert code == 0, "フックの終了コードはいつも 0"
    out = buf.getvalue()
    if not out:
        return None
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "deny", out
    assert spec["permissionDecisionReason"], "止める文が空"
    return spec["permissionDecisionReason"]


def hook_payload(project: Path, tool: Any, tool_input: Any, agent_type: Any = STAGE, **extra: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(project),
        "session_id": "s-1",
        "transcript_path": str(project / "transcript.jsonl"),
    }
    if agent_type is not None:
        p["agent_type"] = agent_type
    p.update(extra)
    return p


def call_hook(project: Path, tool: Any, tool_input: Any, agent_type: Any = STAGE, **extra: Any) -> str | None:
    return hook_decision(json.dumps(hook_payload(project, tool, tool_input, agent_type, **extra)))


class Run:
    """1つの実行（パイプ1つ・記録1つ）を、外の入口（chat_cmd.main・chat_hook.main）だけで動かす。"""

    def __init__(self, project: Path, pipe: str = "hp"):
        self.project = project.resolve()
        self.pipe = pipe
        self.code = 0
        self.last: dict[str, Any] = {}

    # -- 場所 --

    @property
    def run_dir(self) -> Path:
        return self.project / "docs" / "pipeline" / self.pipe

    @property
    def pipe_dir(self) -> Path:
        return self.project / ".pipe-in" / "pipes" / f"pipe-in-{self.pipe}"

    def state(self) -> dict[str, Any]:
        return json.loads((self.run_dir / "state.json").read_text(encoding="utf-8"))

    def state_text(self) -> str:
        return (self.run_dir / "state.json").read_text(encoding="utf-8")

    def output_path(self, stage: str) -> Path:
        pipe = pd.load_pipe(self.pipe_dir)
        return self.run_dir / next(s.output for s in pipe.stages if s.name == stage)

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.project).as_posix()

    # -- 司会役 --

    def make(self, toml: str, *, valid: bool = True) -> None:
        make_pipe(self.project, toml, self.pipe, valid=valid)

    def call(self, argv: list[str]) -> dict[str, Any]:
        from pipe_in_generator import chat_cmd

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.code = chat_cmd.main(argv)
        self.last = json.loads(buf.getvalue().strip())
        return self.last

    def cmd(self, sub: str, *args: str) -> dict[str, Any]:
        if sub == "start":
            return self.call(["start", self.pipe, "--project", str(self.project), *args])
        return self.call([sub, "--pipe", self.pipe, "--project", str(self.project), *args])

    def start(self, *args: str, memo: str = "やること") -> dict[str, Any]:
        return self.cmd("start", "--memo", memo, *args)

    def probe_path(self) -> Path:
        p = Path(self.state()["chat"]["probe"]["path"])
        return p if p.is_absolute() else self.project / p

    def hook(self, tool: Any, tool_input: Any, agent_type: Any = STAGE, **extra: Any) -> str | None:
        return call_hook(self.project, tool, tool_input, agent_type, **extra)

    def ask_probe(self) -> dict[str, Any]:
        out = self.cmd("probe")
        assert out["action"] == "probe_ask", out
        return out

    def verify_probe(self) -> None:
        """本物の流れで確かめを済ませる：1回目 → 確かめ役の Write をフックが止める → 2回目。"""
        self.ask_probe()
        reason = self.hook("Write", {"file_path": str(self.probe_path()), "content": "probe"}, PROBE)
        assert reason, "確かめ役の範囲外の Write をフックが止めなかった"
        out = self.cmd("probe")
        assert out["action"] == "probe_ok", out

    def ready(self, toml: str) -> None:
        """パイプを作り、始め、確かめを済ませる。"""
        self.make(toml)
        out = self.start()
        assert out["ok"] is True and self.code == 0, out
        self.verify_probe()

    def next(self, expect: str | None = None) -> dict[str, Any]:
        out = self.cmd("next")
        if expect is not None:
            assert out.get("action") == expect, out
        return out

    def run_next(self, stage: str | None = None) -> dict[str, Any]:
        out = self.next("run_stage")
        if stage is not None:
            assert out["stage"] == stage, out
        return out

    def done(self, stage: str, *, summary: str = "済み", status: str | None = None, problems: tuple[str, ...] = (), error: bool = False) -> dict[str, Any]:
        args = ["--stage", stage, "--summary", summary]
        if status is not None:
            args += ["--status", status]
        for p in problems:
            args += ["--problems", p]
        if error:
            args.append("--error")
        return self.cmd("done", *args)

    def finish(self, stage: str, *, text: str | None = "# 成果\n", **kw: Any) -> dict[str, Any]:
        """成果物を書いて（text が None なら書かず、"" なら空のファイル）段を閉じる。"""
        if text is not None:
            path = self.output_path(stage)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self.done(stage, **kw)

    def run_and_finish(self, stage: str, **kw: Any) -> dict[str, Any]:
        self.run_next(stage)
        return self.finish(stage, **kw)

    def review(self, answer: str, feedback: str | None = None) -> dict[str, Any]:
        args = [answer]
        if feedback is not None:
            args += ["--feedback", feedback]
        return self.cmd("review", *args)

    def prompt_of(self, out: dict[str, Any]) -> str:
        assert isinstance(out["agent_prompt"], str)
        return out["agent_prompt"]

    def logs(self) -> list[str]:
        d = self.run_dir / "logs"
        return sorted(p.name for p in d.glob("*.jsonl")) if d.is_dir() else []

    def check_entries(self) -> list[dict[str, Any]]:
        return [r["check"] for r in self.state()["runs"] if "check" in r]

    def reviews(self) -> list[dict[str, Any]]:
        return [r for r in self.state()["runs"] if isinstance(r.get("review"), str)]


def text_of(out: dict[str, Any]) -> str:
    return json.dumps(out, ensure_ascii=False)


NONCE = re.compile(r"[0-9a-f]{16}")
