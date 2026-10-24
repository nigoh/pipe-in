"""段が大きい画像を Read しても落ちないようにする（D0026）：受信バッファの上限の設定・SDK への受け渡し・上限を超えたときの案内と段の失敗。
D0033：パイプ（--pipe）の道と pipe-in-gen design で上限を超えたとき。

SDK は呼ばない。run_stage_sdk を通すテストは、sys.modules の claude_agent_sdk を手で書いた偽物の箱に差し替える（テストのあとに戻る）。
ファイルは tmp_path の中にだけ作る。runner.buffer_overflow_notice は使うところで取り、名前が消えたらその理由で落とす（テスト先行のときの形を残している）。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sys
import types
from pathlib import Path

import pytest

from pipe_in.dev import specs as dev_specs
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine import runner as runner_mod
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit, ShellResult
from pipe_in.engine.runner import StageRun, run_stage_sdk, sdk_options
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as ps

MIB = 1024 * 1024
OVERFLOW_TEXT = "Failed to decode JSON: JSON message exceeded maximum buffer size of 1048576 bytes..."
PIPE_TOML = '[pipe]\nkind = "linear"\nlabel = "x"\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\nprompt = "x"\n'


# ---- 補助 ------------------------------------------------------------------


def notice_fn():
    """runner.buffer_overflow_notice（無ければ、無いことを理由に落とす）。"""
    fn = getattr(runner_mod, "buffer_overflow_notice", None)
    if fn is None:
        pytest.fail("pipe_in.engine.runner.buffer_overflow_notice が無い")
    return fn


def write_toml(project: Path, text: str) -> None:
    (project / "pipeline.toml").write_text(text, encoding="utf-8")


def cfg_of(project: Path):
    return load_config(project, None, auto_approve=True)


def requirements_opts(cfg) -> dict:
    return sdk_options(dev_specs.build_specs(cfg)["requirements"], cfg, resume=None)


class FakeSDK:
    """claude_agent_sdk の代わりの箱。receive_response は、渡された例外を最初に投げる（None なら何も返さずに終わる）。"""

    def __init__(self, error: BaseException | None):
        self.error = error
        self.options: dict = {}
        self.module = self._build()

    def _build(self) -> types.ModuleType:
        box = self

        class AgentDefinition:
            def __init__(self, **kw):
                self.kw = kw

        class HookMatcher:
            def __init__(self, matcher=None, hooks=None):
                self.matcher, self.hooks = matcher, hooks

        class ClaudeAgentOptions:
            def __init__(self, **kw):
                box.options = kw

        class AssistantMessage:
            pass

        class ResultMessage:
            pass

        class TextBlock:
            pass

        class ToolUseBlock:
            pass

        # 例外の形は入っている SDK（claude_agent_sdk/_errors.py）に合わせる（D0026-AC-10 で型を見分けるため）
        class ClaudeSDKError(Exception):
            pass

        class CLIConnectionError(ClaudeSDKError):
            pass

        class ProcessError(ClaudeSDKError):
            pass

        class MessageParseError(ClaudeSDKError):
            pass

        class CLIJSONDecodeError(ClaudeSDKError):
            def __init__(self, line, original_error):
                self.line, self.original_error = line, original_error
                super().__init__(f"Failed to decode JSON: {line[:100]}...")

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
                if box.error is not None:
                    raise box.error
                return
                yield  # async の生成器にするため

        m = types.ModuleType("claude_agent_sdk")
        for cls in (AgentDefinition, HookMatcher, ClaudeAgentOptions, AssistantMessage, ResultMessage,
                    TextBlock, ToolUseBlock, ClaudeSDKError, CLIConnectionError, ProcessError, MessageParseError,
                    CLIJSONDecodeError, ClaudeSDKClient):
            setattr(m, cls.__name__, cls)
        return m


def run_requirements(tmp_path: Path, monkeypatch, error: BaseException | None) -> tuple[StageRun, FakeSDK]:
    fake = FakeSDK(error)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake.module)
    cfg = cfg_of(tmp_path)
    spec = dev_specs.build_specs(cfg)["requirements"]
    run = asyncio.run(run_stage_sdk(spec, "x", cfg, resume=None, log_name="01_requirements"))
    return run, fake


# ---- D0026-AC-01: 既定の上限は 32MB -----------------------------------------------


def test_D0026_AC_01_キーが無いと上限は32MB(tmp_path):
    """D0026-AC-01: [pipeline] に max_buffer_mb が無いとき、load_config の上限は 32MB（33554432 バイト）。"""
    write_toml(tmp_path, '[pipeline]\nwork_dir = "docs/pipeline"\n')
    cfg = cfg_of(tmp_path)
    assert getattr(cfg, "max_buffer_mb", None) == 32
    assert getattr(cfg, "max_buffer_bytes", None) == 33554432


def test_D0026_AC_01_pipeline_tomlが無くても上限は32MB(tmp_path):
    """D0026-AC-01: pipeline.toml が無いときも、load_config の上限は 32MB（33554432 バイト）。"""
    cfg = cfg_of(tmp_path)
    assert getattr(cfg, "max_buffer_mb", None) == 32
    assert getattr(cfg, "max_buffer_bytes", None) == 33554432


def test_D0026_AC_01_sdk_optionsはいつもmax_buffer_sizeを返す(tmp_path):
    """D0026-AC-01: 設定に書かなくても、sdk_options が返す dict に max_buffer_size = 33554432 が入る。"""
    opts = requirements_opts(cfg_of(tmp_path))
    assert opts.get("max_buffer_size") == 33554432


def test_D0026_AC_01_入っているSDKのClaudeAgentOptionsにmax_buffer_sizeがある():
    """D0026-AC-01: 入っている SDK の ClaudeAgentOptions に max_buffer_size の項目がある（クラスを見るだけで SDK は呼ばない）。"""
    sdk = pytest.importorskip("claude_agent_sdk")
    assert "max_buffer_size" in {f.name for f in dataclasses.fields(sdk.ClaudeAgentOptions)}


# ---- D0026-AC-02: 設定した上限がどの段にも渡る ---------------------------------------


def test_D0026_AC_02_開発フローの段に設定の上限が渡る(tmp_path):
    """D0026-AC-02: [pipeline] max_buffer_mb = 64 のとき、開発フローの requirements の段の max_buffer_size は 67108864。"""
    write_toml(tmp_path, "[pipeline]\nmax_buffer_mb = 64\n")
    assert requirements_opts(cfg_of(tmp_path)).get("max_buffer_size") == 67108864


def test_D0026_AC_02_パイプの段にも同じ上限が渡る(tmp_path):
    """D0026-AC-02: 同じ pipeline.toml で、パイプ（pipe_in/pipe/specs.py で作った段）の max_buffer_size も 67108864。"""
    write_toml(tmp_path, "[pipeline]\nmax_buffer_mb = 64\n")
    d = tmp_path / "pipes" / "pipe-in-p"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(PIPE_TOML, encoding="utf-8")
    pipe = pd.load_pipe(d)
    cfg = cfg_of(tmp_path).for_pipe(pipe.name, own_work_dir=True)
    spec = ps.build_pipe_specs(cfg, pipe)["a"]
    assert sdk_options(spec, cfg, resume=None).get("max_buffer_size") == 67108864


# ---- D0026-AC-03: 1 以上の整数でない値は止める ---------------------------------------


@pytest.mark.parametrize("value", ["0", "-1", "1.5", '"32"', "true"], ids=["zero", "negative", "float", "string", "bool"])
def test_D0026_AC_03_1以上の整数でない値は止める(tmp_path, value):
    """D0026-AC-03: max_buffer_mb が 0・-1・1.5・"32"・true のとき、load_config は SystemExit で止まり、文に max_buffer_mb と「1 以上の整数」が入る。"""
    write_toml(tmp_path, f"[pipeline]\nmax_buffer_mb = {value}\n")
    with pytest.raises(SystemExit) as e:
        cfg_of(tmp_path)
    message = str(e.value)
    assert "max_buffer_mb" in message, message
    assert "1 以上の整数" in message, message


# ---- D0026-AC-04: 上限を超えた文から案内を作る ---------------------------------------


def test_D0026_AC_04_上限を超えた文から案内を作る():
    """D0026-AC-04: 上限を超えたことを表す SDK の文と今の上限（32MB）から、今の上限（32MB）・max_buffer_mb・pipeline.toml の入った案内を返す。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    assert isinstance(notice, str), notice
    for word in ("32MB", "max_buffer_mb", "pipeline.toml"):
        assert word in notice, f"案内に「{word}」が無い: {notice}"


def test_D0026_AC_04_案内の最後にSDKの元の文が付く():
    """D0026-AC-04: 案内の文の最後に、SDK の元の文（実際に効いていた上限のバイト数が見える）が付く（D0026 の「決めたことと理由」どおり）。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    assert isinstance(notice, str), notice
    assert "maximum buffer size of 1048576 bytes" in notice, notice


def test_D0026_AC_04_ほかのJSONの誤りには案内を作らない():
    """D0026-AC-04: 上限を超えたことを表さない文（ただの JSON の読み誤り）には None を返す。"""
    assert notice_fn()('Failed to decode JSON: {"a":', 32 * MIB) is None


def test_D0026_AC_04_入っているSDKの例外の文を見分けられる():
    """D0026-AC-04: 入っている SDK の CLIJSONDecodeError を作るだけで（SDK は呼ばない）、その str() から案内が返る。SDK が文を変えたら落ちて気づける。"""
    sdk = pytest.importorskip("claude_agent_sdk")
    e = sdk.CLIJSONDecodeError("JSON message exceeded maximum buffer size of 1048576 bytes", ValueError("x"))
    assert isinstance(notice_fn()(str(e), 32 * MIB), str), str(e)


# ---- D0026-AC-05・06: run_stage_sdk の受け止め方 -------------------------------------


def test_D0026_AC_05_上限を超えたら失敗のStageRunを返す(tmp_path, monkeypatch, capsys):
    """D0026-AC-05: 段の実行中に上限を超えた例外が出ても run_stage_sdk は外へ出さず、is_error=True・subtype=error_max_buffer_size・
    errors に案内の文を入れた StageRun を返し、画面にも案内を出す。"""
    try:
        run, _ = run_requirements(tmp_path, monkeypatch, Exception(OVERFLOW_TEXT))
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"上限を超えた例外が run_stage_sdk の外へ出た: {e!r}")
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    assert run.is_error is True
    assert run.subtype == "error_max_buffer_size"
    assert run.errors == [notice]
    assert notice in capsys.readouterr().out


def test_D0026_AC_05_SDKに渡すoptionsに上限が入る(tmp_path, monkeypatch):
    """D0026-AC-05: run_stage_sdk が ClaudeAgentOptions に渡す max_buffer_size が、設定の上限（既定 33554432）になる。"""
    _, fake = run_requirements(tmp_path, monkeypatch, None)
    assert fake.options.get("max_buffer_size") == 33554432


def test_D0026_AC_06_ほかのSDKの例外は外へ出る(tmp_path, monkeypatch):
    """D0026-AC-06: 上限を超えたこと以外の SDK の例外（CLIConnectionError）は、run_stage_sdk から今までどおり外へ出る。"""
    fake = FakeSDK(None)
    fake.error = fake.module.CLIConnectionError("接続できない")
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake.module)
    cfg = cfg_of(tmp_path)
    spec = dev_specs.build_specs(cfg)["requirements"]
    with pytest.raises(fake.module.CLIConnectionError):
        asyncio.run(run_stage_sdk(spec, "x", cfg, resume=None, log_name="01_requirements"))


# ---- D0026-AC-07: 終了コード 3 と state.json ------------------------------------------


class OverflowRunner:
    """要件定義の段で、上限を超えたときの形の StageRun を返す（文書は書かない）。"""

    def __init__(self, notice: str):
        self.notice = notice
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        return StageRun(stage=spec.name, is_error=True, subtype="error_max_buffer_size", errors=[self.notice])


def test_D0026_AC_07_上限を超えた段で終了コード3になりstate_jsonに残る(tmp_path):
    """D0026-AC-07: 要件定義の段の runner が上限を超えた形の StageRun を返すと、終了コード 3（STAGE_ERROR）で止まり、
    state.json の runs にその段の実行と案内の文が残る。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    cfg = cfg_of(tmp_path)
    r = OverflowRunner(notice)
    result = asyncio.run(DevPipeline(cfg, runner=r).run("x", "requirements"))
    assert result == Exit.STAGE_ERROR
    assert int(result) == 3
    assert r.calls == ["requirements"]
    state = json.loads((cfg.work_dir / "state.json").read_text(encoding="utf-8"))
    assert state["final"] == "STAGE_ERROR"
    first = state["runs"][0]
    assert first["stage"] == "requirements"
    assert first["is_error"] is True
    assert first["errors"] == [notice]


# ---- D0026-AC-08: 前の版の pipeline.toml ----------------------------------------------

OLD_TOML = """[pipeline]
work_dir = "docs/pipeline"
max_retries = 2

[stages.requirements]
model = "sonnet"
max_turns = 20
max_budget_usd = 0.6
"""


def test_D0026_AC_08_前の版のpipeline_tomlは今までどおり読める(tmp_path):
    """D0026-AC-08: max_buffer_mb の無い前の版の pipeline.toml（[stages.requirements] に model・max_turns・max_budget_usd だけ）を読むと、
    段の設定は書いたとおりに効き、上限は既定の 32MB。"""
    write_toml(tmp_path, OLD_TOML)
    cfg = cfg_of(tmp_path)
    sc = cfg.stage("requirements")
    assert (sc.model, sc.max_turns, sc.max_budget_usd) == ("sonnet", 20, 0.6)
    opts = requirements_opts(cfg)
    assert (opts["model"], opts["max_turns"], opts["max_budget_usd"]) == ("sonnet", 20, 0.6)
    assert opts.get("max_buffer_size") == 33554432


# ---- D0026-AC-10: 受け止める例外の型を絞る（監査と助言の V-02） ------------------------------

SDK_OVERFLOW_LINE = "JSON message exceeded maximum buffer size of 33554432 bytes"


class Flattened(Exception):
    """素の Exception の子（ちょうど Exception ではない型）。"""


def run_with(tmp_path: Path, monkeypatch, make_error) -> StageRun:
    """偽の SDK の箱を作り、make_error(箱の module) で作った例外を receive_response から投げさせて run_stage_sdk を流す。"""
    fake = FakeSDK(None)
    fake.error = make_error(fake.module)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake.module)
    cfg = cfg_of(tmp_path)
    spec = dev_specs.build_specs(cfg)["requirements"]
    return asyncio.run(run_stage_sdk(spec, "x", cfg, resume=None, log_name="01_requirements"))


CAUGHT = {
    "CLIJSONDecodeError": lambda m: m.CLIJSONDecodeError(SDK_OVERFLOW_LINE, ValueError("Buffer size exceeds limit")),
    "素のException": lambda m: Exception(OVERFLOW_TEXT),
}


@pytest.mark.parametrize("make_error", list(CAUGHT.values()), ids=list(CAUGHT))
def test_D0026_AC_10_SDKのCLIJSONDecodeErrorか素のExceptionで文に上限超えがあれば段の失敗にする(tmp_path, monkeypatch, make_error):
    """D0026-AC-10: 型が偽の SDK の CLIJSONDecodeError か、ちょうど素の Exception で、文に "maximum buffer size" があるとき、
    run_stage_sdk は外へ出さず、is_error=True・subtype=error_max_buffer_size・errors に案内を入れた StageRun を返す。"""
    try:
        run = run_with(tmp_path, monkeypatch, make_error)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"上限を超えた例外が run_stage_sdk の外へ出た: {type(e).__name__}: {e}")
    assert run.is_error is True
    assert run.subtype == "error_max_buffer_size"
    assert len(run.errors) == 1 and "maximum buffer size" in run.errors[0], run.errors


ESCAPES = {
    "ProcessError": lambda m: m.ProcessError(f"Command failed: {SDK_OVERFLOW_LINE}"),
    "MessageParseError": lambda m: m.MessageParseError(SDK_OVERFLOW_LINE),
    "ClaudeSDKError": lambda m: m.ClaudeSDKError(SDK_OVERFLOW_LINE),
    "CLIConnectionError": lambda m: m.CLIConnectionError(SDK_OVERFLOW_LINE),
    "RuntimeError": lambda m: RuntimeError(OVERFLOW_TEXT),
    "ValueError": lambda m: ValueError(OVERFLOW_TEXT),
    "Exceptionの子": lambda m: Flattened(OVERFLOW_TEXT),
}


@pytest.mark.parametrize("make_error", list(ESCAPES.values()), ids=list(ESCAPES))
def test_D0026_AC_10_ほかの型は文に上限超えがあっても外へ出る(tmp_path, monkeypatch, make_error):
    """D0026-AC-10: 型が CLIJSONDecodeError でもちょうど素の Exception でもない例外（偽の ProcessError・ClaudeSDKError の別の子・
    RuntimeError・Exception の子など）は、文に "maximum buffer size" を含んでいても run_stage_sdk の外へそのまま出る。"""
    expected = make_error(FakeSDK(None).module)
    with pytest.raises(Exception) as e:
        run_with(tmp_path, monkeypatch, make_error)
    assert type(e.value).__name__ == type(expected).__name__, repr(e.value)
    assert "maximum buffer size" in str(e.value)


NOT_OVERFLOW = {
    "CLIJSONDecodeError": lambda m: m.CLIJSONDecodeError('{"a":', ValueError("Expecting value")),
    "素のException": lambda m: Exception("Command failed"),
}


@pytest.mark.parametrize("make_error", list(NOT_OVERFLOW.values()), ids=list(NOT_OVERFLOW))
def test_D0026_AC_10_受け止める型でも文に上限超えが無ければ外へ出る(tmp_path, monkeypatch, make_error):
    """D0026-AC-10: CLIJSONDecodeError でも素の Exception でも、文に "maximum buffer size" が無ければ（ただの JSON の読み誤りなど）外へ出る。"""
    expected = make_error(FakeSDK(None).module)
    with pytest.raises(Exception) as e:
        run_with(tmp_path, monkeypatch, make_error)
    assert type(e.value).__name__ == type(expected).__name__, repr(e.value)


# ---- D0026-AC-11: 案内の文（監査と助言の V-03） -------------------------------------------


@pytest.mark.parametrize("mb", [1, 16, 31, 32, 64])
def test_D0026_AC_11_案内に画像を小さくする道と切り出す道がある(mb):
    """D0026-AC-11: 上限がいくつでも、案内に「画像を小さくする」道と「必要な所を切り出してから読ませる」道が入る。"""
    notice = notice_fn()(OVERFLOW_TEXT, mb * MIB)
    assert isinstance(notice, str), notice
    assert "小さく" in notice, f"案内に画像を小さくする道が無い: {notice}"
    assert "切り出" in notice, f"案内に必要な所を切り出す道が無い: {notice}"


@pytest.mark.parametrize("mb", [1, 16, 31])
def test_D0026_AC_11_上限が32MB未満なら倍の値を勧める(mb):
    """D0026-AC-11: 今の上限が 32MB 未満のときは、max_buffer_mb を倍の値（例: 16MB なら 32）にする文が入る。"""
    notice = notice_fn()(OVERFLOW_TEXT, mb * MIB)
    assert isinstance(notice, str), notice
    assert re.search(rf"max_buffer_mb\s*=\s*{mb * 2}\b", notice), f"倍の値 {mb * 2} を勧める文が無い: {notice}"


@pytest.mark.parametrize("mb", [32, 64])
def test_D0026_AC_11_上限が32MB以上なら倍の値を出さない(mb):
    """D0026-AC-11: 今の上限が 32MB 以上のときは、max_buffer_mb を倍の値にする文を出さない（API のリクエストの上限も 32MB のため）。"""
    notice = notice_fn()(OVERFLOW_TEXT, mb * MIB)
    assert isinstance(notice, str), notice
    assert not re.search(rf"max_buffer_mb\s*=\s*{mb * 2}\b", notice), f"倍の値 {mb * 2} を勧めている: {notice}"
    assert f"{mb * 2}MB" not in notice, f"倍の値 {mb * 2}MB が出ている: {notice}"


@pytest.mark.parametrize("mb", [32, 64])
def test_D0026_AC_11_上限が32MB以上ならAPIのリクエストの上限も32MBと書く(mb):
    """D0026-AC-11: 今の上限が 32MB 以上のときは、API のリクエストの上限も 32MB なので、上げても通らないおそれがあると書く。"""
    notice = notice_fn()(OVERFLOW_TEXT, mb * MIB)
    assert isinstance(notice, str), notice
    assert "API" in notice and "リクエスト" in notice, f"API のリクエストの上限の話が無い: {notice}"
    assert "通らない" in notice, f"上げても通らないおそれがある、という文が無い: {notice}"


# ---- D0026-AC-12: 検証の段で超えても終了コード 3（監査と助言の A-01） ------------------------


class StageOverflowRunner:
    """target の段だけ上限を超えた形の StageRun を返し、ほかの段はただ終わる（文書は書かない）。"""

    def __init__(self, target: str, notice: str):
        self.target, self.notice = target, notice
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        if spec.name == self.target:
            return StageRun(stage=spec.name, is_error=True, subtype="error_max_buffer_size", errors=[self.notice])
        return StageRun(stage=spec.name)


def ready_until_red(cfg) -> None:
    """検証・実装の段から始められるよう、tmp_path の中の work_dir に要件定義・設計・テスト先行の文書を置く。"""
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    for name in (dev_specs.REQUIREMENTS, dev_specs.DESIGN, dev_specs.RED):
        (cfg.work_dir / name).write_text("# x\n", encoding="utf-8")


def ok_shell(command, cwd, timeout):
    """確認用コマンドの偽物（いつも通る。本物のコマンドは起こさない）。"""
    return ShellResult(returncode=0, output_tail="")


@pytest.mark.parametrize(
    ("from_stage", "test_command", "expected_calls"),
    [("test", None, ["test"]), ("implement", None, ["implement", "test"]), ("test", "make check", ["test"])],
    ids=["from_test", "from_implement", "with_test_command"],
)
def test_D0026_AC_12_検証の段で上限を超えると終了コード3になりstate_jsonに残る(tmp_path, from_stage, test_command, expected_calls):
    """D0026-AC-12: 開発フローの検証（test）の段の runner が上限を超えた形の StageRun を返すと、BLOCKED（4）でなく
    終了コード 3（STAGE_ERROR）で止まり、state.json の runs にその段の実行と案内の文が残る（AC-07 と同じ流儀）。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    cfg = load_config(tmp_path, None, test_command=test_command, auto_approve=True)
    ready_until_red(cfg)
    r = StageOverflowRunner("test", notice)
    result = asyncio.run(DevPipeline(cfg, runner=r, shell=ok_shell).run(None, from_stage))
    assert result == Exit.STAGE_ERROR, f"終了コードが {result!r}（{int(result)}）"
    assert int(result) == 3
    assert r.calls == expected_calls
    state = json.loads((cfg.work_dir / "state.json").read_text(encoding="utf-8"))
    assert state["final"] == "STAGE_ERROR"
    runs = [h for h in state["runs"] if h.get("stage") == "test" and "is_error" in h]
    assert len(runs) == 1, state["runs"]
    assert runs[0]["is_error"] is True
    assert runs[0]["subtype"] == "error_max_buffer_size"
    assert runs[0]["errors"] == [notice]


# ==== D0033: パイプ・pipe-in-gen design で上限を超えたとき ===================================
#
# パイプ（LinearPipeline）と pipe-in-gen design（pipe_in_generator.design）で、段が上限を超えた形の StageRun を返したときの
# 止まり方を確かめる。runner・shell は偽物。ファイルは tmp_path の中だけに作る。


class PipeOverflowRunner:
    """パイプの段の偽物。targets の段では上限を超えた形の StageRun を返し（write_target が真ならその段の成果物も書く）、
    ほかの段は成果物を書いてただ終わる。呼ばれた段の名前を calls に残す。"""

    def __init__(self, targets, notice: str, *, write_target: bool = False):
        self.targets, self.notice, self.write_target = set(targets), notice, write_target
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        overflow = spec.name in self.targets
        if not overflow or self.write_target:
            (cfg.work_dir / f"{spec.name}.md").write_text(f"# {spec.name}\n", encoding="utf-8")
        if overflow:
            return StageRun(stage=spec.name, is_error=True, subtype="error_max_buffer_size", errors=[self.notice])
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}")


class CountingShell:
    """確認用のコマンドの偽物。呼ばれたコマンドを calls に残し、いつも通る（本物のコマンドは起こさない）。"""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, command, cwd, timeout):
        self.calls.append(command)
        return ShellResult(0, "")


def pipe_stage(name: str, extra: str = "") -> str:
    """成果物が <段>.md の、読むだけの段（PipeOverflowRunner が書く名前に合わせる）。"""
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def pipe_toml_of(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages)


def make_pipe_def(project: Path, toml: str) -> pd.PipeDef:
    d = project / "pipes" / "pipe-in-p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def run_pipe(tmp_path: Path, toml: str, runner, shell=None) -> tuple[Exit, dict]:
    """tmp_path の中にパイプを置いて LinearPipeline で流し、終了コードと state.json を返す。"""
    from pipe_in.pipe.pipeline import LinearPipeline

    pipe = make_pipe_def(tmp_path, toml)
    cfg = load_config(tmp_path, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)
    extra = {"shell": shell} if shell is not None else {}
    result = asyncio.run(LinearPipeline(cfg, pipe, runner=runner, **extra).run("x"))
    state = json.loads((cfg.work_dir / "state.json").read_text(encoding="utf-8"))
    return result, state


def overflow_runs(state: dict, stage: str) -> list[dict]:
    return [h for h in state["runs"] if h.get("stage") == stage and "is_error" in h]


# ---- D0033-AC-01: パイプのふつうの段 -----------------------------------------------------


@pytest.mark.parametrize("write_target", [False, True], ids=["no_output", "with_output"])
def test_D0033_AC_01_パイプのふつうの段で上限を超えると終了コード3になりstate_jsonに残る(tmp_path, write_target):
    """D0033-AC-01: 2段のパイプの1段目の runner が上限を超えた形の StageRun を返すと、終了コード 3（STAGE_ERROR）で止まり、
    2段目は呼ばれず、state.json の final は STAGE_ERROR、runs にその段の is_error・subtype・errors が残る。成果物を書いていても止まる。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    r = PipeOverflowRunner(["a"], notice, write_target=write_target)
    result, state = run_pipe(tmp_path, pipe_toml_of(pipe_stage("a"), pipe_stage("b")), r)
    assert result == Exit.STAGE_ERROR, f"終了コードが {result!r}（{int(result)}）"
    assert int(result) == 3
    assert r.calls == ["a"]
    assert state["final"] == "STAGE_ERROR"
    runs = overflow_runs(state, "a")
    assert len(runs) == 1, state["runs"]
    assert runs[0]["is_error"] is True
    assert runs[0]["subtype"] == "error_max_buffer_size"
    assert runs[0]["errors"] == [notice]


# ---- D0033-AC-02: 検証つきの段 ---------------------------------------------------------


@pytest.mark.parametrize("on_fail", ["self", "a"])
def test_D0033_AC_02_検証つきの段で上限を超えると差し戻さず終了コード3(tmp_path, on_fail):
    """D0033-AC-02: 検証（verdict・command・max_retries = 2）つきの段の runner が上限を超えた形の StageRun を返すと、
    差し戻さず（その段の runner は1回だけ、on_fail の段も1回だけ）終了コード 3 で止まり、TEST_FAILED にならない。
    確認用のコマンドは流れず、state.json に検証の記録も残らない。on_fail = "self" は on_fail を書かない（自分へ戻す）形。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    back = "" if on_fail == "self" else f'on_fail = "{on_fail}"\n'
    check = f'[stages.check]\nverdict = true\ncommand = "make check"\n{back}max_retries = 2\n'
    r = PipeOverflowRunner(["verify"], notice)
    shell = CountingShell()
    result, state = run_pipe(tmp_path, pipe_toml_of(pipe_stage("a"), pipe_stage("verify", check)), r, shell)
    assert result != Exit.TEST_FAILED, "差し戻しの上限まで検証に通らなかった扱いになった"
    assert result == Exit.STAGE_ERROR, f"終了コードが {result!r}（{int(result)}）"
    assert r.calls.count("verify") == 1, r.calls
    assert r.calls.count("a") == 1, r.calls
    assert shell.calls == []
    assert [h for h in state["runs"] if "check" in h] == []
    assert overflow_runs(state, "verify")[0]["subtype"] == "error_max_buffer_size"


# ---- D0033-AC-03: グループの段 ---------------------------------------------------------


@pytest.mark.parametrize("target", ["a", "b"])
def test_D0033_AC_03_グループの片方で上限を超えると終了コード3で後の段に進まない(tmp_path, target):
    """D0033-AC-03: 同じ group の2段（a・b）の片方が上限を超えた形の StageRun を返し、もう片方がふつうに終わると、
    終了コード 3 で止まり、グループのあとの段（c）は呼ばれず、超えた段の subtype が state.json に残る。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    toml = pipe_toml_of(pipe_stage("a", 'group = "g"\n'), pipe_stage("b", 'group = "g"\n'), pipe_stage("c"))
    r = PipeOverflowRunner([target], notice)
    result, state = run_pipe(tmp_path, toml, r)
    assert result == Exit.STAGE_ERROR, f"終了コードが {result!r}（{int(result)}）"
    assert set(r.calls) == {"a", "b"}, r.calls
    assert "c" not in r.calls
    runs = overflow_runs(state, target)
    assert len(runs) == 1, state["runs"]
    assert runs[0]["subtype"] == "error_max_buffer_size"


# ---- D0033-AC-04: パイプの段の上限は pipeline.toml で決まる ----------------------------------


@pytest.mark.parametrize(("line", "expected"), [("max_buffer_mb = 64", 67108864), ("", 33554432)], ids=["64MB", "no_key"])
def test_D0033_AC_04_パイプの段の上限はpipeline_tomlのmax_buffer_mbで決まる(tmp_path, line, expected):
    """D0033-AC-04: pipeline.toml に max_buffer_mb = 64 を書くと、for_pipe("x", own_work_dir=True) の設定とパイプの段から作る
    sdk_options の max_buffer_size は 67108864。書かないときは 33554432。"""
    write_toml(tmp_path, f"[pipeline]\n{line}\n")
    pipe = make_pipe_def(tmp_path, PIPE_TOML)
    cfg = cfg_of(tmp_path).for_pipe("x", own_work_dir=True)
    spec = ps.build_pipe_specs(cfg, pipe)["a"]
    assert sdk_options(spec, cfg, resume=None).get("max_buffer_size") == expected


# ---- D0033-AC-05・06: pipe-in-gen design --------------------------------------------------


class DesignSeqRunner:
    """設計の段の偽物。渡した StageRun を順に返し、尽きたら最後のものを返し続ける。呼ばれた回数を calls に数える。"""

    def __init__(self, runs: list[StageRun]):
        self.runs = list(runs)
        self.calls = 0

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls += 1
        return self.runs[min(self.calls, len(self.runs)) - 1]


def design_with(tmp_path: Path, monkeypatch, runner, max_rounds: int = 3) -> int:
    """tmp_path/shop に pyproject.toml だけの小さなプロジェクトを作り、置き場所を tmp_path/pipes にして design_pipe を流す。
    既定の置き場所（リポジトリの pipes/）は tmp_path の中に向け、置き場所の環境変数は消してから始める。"""
    import os

    from pipe_in_generator import design
    from test_readme import OLD  # 前の名前はこのファイルに直接書かない（tests/test_rename.py の一覧に無いため）

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(OLD.upper() + "_PIPES_DIR", raising=False)

    def fake_default() -> Path:
        env = pd.env_pipes_dir(os.environ)
        return Path(env) if env else tmp_path / "repo-pipes"

    monkeypatch.setattr(pd, "default_pipes_dir", fake_default)
    project = tmp_path / "shop"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "shop"\n', encoding="utf-8")
    return design.design_pipe(
        project, "apidoc", "API の文書を作りたい", pipes_dir=tmp_path / "pipes", runner=runner, max_rounds=max_rounds
    )


def overflow_run(notice: str) -> StageRun:
    return StageRun(stage="design", session_id="d-1", is_error=True, subtype="error_max_buffer_size", errors=[notice])


def test_D0033_AC_05_designで上限を超えるとやり直さず案内を出して何も作らない(tmp_path, monkeypatch, capsys):
    """D0033-AC-05: pipe-in-gen design の設計の段の runner が上限を超えた形の StageRun を返すと、runner は1回だけ呼ばれ（やり直さない）、
    標準出力に案内の文（errors[0]）が出て、パイプのフォルダも .design-staging も無く、終了コードは 1。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    r = DesignSeqRunner([overflow_run(notice)])
    capsys.readouterr()
    code = design_with(tmp_path, monkeypatch, r)
    out = capsys.readouterr().out
    assert r.calls == 1, f"設計の段が {r.calls} 回呼ばれた（上限を超えたのにやり直した）"
    assert code == 1
    assert notice in out, f"標準出力に案内の文が無い:\n{out}"
    assert "回直しても検査に通らなかった" not in out, out
    assert not (tmp_path / "pipes" / "pipe-in-apidoc").exists()
    assert not (tmp_path / "pipes" / ".design-staging").exists()


def test_D0033_AC_05_前の回で検査に落ちたあと上限を超えても作業用フォルダが残らない(tmp_path, monkeypatch, capsys):
    """D0033-AC-05（補い）: 1回目は検査に通らない設計（stages が空）、2回目で上限を超えると、3回目は流さず（呼び出しは2回）終了コード 1 で、
    .design-staging もパイプのフォルダも残らない。"""
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    bad = StageRun(stage="design", session_id="d-1", structured={"label": "x", "input": "optional", "stages": []})
    r = DesignSeqRunner([bad, overflow_run(notice)])
    code = design_with(tmp_path, monkeypatch, r)
    assert r.calls == 2, f"設計の段が {r.calls} 回呼ばれた（上限を超えたあともやり直した）"
    assert code == 1
    assert not (tmp_path / "pipes" / ".design-staging").exists()
    assert not (tmp_path / "pipes" / "pipe-in-apidoc").exists()


@pytest.mark.parametrize("subtype", ["error_max_turns", ""])
def test_D0033_AC_06_designは上限超え以外の失敗では今までどおりやり直す(tmp_path, monkeypatch, capsys, subtype):
    """D0033-AC-06: 設計の段の runner が上限を超えた以外の失敗（is_error=True・subtype が error_max_buffer_size でない）を返し続けると、
    今までどおり max_rounds（3）回までやり直し、終了コード 1 で「3 回直しても検査に通らなかった」と出す。"""
    r = DesignSeqRunner([StageRun(stage="design", session_id="d-1", is_error=True, subtype=subtype)])
    capsys.readouterr()
    code = design_with(tmp_path, monkeypatch, r, max_rounds=3)
    out = capsys.readouterr().out
    assert r.calls == 3
    assert code == 1
    assert "3 回直しても検査に通らなかった" in out, out


# ---- D0033-AC-07: 前の版の pipeline.toml と pipe.toml -----------------------------------------


def test_D0033_AC_07_前の版のpipeline_tomlとpipe_tomlでも上限超えは終了コード3(tmp_path):
    """D0033-AC-07: max_buffer_mb の無い前の版の pipeline.toml（OLD_TOML）と、上限の項目の無い前の版の pipe.toml（PIPE_TOML に2段目を足したもの）で
    AC-01 の流れを流しても、読み込みで止まらず、段の上限は 33554432 で、終了コード 3 になる。"""
    write_toml(tmp_path, OLD_TOML)
    toml = PIPE_TOML + '[[stages]]\nname = "b"\nlabel = "b"\noutput = "b.md"\nprompt = "x"\n'
    pipe = make_pipe_def(tmp_path, toml)
    cfg = cfg_of(tmp_path).for_pipe(pipe.name, own_work_dir=True)
    assert sdk_options(ps.build_pipe_specs(cfg, pipe)["a"], cfg, resume=None).get("max_buffer_size") == 33554432
    notice = notice_fn()(OVERFLOW_TEXT, 32 * MIB)
    r = PipeOverflowRunner(["a"], notice)
    result, state = run_pipe(tmp_path, toml, r)
    assert result == Exit.STAGE_ERROR, f"終了コードが {result!r}（{int(result)}）"
    assert int(result) == 3
    assert r.calls == ["a"]
    assert state["final"] == "STAGE_ERROR"
