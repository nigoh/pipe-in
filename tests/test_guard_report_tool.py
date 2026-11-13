"""D0096-AC-38〜44：プラグインのフック（guard_hook・chat_hook）は、報告を親に渡す道具 SubagentHandback を、名前の分かるエージェントには止めない。
似た名前・ほかの道具・型のおかしい agent_type・例外は今までどおり止める。SDK は呼ばない。ファイルは tmp_path の中だけ。

フックは、本物の入口（chat_hook.main・guard_hook.main・cli.main(["guard-hook"])。標準入力の JSON → 標準出力の deny）か、
判断の関数 guard_hook.decide を、同じプロセスの中で呼ぶ（子プロセスは起こさない）。会話の道の段は、本物の chat start / probe / next で開く。
名前（SubagentHandback と似た名前）は、実装の定数を読まずにテストの側で書く。
今の作りのままで通るテスト（すり抜けの道が止まったままであること）は、docstring に「今の作りで通る（守る）」と書いた。
"""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from chat_support import OLD_PIPES_ENV, PROBE, STAGE, Run, call_hook, fill, hook_decision, hook_payload, no_sdk  # noqa: F401
from guard_matrix import COLUMNS, EXPECT, ROWS, dev_hook
from test_chat_hook import CONFIGS, OTHERS, opened
from test_guard_hook_input import deny_json

from pipe_in.engine import guard

pytestmark = pytest.mark.usefixtures("no_sdk")

REPO = Path(__file__).resolve().parents[1]
GEN_DIR = REPO / "generator"

HANDBACK = "SubagentHandback"
REPORT = {"message": "報告"}
LOOKALIKES = [
    "subagenthandback",
    "SUBAGENTHANDBACK",
    "SubAgentHandback",
    "SubagentHandback ",
    " SubagentHandback",
    "SubagentHandbackX",
    "Subagent_Handback",
    "SubagentHand",
    "mcp__x__SubagentHandback",
    "mcp__SubagentHandback",
]
# 判断の途中で例外が出たときの止める文（chat_hook.decide と guard_hook._run の今の文）
EXCEPTION_REASON = "フックが入力を判断できなかったため止めました"
JUDGE = "pipe-in:pipe-judge"
BUILDER = "pipe-in:pipe-builder"
MISSING = "<無い>"


def gh() -> Any:
    from pipe_in_generator import guard_hook

    return guard_hook


def decide(project: Path, tool: Any, tool_input: Any, agent: Any) -> str | None:
    """guard_hook.decide を、置き場所の環境変数なしで 1 回呼ぶ。"""
    return gh().decide(hook_payload(project, tool, tool_input, agent), pipes_env=[])


def trace_lines(r: Run) -> int:
    """跡（hook/trace.jsonl）の行の数。無ければ 0。"""
    path = r.run_dir / "hook" / "trace.jsonl"
    if not path.is_file():
        return 0
    return len([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()])


def open_stage(tmp_path: Path) -> Run:
    """読むだけの段（read）を、本物の流れ（始める → 確かめ → 次の段）で開く。"""
    r, _ = opened(tmp_path, CONFIGS["read"]())
    return r


# ---- AC-38：pipe-judge と pipe-builder ---------------------------------------------------------------------------

BUILDER_AND_JUDGE = ["pipe-builder", "pipe-in:pipe-builder", "pipe-judge", "pipe-in:pipe-judge", "xyz:pipe-judge"]
HANDBACK_INPUTS = {"message": REPORT, "empty": {}, "missing": MISSING, "not-dict": "text"}


@pytest.mark.parametrize("kind", sorted(HANDBACK_INPUTS))
@pytest.mark.parametrize("agent", BUILDER_AND_JUDGE)
def test_d0096_ac38_builder_and_judge_can_hand_back(tmp_path, agent, kind):
    """D0096-AC-38: pipe-judge と pipe-builder（pipe-in:・xyz: の付いた名前も）の SubagentHandback は、入力が {"message": "報告"}・空・無い・
    辞書でないのどれでも、guard_hook.decide で止まらない（None）。"""
    payload = hook_payload(tmp_path, HANDBACK, HANDBACK_INPUTS[kind], agent)
    if kind == "missing":
        del payload["tool_input"]
    reason = gh().decide(payload, pipes_env=[])
    assert reason is None, f"{agent} の {HANDBACK}（入力 {kind}）が止まった: {reason}"


@pytest.mark.parametrize("agent", ["pipe-builder", "pipe-in:pipe-builder", "pipe-judge", "pipe-in:pipe-judge"])
def test_d0096_ac38_guard_hook_entry_passes_hand_back(tmp_path, agent):
    """D0096-AC-38: pipe-in-gen guard-hook の入口（cli.main(["guard-hook"])。標準入力）に pipe-builder・pipe-judge の SubagentHandback を渡すと、
    deny の JSON を出さず（標準出力が空）、終了コード 0 で終わる。記録の無い作業フォルダで流す。"""
    reason = deny_json(json.dumps(hook_payload(tmp_path.resolve(), HANDBACK, REPORT, agent)))
    assert reason is None, f"{agent} の {HANDBACK} が入口で止まった: {reason}"


# ---- AC-39：会話の道（pipe-stage・pipe-probe・ほかのエージェント） --------------------------------------------------


def _stage_open(tmp_path: Path) -> Run:
    return open_stage(tmp_path)


def _stage_closed(tmp_path: Path) -> Run:
    r = open_stage(tmp_path)
    r.finish("s")
    assert r.state()["open"] is None, "前提：段を閉じた"
    return r


def _state_broken(tmp_path: Path) -> Run:
    """state.json を JSON として読めなくする。会話の道の記録の印（driver の pipe-chat）は残す（残さないと、記録が無いのと同じに扱われる）。"""
    r = open_stage(tmp_path)
    path = r.run_dir / "state.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n{壊れた", encoding="utf-8")
    return r


def _pipe_toml_changed(tmp_path: Path) -> Run:
    r = open_stage(tmp_path)
    path = r.pipe_dir / "pipe.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# 変えた\n", encoding="utf-8")
    return r


# 状態の名前 → (作り方, その状態での pipe-stage の Read の止める文に入る語（None なら通る）)
STAGE_STATES = {
    "open": (_stage_open, None),
    "closed": (_stage_closed, "いま開いている段がありません"),
    "broken-state": (_state_broken, "記録（state.json）が読めない"),
    "changed-pipe-toml": (_pipe_toml_changed, "始めたときから変わっている"),
}


def _assert_state(r: Run, state: str) -> None:
    """前提の確かめ：その状態で、pipe-stage の Read が今までどおりの道で判断される（開いた段だけ通り、ほかはその状態の文で止まる）。"""
    want = STAGE_STATES[state][1]
    read = r.hook("Read", {"file_path": str(r.project / "src" / "a.py")}, STAGE)
    if want is None:
        assert read is None, f"前提：{state} で pipe-stage の Read が止まった（{read}）"
    else:
        assert read and want in read, f"前提：{state} で pipe-stage の Read の止める文が想定と違う（{read}）"


@pytest.mark.parametrize("state", list(STAGE_STATES))
def test_d0096_ac39_stage_can_hand_back_in_any_state(tmp_path, state):
    """D0096-AC-39: 会話の道（chat_hook の入口）で、pipe-stage の SubagentHandback は、段が開いているとき・段を閉じたあと・state.json が壊れているとき・
    pipe.toml が始めたときから変わったときのどれでも止まらず、跡（hook/trace.jsonl）の行が増えない。
    前提として、その状態で pipe-stage の Read が今までどおりの道（開いた段だけ通り、ほかはその状態の文で止まる）で判断されることを先に見る。"""
    r = STAGE_STATES[state][0](tmp_path)
    _assert_state(r, state)
    before = trace_lines(r)
    reason = r.hook(HANDBACK, REPORT, STAGE)
    assert reason is None, f"{state} で pipe-stage の {HANDBACK} が止まった: {reason}"
    assert trace_lines(r) == before, f"{state} で跡の行が増えた"


def test_d0096_ac39_probe_can_hand_back_and_cannot_fake_probe(tmp_path):
    """D0096-AC-39: pipe-probe の SubagentHandback は、確かめの前（1 回目の前・1 回目のあと）と、確かめ済みのあとのどれでも止まらず、跡の行が増えない。
    確かめ（chat probe）は、報告の道具だけを呼んで 2 回目を呼ぶと probe_failed（フックの跡がありません）になり、
    確かめ用のパスへの Write（フックが止める）と報告を呼んで 2 回目を呼ぶと probe_ok になる（報告の道具で確かめを偽れない）。"""
    r = Run(tmp_path)
    r.make(CONFIGS["read"]())
    assert r.start()["ok"] is True
    # 確かめの 1 回目の前
    before = trace_lines(r)
    assert r.hook(HANDBACK, REPORT, PROBE) is None, "1 回目の前に pipe-probe の報告が止まった"
    assert trace_lines(r) == before
    # 確かめの 1 回目のあと（跡を読む前）
    r.ask_probe()
    before = trace_lines(r)
    reason = r.hook(HANDBACK, REPORT, PROBE)
    assert reason is None, f"1 回目のあとに pipe-probe の報告が止まった: {reason}"
    assert trace_lines(r) == before, "報告の道具で跡の行が増えた（確かめの跡に混ざる）"
    # 報告だけでは確かめは通らない
    out = r.cmd("probe")
    assert out["action"] == "probe_failed", out
    assert "フックの跡がありません" in str(out.get("reason")), out
    # 確かめ用のパスへの Write（止まる）と報告で、確かめが通る
    r.ask_probe()
    assert r.hook("Write", {"file_path": str(r.probe_path()), "content": "probe"}, PROBE), "確かめ役の範囲外の Write は止まる"
    assert r.hook(HANDBACK, REPORT, PROBE) is None
    out = r.cmd("probe")
    assert out["action"] == "probe_ok", out
    # 確かめ済みのあと
    before = trace_lines(r)
    assert r.hook(HANDBACK, REPORT, PROBE) is None, "確かめ済みのあとに pipe-probe の報告が止まった"
    assert trace_lines(r) == before


OTHER_STATES = ["open", "broken-state"]


@pytest.mark.parametrize("state", OTHER_STATES)
@pytest.mark.parametrize("agent", OTHERS)
def test_d0096_ac39_other_agents_can_hand_back_while_stage_open(tmp_path, agent, state):
    """D0096-AC-39: 段が開いている間と、記録（state.json）が読めないときの、ほかのエージェント（general-purpose・Explore・pipe-builder・
    pipe-in:pipe-builder・pipe-in:pipe-judge・pipe-in-auditor・xyz:other）の SubagentHandback は止まらず、跡の行が増えない。
    同じ相手の Read は今までどおり止まる（前提として、状態の確かめと一緒に先に見る）。"""
    r = STAGE_STATES[state][0](tmp_path)
    _assert_state(r, state)
    assert r.hook("Read", {"file_path": str(r.project / "src" / "a.py")}, agent), f"前提：{state} で {agent} の Read は止まる"
    before = trace_lines(r)
    reason = r.hook(HANDBACK, REPORT, agent)
    assert reason is None, f"{state} で {agent} の {HANDBACK} が止まった: {reason}"
    assert trace_lines(r) == before, f"{state} で {agent} の報告が跡に残った"


# ---- AC-40：似た名前・すり抜けの道・文字列でない道具の名前は止まったまま ------------------------------------------------


def _by_decide(agent: str):
    def call(tmp_path: Path, tool: Any, tool_input: Any) -> str | None:
        return decide(tmp_path, tool, fill(tool_input, tmp_path), agent)

    return call


def _by_hook_in_open_stage(agent: str):
    def call(tmp_path: Path, tool: Any, tool_input: Any) -> str | None:
        r = open_stage(tmp_path)
        return r.hook(tool, fill(tool_input, r.project), agent)

    return call


# 相手：pipe-judge・pipe-builder は guard_hook.decide、pipe-probe・開いた段の pipe-stage・段の間の general-purpose は chat_hook の入口
TARGETS = {
    "pipe-judge": _by_decide(JUDGE),
    "pipe-builder": _by_decide(BUILDER),
    "pipe-probe": _by_hook_in_open_stage(PROBE),
    "pipe-stage": _by_hook_in_open_stage(STAGE),
    "general-purpose": _by_hook_in_open_stage("general-purpose"),
}


@pytest.mark.parametrize("name", LOOKALIKES, ids=repr)
@pytest.mark.parametrize("target", list(TARGETS))
def test_d0096_ac40_lookalike_names_stay_denied(tmp_path, target, name):
    """D0096-AC-40: SubagentHandback に似た名前（大文字小文字・前後の空白・後ろに足した字・区切り・前の部分だけ・mcp__ の形）は、
    pipe-judge・pipe-builder・pipe-probe・開いた段の pipe-stage・段の間の general-purpose のどれでも止まる。
    今の作りで通る（守る。前方一致や大文字小文字を無視する作りを入れると落ちる）。"""
    reason = TARGETS[target](tmp_path, name, REPORT)
    assert reason, f"{target} の {name!r} が通った"


BYPASS = {
    "write": ("Write", {"file_path": "{P}/.claude/settings.json", "content": "{}"}),
    "edit": ("Edit", {"file_path": "{P}/.claude/settings.json", "old_string": "a", "new_string": "b"}),
    "multiedit": ("MultiEdit", {"file_path": "{P}/.claude/settings.json", "edits": []}),
    "notebookedit": ("NotebookEdit", {"notebook_path": "{P}/.claude/a.ipynb"}),
    "bash-redirect": ("Bash", {"command": "echo x > .claude/settings.json"}),
    "bash-chain": ("Bash", {"command": "pipe-in-gen list; touch x"}),
    "powershell": ("PowerShell", {"command": "Set-Content .claude/settings.json x"}),
    "mcp": ("mcp__x__y", {}),
    "agent": ("Agent", {"prompt": "x", "run_in_background": False}),
    "task": ("Task", {"prompt": "x", "run_in_background": False}),
    "webfetch": ("WebFetch", {"url": "https://example.com"}),
}


@pytest.mark.parametrize("route", list(BYPASS))
@pytest.mark.parametrize("target", list(TARGETS))
def test_d0096_ac40_bypass_routes_stay_denied(tmp_path, target, route):
    """D0096-AC-40: 同じ相手の、範囲外（.claude/settings.json）への Write・Edit・MultiEdit・NotebookEdit、範囲外の Bash（> での書き出し・
    pipe-in-gen list に別のコマンドをつないだ形）、PowerShell、mcp__x__y、Agent（run_in_background: false）、Task、WebFetch は止まる。
    今の作りで通る（守る）。"""
    tool, tool_input = BYPASS[route]
    reason = TARGETS[target](tmp_path, tool, tool_input)
    assert reason, f"{target} の {route}（{tool}）が通った"


ODD_TOOL_NAMES = {"missing": MISSING, "int": 1, "list": [HANDBACK], "dict": {"a": HANDBACK}, "tuple": (HANDBACK,)}
# 相手 → (agent_type, 段を開いた作業フォルダで流すか)
ENTRY_TARGETS = {
    "pipe-judge": (JUDGE, False),
    "pipe-builder": (BUILDER, False),
    "pipe-probe": (PROBE, True),
    "pipe-stage": (STAGE, True),
    "general-purpose": ("general-purpose", True),
}


@pytest.mark.parametrize("kind", list(ODD_TOOL_NAMES))
@pytest.mark.parametrize("target", list(ENTRY_TARGETS))
def test_d0096_ac40_odd_tool_name_types_stay_denied(tmp_path, target, kind):
    """D0096-AC-40: 道具の名前（tool_name）が無い・数・list・dict・tuple（JSON では list）の呼び出しは、同じ相手のどれでも止まる。
    フックの入口（chat_hook.main。標準入力）を通すので、判断の途中の例外で通ることも無いことを見る。pipe-judge・pipe-builder は記録の無い作業フォルダ、
    ほかは段を開いた作業フォルダで流す。今の作りで通る（守る。「名前を含むか」で見る作りを入れると list の形が落ちる）。"""
    agent, in_stage = ENTRY_TARGETS[target]
    project = open_stage(tmp_path).project if in_stage else tmp_path.resolve()
    payload = hook_payload(project, ODD_TOOL_NAMES[kind], REPORT, agent)
    if kind == "missing":
        del payload["tool_name"]
    assert hook_decision(json.dumps(payload)), f"{target} の tool_name（{kind}）が通った"


@pytest.mark.parametrize(
    "tool,want",
    [(HANDBACK, True), *[(n, False) for n in LOOKALIKES], (None, False), (1, False), ([HANDBACK], False), ({"a": HANDBACK}, False), ((HANDBACK,), False), ("Read", False)],
    ids=repr,
)
def test_d0096_ac40_is_report_tool_matches_exact_name_only(tool, want):
    """D0096-AC-40: 報告の道具かの判定 guard_hook.is_report_tool は、文字列で SubagentHandback とちょうど同じときだけ True。
    似た名前・文字列でない値・読む道具は False で、例外を出さない（設計 18.2.2 の関数の決まり）。"""
    is_report_tool = getattr(gh(), "is_report_tool", None)
    assert callable(is_report_tool), "guard_hook.is_report_tool が無い"
    assert is_report_tool(tool) is want, tool


# ---- AC-41：型のおかしい agent_type・会話本体・例外 ---------------------------------------------------------------

ODD_AGENTS = [1, True, 3.5, ["pipe-judge"], {"a": "pipe-stage"}]


@pytest.mark.parametrize("where", ["no-record", "open-stage"])
@pytest.mark.parametrize("agent_type", ODD_AGENTS, ids=repr)
def test_d0096_ac41_odd_agent_type_hand_back_stays_denied(tmp_path, agent_type, where):
    """D0096-AC-41: agent_type が文字列でも null でもない呼び出し（数・真偽・list・dict）の SubagentHandback は、記録が無いとき・段が開いているときの
    どちらでも、guard_hook.decide・chat_hook の入口（標準入力）・pipe-in-gen guard-hook の入口（cli.main）のどれでも止まる。
    今の作りで通る（守る。isinstance を見ない作りを入れると落ちる）。"""
    project = open_stage(tmp_path).project if where == "open-stage" else tmp_path.resolve()
    payload = hook_payload(project, HANDBACK, REPORT, agent_type)
    assert gh().decide(payload, pipes_env=[]), "guard_hook.decide で通った"
    assert hook_decision(json.dumps(payload)), "chat_hook の入口で通った"
    assert deny_json(json.dumps(payload)), "pipe-in-gen guard-hook の入口で通った"


@pytest.mark.parametrize("where", ["no-record", "open-stage"])
def test_d0096_ac41_main_conversation_untouched(tmp_path, where):
    """D0096-AC-41: agent_type が無い・null の呼び出し（会話本体）の SubagentHandback・Write・Bash は、記録が無いとき・段が開いているときの
    どちらでも、今までどおり何もされない。今の作りで通る（守る）。"""
    project = open_stage(tmp_path).project if where == "open-stage" else tmp_path.resolve()
    calls = [(HANDBACK, REPORT), ("Write", {"file_path": "{P}/src/a.py", "content": "x"}), ("Bash", {"command": "ls"})]
    for tool, data in calls:
        for form in ("missing", "null"):
            payload = hook_payload(project, tool, fill(data, project), None)
            if form == "null":
                payload["agent_type"] = None
            assert hook_decision(json.dumps(payload)) is None, (where, tool, form)


def test_d0096_ac41_exception_denies_hand_back(tmp_path, monkeypatch, capsys):
    """D0096-AC-41: 報告の道具の判定（guard_hook.is_report_tool）を例外を出す関数に替えると、chat_hook の入口（段を開いた作業フォルダの
    pipe-stage と pipe-judge）と guard_hook.main（標準入力。pipe-judge）の両方で、SubagentHandback が「判断できなかった」の文で止まる。"""
    guard_hook = gh()

    def boom(tool: Any) -> bool:
        raise RuntimeError("判定の途中の例外")

    # 段は差し替えの前に開く（開く途中の確かめ（pipe-probe の Write）も同じ判定を通るので、先に差し替えると開けない）
    r = open_stage(tmp_path / "stage")
    monkeypatch.setattr(guard_hook, "is_report_tool", boom)
    for agent in (STAGE, JUDGE):
        assert r.hook(HANDBACK, REPORT, agent) == EXCEPTION_REASON, agent
    payload = hook_payload(tmp_path.resolve(), HANDBACK, REPORT, JUDGE)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    code = guard_hook.main()
    out = capsys.readouterr().out
    assert code == 0
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["permissionDecision"] == "deny", out
    assert spec["permissionDecisionReason"] == EXCEPTION_REASON, out


# ---- AC-42：4 つの守りの表の行 ---------------------------------------------------------------------------------


def test_d0096_ac42_report_row_in_matrix():
    """D0096-AC-42: 4 つの守りの表（tests/guard_matrix.py）に SubagentHandback の行 report-handback があり、期待が SDK の道の 2 列（sdk・sdk_protected）で
    止める（D）、会話の道・プラグインの 2 役・開発用の 4 役の 7 列で許す（A）。行の id は bypass- で始まらない。実際の結果が表のとおりかは
    tests/test_guard_matrix.py が見る。"""
    rows = [r for r in ROWS if r.tool == HANDBACK]
    assert [r.id for r in rows] == ["report-handback"], [r.id for r in rows]
    want = "".join("D" if c in ("sdk", "sdk_protected") else "A" for c in COLUMNS)
    assert EXPECT["report-handback"] == want


# ---- AC-43：許す名前は 1 か所だけ ------------------------------------------------------------------------------


def _string_constants(path: Path, value: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == value)


def _calls_of(path: Path, owner: str, attr: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == owner
    )


def test_d0096_ac43_report_tools_live_in_one_place():
    """D0096-AC-43: 許す名前は guard_hook.REPORT_TOOLS（SubagentHandback の 1 つだけ）にあり、guard_hook.py の中で値がちょうど SubagentHandback の
    文字の定数は 1 つだけ。chat_hook.py はその名前を自分で書かず（0 個）、guard_hook.is_report_tool(…) を呼ぶ。
    pipe_in/engine/guard.py の ALWAYS_ALLOWED に SubagentHandback は無く、開発用のフックの REPORT_TOOLS と同じ集まり。"""
    guard_hook = gh()
    report_tools = getattr(guard_hook, "REPORT_TOOLS", None)
    assert report_tools == frozenset({HANDBACK}), f"guard_hook.REPORT_TOOLS が {report_tools!r}"
    assert _string_constants(GEN_DIR / "guard_hook.py", HANDBACK) == 1
    assert _string_constants(GEN_DIR / "chat_hook.py", HANDBACK) == 0
    assert _calls_of(GEN_DIR / "chat_hook.py", "guard_hook", "is_report_tool") >= 1, "chat_hook.py が guard_hook.is_report_tool を呼んでいない"
    assert HANDBACK not in guard.ALWAYS_ALLOWED, "SDK の道の ALWAYS_ALLOWED は変えない"
    assert set(dev_hook().REPORT_TOOLS) == set(report_tools)


# ---- AC-44：文書 -----------------------------------------------------------------------------------------------


def _section(text: str, head: str) -> str:
    """「## 見出し」から次の「## 」の手前まで（見出しが無ければ空）。"""
    lines = text.splitlines()
    if head not in lines:
        return ""
    body: list[str] = []
    for ln in lines[lines.index(head) + 1 :]:
        if ln.startswith("## "):
            break
        body.append(ln)
    return "\n".join(body)


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def test_d0096_ac44_docs_say_hand_back_is_not_stopped():
    """D0096-AC-44: plugin/hooks/hooks.json の description に SubagentHandback があり、pipe-stage・pipe-probe・pipe-builder・pipe-judge の語も残る。
    docs/guide/plugin.md のフックの行（「| フック（」で始まる行）と、docs/guide/safety.md の「## 会話の中で流すときの守り」の節に SubagentHandback があり、
    「## 4つの守りの比較」の表に SubagentHandback の行が 1 つあって、その 9 つの印（○ 許す・× 止める）が守りの表の期待（report-handback）と同じ。"""
    problems: list[str] = []
    desc = json.loads((REPO / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8"))["description"]
    problems += [f"hooks.json の description に {w} が無い" for w in (HANDBACK, "pipe-stage", "pipe-probe", "pipe-builder", "pipe-judge") if w not in desc]
    plugin_rows = [ln for ln in (REPO / "docs" / "guide" / "plugin.md").read_text(encoding="utf-8").splitlines() if ln.startswith("| フック（")]
    if len(plugin_rows) != 1:
        problems.append(f"plugin.md のフックの行が {len(plugin_rows)} 個")
    elif HANDBACK not in plugin_rows[0]:
        problems.append(f"plugin.md のフックの行に {HANDBACK} が無い")
    safety = (REPO / "docs" / "guide" / "safety.md").read_text(encoding="utf-8")
    chat = _section(safety, "## 会話の中で流すときの守り")
    if not chat:
        problems.append("safety.md に「## 会話の中で流すときの守り」の節が無い")
    elif HANDBACK not in chat:
        problems.append(f"safety.md の「## 会話の中で流すときの守り」に {HANDBACK} が無い")
    table = [ln for ln in _section(safety, "## 4つの守りの比較").splitlines() if ln.startswith("|") and HANDBACK in ln]
    if len(table) != 1:
        problems.append(f"safety.md の「## 4つの守りの比較」の表の {HANDBACK} の行が {len(table)} 個")
    else:
        marks = _cells(table[0])[1:]
        want = ["×" if c == "D" else "○" for c in EXPECT["report-handback"]]
        if marks != want:
            problems.append(f"safety.md の表の {HANDBACK} の行の印が {marks}（守りの表の期待は {want}）")
    assert problems == []
