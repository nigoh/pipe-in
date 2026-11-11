"""D0077-AC-26〜32：プラグインの PreToolUse フックが、会話の中で流す段（pipe-stage）の書ける範囲を、今の段の定義から絞る。

フックは本物の入口 chat_hook.main()（標準入力のフックの入力 → 標準出力の deny）を通す。今の段は、本物の chat start / probe / next で開く。
判断は本体の道（build_pipe_specs → guard.check_tool）と同じ結果になることを、同じ定義から作った表で突き合わせる。
会話の道だけが追加で止めるもの（記録・Skill）と、D0084 で本体の道でも止まるもの（.claude/・.git/・pipeline.toml）は、別の表で「止まる」を確かめる。
SDK は読まない（no_sdk）。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import json
import os

import pytest
from chat_support import OLD_PIPES_ENV, PROBE, STAGE, Run, call_hook, fill, hook_decision, hook_payload, no_sdk, pipe_toml, stage_toml  # noqa: F401

from pipe_in.engine.bashwrite import BashState
from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool
from pipe_in.pipe import definition as pd
from pipe_in.pipe.specs import build_pipe_specs

pytestmark = pytest.mark.usefixtures("no_sdk")

OWN = "docs/pipeline/hp/out.md"


def one(access: str, *, docs_dir: str | None = None, bash: bool = False, writes: list[str] | None = None) -> str:
    extra = ("bash = true\n" if bash else "") + (f"writes = {json.dumps(writes)}\n" if writes else "")
    return pipe_toml(stage_toml("s", access=access, output="out.md", docs_dir=docs_dir, extra=extra))


CONFIGS = {
    "read": lambda: one("read"),
    "read_bash": lambda: one("read", bash=True),
    "docs": lambda: one("docs", docs_dir="docs/out"),
    "docs_w": lambda: one("docs", docs_dir="docs/out", writes=["docs/out/a/*"]),
    "docs_wide": lambda: one("docs", docs_dir="docs"),
    "tests_b": lambda: one("tests", bash=True),
    "tests_w": lambda: one("tests", writes=["tests/unit/*"]),
    "code_b": lambda: one("code", bash=True),
    "code_w": lambda: one("code", bash=True, writes=["src/*"]),
}


class Sdk:
    """本体の道の判断：同じ定義から build_pipe_specs で段の範囲を作り、guard.check_tool に掛ける。"""

    def __init__(self, r: Run, stage: str = "s"):
        self.cfg = load_config(r.project).for_pipe(r.pipe, own_work_dir=True)
        self.spec = build_pipe_specs(self.cfg, pd.load_pipe(r.pipe_dir))[stage]

    def __call__(self, tool: str, tool_input: dict, state: BashState | None = None) -> str | None:
        s = self.spec
        return check_tool(
            tool,
            tool_input,
            project_dir=self.cfg.project_dir,
            can_write=s.can_write,
            allow_bash=s.allow_bash,
            write_scope_hint=s.write_scope_hint,
            allowed_tools=s.allowed_tools,
            fetch_domains=s.fetch_domains,
            bash_state=state,
        )


def prepared(tmp_path, toml: str) -> tuple[Run, Sdk]:
    """パイプを作り、本体の道の判断を用意する（まだ始めない。本体の道の前提を、司会役より先に確かめるため）。"""
    r = Run(tmp_path)
    r.make(toml)
    return r, Sdk(r)


def opened(tmp_path, toml: str, stage: str = "s") -> tuple[Run, Sdk]:
    r, sdk = prepared(tmp_path, toml)
    assert r.start()["ok"] is True
    r.verify_probe()
    r.run_next(stage)
    return r, sdk


# ---- AC-26：書ける範囲は check_tool と同じ結果 ---------------------------------------------------

WRITE_PATHS = [
    OWN,
    "docs/out/a/x.md",
    "docs/out/b.md",
    "tests/unit/test_a.py",
    "tests/test_b.py",
    "src/app.py",
    "src/lib/x.py",
    "README.md",
    "other/x.txt",
    "docs/other.md",
    "conftest.py",
]
WRITE_TOOLS = [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")]
BASH_COMMANDS = [
    "ls",
    "echo hi",
    f"echo x > {OWN}",
    "echo x > src/app.py",
    "echo x > tests/unit/test_a.py",
    "echo x > docs/out/a/x.md",
    "echo x > README.md",
    "cat src/app.py",
    "touch tests/test_b.py",
    "tee docs/out/b.md",
    "git push origin main",
    "rm -rf build",
    "curl http://example.com",
]


@pytest.mark.parametrize("config", sorted(CONFIGS))
def test_d0077_ac26_pipe_stageの書ける範囲はcheck_toolと同じ結果になる(tmp_path, config):
    """D0077-AC-26: read は成果物以外、docs は成果物と docs_dir の下、tests はテストファイルと成果物、code はテスト以外と成果物だけに書ける。
    writes はその範囲をさらに絞る。判断は guard.check_tool と同じ結果になる（同じ定義から作った表で突き合わせる）。"""
    r, sdk = prepared(tmp_path, CONFIGS[config]())
    assert r.start()["ok"] is True
    r.verify_probe()
    r.run_next("s")
    mismatches: list[str] = []
    for tool, key in WRITE_TOOLS:
        for rel in WRITE_PATHS:
            for form, path in (("abs", str(r.project / rel)), ("rel", rel)):
                data = {key: path}
                want = sdk(tool, data)
                got = r.hook(tool, data)
                if (want is None) != (got is None):
                    mismatches.append(f"{tool} {form} {rel}: 本体の道={'通す' if want is None else '止める'} フック={'通す' if got is None else '止める'}")
    outside = {"file_path": str(r.project.parent / "outside.txt")}
    assert sdk("Write", outside) and r.hook("Write", outside), "プロジェクトの外はどちらも止まる"
    for command in BASH_COMMANDS:
        want = sdk("Bash", {"command": command})
        got = r.hook("Bash", {"command": command})
        if (want is None) != (got is None):
            mismatches.append(f"Bash {command!r}: 本体の道={'通す' if want is None else '止める'} フック={'通す' if got is None else '止める'}")
    assert mismatches == []


@pytest.mark.parametrize("config", sorted(CONFIGS))
def test_d0077_ac26_範囲外は止まり止める文に書ける範囲が出る(tmp_path, config):
    """D0077-AC-26: 範囲外の書き込みは止まり、止める文に書ける範囲（その段の成果物の場所）が出る。"""
    r, sdk = opened(tmp_path, CONFIGS[config]())
    assert r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"}) is None, "成果物にはどの段でも書ける"
    blocked = [p for p in WRITE_PATHS if sdk("Write", {"file_path": str(r.project / p)})]
    assert blocked, "前提：この定義で範囲外になる書き込み先がある"
    for path in blocked:
        reason = r.hook("Write", {"file_path": str(r.project / path), "content": "x"})
        assert reason, path
        assert OWN in reason, f"止める文に書ける範囲（成果物 {OWN}）が出ていない（{path}）: {reason}"


ALLOWED_BY_SDK = {
    "read": {OWN},
    "read_bash": {OWN},
    "docs": {OWN, "docs/out/a/x.md", "docs/out/b.md"},
    "docs_w": {OWN, "docs/out/a/x.md"},
    "docs_wide": {OWN, "docs/out/a/x.md", "docs/out/b.md", "docs/other.md"},
    "tests_b": {OWN, "tests/unit/test_a.py", "tests/test_b.py", "conftest.py"},
    "tests_w": {OWN, "tests/unit/test_a.py"},
    "code_b": {OWN, "src/app.py", "src/lib/x.py", "README.md", "other/x.txt", "docs/out/a/x.md", "docs/out/b.md", "docs/other.md"},
    "code_w": {OWN, "src/app.py", "src/lib/x.py"},
}


@pytest.mark.parametrize("config", sorted(CONFIGS))
def test_d0077_ac26_前提_本体の道の判断の表は書ける範囲の説明どおり_守る(tmp_path, config):
    """D0077-AC-26（前提）: 本体の道（build_pipe_specs → check_tool）の判断が、要件の説明（read は成果物以外、docs は成果物と docs_dir の下、
    tests はテストファイルと成果物、code はテスト以外と成果物、writes はさらに絞る）どおりであること。突き合わせの表が意味を持つための前提（今のまま通る。守る）。"""
    r, sdk = prepared(tmp_path, CONFIGS[config]())
    allowed = {p for p in WRITE_PATHS if sdk("Write", {"file_path": str(r.project / p)}) is None}
    assert allowed == ALLOWED_BY_SDK[config]
    assert sdk("Write", {"file_path": str(r.project.parent / "outside.txt")}), "プロジェクトの外は止まる"
    assert (sdk("Bash", {"command": "ls"}) is None) == (config in ("read_bash", "tests_b", "code_b", "code_w"))


def test_d0077_ac26_止めた操作は跡に残り段の記録とまとめに写る(tmp_path):
    """D0077-AC-26（設計 4.2・5.3）: pipe-stage が止められた操作は hook/trace.jsonl に残り、chat done で段の記録の denials とまとめの「止めた操作」に写る。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    assert r.hook("Write", {"file_path": str(r.project / "src" / "a.py"), "content": "x"})
    rows = [json.loads(x) for x in (r.run_dir / "hook" / "trace.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    stage_rows = [x for x in rows if x.get("event") == "stage_denied"]
    assert stage_rows and stage_rows[-1]["as"] == "pipe-stage" and stage_rows[-1]["tool"] == "Write" and stage_rows[-1]["seq"] == 1, rows
    r.finish("s")
    run = next(x for x in r.state()["runs"] if "seq" in x)
    assert run["denials"], run
    assert "止めた操作" in (r.run_dir / "99_summary.md").read_text(encoding="utf-8")


# ---- AC-27：すり抜けの道 ----------------------------------------------------------------------

# (id, 定義, 道具, 入力, 本体の道でも止まるか)。{P} はプロジェクト、{PP} はその親
ESCAPES = [
    # bash = false の段
    ("bash-off-write", "docs", "Bash", {"command": "echo x > docs/out/a.md"}, True),
    ("bash-off-ls", "docs", "Bash", {"command": "ls"}, True),
    ("powershell", "docs", "PowerShell", {"command": "Set-Content docs/out/a.md x"}, True),
    ("mcp", "docs", "mcp__x__y", {}, True),
    ("mcp-github", "docs", "mcp__github__create_issue", {}, True),
    ("agent", "docs", "Agent", {"prompt": "x", "subagent_type": "general-purpose", "run_in_background": False}, True),
    ("task", "docs", "Task", {"prompt": "x", "run_in_background": False}, True),
    ("webfetch", "docs", "WebFetch", {"url": "https://example.com"}, True),
    ("websearch", "docs", "WebSearch", {"query": "x"}, True),
    ("notebook-out-of-range", "docs", "NotebookEdit", {"notebook_path": "{P}/src/a.ipynb"}, True),
    ("dotdot-abs", "docs", "Write", {"file_path": "{P}/docs/out/../../src/a.py", "content": "x"}, True),
    ("dotdot-rel", "docs", "Write", {"file_path": "docs/out/../../src/a.py", "content": "x"}, True),
    ("dotdot-outside", "docs", "Write", {"file_path": "../outside.txt", "content": "x"}, True),
    ("pipe-toml", "docs", "Write", {"file_path": "{P}/.pipe-in/pipes/pipe-in-hp/pipe.toml", "content": "x"}, True),
    ("skill", "docs", "Skill", {"skill": "x"}, False),
    # docs_dir が記録を含む段（本体の道では記録に書けてしまう所。会話の道では止める）
    ("record-state", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/state.json", "content": "{}"}, False),
    ("record-state-edit", "docs_wide", "Edit", {"file_path": "{P}/docs/pipeline/hp/state.json", "old_string": "a", "new_string": "b"}, False),
    ("record-state-multiedit", "docs_wide", "MultiEdit", {"file_path": "{P}/docs/pipeline/hp/state.json", "edits": []}, False),
    ("record-state-notebook", "docs_wide", "NotebookEdit", {"notebook_path": "{P}/docs/pipeline/hp/state.json"}, False),
    ("record-logs", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/logs/01_s.jsonl", "content": "x"}, False),
    ("record-hook-trace", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/hook/trace.jsonl", "content": "x"}, False),
    ("record-hook-bash-state", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/hook/bash_state.json", "content": "x"}, False),
    ("record-input", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/00_input.md", "content": "x"}, False),
    ("record-summary", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/99_summary.md", "content": "x"}, False),
    ("record-probe", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/probe/0123456789abcdef.txt", "content": "x"}, False),
    ("record-other-pipe", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/other/02_design.md", "content": "x"}, False),
    ("record-archive", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/archive/20260101-000000/state.json", "content": "x"}, False),
    ("record-bash-redirect", "docs_wide_bash", "Bash", {"command": "echo x > docs/pipeline/hp/state.json"}, False),
    ("docs-wide-own-sibling", "docs_wide", "Write", {"file_path": "{P}/docs/pipeline/hp/other.md", "content": "x"}, False),
    # code の段：.claude/・.git/・pipeline.toml・パイプのフォルダ・記録
    ("claude-settings", "code_b", "Write", {"file_path": "{P}/.claude/settings.json", "content": "{}"}, True),
    ("claude-hooks", "code_b", "Edit", {"file_path": "{P}/.claude/hooks/pipe_in_guard.py", "old_string": "a", "new_string": "b"}, True),
    ("git-config", "code_b", "Write", {"file_path": "{P}/.git/config", "content": "x"}, True),
    ("pipeline-toml", "code_b", "Write", {"file_path": "{P}/pipeline.toml", "content": "x"}, True),
    ("pipe-prompts", "code_b", "Write", {"file_path": "{P}/.pipe-in/pipes/pipe-in-hp/prompts/a.md", "content": "x"}, True),
    ("code-record", "code_b", "Write", {"file_path": "{P}/docs/pipeline/hp/state.json", "content": "x"}, True),
    ("code-writes-tests", "code_b", "Write", {"file_path": "{P}/tests/test_a.py", "content": "x"}, True),
    # bash = true の段の危険なコマンドと書き込みの形
    ("bash-git-push", "code_b", "Bash", {"command": "git push origin main"}, True),
    ("bash-reset-hard", "code_b", "Bash", {"command": "git reset --hard"}, True),
    ("bash-rm-rf", "code_b", "Bash", {"command": "rm -rf build"}, True),
    ("bash-curl", "code_b", "Bash", {"command": "curl http://example.com"}, True),
    ("bash-sudo", "code_b", "Bash", {"command": "sudo ls"}, True),
    ("bash-redirect-tests", "code_b", "Bash", {"command": "echo x > tests/test_a.py"}, True),
    ("bash-redirect-claude", "code_b", "Bash", {"command": "echo x > .claude/settings.json"}, True),
    ("bash-redirect-pipeline-toml", "code_b", "Bash", {"command": "echo x > pipeline.toml"}, True),
    ("bash-redirect-git", "code_b", "Bash", {"command": "echo x > .git/config"}, True),
    ("bash-tee-record", "code_b", "Bash", {"command": "tee docs/pipeline/hp/state.json"}, True),
    ("bash-cp-pipe-folder", "code_b", "Bash", {"command": "cp src/a.py .pipe-in/pipes/pipe-in-hp/pipe.toml"}, True),
    ("bash-sed-i-record", "code_b", "Bash", {"command": "sed -i s/a/b/ docs/pipeline/hp/state.json"}, True),
    ("bash-background", "code_b", "Bash", {"command": "ls", "run_in_background": True}, True),
    ("bash-tests-stage-src", "tests_b", "Bash", {"command": "echo x > src/app.py"}, True),
]
ESCAPE_CONFIGS = {**{k: v for k, v in CONFIGS.items()}, "docs_wide_bash": lambda: one("docs", docs_dir="docs", bash=True)}


@pytest.mark.parametrize("name,config,tool,tool_input,sdk_blocks", ESCAPES, ids=[e[0] for e in ESCAPES])
def test_d0077_ac27_すり抜けの道は止まる(tmp_path, name, config, tool, tool_input, sdk_blocks):
    """D0077-AC-27: 書ける範囲の外を、Bash（bash = false の段）・危険なコマンド・PowerShell・MCP・Agent・Task・Web・ノートブック・.. を含むパス・
    パイプのフォルダ・記録・前のパイプの記録・.claude/・.git/・pipeline.toml・Skill のどの道で書こうとしても止まる。"""
    r, sdk = prepared(tmp_path, ESCAPE_CONFIGS[config]())
    data = fill(tool_input, r.project)
    if sdk_blocks:
        assert sdk(tool, data), f"前提：本体の道でも止まる形のはず（{name}）"
    else:
        assert sdk(tool, data) is None, f"前提：本体の道では止まらず、会話の道が追加で止める形のはず（{name}）"
    assert r.start()["ok"] is True
    r.verify_probe()
    r.run_next("s")
    assert r.hook(tool, data), f"{name} が止まらなかった"


def test_d0077_ac27_bashのcdをまたいだ覚えは呼び出しをまたいで効く(tmp_path):
    """D0077-AC-27: bash = true の段で cd tests したあとの相対パスの書き込みは、別の呼び出し（別プロセスのフック）でも覚えていて、テストへの書き込みとして止まる。"""
    (tmp_path / "tests").mkdir()
    r, sdk = prepared(tmp_path, CONFIGS["code_b"]())
    state = BashState.new(sdk.cfg.project_dir)
    assert sdk("Bash", {"command": "cd tests"}, state) is None
    assert sdk("Bash", {"command": "echo x > a.py"}, state), "前提：本体の道は cd を覚えて止める"
    assert r.start()["ok"] is True
    r.verify_probe()
    r.run_next("s")
    assert r.hook("Bash", {"command": "cd tests"}) is None
    assert r.hook("Bash", {"command": "echo x > a.py"}), "cd を覚えていない（別の呼び出しで忘れた）"


def test_d0077_ac27_覚えは新しい段で作り直す(tmp_path):
    """D0077-AC-27: Bash の覚え（hook/bash_state.json）は段が変わると作り直す。前の段の cd を次の段に持ち越さない。"""
    (tmp_path / "tests").mkdir()
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("s1", access="code", extra="bash = true\n"), stage_toml("s2", access="code", extra="bash = true\n")))
    r.run_next("s1")
    assert r.hook("Bash", {"command": "cd tests"}) is None
    assert r.hook("Bash", {"command": "echo x > a.py"}), "同じ段の中では覚えている"
    r.finish("s1")
    r.run_next("s2")
    assert r.hook("Bash", {"command": "echo x > a.py"}) is None, "次の段にも cd を持ち越した"


def test_d0077_ac27_覚えが壊れていれば相対パスの書き込みを止める(tmp_path):
    """D0077-AC-27: hook/bash_state.json が壊れて読めないときは、相対パスの書き込みを止める（安全側）。壊れる前は同じ書き込みが通る。"""
    r, _ = opened(tmp_path, CONFIGS["code_b"]())
    assert r.hook("Bash", {"command": "echo x > src/a.py"}) is None, "前提：壊れる前は通る"
    state_file = r.run_dir / "hook" / "bash_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{壊れた", encoding="utf-8")
    assert r.hook("Bash", {"command": "echo x > src/a.py"}), "覚えが壊れているのに相対パスの書き込みが通った"


# ---- AC-28 ----------------------------------------------------------------------------------

READS = [
    ("Read", {"file_path": "{P}/src/app.py"}),
    ("Read", {"file_path": "{P}/docs/pipeline/hp/state.json"}),
    ("Read", {"file_path": "{PP}/outside.txt"}),
    ("Glob", {"pattern": "**/*.py"}),
    ("Glob", {"pattern": "*.md", "path": "{P}/docs"}),
    ("Grep", {"pattern": "x", "path": "{P}/src"}),
    ("Grep", {"pattern": "x"}),
]


@pytest.mark.parametrize("config", ["read", "docs", "tests_w", "code_w"])
def test_d0077_ac28_読む道具はどの段でも通る(tmp_path, config):
    """D0077-AC-28: Read・Glob・Grep は、どの段でも（記録や範囲外のパスに対しても）通る。"""
    r, _ = opened(tmp_path, CONFIGS[config]())
    for tool, data in READS:
        assert r.hook(tool, fill(data, r.project)) is None, (tool, data)


# ---- AC-29：読めない時や段が無い時は pipe-stage をすべて止める ------------------------------------


def _control(r: Run) -> None:
    """前提：変える前は、成果物への書き込みが通る。"""
    assert r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"}) is None


def _write_own(r: Run) -> str | None:
    return r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"})


@pytest.mark.parametrize("text", ["{not json", "", "[]", "null", '"x"', "1"], ids=["broken", "empty", "list", "null", "string", "number"])
def test_d0077_ac29_標準入力がJSONとして読めないと止める(tmp_path, text):
    """D0077-AC-29: 標準入力が JSON（の辞書）として読めないときは止める。"""
    reason = hook_decision(text)
    assert reason


@pytest.mark.parametrize("agent_type", [1, True, 3.5, ["pipe-stage"], {"a": "pipe-stage"}], ids=["int", "bool", "float", "list", "dict"])
def test_d0077_ac29_agent_typeが文字列でないと段が開いている間は止まる(tmp_path, agent_type):
    """D0077-AC-29: agent_type が文字列でない呼び出しは pipe-stage とは判定できないが、段が開いているので FR-12 で止まる。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    _control(r)
    assert r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"}, agent_type)


def test_d0077_ac29_openが無いとpipe_stageをすべて止める(tmp_path):
    """D0077-AC-29: open（今の段）が無い（確かめだけ済んで、まだ段が始まっていない）ときは、pipe-stage の呼び出しをすべて止める。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("s", output="out.md")))
    assert r.state()["open"] is None
    assert _write_own(r), "段が開いていないのに通った"
    assert r.hook("Read", {"file_path": str(tmp_path / "x")}), "読む道具も止める"
    r.run_next("s")
    _control(r)
    r.finish("s")
    assert _write_own(r), "段が閉じたあとも通ってはいけない"


def test_d0077_ac29_state_jsonが壊れているとpipe_stageをすべて止める(tmp_path):
    """D0077-AC-29: state.json が壊れて読めないときは、pipe-stage の呼び出しをすべて止める（読む道具も）。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    _control(r)
    (r.run_dir / "state.json").write_text("{壊れた", encoding="utf-8")
    assert _write_own(r)
    assert r.hook("Read", {"file_path": str(tmp_path / "x")})


@pytest.mark.parametrize("which", ["pipe.toml", "pipeline.toml"])
def test_d0077_ac29_定義が始めたときと違うとpipe_stageをすべて止める(tmp_path, which):
    """D0077-AC-29: pipe.toml（と pipeline.toml）が始めたときと違うときは、pipe-stage の呼び出しをすべて止める。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    _control(r)
    if which == "pipe.toml":
        path = r.pipe_dir / "pipe.toml"
        path.write_text(path.read_text(encoding="utf-8") + "\n# 変えた\n", encoding="utf-8")
    else:
        (tmp_path / "pipeline.toml").write_text('[pipeline]\nprotected_paths = ["x/*"]\n', encoding="utf-8")
    assert _write_own(r)
    assert r.hook("Read", {"file_path": str(tmp_path / "x")})


def test_d0077_ac29_openの段が定義に無いとpipe_stageをすべて止める(tmp_path):
    """D0077-AC-29: open の段の名前が定義に無いときは、pipe-stage の呼び出しをすべて止める。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    _control(r)
    state = r.state()
    state["open"]["stage"] = "nope"
    (r.run_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    assert _write_own(r)


def test_d0077_ac29_openが2つあるとpipe_stageをすべて止める(tmp_path):
    """D0077-AC-29: 別のパイプの記録にも open があり、どちらの段か決められないときは、pipe-stage の呼び出しをすべて止める。"""
    a, b = Run(tmp_path, "hp"), Run(tmp_path, "hq")
    for r in (a, b):
        r.make(CONFIGS["read"]())
        assert r.start()["ok"] is True
        r.verify_probe()
    a.run_next("s")
    _control(a)
    b.run_next("s")
    assert a.state()["open"] and b.state()["open"]
    assert _write_own(a) and _write_own(b)


def test_d0077_ac29_記録が見つからないとpipe_stageを止める(tmp_path):
    """D0077-AC-29: 記録（docs/pipeline/<パイプ>/state.json）が見つからない作業フォルダでの pipe-stage の呼び出しは止める。"""
    assert call_hook(tmp_path, "Write", {"file_path": str(tmp_path / "src" / "a.py"), "content": "x"})
    assert call_hook(tmp_path, "Read", {"file_path": str(tmp_path / "src" / "a.py")})


# ---- AC-30：他のエージェントと、会話本体 ----------------------------------------------------------

OTHERS = ["general-purpose", "Explore", "pipe-builder", "pipe-in:pipe-builder", "pipe-in:pipe-judge", "pipe-in-auditor", "xyz:other"]
ANY_TOOLS = [
    ("Read", {"file_path": "{P}/src/a.py"}),
    ("Write", {"file_path": "{P}/src/a.py", "content": "x"}),
    ("Bash", {"command": "ls"}),
    ("Agent", {"prompt": "x", "run_in_background": False}),
]


@pytest.mark.parametrize("agent_type", OTHERS)
def test_d0077_ac30_段が開いている間は他のエージェントを止める(tmp_path, agent_type):
    """D0077-AC-30: 段が開いている間、pipe-stage・pipe-probe 以外の agent_type の道具の呼び出しは止まる（読む道具も）。段が閉じれば止めない。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    for tool, data in ANY_TOOLS:
        assert r.hook(tool, fill(data, r.project), agent_type), f"{agent_type} の {tool} が段の間に通った"
    r.finish("s")
    assert r.state()["open"] is None
    assert r.hook("Write", {"file_path": str(r.project / "src" / "a.py"), "content": "x"}, agent_type) is None or agent_type in (
        "pipe-builder",
        "pipe-in:pipe-builder",
        "pipe-in:pipe-judge",
    ), "段が閉じたあとは何もしない"


def test_d0077_ac30_会話本体は何もされない(tmp_path):
    """D0077-AC-30: agent_type の無い呼び出し（会話本体）は、段が開いている間も何もしない。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    for tool, data in ANY_TOOLS:
        assert r.hook(tool, fill(data, r.project), None) is None, tool


def test_d0077_ac30_pipe_chatでない記録の作業フォルダでは何もしない(tmp_path):
    """D0077-AC-30: 記録が pipe-chat でない作業フォルダ（開発フローの記録・記録なし）では、他のエージェントの呼び出しに何もしない。"""
    from pipe_in.dev.record import Recorder

    rec = Recorder(load_config(tmp_path))
    rec.start("メモ")
    rec.begin("requirements")
    assert json.loads((tmp_path / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))["open"], "前提：開いた段がある"
    for agent in ["general-purpose", "Explore", None]:
        assert call_hook(tmp_path, "Write", {"file_path": str(tmp_path / "src" / "a.py"), "content": "x"}, agent) is None, agent
        assert call_hook(tmp_path, "Bash", {"command": "ls"}, agent) is None, agent
    empty = tmp_path / "empty"
    empty.mkdir()
    assert call_hook(empty, "Write", {"file_path": str(empty / "a.py"), "content": "x"}, "general-purpose") is None


# ---- AC-31：名前 ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_type", ["pipe-stage", "pipe-in:pipe-stage", "xyz:pipe-stage"])
def test_d0077_ac31_プラグイン付きの名前はpipe_stageと同じ扱い(tmp_path, agent_type):
    """D0077-AC-31: <プラグイン>:pipe-stage の形でも pipe-stage と同じに扱う（成果物には書け、範囲外は止まる）。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    assert r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"}, agent_type) is None
    assert r.hook("Write", {"file_path": str(r.project / "src" / "a.py"), "content": "x"}, agent_type)
    assert r.hook("Read", {"file_path": str(r.project / "src" / "a.py")}, agent_type) is None


@pytest.mark.parametrize(
    "agent_type",
    ["pipe-stage-x", "my-pipe-stage", "pipe-stage2", "Pipe-Stage", "pipe-stages", "pipe-stage:x", "pipe-stage ", "pipe-probe-x", "my-pipe-probe"],
)
def test_d0077_ac31_前方一致と部分一致はpipe_stageではなく段の間は止まる(tmp_path, agent_type):
    """D0077-AC-31: 名前の前方一致・部分一致（pipe-stage-x・my-pipe-stage など）は pipe-stage として扱わない（成果物にも書けず、段の間は FR-12 で止まる）。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    assert r.hook("Write", {"file_path": str(r.output_path("s")), "content": "x"}, agent_type)
    assert r.hook("Read", {"file_path": str(r.project / "src" / "a.py")}, agent_type)


# ---- AC-32：既存の pipe-builder・pipe-judge の判断は変わらない ----------------------------------------

# (agent_type, 道具, 入力, 通すか)。tests/test_guard_hook.py の表の代表
GUARD_TABLE = [
    ("pipe-in:pipe-builder", "Write", {"file_path": ".pipe-in/pipes/pipe-in-x/pipe.toml"}, True),
    ("pipe-builder", "Write", {"file_path": "pipes/pipe-in-x/prompts/02_b.md"}, True),
    ("pipe-in:pipe-builder", "Write", {"file_path": "src/a.py"}, False),
    ("pipe-in:pipe-builder", "Edit", {"file_path": ".pipe-in/pipes/pipe-in-x/run.sh"}, False),
    ("pipe-in:pipe-builder", "Write", {"file_path": ".pipe-in/pipes/pipe-in-x/../../src/a.py"}, False),
    ("pipe-in:pipe-builder", "Bash", {"command": "pipe-in-gen list"}, True),
    ("pipe-in:pipe-builder", "Bash", {"command": "pipe-in-gen new x --from diagrams"}, True),
    ("pipe-in:pipe-builder", "Bash", {"command": "pipe-in-gen new x --force"}, False),
    ("pipe-in:pipe-builder", "Bash", {"command": "pipe-in-gen design x"}, False),
    ("pipe-in:pipe-builder", "Bash", {"command": "pipe-in-gen list; rm -rf ."}, False),
    ("pipe-in:pipe-builder", "Read", {"file_path": "src/a.py"}, True),
    ("pipe-in:pipe-builder", "PowerShell", {"command": "pipe-in-gen list"}, False),
    ("pipe-in:pipe-builder", "mcp__x__y", {}, False),
    ("pipe-in:pipe-builder", "Agent", {"prompt": "x"}, False),
    ("pipe-in:pipe-builder", "Skill", {"skill": "x"}, False),
    ("pipe-in:pipe-builder", "WebFetch", {"url": "https://example.com"}, False),
    ("pipe-judge", "Read", {"file_path": "out/report.md"}, True),
    ("pipe-in:pipe-judge", "Grep", {"pattern": "x"}, True),
    ("xyz:pipe-judge", "Glob", {"pattern": "**/*.md"}, True),
    ("pipe-in:pipe-judge", "Write", {"file_path": "out/a.md"}, False),
    ("pipe-in:pipe-judge", "Bash", {"command": "pipe-in-gen list"}, False),
    ("pipe-in:pipe-judge", "Task", {"prompt": "x"}, False),
    ("pipe-in:pipe-judge", "Foo", {}, False),
    ("Explore", "Write", {"file_path": "src/a.py"}, True),
    ("general-purpose", "Bash", {"command": "rm -rf build"}, True),
    ("pipe-judge2", "Write", {"file_path": "src/a.py"}, True),
    ("my-pipe-judge", "Bash", {"command": "touch x"}, True),
    ("pipe-builder-x", "Write", {"file_path": "src/a.py"}, True),
    (None, "Bash", {"command": "rm -rf build"}, True),
    (None, "Write", {"file_path": "src/a.py"}, True),
]


def test_d0077_ac32_前提_今のguard_hookの結果が表と同じ_守る(tmp_path, monkeypatch):
    """D0077-AC-32（前提）: 表の各行が、今の guard_hook.decide の結果と同じであること（表の期待が正しいことの確かめ。今のまま通る。守る）。"""
    from pipe_in_generator import guard_hook

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(OLD_PIPES_ENV, raising=False)
    for agent, tool, data, allowed in GUARD_TABLE:
        want = guard_hook.decide(hook_payload(tmp_path, tool, data, agent), pipes_env=guard_hook.env_pipes_dirs(os.environ))
        assert (want is None) == allowed, (agent, tool, data)


@pytest.mark.parametrize("with_record", [False, True], ids=["no-record", "chat-record-no-open-stage"])
def test_d0077_ac32_既存のpipe_builderとpipe_judgeの判断は変わらない(tmp_path, monkeypatch, with_record):
    """D0077-AC-32: 会話の記録が無い作業フォルダ（と、記録はあるが段が開いていない作業フォルダ）では、chat_hook.main 経由でも
    pipe-builder・pipe-judge の絞りと、ほかのエージェントへの無干渉が、今の guard_hook.decide と同じ結果になる。"""
    from pipe_in_generator import guard_hook

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(OLD_PIPES_ENV, raising=False)
    if with_record:
        r = Run(tmp_path)
        r.make(CONFIGS["read"]())
        assert r.start()["ok"] is True
    project = tmp_path.resolve()
    bad: list[str] = []
    for agent, tool, data, allowed in GUARD_TABLE:
        payload = hook_payload(project, tool, data, agent)
        want = guard_hook.decide(payload, pipes_env=guard_hook.env_pipes_dirs(os.environ))
        assert (want is None) == allowed, f"前提：今の guard_hook の結果が表と違う {agent} {tool} {data}"
        got = hook_decision(json.dumps(payload))
        if (got is None) != allowed:
            bad.append(f"{agent} {tool} {data}: 今={'通す' if allowed else '止める'} chat_hook={'通す' if got is None else '止める'}")
    assert bad == []
