"""D0083-AC-01〜03・06・07：4つの守り（SDK の道・会話の道・プラグイン・開発用）の結果を、1つの表で横に比べて固定する。

表は tests/guard_matrix.py。ここは、表の 1 行ずつを 9 つの列に通して、実際の結果が表のとおりかを見る。
これは「いまの結果を固定する」テスト（今の作りで通る）。守りを変えて、行が「許す → 止める」に変わったら落ちて、差が見える。
SDK は呼ばない。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import pytest
from chat_support import OLD_NAME, OLD_PIPES_ENV, no_sdk  # noqa: F401
from guard_matrix import BASE_ROW, BYPASS_ROWS, COLUMNS, LINK_ROWS, ROWS, build_kind, evaluate, plugin_verdict

pytestmark = pytest.mark.usefixtures("no_sdk")

BY_ID = {r.id: r for r in ROWS}
KINDS = sorted({r.kind for r in ROWS})


@pytest.fixture(scope="module")
def envs(tmp_path_factory):
    """段の種類ごとのプロジェクト（会話の道の段は開いたまま）。モジュールで 1 回だけ作る。"""
    root = tmp_path_factory.mktemp("matrix")
    # 司会役とフックは SDK を読まない。モジュール用の fixture は function の monkeypatch を使えないので、ここで同じことをする
    import sys

    mp = pytest.MonkeyPatch()
    mp.setitem(sys.modules, "claude_agent_sdk", None)
    mp.delenv("PIPE_IN_PIPES_DIR", raising=False)
    mp.delenv(OLD_PIPES_ENV, raising=False)
    try:
        yield {kind: build_kind(root, kind) for kind in KINDS}
    finally:
        mp.undo()


def result(envs, row_id: str) -> str:
    row = BY_ID[row_id]
    env = envs[row.kind]
    if row_id in LINK_ROWS and not env.links_ok:
        pytest.skip("この環境ではリンクを作れない")
    return evaluate(env, row)


def show(actual: str) -> str:
    return " ".join(f"{c}={a}" for c, a in zip(COLUMNS, actual, strict=True))


def test_d0083_matrix_shape():
    """D0083-AC-01（形の検査）: 全行の expect が列の数と同じ長さ・id が重ならない・Skill と Agent の行の前に理由のコメントがある。"""
    ids = [r.id for r in ROWS]
    assert len(ids) == len(set(ids)), "id が重なっている"
    assert all(len(r.expect) == len(COLUMNS) for r in ROWS), [r.id for r in ROWS if len(r.expect) != len(COLUMNS)]
    assert all(set(r.expect) <= {"A", "D", "-"} for r in ROWS), "expect は A・D・- だけ（? の入れ忘れが無い）"
    assert BASE_ROW in BY_ID and all(i in BY_ID for i in BYPASS_ROWS)
    from pathlib import Path

    text = (Path(__file__).parent / "guard_matrix.py").read_text(encoding="utf-8").splitlines()
    for key in ('Row("skill"', 'Row("agent-listed"'):
        i = next(n for n, line in enumerate(text) if line.lstrip().startswith(key))
        assert text[i - 1].lstrip().startswith("#"), f"{key} の前にコメントが無い"
    assert any("Skill" in line and line.lstrip().startswith("#") for line in text)
    assert any("Agent・Task" in line and line.lstrip().startswith("#") for line in text)


@pytest.mark.parametrize("row_id", [r.id for r in ROWS])
def test_d0083_ac01_matrix_row_matches_each_guard(envs, row_id):
    """D0083-AC-01: 表の 1 行を 9 つの列に通した結果が、表のとおり（許す行と止める行の両方。今の結果を固定する）。"""
    actual = result(envs, row_id)
    want = BY_ID[row_id].expect
    assert actual == want, f"{row_id}\n  実際: {actual}  {show(actual)}\n  表  : {want}"


# ---- AC-02：止める行は、すり抜けの道でも止まる ------------------------------------------------------------------

# 基準の行（何も工夫せずに .claude/settings.json に書く）が止まる列で、すり抜けの道の行が許してしまう組。
# 守りが元々その道を扱わない列は、道具ごと止める（D）として表に載っている。ここに書くのは、実測で許してしまったもの。
KNOWN_GAPS: set[tuple[str, str]] = set()


@pytest.mark.parametrize("row_id", BYPASS_ROWS)
def test_d0083_ac02_bypass_rows_are_denied(envs, row_id):
    """D0083-AC-02: 基準の行（write-dotclaude）を止める列は、絶対パス・相対パス・.. を含むパス・MultiEdit・NotebookEdit・Bash の書き込みの形・
    サブエージェントの中・PowerShell・MCP の道でも止める（表のとおり。許してしまう組は KNOWN_GAPS に理由つきで固定）。"""
    base = BY_ID[BASE_ROW].expect
    row = BY_ID[row_id].expect
    leaks = [c for c, b, r in zip(COLUMNS, base, row, strict=True) if b == "D" and r != "D" and (row_id, c) not in KNOWN_GAPS]
    assert leaks == [], f"{row_id} が {leaks} で通る（基準の行は止める）"


def test_d0083_ac02_symlink_row_records_actual_result(envs):
    """D0083-AC-02: リンクを経た道は、守りごとに実際の結果をそのまま固定する（SDK の道と会話の道はリンクをたどり、プラグインと開発用はたどらない）。
    差があれば別の件で扱う（D0083 の推し 3）。リンクを作れない環境では skip。"""
    if not all(envs[k].links_ok for k in KINDS):
        pytest.skip("この環境ではリンクを作れない")
    for rid in sorted(LINK_ROWS):
        actual = result(envs, rid)
        assert actual == BY_ID[rid].expect, f"{rid}\n  実際: {show(actual)}"


# ---- AC-03：許す行は、許す列で通る -------------------------------------------------------------------------------

ALLOWED_AT = {
    "write-code-ok": ["sdk", "sdk_protected", "chat", "dev_coder"],
    "write-test-ok": ["sdk", "sdk_protected", "chat", "dev_tester"],
    "write-docs-ok": ["sdk", "sdk_protected", "chat"],
    "write-output-ok": ["sdk", "sdk_protected", "chat"],
    "read-ok": list(COLUMNS),
    "bash-pytest-ok": ["sdk", "sdk_protected", "chat", "dev_tester", "dev_coder", "dev_verifier"],
    "write-pipes-prompt": ["sdk", "sdk_protected", "chat", "plugin_builder", "dev_coder"],
    "write-pipes-toml": ["sdk", "sdk_protected", "chat", "plugin_builder", "dev_coder"],
    "write-pipes-readme": ["sdk", "sdk_protected", "chat", "plugin_builder", "dev_coder"],
    "bash-pipe-in-gen-list": ["plugin_builder"],
    "skill": ["sdk", "sdk_protected"],
    "agent-listed": ["sdk", "sdk_protected"],  # 会話の道は agents を持つ段を流せないので判断しない（-）
    "task-listed": ["sdk", "sdk_protected"],
}


@pytest.mark.parametrize("row_id", sorted(ALLOWED_AT))
def test_d0083_ac03_allowed_rows_pass_where_allowed(envs, row_id):
    """D0083-AC-03: 許す行（ふつうのコード・テスト・成果物・読む・pytest・パイプのファイル・pipe-in-gen・Skill・Agent）は、それを許す列で通る。
    ここに書いた列は、表（AC-01）の A の列の部分集合であること。"""
    expect = BY_ID[row_id].expect
    for col in ALLOWED_AT[row_id]:
        assert expect[COLUMNS.index(col)] == "A", f"{row_id} は {col} で通るはずだが、表では止める"
    actual = result(envs, row_id)
    for col in ALLOWED_AT[row_id]:
        assert actual[COLUMNS.index(col)] == "A", f"{row_id} が {col} で止まった: {show(actual)}"


# ---- AC-06・07（プラグインの作る役と審査役。(B) の後も通る） ----------------------------------------------------


def test_d0083_ac06_builder_can_write_pipe_files(tmp_path):
    """D0083-AC-06: 作る役が書ける pipes/pipe-in-<名前>/prompts/a.md・pipe.toml・README.md は、Write・Edit・MultiEdit のどれでも通る（(B) の後も通る）。"""
    for tool in ("Write", "Edit", "MultiEdit"):
        for rel in ("prompts/a.md", "pipe.toml", "README.md"):
            path = str(tmp_path / "pipes" / "pipe-in-x" / rel)
            assert plugin_verdict("pipe-in:pipe-builder", tmp_path, tool, {"file_path": path}, {}) == "A", (tool, rel)


def test_d0083_ac06_judge_can_read(tmp_path):
    """D0083-AC-06: 審査役は Read・Glob・Grep が通り、Write は止まる（(B) の後も通る）。"""
    for tool in ("Read", "Glob", "Grep"):
        assert plugin_verdict("pipe-in:pipe-judge", tmp_path, tool, {"file_path": str(tmp_path / "a.md")}, {}) == "A", tool
    path = str(tmp_path / "pipes" / "pipe-in-x" / "pipe.toml")
    assert plugin_verdict("pipe-in:pipe-judge", tmp_path, "Write", {"file_path": path}, {}) == "D"


@pytest.mark.parametrize("sub", ["list", "new x", "check x"])
def test_d0083_ac06_pipe_in_gen_list_new_check_pass(tmp_path, sub):
    """D0083-AC-06: 作る役の Bash は pipe-in-gen list・new・check が通り、--force は止まる（(B) の後も通る）。"""
    assert plugin_verdict("pipe-in:pipe-builder", tmp_path, "Bash", {"command": f"pipe-in-gen {sub}"}, {}) == "A"
    assert plugin_verdict("pipe-in:pipe-builder", tmp_path, "Bash", {"command": f"pipe-in-gen {sub} --force"}, {}) == "D"


def test_d0083_ac07_old_form_gives_same_result_as_new(tmp_path):
    """D0083-AC-07: 前の版の形（前の名前のフォルダ名の頭・置き場所の環境変数）でも、新しい形と同じ結果。前の名前の -gen コマンドは止まる。"""
    old = OLD_NAME
    env_dir = tmp_path / "elsewhere"
    cases = [
        ("Write", {"file_path": str(tmp_path / "pipes" / "pipe-in-x" / "prompts" / "a.md")}),
        ("Write", {"file_path": str(tmp_path / "pipes" / "pipe-in-x" / "pipe.toml")}),
        ("Write", {"file_path": str(tmp_path / "pipes" / "pipe-in-x" / "src.py")}),
        ("Write", {"file_path": str(tmp_path / ".claude" / "settings.json")}),
    ]
    for tool, tin in cases:
        new_form = plugin_verdict("pipe-in:pipe-builder", tmp_path, tool, tin, {})
        old_in = {"file_path": tin["file_path"].replace("pipe-in-x", f"{old}-x")}
        assert plugin_verdict("pipe-in:pipe-builder", tmp_path, tool, old_in, {}) == new_form, tin
    # 置き場所の環境変数の下（新しい名前の環境変数も前の版の名前の環境変数も、同じ決まりで見る。pipes_env にはその値が並ぶ）
    from pipe_in_generator import guard_hook

    for env_name in ("PIPE_IN_PIPES_DIR", OLD_PIPES_ENV):
        pipes_env = guard_hook.env_pipes_dirs({env_name: str(env_dir)})
        assert pipes_env == [str(env_dir)], env_name
        for folder, rel, want in (("pipe-in-x", "pipe.toml", "A"), (f"{old}-x", "pipe.toml", "A"), ("pipe-in-x", "run.py", "D")):
            tin = {"file_path": str(env_dir / folder / rel)}
            assert plugin_verdict("pipe-in:pipe-builder", tmp_path, "Write", tin, {}, pipes_env=pipes_env) == want, (env_name, folder, rel)
    assert plugin_verdict("pipe-in:pipe-builder", tmp_path, "Bash", {"command": "pipe-in-gen list"}, {}) == "A"
    assert plugin_verdict("pipe-in:pipe-builder", tmp_path, "Bash", {"command": f"{old}-gen list"}, {}) == "D"
