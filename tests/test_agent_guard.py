"""段の中のサブエージェントの呼び方を守る（D0032）：裏で動かす形を止める・1回の実行で呼べる数の上限・入れ子を止める・
上限の設定と検査・段の決まりの文。SDK は呼ばない（ガードは make_guard_hook / stage_guard で作った関数を asyncio.run で直接呼ぶ）。

まだ無い名前（stage_guard・max_agent_calls など）は、使うところで取る（ほかのテストまで import で落とさないため）。
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
import types
from pathlib import Path

import pytest

from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool, make_guard_hook
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as ps

AGENTS = '[stages.agents.reader]\ndescription = "1つのモジュールを読む"\nprompt = "渡されたモジュールだけを読む"\ntools = ["Read", "Grep"]\n'


# ---- 補助 ------------------------------------------------------------------


def make_pipe(project: Path, toml: str, folder: str = "pipe-in-p") -> pd.PipeDef:
    d = project / "pipes" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def stage_toml(name: str, extra: str = "", *, access: str = "read") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "{access}"\nprompt = "{name}をする"\n{extra}'


def pipe_toml(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages)


def cfg_for(project: Path, pipe: pd.PipeDef):
    return load_config(project, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)


def spec_of(project: Path, extra: str = AGENTS, *, access: str = "read"):
    pipe = make_pipe(project, pipe_toml(stage_toml("s", extra, access=access)))
    cfg = cfg_for(project, pipe)
    return ps.build_pipe_specs(cfg, pipe)["s"], cfg


def check(tool: str, tool_input, *, allowed=("Agent", "Task", "Bash"), allow_bash: bool = True) -> str | None:
    """Agent・Task・Bash を許した段の check_tool。"""
    return check_tool(
        tool, tool_input, project_dir=Path("/proj"), can_write=lambda rel: False, allow_bash=allow_bash,
        write_scope_hint="なし", allowed_tools=list(allowed),
    )


def guard_with(limit: int, on_deny=None):
    """上限 limit の、Agent・Task を許した段の1回の実行のガード。"""
    return make_guard_hook(
        project_dir=Path("/proj"), can_write=lambda rel: False, allow_bash=True, write_scope_hint="なし",
        allowed_tools=["Agent", "Task", "Bash"], max_agent_calls=limit, on_deny=on_deny,
    )


def fg(**extra) -> dict:
    """待つ形の Agent・Task の入力（run_in_background: False を書いたもの。D0032-AC-22 から、書かない形は止まる）。"""
    return {"prompt": "x", "run_in_background": False, **extra}


def call(guard, tool: str = "Agent", tool_input: dict | None = None, **top) -> dict:
    """ガードを1回呼ぶ。top はフックの入力の上の段に置くもの（agent_id・agent_type など）。
    tool_input を渡さなければ、待つ形（run_in_background: False）の入力にする。"""
    data = {"tool_name": tool, "tool_input": fg() if tool_input is None else tool_input, **top}
    return asyncio.run(guard(data, "t-1", None))


def denied(result: dict) -> bool:
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason_of(result: dict) -> str:
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def stage_guard_of(spec, cfg, on_deny=None):
    from pipe_in.engine.runner import stage_guard

    return stage_guard(spec, cfg, on_deny)


# ---- 止めるほう：裏で動かす形 -------------------------------------------------------


def test_d0032_ac01_agentを裏で動かす形で呼ぶと止まり理由にfalseで呼び直す文が入る():
    """D0032-AC-01: Agent を run_in_background: True で呼ぶと理由を返し、その文に run_in_background: false が入る。"""
    reason = check("Agent", {"prompt": "x", "subagent_type": "reader", "run_in_background": True})
    assert reason is not None
    assert "run_in_background: false" in reason


def test_d0032_ac02_taskを裏で動かす形で呼ぶと止まる():
    """D0032-AC-02: Task を run_in_background: True で呼ぶと理由を返す。"""
    assert check("Task", {"prompt": "x", "run_in_background": True}) is not None


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}], ids=repr)
def test_d0032_ac03_run_in_backgroundがfalse以外の値なら止まる(tool, value):
    """D0032-AC-03: run_in_background が False（真偽値）以外の値（文字・数・None・空の一覧と表）なら、True と同じく止まる。"""
    assert check(tool, {"prompt": "x", "run_in_background": value}) is not None


@pytest.mark.parametrize("value", [True, "true", None, 1], ids=repr)
def test_d0032_ac04_bashを裏で動かす形で呼ぶと止まる(value):
    """D0032-AC-04: Bash を許した段でも、run_in_background を付けた ls は止まり、理由に「run_in_background を付けずに」が入る。"""
    reason = check("Bash", {"command": "ls", "run_in_background": value})
    assert reason is not None
    assert "run_in_background を付けずに" in reason


# ---- 止めるほう：数の上限 --------------------------------------------------------------


def test_d0032_ac05_上限3なら4回目のagentがdenyになり理由に上限の数が入る():
    """D0032-AC-05: 上限 3 のガードに Agent を4回通すと、1〜3回目は {}、4回目は deny で、理由に 3 が入る。"""
    guard = guard_with(3)
    results = [call(guard, "Agent") for _ in range(4)]
    assert results[:3] == [{}, {}, {}]
    assert denied(results[3])
    assert "3" in reason_of(results[3])


def test_d0032_ac05_agentとtaskを混ぜても合わせて数える():
    """D0032-AC-05: Agent と Task を混ぜて呼んでも、合わせて数える（上限 3 で Agent・Task・Agent のあとの Task が止まる）。"""
    guard = guard_with(3)
    results = [call(guard, t) for t in ["Agent", "Task", "Agent", "Task"]]
    assert results[:3] == [{}, {}, {}]
    assert denied(results[3])


def test_d0032_ac06_上限を超えたあとは何度呼んでもdenyのまま():
    """D0032-AC-06: 上限 2 で 10 回呼ぶと、3〜10 回目がすべて deny（数え直しや、すきまで通るものが無い）。"""
    guard = guard_with(2)
    results = [call(guard, "Agent" if i % 2 else "Task") for i in range(10)]
    assert results[:2] == [{}, {}]
    assert all(denied(r) for r in results[2:]), results


def test_d0032_ac07_止めた呼び出しは数に入らない():
    """D0032-AC-07: 上限 1 で、裏で動かす形 → deny、待つ形 → 通る、その次 → deny。"""
    guard = guard_with(1)
    assert denied(call(guard, "Agent", {"prompt": "x", "run_in_background": True}))
    assert call(guard, "Agent", fg()) == {}
    assert denied(call(guard, "Agent", fg()))


def test_d0032_ac07_入れ子で止めた呼び出しも数に入らない():
    """D0032-AC-07: 上限 1 で、agent_id 付き（サブエージェントの中から）→ deny、印なし → 通る。"""
    guard = guard_with(1)
    assert denied(call(guard, "Agent", agent_id="a-1"))
    assert call(guard, "Agent") == {}


# ---- 止めるほう：入れ子 --------------------------------------------------------------


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("agent_id", ["a-1", "", None], ids=repr)
def test_d0032_ac08_サブエージェントの中からのagentとtaskは上限に余りがあっても止まる(tool, agent_id):
    """D0032-AC-08: フックの入力に agent_id（値は問わない）があれば、上限に余りがあっても Agent・Task は deny。"""
    guard = guard_with(20)
    assert denied(call(guard, tool, agent_id=agent_id))


def test_d0032_ac08_agent_typeだけの呼び出しは入れ子とみなさず数える():
    """D0032-AC-08: agent_type だけ（--agent で始めたメインのスレッドの形）は入れ子とみなさず、段の呼び出しとして数える。"""
    guard = guard_with(1)
    assert call(guard, "Agent", agent_type="reviewer") == {}
    assert denied(call(guard, "Agent", agent_type="reviewer"))


def test_d0032_ac08_サブエージェントの中のreadは通る():
    """D0032-AC-08: 入れ子の印で止めるのは Agent・Task だけで、サブエージェントの中の Read は通る。

    今の作りのままで通る（守り続けるための検査）。
    """
    guard = make_guard_hook(
        project_dir=Path("/proj"), can_write=lambda rel: False, allow_bash=False, write_scope_hint="なし",
        allowed_tools=["Agent", "Task"],
    )
    assert call(guard, "Read", {"file_path": "/proj/a.py"}, agent_id="a-1") == {}


def test_d0032_ac09_上限で止めるとon_denyが呼ばれdenialsと同じ形で残る():
    """D0032-AC-09: 上限で止めたとき on_deny が呼ばれ、StageRun.denials と同じ形（"Agent: <理由>"）で残り、上限の数が入る。"""
    denials: list[str] = []
    guard = guard_with(2, on_deny=lambda t, r: denials.append(f"{t}: {r}"))
    for _ in range(3):
        call(guard, "Agent")
    assert len(denials) == 1, denials
    assert denials[0].startswith("Agent: ")
    assert "2" in denials[0]


# ---- 許すほう -----------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_d0032_ac10_run_in_backgroundがfalseなら上限まで通る(tool):
    """D0032-AC-10: run_in_background: False の Agent・Task は、check_tool が None、ガードは上限（3）まで {}。

    差し戻し（V-01）で「キーなし」の形を外した（書かない形は D0032-AC-22 で止まる）。
    """
    inp = fg()
    assert check(tool, inp) is None
    guard = guard_with(3)
    assert [call(guard, tool, dict(inp)) for _ in range(3)] == [{}, {}, {}]


@pytest.mark.parametrize("form", ["キーなし", "False"])
@pytest.mark.parametrize("command,ok", [("ls", True), ("git push", False)])
def test_d0032_ac11_bashはrun_in_backgroundなしかfalseなら今までどおり(form, command, ok):
    """D0032-AC-11: run_in_background なし・False の Bash は、今までどおり危ないコマンドの判定だけが掛かる（ls は通る、git push は止まる）。

    今の作りのままで通る（守り続けるための検査）。
    """
    inp = {"command": command} if form == "キーなし" else {"command": command, "run_in_background": False}
    assert (check("Bash", inp) is None) is ok


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("background", [False, True])
def test_d0032_ac12_agentsの無い段ではagentは数えるより前に使えないで止まる(tmp_path, tool, background):
    """D0032-AC-12: agents の無い段の stage_guard では、待つ形・裏の形のどちらも「この段では … を使えません」で止まる。"""
    spec, cfg = spec_of(tmp_path, "")
    guard = stage_guard_of(spec, cfg)
    inp = {"prompt": "x", "run_in_background": True} if background else {"prompt": "x"}
    result = call(guard, tool, inp)
    assert denied(result)
    assert reason_of(result) == f"この段では {tool} を使えません"


# ---- 数え直し -----------------------------------------------------------------------


def test_d0032_ac13_別々に作ったガードは数を分け合わない():
    """D0032-AC-13: 段の2回の実行に当たる2つのガードは数を分け合わず、1つ目で上限に達しても2つ目の最初の呼び出しは通る。"""
    first, second = guard_with(2), guard_with(2)
    assert [call(first, "Agent") for _ in range(2)] == [{}, {}]
    assert denied(call(first, "Agent"))
    assert call(second, "Agent") == {}


# ---- 設定と検査 -----------------------------------------------------------------------


def test_d0032_ac15_max_agent_callsを書かない段の上限は20(tmp_path):
    """D0032-AC-15: max_agent_calls を書かない段は、build_pipe_specs で作る段の設定の上限が 20。"""
    spec, _ = spec_of(tmp_path)
    assert spec.max_agent_calls == 20


def test_d0032_ac16_max_agent_calls5の段のガードは6回目を止める(tmp_path):
    """D0032-AC-16: max_agent_calls = 5 の段は上限が 5 になり、その段の stage_guard は 6 回目を止める。"""
    spec, cfg = spec_of(tmp_path, "max_agent_calls = 5\n" + AGENTS)
    assert spec.max_agent_calls == 5
    guard = stage_guard_of(spec, cfg)
    results = [call(guard, "Agent") for _ in range(6)]
    assert results[:5] == [{}] * 5
    assert denied(results[5])


@pytest.mark.parametrize("value", ["0", "-1", '"5"', "true", "1.5"])
def test_d0032_ac17_max_agent_callsが1以上の整数でなければ検査が止める(tmp_path, value):
    """D0032-AC-17: max_agent_calls が 0・-1・"5"・true・1.5 のとき、check_pipe が「max_agent_calls は 1 以上の整数で書いてください」を返す。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("s", f"max_agent_calls = {value}\n" + AGENTS)))
    errors = pd.check_pipe(pipe, tmp_path)
    assert any("max_agent_calls は 1 以上の整数で書いてください" in e for e in errors), errors


def test_d0032_ac18_agentsの無い段のmax_agent_callsは検査が止める(tmp_path):
    """D0032-AC-18: agents の無い段に max_agent_calls を書くと、check_pipe が max_agent_calls の誤りを返す。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("s", "max_agent_calls = 5\n")))
    errors = pd.check_pipe(pipe, tmp_path)
    assert any("max_agent_calls" in e and "agents" in e for e in errors), errors


@pytest.mark.parametrize("extra,limit", [("max_agent_calls = 5\n" + AGENTS, 5), (AGENTS, 20)], ids=["上限5", "書かない"])
def test_d0032_ac19_agentsのある段のsystem_appendに呼び方と上限の数が入る(tmp_path, extra, limit):
    """D0032-AC-19: agents のある段の system_append に、run_in_background を付けずに呼ぶことと上限の数（書かなければ 20）が入る。"""
    spec, _ = spec_of(tmp_path, extra)
    text = spec.system_append
    assert "run_in_background" in text
    assert re.search(rf"(?<!\d){limit}\s*回まで", text), text[-600:]


def test_d0032_ac19_agentsの無い段のsystem_appendには入らない(tmp_path):
    """D0032-AC-19: agents の無い段の system_append には、サブエージェントの呼び方の決まりが入らない。

    今の作りのままで通る（守り続けるための検査）。
    """
    spec, _ = spec_of(tmp_path, "")
    assert "run_in_background" not in spec.system_append
    assert "サブエージェントの呼び方" not in spec.system_append


# ---- 古い形 --------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", [pd.PREFIX, pd.LEGACY_PREFIX], ids=["今の頭", "前の版の頭"])
@pytest.mark.parametrize("extra", [AGENTS, ""], ids=["agentsあり", "agentsなし"])
def test_d0032_ac20_max_agent_callsの無い古いpipe_tomlは今までどおり通り上限は20(tmp_path, prefix, extra):
    """D0032-AC-20: max_agent_calls の無い前からの pipe.toml（pipe-in- と前の版の頭のフォルダ）は、check_pipe が空で、上限は 20。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("s", extra)), folder=f"{prefix}old")
    assert pipe.name == "old"
    assert pd.check_pipe(pipe, tmp_path) == []
    spec = ps.build_pipe_specs(cfg_for(tmp_path, pipe), pipe)["s"]
    assert spec.max_agent_calls == 20


def test_d0032_ac21_開発フローの段はagentとtaskを今までどおり止める(tmp_path):
    """D0032-AC-21: 開発フローの全部の段で、stage_guard に Agent・Task（待つ形）を渡すと「この段では … を使えません」で止まる。"""
    from pipe_in.dev import specs as dev_specs

    cfg = load_config(tmp_path, None, auto_approve=True)
    specs = dev_specs.build_specs(cfg)
    assert specs
    for name, spec in specs.items():
        guard = stage_guard_of(spec, cfg)
        for tool in ("Agent", "Task"):
            result = call(guard, tool)
            assert denied(result), (name, tool)
            assert reason_of(result) == f"この段では {tool} を使えません", (name, tool)


# ---- 要件の AC の外の守り ------------------------------------------------------------------


def test_d0032_並べて呼んでも通るのは上限の数だけ():
    """D0032-AC-05: 1つの応答で 25 個の Agent を asyncio.gather で並べて渡しても、上限 20 なら {} はちょうど 20。"""
    guard = guard_with(20)

    async def many():
        data = [{"tool_name": "Agent", "tool_input": {"prompt": f"x{i}", "run_in_background": False}} for i in range(25)]
        return await asyncio.gather(*(guard(d, f"t-{i}", None) for i, d in enumerate(data)))

    results = asyncio.run(many())
    assert sum(1 for r in results if r == {}) == 20
    assert sum(1 for r in results if denied(r)) == 5


@pytest.mark.parametrize("value", [0, -1, True, None, "5"], ids=repr)
def test_d0032_make_guard_hookは1未満や整数でない上限を受けない(value):
    """D0032-AC-06: 上限の効かないガードを作れないよう、make_guard_hook は 1 未満・真偽値・None・文字の上限で ValueError。"""
    with pytest.raises(ValueError):
        guard_with(value)


@pytest.mark.parametrize("tool", ["Agent", "Task", "Bash"])
@pytest.mark.parametrize("tool_input", ["x", ["x"]], ids=repr)
def test_d0032_tool_inputが表でないagentとbashは止まる(tool, tool_input):
    """D0032-AC-03: tool_input が表（dict）でない Agent・Task・Bash は、読めない入力として止まる（落ちずに理由を返す）。"""
    assert check(tool, tool_input) is not None


def test_d0032_sdk_optionsのサブエージェントにbackgroundが入らない(tmp_path):
    """D0032-AC-01: SDK に渡すサブエージェントの dict は description・prompt・tools・model・disallowedTools だけで、
    background（いつも裏で動かす）を持たない。

    差し戻し（V-04）で、許す項目に disallowedTools（D0032-AC-27）を足した。今の作りのままで通る（守り続けるための検査）。
    """
    from pipe_in.engine.runner import sdk_options

    spec, cfg = spec_of(tmp_path, AGENTS.replace('tools = ["Read", "Grep"]\n', 'tools = ["Read", "Grep"]\nmodel = "haiku"\nbackground = true\n'))
    opts = sdk_options(spec, cfg, resume=None)
    assert opts["agents"]
    for name, a in opts["agents"].items():
        assert set(a) <= {"description", "prompt", "tools", "model", "disallowedTools"}, (name, a)


def test_d0032_run_stage_sdkは段のガードをstage_guardで作る():
    """D0032-AC-13: 本物の経路（run_stage_sdk）も、段の1回の実行ごとに stage_guard でガードを作る（make_guard_hook を直に呼ばない）。"""
    from pipe_in.engine import runner

    source = inspect.getsource(runner.run_stage_sdk)
    assert "stage_guard(" in source
    assert "make_guard_hook(" not in source


# ---- 差し戻し（監査と助言の反映）：D0032-AC-22 から ---------------------------------------------

# 段の SDK の子プロセスに必ず渡す環境変数（V-02・V-05）。裏の作業を止め、サブエージェントの入れ子を 1 段までにする。
REQUIRED_ENV = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"}
TWO_AGENTS = AGENTS + '[stages.agents.writer]\ndescription = "まとめる"\nprompt = "まとめを書く"\n'


def raw_call(guard, data: dict) -> dict:
    """フックの入力をそのまま渡す（call と違い、tool_input を補わない）。"""
    return asyncio.run(guard(data, "t-1", None))


def guard_by(maker: str, project: Path):
    """上限 1 の、Agent・Task・Bash を許したガード。make_guard_hook で直に作るか、段の設定から stage_guard で作る。"""
    if maker == "make_guard_hook":
        return guard_with(1)
    spec, cfg = spec_of(project, "bash = true\nmax_agent_calls = 1\n" + AGENTS)
    return stage_guard_of(spec, cfg)


def fake_sdk_module(box: dict) -> types.ModuleType:
    """claude_agent_sdk の代わりの箱。ClaudeAgentOptions に渡した値を box["options"] に残し、応答は何も返さない。"""
    m = types.ModuleType("claude_agent_sdk")

    class AgentDefinition:
        def __init__(self, **kw):
            self.kw = kw

    class ClaudeAgentOptions:
        def __init__(self, **kw):
            box["options"] = kw

    class HookMatcher:
        def __init__(self, matcher=None, hooks=None):
            self.matcher, self.hooks = matcher, hooks

    class CLIJSONDecodeError(Exception):
        pass

    class ClaudeSDKClient:
        def __init__(self, options=None):
            self.options = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def query(self, prompt):
            return None

        async def receive_response(self):
            if False:
                yield None

    for cls in (AgentDefinition, ClaudeAgentOptions, HookMatcher, CLIJSONDecodeError, ClaudeSDKClient):
        setattr(m, cls.__name__, cls)
    for name in ("AssistantMessage", "ResultMessage", "TextBlock", "ToolUseBlock"):
        setattr(m, name, type(name, (), {}))
    return m


def run_with_fake_sdk(spec, cfg, monkeypatch) -> dict:
    """偽の箱で run_stage_sdk を流し、ClaudeAgentOptions に渡した値を返す（SDK は呼ばない）。"""
    from pipe_in.engine.runner import run_stage_sdk

    box: dict = {}
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk_module(box))
    asyncio.run(run_stage_sdk(spec, "x", cfg, resume=None, log_name="s"))
    return box["options"]


# ---- V-01：Agent・Task は run_in_background: false を書いたときだけ通す ---------------------------


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_d0032_ac22_agentとtaskはrun_in_backgroundを書かないと止まり理由にfalseを付けて呼び直す文が入る(tool):
    """D0032-AC-22: Agent・Task は run_in_background を書かないとメインからは裏で動くので、書かない呼び出しも止め、
    理由に「run_in_background: false を付けて呼び直してください」が入る。"""
    reason = check(tool, {"prompt": "x", "subagent_type": "reader"})
    assert reason is not None
    assert "run_in_background: false を付けて呼び直してください" in reason, reason


@pytest.mark.parametrize("maker", ["make_guard_hook", "stage_guard"])
@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_d0032_ac22_書かないで止めた呼び出しは数に入らない(tmp_path, maker, tool):
    """D0032-AC-22: 本物の経路のガード（上限 1）で、書かない形 → deny、そのあとの run_in_background: False → 通る。"""
    guard = guard_by(maker, tmp_path)
    result = call(guard, tool, {"prompt": "x"})
    assert denied(result)
    assert "run_in_background: false を付けて" in reason_of(result)
    assert call(guard, tool, fg()) == {}


def test_d0032_ac22_bashはrun_in_backgroundを書かなくても今までどおり通る():
    """D0032-AC-22: Bash は書かなければ待つ形なので、書かない ls は今までどおり通る（Agent・Task だけを変える）。

    今の作りのままで通る（守り続けるための検査）。
    """
    assert check("Bash", {"command": "ls"}) is None


def test_d0032_ac23_agentsのある段のsystem_appendはrun_in_background_falseを付けて呼ぶよう伝える(tmp_path):
    """D0032-AC-23: agents のある段の system_append は、Agent・Task を run_in_background: false を付けて呼ぶよう伝え、
    Agent・Task の行に「付けずに」と書かない（ガードの決まりと食い違わない）。"""
    spec, _ = spec_of(tmp_path)
    text = spec.system_append
    assert "run_in_background: false" in text, text[-600:]
    agent_lines = [line for line in text.splitlines() if "Agent・Task" in line]
    assert agent_lines, text[-600:]
    assert not any("付けずに" in line for line in agent_lines), agent_lines


# ---- A-01・A-02：本物の経路で、tool_input が表でない・キーが無い ---------------------------------


@pytest.mark.parametrize("maker", ["make_guard_hook", "stage_guard"])
@pytest.mark.parametrize("tool", ["Agent", "Task", "Bash"])
@pytest.mark.parametrize("tool_input", [[], "", None, "x", ["x"]], ids=repr)
def test_d0032_ac24_本物の経路でtool_inputが表でないと止まり数に入らない(tmp_path, maker, tool, tool_input):
    """D0032-AC-24: make_guard_hook・stage_guard で作ったフックに、tool_input が表でない値（[]・""・None・"x"・["x"]）を渡すと、
    Agent・Task・Bash とも deny。止めた呼び出しは数に入らず（上限 1 のあとの待つ形の Agent が通る）、待つ形の Bash ls は通る。"""
    guard = guard_by(maker, tmp_path)
    assert denied(raw_call(guard, {"tool_name": tool, "tool_input": tool_input}))
    assert call(guard, "Bash", {"command": "ls"}) == {}
    assert call(guard, "Agent", fg()) == {}


@pytest.mark.parametrize("maker", ["make_guard_hook", "stage_guard"])
@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_d0032_ac25_tool_inputのキーが無いagentとtaskは止まり数に入らない(tmp_path, maker, tool):
    """D0032-AC-25: フックの入力に tool_input のキーそのものが無い Agent・Task は deny（run_in_background: false が無い）。
    止めた呼び出しは数に入らない。"""
    guard = guard_by(maker, tmp_path)
    assert denied(raw_call(guard, {"tool_name": tool}))
    assert call(guard, tool, fg()) == {}


@pytest.mark.parametrize("tool", ["Read", "Bash"])
def test_d0032_ac25_tool_inputのキーが無いreadとbashは今までどおり通る(tool):
    """D0032-AC-25: tool_input のキーが無いとき、Agent・Task 以外は今までどおり（空の入力として扱い、Read・Bash は通る）。

    今の作りのままで通る（守り続けるための検査）。
    """
    assert raw_call(guard_with(1), {"tool_name": tool}) == {}


# ---- V-02・V-05：段の SDK の env ----------------------------------------------------------


@pytest.mark.parametrize("extra", [AGENTS, ""], ids=["agentsあり", "agentsなし"])
def test_d0032_ac26_パイプの段のsdk_optionsのenvに裏の作業を止める値と入れ子の深さ1が入る(tmp_path, extra):
    """D0032-AC-26: パイプの段の sdk_options の env に CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1" と
    CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH="1" が入る（agents の有無によらない）。"""
    from pipe_in.engine.runner import sdk_options

    spec, cfg = spec_of(tmp_path, extra)
    env = sdk_options(spec, cfg, resume=None).get("env")
    assert isinstance(env, dict), env
    assert {k: env.get(k) for k in REQUIRED_ENV} == REQUIRED_ENV


def test_d0032_ac26_開発フローの全部の段のsdk_optionsのenvにも入る(tmp_path):
    """D0032-AC-26: 開発フローの全部の段の sdk_options の env にも、同じ2つの値が入る。"""
    from pipe_in.dev import specs as dev_specs
    from pipe_in.engine.runner import sdk_options

    cfg = load_config(tmp_path, None, auto_approve=True)
    for name, spec in dev_specs.build_specs(cfg).items():
        env = sdk_options(spec, cfg, resume=None).get("env") or {}
        assert {k: env.get(k) for k in REQUIRED_ENV} == REQUIRED_ENV, name


def test_d0032_ac26_手元の環境変数に別の値があってもenvの値は変わらない(tmp_path, monkeypatch):
    """D0032-AC-26: 手元の環境変数に CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="0"・CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH="5" があっても、
    sdk_options の env は "1" のまま（段の設定に env を足す仕組みは今は無いので、上書きの道はこれだけ）。"""
    from pipe_in.engine.runner import sdk_options

    monkeypatch.setenv("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "0")
    monkeypatch.setenv("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH", "5")
    spec, cfg = spec_of(tmp_path)
    env = sdk_options(spec, cfg, resume=None).get("env") or {}
    assert {k: env.get(k) for k in REQUIRED_ENV} == REQUIRED_ENV


def test_d0032_ac26_run_stage_sdkはClaudeAgentOptionsにenvを渡す(tmp_path, monkeypatch):
    """D0032-AC-26: 本物の経路（run_stage_sdk。SDK は偽の箱）で、ClaudeAgentOptions に渡す env に2つの値が入る。"""
    spec, cfg = spec_of(tmp_path)
    options = run_with_fake_sdk(spec, cfg, monkeypatch)
    env = options.get("env") or {}
    assert {k: env.get(k) for k in REQUIRED_ENV} == REQUIRED_ENV, options.keys()


# ---- V-04：サブエージェントの disallowedTools --------------------------------------------------


def test_d0032_ac27_sdk_optionsのサブエージェントにdisallowedToolsでagentとtaskが入る(tmp_path):
    """D0032-AC-27: 段の sdk_options の各サブエージェントの dict に、disallowedTools（camelCase）= Agent・Task が入る。"""
    from pipe_in.engine.runner import sdk_options

    spec, cfg = spec_of(tmp_path, TWO_AGENTS)
    agents = sdk_options(spec, cfg, resume=None)["agents"]
    assert set(agents) == {"reader", "writer"}
    for name, a in agents.items():
        assert sorted(a.get("disallowedTools") or []) == ["Agent", "Task"], (name, a)


def test_d0032_ac27_入っているSDKのAgentDefinitionがその形を受けてdisallowedToolsを持つ(tmp_path):
    """D0032-AC-27: 入っている SDK の AgentDefinition（型を作るだけで、SDK は呼ばない）が sdk_options の dict を受け、
    disallowedTools に Agent・Task を持つ（項目の名前が SDK と合っている）。"""
    sdk = pytest.importorskip("claude_agent_sdk")
    from pipe_in.engine.runner import sdk_options

    spec, cfg = spec_of(tmp_path, TWO_AGENTS)
    for name, a in sdk_options(spec, cfg, resume=None)["agents"].items():
        d = sdk.AgentDefinition(**a)
        assert sorted(d.disallowedTools or []) == ["Agent", "Task"], (name, d)


def test_d0032_ac27_run_stage_sdkはAgentDefinitionにdisallowedToolsを渡す(tmp_path, monkeypatch):
    """D0032-AC-27: 本物の経路（run_stage_sdk。SDK は偽の箱）で、各サブエージェントの AgentDefinition に disallowedTools = Agent・Task が渡る。"""
    spec, cfg = spec_of(tmp_path, TWO_AGENTS)
    options = run_with_fake_sdk(spec, cfg, monkeypatch)
    assert set(options["agents"]) == {"reader", "writer"}
    for name, d in options["agents"].items():
        assert sorted(d.kw.get("disallowedTools") or []) == ["Agent", "Task"], (name, d.kw)


# ---- V-07：Agent・Task の isolation ----------------------------------------------------------


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("value", ["worktree", "remote", None, "", False, {}], ids=repr)
def test_d0032_ac28_isolationを書いたagentとtaskは値によらず止まる(tool, value):
    """D0032-AC-28: Agent・Task の isolation は書かないときだけ通す。worktree・remote・None・空・False・表など、
    値があれば（run_in_background: False でも）止まり、理由に isolation が入る。"""
    reason = check(tool, fg(isolation=value))
    assert reason is not None
    assert "isolation" in reason, reason


def test_d0032_ac28_isolationで止めた呼び出しは数に入らない():
    """D0032-AC-28: 上限 1 のガードで、isolation: worktree → deny、そのあとの isolation なしの待つ形 → 通る。"""
    guard = guard_with(1)
    assert denied(call(guard, "Agent", fg(isolation="worktree")))
    assert call(guard, "Agent", fg()) == {}
