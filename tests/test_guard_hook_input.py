"""D0083-AC-04・05・08・09・10：プラグインのフック（generator/guard_hook.py）の入力の読みを固くする。

読めない入力・上限を超える入力・標準出力に書けない場合・文字列でない agent_type で、止めない側に倒れない。
標準入力・標準出力は手書きの偽物（ファイルのような物）に差し替える。SDK は呼ばない。ファイルは tmp_path の中だけに作る。
上限は定数 MAX_STDIN_BYTES を小さく差し替えて確かめる（16 MiB の入力は作らない）。

「部品がまだ無い」ことと「今の作りが決まりと違う」ことを分けるため、新しい部品（MAX_STDIN_BYTES・quiet_exit_streams）は
使うところで取る。定数が無くても差し替えは raising=False で行い、定数の値そのものは AC-08 の専用のテストで確かめる。
今の作りのままで通るテスト（許す入力が止まらないことの守り）は、docstring に「今の作りで通る」と書いた。
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import gen_loader
import pytest
from chat_support import Run, hook_decision, hook_payload, no_sdk, pipe_toml, stage_toml  # noqa: F401

GEN_DIR = Path(__file__).resolve().parents[1] / "generator"
SMALL_LIMIT = 256
BUILDER = "pipe-in:pipe-builder"


def hook():
    from pipe_in_generator import guard_hook

    return guard_hook


# ---- 手書きの偽物 -------------------------------------------------------------------------------------


class FakeBuffer:
    """標準入力の buffer：読んだ大きさを覚える。exc があれば read で出す。"""

    def __init__(self, data: bytes = b"", exc: BaseException | None = None):
        self.data = data
        self.exc = exc
        self.sizes: list[Any] = []

    def read(self, size: Any = -1) -> bytes:
        self.sizes.append(size)
        if self.exc is not None:
            raise self.exc
        if size is None or size < 0:
            return self.data
        return self.data[:size]


class FakeStdin:
    def __init__(self, buffer: FakeBuffer):
        self.buffer = buffer


class BrokenOut:
    """書けない標準出力（または標準エラー）。write か flush のどちらかが、またはどちらも失敗する。"""

    def __init__(self, exc: BaseException | None = None, *, write_fails: bool = True, flush_fails: bool = True):
        self.exc = exc or BrokenPipeError(32, "Broken pipe")
        self.write_fails = write_fails
        self.flush_fails = flush_fails

    def write(self, text: str) -> int:
        if self.write_fails:
            raise self.exc
        return len(text)

    def flush(self) -> None:
        if self.flush_fails:
            raise self.exc


def payload_bytes(**fields: Any) -> bytes:
    p = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}, "agent_type": BUILDER, "cwd": "/proj"}
    p.update(fields)
    return json.dumps(p).encode("utf-8")


def padded(size: int) -> bytes:
    """許される入力（作る役の Read）を、空白で埋めてちょうど size バイトにしたもの。"""
    raw = payload_bytes()
    assert len(raw) <= size
    return raw + b" " * (size - len(raw))


def set_limit(monkeypatch, limit: int = SMALL_LIMIT) -> None:
    # 定数がまだ無くても差し替えは通す（無いことは AC-08 の専用のテストが見る）
    monkeypatch.setattr(hook(), "MAX_STDIN_BYTES", limit, raising=False)


def run_main(monkeypatch, capsys, stdin: Any) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "stdin", stdin)
    code = hook().main()
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def assert_denied(code: int, out: str) -> str:
    assert code == 0, f"deny を出したときの終了コードは 0（実際 {code}）"
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "deny", out
    assert spec["permissionDecisionReason"], "止める文が空"
    return spec["permissionDecisionReason"]


# ---- AC-04：読めない入力は、deny を出して終了コード 0 で終わる（例外で落ちない） -----------------------------------


@pytest.mark.parametrize(
    "name,data,exc,limit",
    [
        ("broken-json", b"{not json", None, None),
        ("not-utf8", b"\xff\xfe\x00{", None, None),
        ("empty", b"", None, None),
        ("not-object", b"[1, 2]", None, None),
        ("deep-array", b"[" * 100_000, None, None),
        ("deep-object", b'{"a":' * 100_000, None, None),
        ("stdin-oserror", b"", OSError(5, "Input/output error"), None),
        ("stdin-memoryerror", b"", MemoryError(), None),
        ("over-limit", padded(SMALL_LIMIT) + b" ", None, SMALL_LIMIT),
    ],
)
def test_d0083_ac04_unreadable_input_denies_with_code_0(monkeypatch, capsys, name, data, exc, limit):
    """D0083-AC-04: 壊れた JSON・UTF-8 でない入力・空・JSON の物でない入力・深い入れ子（RecursionError）・標準入力の読み取りの
    OSError / MemoryError・上限を超える入力は、deny の JSON を標準出力に出して終了コード 0 で終わり、例外で落ちない。
    （broken-json・not-utf8・empty・not-object は今の作りで通る。残りは今の作りでは例外が外へ出る・上限が無い）"""
    if limit is not None:
        set_limit(monkeypatch, limit)
    code, out, _ = run_main(monkeypatch, capsys, FakeStdin(FakeBuffer(data, exc)))
    assert_denied(code, out)


def test_d0083_ac04_deny_reason_does_not_echo_input(monkeypatch, capsys):
    """D0083-AC-04: 読めない入力で止めるときの理由に、入力の文字を入れない（外から来た文字を理由に増やさない）。"""
    secret = "SECRET-MARKER-12345"
    code, out, _ = run_main(monkeypatch, capsys, FakeStdin(FakeBuffer(("[" * 100_000 + secret).encode())))
    assert secret not in assert_denied(code, out) and secret not in out


# ---- AC-08：上限 ---------------------------------------------------------------------------------------


def test_d0083_ac08_limit_is_16_mib():
    """D0083-AC-08: 標準入力の上限は定数 MAX_STDIN_BYTES で、16 MiB（部品がまだ無いと、ここが AttributeError で落ちる）。"""
    assert hook().MAX_STDIN_BYTES == 16 * 1024 * 1024


def test_d0083_ac08_input_at_limit_is_read(monkeypatch, capsys):
    """D0083-AC-08: 上限ちょうどの大きさの正しい入力（許す入力）は、止まらずに読める（今の作りで通る。許す入力が止まらないことの守り）。"""
    set_limit(monkeypatch)
    code, out, _ = run_main(monkeypatch, capsys, FakeStdin(FakeBuffer(padded(SMALL_LIMIT))))
    assert (code, out) == (0, "")


def test_d0083_ac08_input_one_byte_over_is_denied(monkeypatch, capsys):
    """D0083-AC-08: 上限を 1 バイト超えると、中身が許す入力でも止まる。"""
    set_limit(monkeypatch)
    code, out, _ = run_main(monkeypatch, capsys, FakeStdin(FakeBuffer(padded(SMALL_LIMIT) + b" ")))
    assert_denied(code, out)


def test_d0083_ac08_reads_at_most_limit_plus_one(monkeypatch, capsys):
    """D0083-AC-08: 超える入力は最後まで読み込まない：buffer.read に渡す大きさは、いつも上限 + 1 バイト以下の正の数。"""
    set_limit(monkeypatch)
    buf = FakeBuffer(b" " * (SMALL_LIMIT * 100))
    code, out, _ = run_main(monkeypatch, capsys, FakeStdin(buf))
    assert_denied(code, out)
    assert buf.sizes, "buffer を読んでいない"
    assert all(isinstance(s, int) and 0 < s <= SMALL_LIMIT + 1 for s in buf.sizes), f"大きさを決めずに読んだ: {buf.sizes}"


@pytest.mark.parametrize("extra,denied", [(0, False), (1, True)])
def test_d0083_ac08_text_stdin_without_buffer_has_the_same_limit(monkeypatch, capsys, extra, denied):
    """D0083-AC-08: buffer の無い標準入力（文字の入力）でも、同じ上限で見る（ちょうどは通り、1 つ超えると止まる）。"""
    set_limit(monkeypatch)
    text = padded(SMALL_LIMIT).decode("utf-8") + " " * extra
    code, out, _ = run_main(monkeypatch, capsys, io.StringIO(text))
    if denied:
        assert_denied(code, out)
    else:
        assert (code, out) == (0, "")


# ---- AC-05：止める返事を書けないときは、標準エラーに理由を書いて終了コード 2 -------------------------------------


def unreadable() -> FakeStdin:
    return FakeStdin(FakeBuffer(b"{broken"))


@pytest.mark.parametrize(
    "name,out_obj",
    [
        ("write-fails", BrokenOut(BrokenPipeError(32, "Broken pipe"))),
        ("write-fails-oserror", BrokenOut(OSError(28, "No space left on device"))),
        ("flush-fails", BrokenOut(OSError(28, "No space left on device"), write_fails=False)),
        ("closed", None),
    ],
)
def test_d0083_ac05_unwritable_stdout_exits_2(monkeypatch, capsys, name, out_obj):
    """D0083-AC-05: deny を標準出力に書けない（書く・flush が失敗する・閉じている）とき、例外を出さず、標準エラーに理由を書いて終了コード 2。"""
    if out_obj is None:
        out_obj = io.StringIO()
        out_obj.close()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out_obj)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(sys, "stdin", unreadable())
    assert hook().main() == 2
    assert err.getvalue().strip(), "標準エラーに理由が無い"


def test_d0083_ac05_stderr_also_unwritable_still_2(monkeypatch):
    """D0083-AC-05: 標準エラーも書けないときは、理由は出せないが、例外を出さず終了コード 2。"""
    monkeypatch.setattr(sys, "stdout", BrokenOut())
    monkeypatch.setattr(sys, "stderr", BrokenOut())
    monkeypatch.setattr(sys, "stdin", unreadable())
    assert hook().main() == 2


def test_d0083_ac05_allowed_call_does_not_need_stdout(monkeypatch):
    """D0083-AC-05: 止めない呼び出し（何も書かない）は、標準出力が書けなくても終了コード 0（今の作りで通る。許す入力を止めない守り）。"""
    monkeypatch.setattr(sys, "stdout", BrokenOut())
    monkeypatch.setattr(sys, "stdin", FakeStdin(FakeBuffer(payload_bytes())))
    assert hook().main() == 0


def test_d0083_ac05_cli_entry_returns_2(monkeypatch):
    """D0083-AC-05: pipe-in-gen guard-hook の入口（cli.main(["guard-hook"])）からも、書けないときは 2 が返る。"""
    from pipe_in_generator import cli

    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", BrokenOut())
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(sys, "stdin", unreadable())
    assert cli.main(["guard-hook"]) == 2


@pytest.mark.skipif(not sys.platform.startswith("linux") or not Path("/dev/full").exists(), reason="/dev/full は Linux だけ")
def test_d0083_ac05_real_process_exit_code_is_2_not_120(tmp_path):
    """D0083-AC-05: 本物の起動（pipe-in-gen と同じ cli.main()・引数なし）で標準出力が書けない（/dev/full）とき、終了コードは 2。
    書けなかったバイトが残ると終了処理の flush が失敗し 120 に化けるので、それを防ぐ。"""
    script = tmp_path / "run_hook.py"
    script.write_text(
        gen_loader.CHILD_PRELUDE + "import sys\n"
        "from pipe_in_generator import cli\n"
        "sys.argv = ['pipe-in-gen', 'guard-hook']\n"
        "sys.exit(cli.main())\n",
        encoding="utf-8",
    )
    with open("/dev/full", "wb") as full:
        proc = subprocess.run(
            [sys.executable, str(script), str(gen_loader.LOADER_PATH), str(GEN_DIR)], input=b"{broken", stdout=full, stderr=subprocess.PIPE, cwd=tmp_path, check=False, timeout=60
        )
    assert proc.returncode == 2, f"終了コード {proc.returncode}（120 は終了処理の flush の失敗）: {proc.stderr.decode('utf-8', 'replace')}"


# ---- AC-09：文字列でない agent_type は、読む道具のほかを止める ---------------------------------------------------

NON_STRING_AGENT_TYPES = [[], ["pipe-in:pipe-builder"], {}, {"agent": "pipe-in:pipe-builder"}, 0, 1, 1.5, False, True]
BLOCKED_TOOLS = [
    ("Write", {"file_path": "src/app.py", "content": "x"}),
    ("Bash", {"command": "rm -rf build"}),
    ("Skill", {"skill": "x"}),
    ("Agent", {"prompt": "x", "run_in_background": False}),
    ("mcp__x__y", {}),
    ("PowerShell", {"command": "Remove-Item x"}),
]


def decide(tool: Any, tool_input: Any, agent_type: Any, *, with_agent: bool = True) -> str | None:
    p: dict[str, Any] = {"tool_name": tool, "tool_input": tool_input, "cwd": "/proj"}
    if with_agent:
        p["agent_type"] = agent_type
    return hook().decide(p, pipes_env=[])


@pytest.mark.parametrize("agent_type", NON_STRING_AGENT_TYPES, ids=repr)
@pytest.mark.parametrize("tool,tool_input", BLOCKED_TOOLS, ids=[t for t, _ in BLOCKED_TOOLS])
def test_d0083_ac09_non_string_agent_type_denies_non_read_tools(tool, tool_input, agent_type):
    """D0083-AC-09: agent_type がリスト・辞書・数値（0 を含む）・真偽（False を含む）のとき、Write・Bash・Skill・Agent・MCP・PowerShell は止まる。"""
    assert decide(tool, tool_input, agent_type), f"{tool} が通った（agent_type={agent_type!r}）"


@pytest.mark.parametrize("agent_type", NON_STRING_AGENT_TYPES, ids=repr)
@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep"])
def test_d0083_ac09_non_string_agent_type_still_reads(tool, agent_type):
    """D0083-AC-09: 文字列でない agent_type でも、読む道具（Read・Glob・Grep）は通る（今の作りで通る。読むことを止めない守り）。"""
    assert decide(tool, {"file_path": "src/app.py"}, agent_type) is None


@pytest.mark.parametrize("agent_type", [0, [], {}, False], ids=repr)
@pytest.mark.parametrize("tool", [["Read"], {"a": 1}, None, 5], ids=repr)
def test_d0083_ac09_non_string_agent_type_with_odd_tool_name_denies_without_raising(tool, agent_type):
    """D0083-AC-09: tool_name が文字列でない（リスト・辞書・null・数値）ときも、文字列でない agent_type なら例外を出さずに止める。"""
    assert decide(tool, {}, agent_type)


def test_d0083_ac09_deny_reason_names_only_the_type():
    """D0083-AC-09: 止める理由に入れるのは型の名前だけ（外から来た agent_type の中身を入れない）。"""
    reason = decide("Write", {"file_path": "x"}, {"SECRET-MARKER-12345": ["y"]})
    assert reason and "SECRET-MARKER-12345" not in reason


@pytest.mark.parametrize("agent_type", [None, "", "Explore", "general-purpose", "pipe-in:other", "pipe-builder-x"], ids=repr)
def test_d0083_ac09_other_agent_types_still_pass(agent_type):
    """D0083-AC-09: agent_type が null・空文字・別の名前の文字列のときは、今までどおり通る（今の作りで通る。許していたものを止めない守り）。"""
    assert decide("Write", {"file_path": "src/app.py", "content": "x"}, agent_type) is None
    assert decide("Bash", {"command": "ls"}, agent_type) is None


def test_d0083_ac09_missing_agent_type_still_passes():
    """D0083-AC-09: agent_type が無い呼び出し（会話の本体）も、今までどおり通る（今の作りで通る）。"""
    assert decide("Write", {"file_path": "src/app.py"}, None, with_agent=False) is None


# ---- AC-10：会話の道（chat_hook）の入口からも同じ結果 -----------------------------------------------------------


def deny_json(text: str) -> str | None:
    """pipe-in-gen guard-hook の入口（cli.main(["guard-hook"])）に text を渡し、止めた理由を返す（通したら None）。"""
    from pipe_in_generator import cli

    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(text), io.StringIO()
    try:
        code = cli.main(["guard-hook"])
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    assert code == 0
    return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("agent_type", [0, [], {}, False, True], ids=repr)
def test_d0083_ac10_chat_hook_denies_non_string_agent_type_without_cwd(agent_type):
    """D0083-AC-10: cwd が無い入力でも、会話の道の入口（chat_hook.main）は文字列でない agent_type の書き込みを止める。"""
    no_cwd = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "src/a.py", "content": "x"}, "agent_type": agent_type}
    assert hook_decision(json.dumps(no_cwd)), "cwd が無いとき通った"


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("agent_type", [0, [], {}, False, True], ids=repr)
def test_d0083_ac10_chat_hook_denies_non_string_agent_type_without_run(tmp_path, agent_type):
    """D0083-AC-10: 記録が無い作業フォルダ（cwd あり）でも、会話の道の入口（chat_hook.main）は文字列でない agent_type の書き込みを止める。"""
    no_run = hook_payload(tmp_path, "Write", {"file_path": str(tmp_path / "src" / "a.py"), "content": "x"}, agent_type)
    assert hook_decision(json.dumps(no_run)), "記録が無い作業フォルダで通った"


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("agent_type", [0, [], {}, False], ids=repr)
def test_d0083_ac10_chat_hook_still_reads_for_non_string_agent_type(tmp_path, agent_type):
    """D0083-AC-10: 会話の道の入口でも、文字列でない agent_type の読む道具（Read）は通る（今の作りで通る。読むことを止めない守り）。"""
    read = hook_payload(tmp_path, "Read", {"file_path": str(tmp_path / "src" / "a.py")}, agent_type)
    assert hook_decision(json.dumps(read)) is None


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("agent_type", [0, [], {}, False], ids=repr)
def test_d0083_ac10_cli_entry_denies_non_string_agent_type(tmp_path, agent_type):
    """D0083-AC-10: pipe-in-gen guard-hook の入口（cli.main(["guard-hook"])）でも、文字列でない agent_type の書き込みは止まり、読む道具は通る。"""
    write = hook_payload(tmp_path, "Write", {"file_path": str(tmp_path / "src" / "a.py"), "content": "x"}, agent_type)
    assert deny_json(json.dumps(write)), "書き込みが通った"
    read = hook_payload(tmp_path, "Read", {"file_path": str(tmp_path / "src" / "a.py")}, agent_type)
    assert deny_json(json.dumps(read)) is None, "読む道具が止まった"


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("agent_type", [0, [], {}, False], ids=repr)
def test_d0083_ac10_chat_hook_denies_with_open_stage(tmp_path, agent_type):
    """D0083-AC-10: 会話の中で段が開いている間は、文字列でない agent_type は「ほかのエージェント」として止まる（今の作りで通る。守り続ける）。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("s", access="code", output="out.md")))
    r.run_next("s")
    assert r.hook("Write", {"file_path": str(r.project / "src" / "a.py"), "content": "x"}, agent_type)
