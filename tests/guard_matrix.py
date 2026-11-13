"""D0083：守りの比較表のデータと、各守りを呼ぶ小さな部品（テストではない。tests/test_guard_matrix.py が使う）。

同じ道具の呼び出しを、9つの列（4つの守りの入口）に通した結果を、1行1つの 9 文字の文字列で持つ。
A＝許す、D＝止める。列の並びは COLUMNS。

この表は「いまの結果を固定する」ためのもので、望ましい結果を決めるものではない（D0083）。
期待の値は、読みからの予想でなく、実際に流した結果をそのまま入れた。1つの守りの中の結果は、既存のテスト
（test_agent_guard.py・test_bash_write_guard.py・test_chat_hook.py・test_guard_hook.py・test_pipe_in_guard.py など）が
固定している。ここは「同じ呼び出しを横に並べて比べる」ことだけを持つ。

守りを変えて、ある行が「許す → 止める」になったら、この表が落ちて差が見える。「止める → 許す」になったときは、
守りが狭まったということなので、理由を決定の記録に書く（CLAUDE.md の「必ず守ること」）。

どれも tmp_path の中だけに書く（リポジトリの pipes/・.pipe-in/・docs/pipeline/・.claude/ には書かない）。SDK は呼ばない。
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
from pathlib import Path
from typing import Any, NamedTuple

from chat_support import STAGE, Run, call_hook, hook_payload, pipe_toml, stage_toml

from pipe_in.engine.config import load_config
from pipe_in.engine.guard import make_guard_hook
from pipe_in.pipe import definition as pd
from pipe_in.pipe.specs import build_pipe_specs

REPO = Path(__file__).resolve().parents[1]
DEV_HOOK = REPO / ".claude" / "hooks" / "pipe_in_guard.py"

# 列の並び（expect の 1 文字が 1 列）
COLUMNS = (
    "sdk",  # SDK の道（既定の守りだけ＝protected_paths は空。D0084 で、既定で守る場所（.claude/・.git/・.pipe-in/・pipeline.toml・.mcp.json）は設定なしで止まる）：guard.make_guard_hook
    "sdk_protected",  # SDK の道（利用者が同じ場所 .claude/・.git/・.pipe-in/・pipeline.toml を protected_paths にも書いた場合）
    "chat",  # 会話の道：chat_hook.main に pipe-in:pipe-stage の呼び出しを通す（段が開いている間）
    "plugin_builder",  # プラグインの作る役：guard_hook.decide（pipe-in:pipe-builder）
    "plugin_judge",  # プラグインの審査役：guard_hook.decide（pipe-in:pipe-judge）
    "dev_analyst",  # 開発用のフック：.claude/hooks/pipe_in_guard.py の decide（pipe-in-analyst）
    "dev_tester",  # 同（pipe-in-tester）
    "dev_coder",  # 同（pipe-in-coder）
    "dev_verifier",  # 同（pipe-in-verifier）
)
DEV_AGENTS = {
    "dev_analyst": "pipe-in-analyst",
    "dev_tester": "pipe-in-tester",
    "dev_coder": "pipe-in-coder",
    "dev_verifier": "pipe-in-verifier",
}
PLUGIN_AGENTS = {"plugin_builder": "pipe-in:pipe-builder", "plugin_judge": "pipe-in:pipe-judge"}

# 段の種類（SDK の道と会話の道の列だけが使う。作る側・開発用の列は段の種類を見ない）。
# どの段も、成果物は docs/pipeline/hp/out.md。code+bash は bash = true で、サブエージェント reader を持つ（Agent・Task を許す段）
OWN = "docs/pipeline/hp/out.md"
AGENTS_TOML = '[stages.agents.reader]\ndescription = "1つのモジュールを読む"\nprompt = "渡されたモジュールだけを読む"\ntools = ["Read", "Grep"]\n'
KIND_TOML = {
    "read": lambda: pipe_toml(stage_toml("s", access="read", output="out.md")),
    "docs": lambda: pipe_toml(stage_toml("s", access="docs", output="out.md", docs_dir="docs/out")),
    "tests": lambda: pipe_toml(stage_toml("s", access="tests", output="out.md")),
    "code": lambda: pipe_toml(stage_toml("s", access="code", output="out.md")),
    "code+bash": lambda: pipe_toml(stage_toml("s", access="code", output="out.md", extra="bash = true\n")),
    # サブエージェントを持つ段（Agent・Task を許す段）。会話の中では流せない形なので（chat start が断る）、会話の道の列は '-'（判断しない）
    "code+bash+agents": lambda: pipe_toml(stage_toml("s", access="code", output="out.md", extra="bash = true\n" + AGENTS_TOML)),
}
# 会話の中で流せない段の種類
NO_CHAT = {"code+bash+agents"}
# 利用者が protected_paths に書く4か所
PROTECTED = [".claude/*", ".git/*", ".pipe-in/*", "pipeline.toml"]


class Row(NamedTuple):
    id: str
    tool: str
    tool_input: dict[str, Any]
    kind: str  # 段の種類（KIND_TOML のキー）
    expect: str  # COLUMNS と同じ長さ。A＝許す、D＝止める
    extra: dict[str, Any] = {}  # フックの入力の上の段に足すもの（agent_id など）


# ---- 実測の入れ物 ------------------------------------------------------------------------------


@dataclasses.dataclass
class KindEnv:
    """段の種類ごとに 1 つ作るプロジェクト。会話の道は、ここで段を開いたまま使う。"""

    kind: str
    run: Run
    cfg: Any
    spec: Any
    protected_spec: Any
    links_ok: bool

    @property
    def project(self) -> Path:
        return self.run.project


def _symlink(link: Path, target: Path) -> bool:
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return False
    return True


def build_kind(root: Path, kind: str) -> KindEnv:
    """root の下に kind 用のプロジェクトを作り、会話の道の段を開く。リンクを作れなければ links_ok は False。"""
    project = root / kind.replace("+", "_")
    project.mkdir(parents=True)
    for rel in (".claude/settings.json", ".git/config", "src/app.py", "tests/test_a.py", ".pipe-in/config.json", "pipeline.toml", ".mcp.json"):
        f = project / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n", encoding="utf-8")
    run = Run(project)
    run.make(KIND_TOML[kind]())
    (run.pipe_dir / "prompts").mkdir(exist_ok=True)
    # pipeline.toml は空のままでよい（protected_paths は後で cfg に足す）。中身を変えたら記録の指紋が変わるので、start の前に決める
    (project / "pipeline.toml").write_text("", encoding="utf-8")
    links_ok = _symlink(run.pipe_dir / "prompts" / "link.md", project / ".claude" / "settings.json")
    links_ok = _symlink(project / "src" / "link.json", project / ".claude" / "settings.json") and links_ok
    cfg = load_config(run.project).for_pipe(run.pipe, own_work_dir=True)
    pipe = pd.load_pipe(run.pipe_dir)
    spec = build_pipe_specs(cfg, pipe)["s"]
    protected_spec = build_pipe_specs(dataclasses.replace(cfg, protected_paths=list(PROTECTED)), pipe)["s"]
    # 会話の道：本物の流れで段を開く（始める → 確かめ → 次の段）。流せない形の段は開かない
    if kind not in NO_CHAT:
        out = run.start()
        assert out["ok"] is True, out
        run.verify_probe()
        run.run_next("s")
    return KindEnv(kind, run, cfg, spec, protected_spec, links_ok)


def fill_row(row: Row, project: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from chat_support import fill

    return fill(row.tool_input, project), dict(row.extra)


# ---- 各守りを呼ぶ -------------------------------------------------------------------------------


def _verdict(reason: Any) -> str:
    return "A" if reason is None else "D"


def sdk_verdict(env: KindEnv, spec: Any, tool: str, tool_input: dict[str, Any], extra: dict[str, Any]) -> str:
    """SDK の道：段の1回の実行のガード（make_guard_hook）を作って 1 回呼ぶ。agent_id などの入力の上の段も渡せる。"""
    guard = make_guard_hook(
        project_dir=env.cfg.project_dir,
        can_write=spec.can_write,
        allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint,
        allowed_tools=spec.allowed_tools,
        fetch_domains=spec.fetch_domains,
        max_agent_calls=spec.max_agent_calls,
    )
    result = asyncio.run(guard({"tool_name": tool, "tool_input": tool_input, **extra}, "t-1", None))
    return "D" if result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" else "A"


def chat_verdict(env: KindEnv, tool: str, tool_input: dict[str, Any], extra: dict[str, Any]) -> str:
    if env.kind in NO_CHAT:
        return "-"  # 会話の中では流せない段（判断しない）
    return _verdict(call_hook(env.project, tool, tool_input, STAGE, **extra))


def plugin_verdict(agent: str, project: Path, tool: str, tool_input: dict[str, Any], extra: dict[str, Any], pipes_env: Any = ()) -> str:
    from pipe_in_generator import guard_hook

    payload = hook_payload(project, tool, tool_input, agent, **extra)
    return _verdict(guard_hook.decide(payload, pipes_env=list(pipes_env)))


_dev_module: Any = None


def dev_hook() -> Any:
    """.claude/hooks/pipe_in_guard.py を読み込む（直さない。読んで呼ぶだけ）。"""
    global _dev_module
    if _dev_module is None:
        spec = importlib.util.spec_from_file_location("pipe_in_guard_matrix", DEV_HOOK)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _dev_module = mod
    return _dev_module


def dev_verdict(agent: str, project: Path, tool: str, tool_input: dict[str, Any], extra: dict[str, Any]) -> str:
    payload = hook_payload(project, tool, tool_input, agent, **extra)
    return _verdict(dev_hook().decide(payload, root=str(project)))


def evaluate(env: KindEnv, row: Row) -> str:
    """行を 9 つの列に通した結果（9 文字）。"""
    tool_input, extra = fill_row(row, env.project)
    out = {
        "sdk": sdk_verdict(env, env.spec, row.tool, tool_input, extra),
        "sdk_protected": sdk_verdict(env, env.protected_spec, row.tool, tool_input, extra),
        "chat": chat_verdict(env, row.tool, tool_input, extra),
    }
    for col, agent in PLUGIN_AGENTS.items():
        out[col] = plugin_verdict(agent, env.project, row.tool, tool_input, extra)
    for col, agent in DEV_AGENTS.items():
        out[col] = dev_verdict(agent, env.project, row.tool, tool_input, extra)
    return "".join(out[c] for c in COLUMNS)


# ---- 表 ------------------------------------------------------------------------------------------

Q = "?" * len(COLUMNS)  # 下の EXPECT で入れる（行の定義と結果の表を分けて、結果を行列として読めるようにする）

SETTINGS = "{P}/.claude/settings.json"
# 4か所に書く行は、段の種類を code にそろえる（SDK の道では code の段が .claude/ などを書けるので、保護の有無の差が出る）
_DEFS: list[Row] = [
    # ---- 許す行（代表） ----
    Row("write-code-ok", "Write", {"file_path": "{P}/src/app.py", "content": "x"}, "code", Q),
    Row("write-test-ok", "Write", {"file_path": "{P}/tests/test_b.py", "content": "x"}, "tests", Q),
    Row("write-docs-ok", "Write", {"file_path": "{P}/docs/out/a.md", "content": "x"}, "docs", Q),
    Row("write-output-ok", "Write", {"file_path": "{P}/" + OWN, "content": "x"}, "read", Q),
    Row("read-ok", "Read", {"file_path": "{P}/src/app.py"}, "read", Q),
    Row("bash-pytest-ok", "Bash", {"command": "python -m pytest -q"}, "code+bash", Q),
    Row("bash-git-add", "Bash", {"command": "git add src/app.py"}, "code+bash", Q),
    Row("bash-git-commit", "Bash", {"command": "git commit -m x"}, "code+bash", Q),
    Row("bash-git-push", "Bash", {"command": "git push origin main"}, "code+bash", Q),
    Row("bash-pipe-in-gen-list", "Bash", {"command": "pipe-in-gen list"}, "code+bash", Q),
    Row("write-pipes-prompt", "Write", {"file_path": "{P}/pipes/pipe-in-x/prompts/a.md", "content": "x"}, "code", Q),
    Row("write-pipes-toml", "Write", {"file_path": "{P}/pipes/pipe-in-x/pipe.toml", "content": "x"}, "code", Q),
    Row("write-pipes-readme", "Write", {"file_path": "{P}/pipes/pipe-in-x/README.md", "content": "x"}, "code", Q),
    # Skill と Agent の差の理由（D0083）：
    #  - Skill は guard.ALWAYS_ALLOWED にあり、allowed_tools があっても SDK の道では通る。Skill はスキルの読み込みで、
    #    書き込みも Bash も持たず、Skill の中の道具の呼び出しは、このフックを別に通る。段の範囲の外へ出る道は無いと見て、止めない。
    #    会話の道だけは Skill を止める（範囲外の操作をする道を残さないため）。Skill を SDK の道で止めるかは別に決める。
    Row("skill", "Skill", {"skill": "x"}, "read", Q),
    # Agent・Task は、サブエージェントが別の道具の組で動き、段の範囲とは別に書き込みができてしまう。そのため allowed_tools に
    # 書いた段（agents を持つ段）だけ、run_in_background: false・isolation なし・agent_id なし・回数が上限内のときだけ通す。
    Row("agent-listed", "Agent", {"prompt": "x", "subagent_type": "reader", "run_in_background": False}, "code+bash+agents", Q),
    Row("task-listed", "Task", {"prompt": "x", "run_in_background": False}, "code+bash+agents", Q),
    Row("agent-not-listed", "Agent", {"prompt": "x", "run_in_background": False}, "read", Q),
    Row("agent-background", "Agent", {"prompt": "x", "run_in_background": True}, "code+bash+agents", Q),
    Row("agent-nested", "Agent", {"prompt": "x", "run_in_background": False}, "code+bash+agents", Q, {"agent_id": "a-1"}),
    # SubagentHandback（D0096）：報告を親の会話に渡すだけの道具（auto モードでサブエージェントに渡される）。書かない。
    # プラグインの 2 役・会話の道・開発用は通す。SDK の道は段が auto で動かずこの道具を受け取らないので、guard.py は変えず止めたまま
    Row("report-handback", "SubagentHandback", {"message": "報告"}, "read", Q),
    # ---- 止める行：既定で守る場所（.claude/・.git/・.pipe-in/・pipeline.toml・.mcp.json）・パイプのフォルダ・記録・外 ----
    Row("write-dotclaude", "Write", {"file_path": SETTINGS, "content": "{}"}, "code", Q),
    Row("write-dotgit", "Write", {"file_path": "{P}/.git/config", "content": "x"}, "code", Q),
    Row("write-dotpipein", "Write", {"file_path": "{P}/.pipe-in/config.json", "content": "x"}, "code", Q),
    Row("write-pipelinetoml", "Write", {"file_path": "{P}/pipeline.toml", "content": "x"}, "code", Q),
    Row("write-mcpjson", "Write", {"file_path": "{P}/.mcp.json", "content": "{}"}, "code", Q),
    Row("write-running-pipe-toml", "Write", {"file_path": "{P}/.pipe-in/pipes/pipe-in-hp/pipe.toml", "content": "x"}, "code", Q),
    Row("write-running-pipe-prompt", "Write", {"file_path": "{P}/.pipe-in/pipes/pipe-in-hp/prompts/a.md", "content": "x"}, "code", Q),
    Row("write-record", "Write", {"file_path": "{P}/docs/pipeline/hp/state.json", "content": "{}"}, "code", Q),
    Row("write-outside", "Write", {"file_path": "{PP}/outside.txt", "content": "x"}, "code", Q),
    # ---- すり抜けの道（.claude/settings.json に対して） ----
    Row("bypass-rel", "Write", {"file_path": ".claude/settings.json", "content": "{}"}, "code", Q),
    Row("bypass-dotdot-abs", "Write", {"file_path": "{P}/src/../.claude/settings.json", "content": "{}"}, "code", Q),
    Row("bypass-dotdot-rel", "Write", {"file_path": "src/../.claude/settings.json", "content": "{}"}, "code", Q),
    # リンクを経た道：src/link.json と パイプの prompts/link.md は、どちらも .claude/settings.json を指す。
    # どの守りも先をたどって止める（D0088。SDK の道と会話の道は Path.resolve()、プラグインと開発用は os.path.realpath）
    Row("bypass-link-src", "Write", {"file_path": "{P}/src/link.json", "content": "{}"}, "code", Q),
    Row("bypass-link-pipe-prompt", "Write", {"file_path": "{P}/.pipe-in/pipes/pipe-in-hp/prompts/link.md", "content": "x"}, "code", Q),
    Row("bypass-edit", "Edit", {"file_path": SETTINGS, "old_string": "a", "new_string": "b"}, "code", Q),
    Row("bypass-multiedit", "MultiEdit", {"file_path": SETTINGS, "edits": []}, "code", Q),
    Row("bypass-notebookedit", "NotebookEdit", {"notebook_path": "{P}/.claude/a.ipynb"}, "code", Q),
    Row("bypass-subagent-write", "Write", {"file_path": SETTINGS, "content": "{}"}, "code", Q, {"agent_id": "a-1"}),
    Row("bypass-powershell", "PowerShell", {"command": "Set-Content .claude/settings.json x"}, "code+bash", Q),
    Row("bypass-mcp", "mcp__x__y", {}, "code+bash", Q),
    Row("bypass-bash-redirect", "Bash", {"command": "echo x > .claude/settings.json"}, "code+bash", Q),
    Row("bypass-bash-tee", "Bash", {"command": "tee .claude/settings.json"}, "code+bash", Q),
    Row("bypass-bash-cp", "Bash", {"command": "cp src/app.py .claude/settings.json"}, "code+bash", Q),
    Row("bypass-bash-sed-i", "Bash", {"command": "sed -i s/a/b/ .claude/settings.json"}, "code+bash", Q),
    Row("bypass-bash-python-c", "Bash", {"command": "python -c \"open('.claude/settings.json','w').write('x')\""}, "code+bash", Q),
    Row("bypass-bash-bash-c", "Bash", {"command": "bash -c 'echo x > .claude/settings.json'"}, "code+bash", Q),
    Row("bypass-bash-subst", "Bash", {"command": "echo x > $(echo .claude/settings.json)"}, "code+bash", Q),
]

# ---- 結果（実際に流した結果をそのまま入れた。読みからの予想ではない） ----------------------------------
#
#                              sdk  sdk_protected  chat  plugin_builder  plugin_judge  dev_analyst  dev_tester  dev_coder  dev_verifier
# A＝許す、D＝止める、-＝その列では判断しない（会話の中では流せない段）。
# 読み方の例：
#  - 4か所（.claude/・.git/・.pipe-in/・pipeline.toml）は、SDK の道でも設定なしで止める（D0084。sdk と sdk_protected が同じ）。
#    会話の道とプラグインも、いつも止める。開発用は pipe-in-coder が .pipe-in/・pipeline.toml に書ける（.claude/・.git/ は止まる）。
#  - .mcp.json（D0087）は、SDK の道・会話の道・プラグインで止める。開発用は pipe-in-coder だけが通す（実測）。
#  - プラグインの作る役と、開発用の pipe-in-coder だけが、流しているパイプのフォルダ（.pipe-in/pipes/pipe-in-hp/）の決まったファイルに書ける。
#  - git add・git commit は、SDK の道と会話の道（Bash を持つ段）では通り、プラグインと開発用では止まる。git push はどこも止まる。
#  - Skill は SDK の道だけが通す。Agent・Task は agents を持つ段の SDK の道だけが通す（会話の中では流せない形）。
EXPECT: dict[str, str] = {
    "write-code-ok": "AAADDDDAD",
    "write-test-ok": "AAADDDADD",
    "write-docs-ok": "AAADDDDAD",
    "write-output-ok": "AAADDDDDD",
    "read-ok": "AAAAAAAAA",
    "bash-pytest-ok": "AAADDDAAA",
    "bash-git-add": "AAADDDDDD",
    "bash-git-commit": "AAADDDDDD",
    "bash-git-push": "DDDDDDDDD",
    "bash-pipe-in-gen-list": "AAAADDDDD",
    "write-pipes-prompt": "AAAADDDAD",
    "write-pipes-toml": "AAAADDDAD",
    "write-pipes-readme": "AAAADDDAD",
    "skill": "AADDDDDDD",
    "agent-listed": "AA-DDDDDD",
    "task-listed": "AA-DDDDDD",
    "agent-not-listed": "DDDDDDDDD",
    "agent-background": "DD-DDDDDD",
    "agent-nested": "DD-DDDDDD",
    # D0096：報告の道具。SDK の道（sdk・sdk_protected）は止め、ほかの 7 列は通す。開発用の 4 列（A）と SDK の道の 2 列（D）は、
    # 行を足した時点の実測（DDDDDAAAA）と同じ。会話の道とプラグインの 2 役（実測では D）は、設計 18.2.2〜3 の直しで A になる見込みを入れた
    "report-handback": "DDAAAAAAA",
    "write-dotclaude": "DDDDDDDDD",
    "write-dotgit": "DDDDDDDDD",
    "write-dotpipein": "DDDDDDDAD",
    "write-pipelinetoml": "DDDDDDDAD",
    # D0087：.mcp.json。SDK の道（sdk・sdk_protected）と会話の道（chat）は止める（D）。
    # プラグインの作る役・審査役・dev_analyst・dev_tester・dev_verifier も止め、dev_coder は自前の一覧に無いので通す（A。残った課題）
    "write-mcpjson": "DDDDDDDAD",
    "write-running-pipe-toml": "DDDADDDAD",
    "write-running-pipe-prompt": "DDDADDDAD",
    "write-record": "DDDDDDDDD",
    "write-outside": "DDDDDDDDD",
    "bypass-rel": "DDDDDDDDD",
    "bypass-dotdot-abs": "DDDDDDDDD",
    "bypass-dotdot-rel": "DDDDDDDDD",
    # リンクを経た道：どの守りも先をたどって止める（D0088）
    "bypass-link-src": "DDDDDDDDD",
    "bypass-link-pipe-prompt": "DDDDDDDDD",
    "bypass-edit": "DDDDDDDDD",
    "bypass-multiedit": "DDDDDDDDD",
    "bypass-notebookedit": "DDDDDDDDD",
    "bypass-subagent-write": "DDDDDDDDD",
    "bypass-powershell": "DDDDDDDDD",
    "bypass-mcp": "DDDDDDDDD",
    "bypass-bash-redirect": "DDDDDDDDD",
    "bypass-bash-tee": "DDDDDDDDD",
    "bypass-bash-cp": "DDDDDDDDD",
    "bypass-bash-sed-i": "DDDDDDDDD",
    "bypass-bash-python-c": "DDDDDDDDD",
    "bypass-bash-bash-c": "DDDDDDDDD",
    "bypass-bash-subst": "DDDDDDDDD",
}
ROWS: list[Row] = [r._replace(expect=EXPECT[r.id]) for r in _DEFS]

# リンクを作れる環境でだけ流す行
LINK_ROWS = {"bypass-link-src", "bypass-link-pipe-prompt"}
# 4か所のうち .claude/settings.json に書くすり抜けの行（AC-02）。リンクの行は別に固定する
BYPASS_ROWS = [r.id for r in ROWS if r.id.startswith("bypass-") and r.id not in LINK_ROWS]
# 基準の行：何も工夫せずに .claude/settings.json に書く
BASE_ROW = "write-dotclaude"

