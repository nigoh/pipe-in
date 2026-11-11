"""D0086：既定で守る場所に、プロジェクト直下の `.mcp.json` を足す（issue #136）。

`.mcp.json` は setting_sources に project があると読まれ、MCP サーバーの定義を足せる。D0084 の既定で守る場所に足して、
設定なしで、どの段も書けないようにする。守りの部品（guard.py・bashwrite.py）は変えず、定数と、場所を字で持つ文だけを確かめる。

部品（段の作り方・すり抜けの道の一覧）は tests/test_default_protected.py のものを使う（写しを作らない）。
SDK は呼ばない。ファイルは tmp_path の中だけに作る。前の版の置き場所の名前は、文字のまま書かず chat_support.OLD_NAME から作る。
"""

from __future__ import annotations

import asyncio
import fnmatch
from dataclasses import replace
from pathlib import Path

import pytest
from chat_support import no_sdk  # noqa: F401
from guard_matrix import build_kind, chat_verdict
from test_default_protected import (
    ALL_KINDS,
    BASH_FORMS,
    BASH_KINDS,
    CODE_KINDS,
    OLD_DIR,
    ROOT,
    SLIP_TARGETS,
    WRITE_TOOLS,
    Started,
    build,
    cfg_with_work_dir,
    cli_project,
    pipe_with,
    render,
    w7,
)
from test_reply_guard import permissive_spec

from pipe_in.engine import spec as spec_mod
from pipe_in.engine.config import load_config
from pipe_in.engine.guard import make_guard_hook
from pipe_in.engine.spec import protect
from pipe_in.pipe import definition as pd
from pipe_in.pipe.lint import lint_pipe

MCP = ".mcp.json"
HINT_WORD = "既定で守る場所"


def hook_denies(env, tool: str, **inp) -> bool:
    """SDK の道のフック（make_guard_hook）を1回呼び、deny になったか。"""
    s = env.spec
    guard = make_guard_hook(
        project_dir=env.cfg.project_dir, can_write=s.can_write, allow_bash=s.allow_bash, write_scope_hint=s.write_scope_hint,
        allowed_tools=s.allowed_tools, fetch_domains=s.fetch_domains, max_agent_calls=s.max_agent_calls,
    )  # fmt: skip
    result = asyncio.run(guard({"tool_name": tool, "tool_input": inp}, "t-1", None))
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def with_link(env) -> bool:
    """プロジェクト直下に .mcp.json を作り、src/mcp-link.json をそれへのリンクにする。リンクを作れなければ False。"""
    (env.project / MCP).write_text("{}", encoding="utf-8")
    try:
        (env.project / "src" / "mcp-link.json").symlink_to(env.project / MCP)
    except (OSError, NotImplementedError):
        return False
    return True


# ---- AC-01：書き込みの道具 ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool,key", WRITE_TOOLS)
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0086_ac01_全段の種類で_mcp_json_への書き込み道具が止まる(tmp_path, kind, tool, key):
    """D0086-AC-01: 開発フローの全段とパイプの access のどの種類の段でも、.mcp.json への Write・Edit・MultiEdit・NotebookEdit が止まる
    （can_write が偽、判断の関数が止める、フックが deny）。絶対パスでも相対パスでも。"""
    env = build(tmp_path, kind)
    assert env.spec.can_write(MCP) is False, f"{kind}: can_write({MCP}) が真"
    for form, path in (("絶対パス", str(env.project / MCP)), ("相対パス", MCP)):
        assert env(tool, **{key: path}) is not None, f"{kind}・{tool}・{form} で {MCP} に書けてしまう"
        assert hook_denies(env, tool, **{key: path}), f"{kind}・{tool}・{form} をフックが止めない"


# ---- AC-02：Bash の書き込み・すり抜けの形 ---------------------------------------------------------


@pytest.mark.parametrize("form", [*BASH_FORMS, "echo x > $(echo {t})"])
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0086_ac02_bashの書き込みが止まる(tmp_path, kind, form):
    """D0086-AC-02: .mcp.json への Bash の書き込み（> >> tee cp mv sed -i touch rm truncate python -c node -e bash -c と $(…)）が止まる。"""
    env = build(tmp_path, kind)
    assert env.spec.allow_bash
    cmd = form.format(t=MCP)
    assert env("Bash", command=cmd) is not None, f"{kind}: {cmd} が通ってしまう"


@pytest.mark.parametrize("target", SLIP_TARGETS)
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0086_ac02_dotdotと絶対パスでも止まる(tmp_path, kind, target):
    """D0086-AC-02: src/../.mcp.json・./.mcp.json・絶対パスでも、Bash の書き込みと Write が止まる。"""
    env = build(tmp_path, kind)
    t = target.format(p=MCP, abs=env.project)
    for cmd in (f"echo x > {t}", f"cp src/a.py {t}"):
        assert env("Bash", command=cmd) is not None, f"{kind}: {cmd}"
    assert env("Write", file_path=t, content="x") is not None, f"{kind}: Write {t}"


@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0086_ac02_リンクを経た道でも止まる(tmp_path, kind):
    """D0086-AC-02: src/mcp-link.json（.mcp.json を指すリンク）を通る書き込みも、Write と Bash で止まる。"""
    env = build(tmp_path, kind)
    if not with_link(env):
        pytest.skip("この環境ではリンクを作れない")
    link = "src/mcp-link.json"
    assert env("Write", file_path=str(env.project / link), content="x") is not None, f"{kind}: Write {link}"
    for cmd in (f"echo x > {link}", f"cp src/a.py {link}", f"touch {link}"):
        assert env("Bash", command=cmd) is not None, f"{kind}: {cmd}"


CD_CASES = [
    (["cd src", "echo x > ../.mcp.json"], "cd のあとの .."),
    (["cd docs", "touch ../.mcp.json"], "別のフォルダから touch"),
    (["cd src && echo x > ../.mcp.json"], "1つの命令の中"),
    (["cd src", "cd ..", "echo x > .mcp.json"], "cd で戻ってから"),
]


@pytest.mark.parametrize("cmds,_why", CD_CASES, ids=[c[1] for c in CD_CASES])
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0086_ac02_cdをまたぐ相対パスでも止まる(tmp_path, kind, cmds, _why):
    """D0086-AC-02: cd をまたいだ相対パスで .mcp.json に書く形も止まる（別の呼び出しをまたいで BashState が覚える）。"""
    env = build(tmp_path, kind)
    results = [env("Bash", command=c) for c in cmds]
    assert results[-1] is not None, f"{kind}: {cmds} の最後が通ってしまう"


# ---- AC-03：会話の道 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("access_kind", ["read", "docs", "tests", "code", "code+bash"])
def test_d0086_ac03_会話の道でも止まる(tmp_path, monkeypatch, no_sdk, access_kind):  # noqa: F811
    """D0086-AC-03: 会話の道（chat_hook）でも、段が開いている間の .mcp.json への書き込み（Write・Edit・MultiEdit・NotebookEdit）が止まる。
    Bash を持つ段では Bash の書き込みも。"""
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    env = build_kind(tmp_path, access_kind)
    target = str(env.project / MCP)
    for tool, key in WRITE_TOOLS:
        assert chat_verdict(env, tool, {key: target}, {}) == "D", f"{access_kind}: {tool} が通る"
    if access_kind == "code+bash":
        assert chat_verdict(env, "Bash", {"command": f"echo x > {MCP}"}, {}) == "D"
        assert chat_verdict(env, "Bash", {"command": f"touch {target}"}, {}) == "D"


# ---- AC-04：止めた理由と書ける範囲の説明 ---------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0086_ac04_止めた理由に_mcp_json_が出る(tmp_path, kind):
    """D0086-AC-04: .mcp.json に書こうとして止まったとき、止めた理由の文に、書ける範囲の説明として既定で守る場所の一覧に
    .mcp.json が出る（理由の文の中の既定で守る場所の一覧の部分）。"""
    env = build(tmp_path, kind)
    reason = env("Write", file_path=str(env.project / MCP), content="{}")
    assert reason and HINT_WORD in reason, reason
    assert MCP in reason.split(HINT_WORD, 1)[1], f"既定で守る場所の一覧に {MCP} が出ない: {reason}"


def test_d0086_ac04_書ける範囲の説明は全段に1回ずつ_mcp_json_を出す(tmp_path):
    """D0086-AC-04: 書ける範囲の説明（write_scope_hint）に .mcp.json が全段に1回ずつ出る（元の文で始まり、既定で守る場所は1回）。"""
    cfg = load_config(tmp_path, None)
    out = protect({"s": permissive_spec(), "t": permissive_spec("t")}, cfg)
    for spec in out.values():
        assert spec.write_scope_hint.startswith("どこでも")
        assert spec.write_scope_hint.count(HINT_WORD) == 1
        assert spec.write_scope_hint.count(MCP) == 1, spec.write_scope_hint


def test_d0086_ac04_利用者が_protected_paths_に書いても1回だけ(tmp_path):
    """D0086-AC-04: 利用者が protected_paths にも .mcp.json を書いても、説明の文に .mcp.json は1回だけ出る（既定の一覧の中。
    利用者の分として二重に出ない）。別の場所を足せば、その場所は protected_paths の分として1回出る。"""
    cfg = replace(load_config(tmp_path, None), protected_paths=[])
    base = protect({"s": permissive_spec()}, cfg)["s"]
    dup = protect({"s": permissive_spec()}, replace(cfg, protected_paths=[MCP]))["s"]
    assert dup.write_scope_hint == base.write_scope_hint, "既定と同じ文字列を足しても説明は変わらない"
    assert dup.write_scope_hint.count(MCP) == 1, dup.write_scope_hint
    assert "protected_paths の" not in dup.write_scope_hint
    more = protect({"s": permissive_spec()}, replace(cfg, protected_paths=[MCP, "CLAUDE.md"]))["s"]
    assert more.write_scope_hint.count(MCP) == 1 and more.write_scope_hint.count("CLAUDE.md") == 1, more.write_scope_hint
    assert more.can_write("CLAUDE.md") is False and more.can_write(MCP) is False


# ---- AC-05：work_dir ----------------------------------------------------------------------------------


@pytest.mark.parametrize("work_dir", [MCP, f"{MCP}/x"])
def test_d0086_ac05_work_dirが_mcp_json_の中なら断り文に出る(tmp_path, work_dir):
    """D0086-AC-05: work_dir が .mcp.json そのもの・その下なら、work_dir_conflict が断り、直し方（docs/pipeline）が出る。"""
    msg = spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", work_dir))
    assert msg, work_dir
    assert "work_dir" in msg and "docs/pipeline" in msg, msg


def test_d0086_ac05_断り文の一覧に_mcp_json_が出る(tmp_path):
    """D0086-AC-05: 断り文の「段が書いてはいけない場所」の一覧に .mcp.json が出る（work_dir 自身の名前ではなく、一覧の部分を見る）。"""
    msg = spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", ".claude/x"))
    assert msg
    assert f"（.claude/・.git/・.pipe-in/・{OLD_DIR}/・.mcp.json・pipeline.toml）" in msg, msg


@pytest.mark.parametrize("entrance", ["pipe-in --pipe", "pipe-in（開発フロー）"])
@pytest.mark.parametrize("work_dir", [MCP, f"{MCP}/x"])
def test_d0086_ac05_work_dirが_mcp_json_の中なら流す前に止まる(tmp_path, monkeypatch, work_dir, entrance):
    """D0086-AC-05: work_dir が .mcp.json の中だと、pipe-in は段を流す前に止まる（流す入口に着かない）。"""
    from pipe_in import cli

    args = {"pipe-in --pipe": ["--pipe", "p", "--text", "x", "--yes"], "pipe-in（開発フロー）": ["--text", "x", "--yes"]}[entrance]
    project = cli_project(tmp_path, monkeypatch, work_dir)
    try:
        cli.main(["--project", str(project), *args])
    except Started:
        pytest.fail("段を流す入口まで進んでしまった（始める前に止まっていない）")
    except SystemExit as e:
        msg = str(e.code)
        assert "work_dir" in msg and "docs/pipeline" in msg, msg
        assert e.code not in (0, None)
    else:
        pytest.fail("止まらなかった")


@pytest.mark.parametrize("work_dir", ["docs/pipeline", "build/records", "mcp.json"])
def test_d0086_ac05_ふつうのwork_dirは止まらない(tmp_path, work_dir):
    """D0086-AC-05: 既定の docs/pipeline と、似た名前（mcp.json）の work_dir は止まらない。今のまま通る。守る。"""
    assert spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", work_dir)) is None


# 型 → 人が読む語。断り文と W7 の文は、場所の一覧を字で持つ。定数に足して文を直し忘れると、次のテストが落ちる（設計 1 節）
CONFLICT_WORD = {".claude/*": ".claude/", "*/.claude/*": ".claude/", ".git/*": ".git/", ".git": ".git/", ".pipe-in/*": ".pipe-in/",
                 "pipeline.toml": "pipeline.toml", MCP: MCP, f"{OLD_DIR}/*": f"{OLD_DIR}/"}  # fmt: skip
W7_WORD = {**CONFLICT_WORD, f"{OLD_DIR}/*": "前の版の置き場所"}


def test_d0086_ac05_断り文とW7の文が定数の全部の型の語を持つ(tmp_path):
    """D0086-AC-05（設計 1 節）: 断り文（work_dir_conflict）と W7 の文が、定数の全部の型の語を持つ。.mcp.json を必ず含める。
    定数に型を足して文を直し忘れる、または表に無い型が定数に入ると落ちる。"""
    globs = set(spec_mod.DEFAULT_PROTECTED_PATHS) | {MCP}
    unknown = globs - set(CONFLICT_WORD)
    assert not unknown, f"このテストの表に無い型が定数にある（文の語を決めて表に足す）: {sorted(unknown)}"
    conflict = spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", ".claude/x"))
    assert conflict
    for g in sorted(globs):
        assert CONFLICT_WORD[g] in conflict, f"断り文に「{CONFLICT_WORD[g]}」（型 {g}）が出ない: {conflict}"
    found = w7(lint_pipe(pipe_with(tmp_path, "docs", 'docs_dir = ".claude"\n')))
    assert len(found) == 1, found
    for g in sorted(globs):
        assert W7_WORD[g] in found[0], f"W7 の文に「{W7_WORD[g]}」（型 {g}）が出ない: {found[0]}"


# ---- AC-06：pipe-in-gen check の警告 W7 ----------------------------------------------------------

OVERLAP_MCP = [
    ("docs", f'docs_dir = "{MCP}"\n'),
    ("docs", f'docs_dir = "./{MCP}"\n'),
    ("code", f'writes = ["{MCP}"]\n'),
]


@pytest.mark.parametrize("access,extra", OVERLAP_MCP, ids=[e.strip() for _, e in OVERLAP_MCP])
def test_d0086_ac06_docs_dirとwritesが重なるとW7が出て文に_mcp_json_が出る(tmp_path, access, extra):
    """D0086-AC-06: docs_dir か writes が .mcp.json と重なるパイプに、lint_pipe が W7 を1件出し、文の一覧に .mcp.json が出る。"""
    found = w7(lint_pipe(pipe_with(tmp_path, access, extra)))
    assert len(found) == 1, found
    assert "段 1" in found[0] and "（a）" in found[0]
    assert "・.mcp.json・pipeline.toml・" in found[0], found[0]


def test_d0086_ac06_終了コードは変わらない(tmp_path, capsys):
    """D0086-AC-06: .mcp.json と重なっていても pipe-in-gen check の終了コードは 0 のまま。出力に警告が出て、文に .mcp.json が出る。"""
    from pipe_in_generator.cli import main as gen_main

    pipe_with(tmp_path, "docs", f'docs_dir = "{MCP}"\n')
    code = gen_main(["check", "w", "--pipes-dir", str(tmp_path / "pipes"), "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert HINT_WORD in out, out
    assert "・.mcp.json・" in out, out


@pytest.mark.parametrize("access,extra", [("docs", 'docs_dir = "docs/out"\n'), ("code", 'writes = ["src/.mcp.json"]\n'), ("code", 'writes = ["mcp.json"]\n')])
def test_d0086_ac06_重ならなければ出ない(tmp_path, access, extra):
    """D0086-AC-06: 重ならない docs_dir・writes（直下でない同じ名前・似た名前を含む）には W7 が出ない。今のまま通る。守る。"""
    assert w7(lint_pipe(pipe_with(tmp_path, access, extra))) == []


# ---- AC-07：許す側 ------------------------------------------------------------------------------------

LOOKALIKES = ["src/.mcp.json", "a/b/.mcp.json", "mcp.json", ".mcp.json.bak", ".mcp.jsonl"]


def test_d0086_ac07_型は直下だけに当たる():
    """D0086-AC-07: 定数の型 .mcp.json は記号を含まない字面で、相対パス .mcp.json にだけ当たる。直下でない同じ名前・似た名前には、
    定数のどの型も当たらない。今のまま通る。守る。（大文字小文字違いの当たる・当たらないは断定しない）"""
    globs = spec_mod.DEFAULT_PROTECTED_PATHS
    assert MCP in globs, "定数に .mcp.json が無い"
    assert not any(ch in MCP for ch in "*?["), "型は記号を含まない字面そのもの"
    assert fnmatch.fnmatch(MCP, MCP)
    for ok in LOOKALIKES:
        assert not any(fnmatch.fnmatch(ok, g) for g in globs), ok


@pytest.mark.parametrize("rel", LOOKALIKES)
@pytest.mark.parametrize("kind", CODE_KINDS)
def test_d0086_ac07_段の書ける範囲では似た名前が通る(tmp_path, kind, rel):
    """D0086-AC-07: 直下でない .mcp.json（src/.mcp.json など）と似た名前への書き込みは、コードを書く段で今までどおり通る
    （Write・Edit・Bash）。今のまま通る。守る。"""
    env = build(tmp_path, kind)
    (env.project / Path(rel).parent).mkdir(parents=True, exist_ok=True)
    assert env.spec.can_write(rel) is True, rel
    assert env("Write", file_path=str(env.project / rel), content="x") is None, rel
    assert env("Edit", file_path=rel, old_string="a", new_string="b") is None, rel
    assert env("Bash", command=f"echo x > {rel}") is None, rel
    assert env("Bash", command=f"touch {rel}") is None, rel


# ---- AC-08：ひな形と見本 ------------------------------------------------------------------------------

TEMPLATE_NAMES = ["dev", "diagrams", "spec-qa", "spec-review", "review-quorum"]


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_d0086_ac08_ひな形に_mcp_json_を書く所が無い(tmp_path, name):
    """D0086-AC-08: ひな形（generator/templates/）を描いた pipe.toml に、.mcp.json を書く行（docs_dir・writes を含む）が無い。
    実物を読むだけで書かない。今のまま通る。守る。"""
    pipe_dir = render(ROOT / "generator" / "templates" / name, tmp_path / "pipe-in-x")
    text = (pipe_dir / "pipe.toml").read_text(encoding="utf-8")
    assert not any(MCP in ln for ln in _code_lines(text)), name
    pipe = pd.load_pipe(pipe_dir)
    assert not any(MCP in (s.docs_dir or "") or any(MCP in w for w in s.writes) for s in pipe.stages)


@pytest.mark.parametrize("name", ["diagrams", "spec-qa", "research", "video"])
def test_d0086_ac08_見本に_mcp_json_を書く所が無い(name):
    """D0086-AC-08: 見本（examples/）のパイプの pipe.toml に、.mcp.json を書く行（docs_dir・writes を含む）が無い。読むだけ。今のまま通る。守る。"""
    pipe_dir = ROOT / "examples" / name / "pipes" / f"pipe-in-{name}"
    text = (pipe_dir / "pipe.toml").read_text(encoding="utf-8")
    assert not any(MCP in ln for ln in _code_lines(text)), name
    pipe = pd.load_pipe(pipe_dir)
    assert not any(MCP in (s.docs_dir or "") or any(MCP in w for w in s.writes) for s in pipe.stages)


# ---- AC-09：守りの比較の表 ----------------------------------------------------------------------------


def test_d0086_ac09_比較の表に_mcp_json_の行があり_sdkと会話の道は止める():
    """D0086-AC-09: 守りの比較の表に行 write-mcpjson があり、SDK の道（sdk・sdk_protected）と会話の道とプラグインは止める（D）。
    開発用の期待は実測のまま（dev_coder だけ A）。ほかの行の照合は tests/test_guard_matrix.py が見る。"""
    from guard_matrix import COLUMNS, EXPECT

    row = EXPECT["write-mcpjson"]
    assert len(row) == len(COLUMNS)
    for col in ("sdk", "sdk_protected", "chat", "plugin_builder", "plugin_judge"):
        assert row[COLUMNS.index(col)] == "D", col
    assert row[COLUMNS.index("sdk")] == row[COLUMNS.index("sdk_protected")]


# ---- AC-10：古い形 ------------------------------------------------------------------------------------


def test_d0086_ac10_mcp_jsonを書かない設定はそのまま読める(tmp_path):
    """D0086-AC-10: .mcp.json を書いていない今までの pipeline.toml（protected_paths だけのもの・無いもの）はそのまま読め、
    Config の protected_paths は読んだまま。protect() で .mcp.json が足され、ふつうの書き込みは通る。"""
    (tmp_path / "pipeline.toml").write_text('[pipeline]\nprotected_paths = ["tests/arch/*"]\n', encoding="utf-8")
    cfg = load_config(tmp_path, None)
    assert cfg.protected_paths == ["tests/arch/*"], "読み方は変えない（既定は読む側で足さない）"
    out = protect({"s": permissive_spec()}, cfg)["s"]
    assert out.can_write(MCP) is False
    assert out.can_write("tests/arch/a.py") is False
    assert out.can_write("src/app.py") is True and out.can_write("src/.mcp.json") is True
    (tmp_path / "pipeline.toml").unlink()
    none = load_config(tmp_path, None)
    assert none.protected_paths == []
    assert protect({"s": permissive_spec()}, none)["s"].can_write(MCP) is False


def test_d0086_ac10_前の版の置き場所のパイプは_mcp_json_を足してもそのまま流せる(tmp_path, monkeypatch):
    """D0086-AC-10: 前の版の置き場所のパイプを読んで流す動きは変わらない（成果物は書け、前の版の置き場所は止まり、.mcp.json も止まる）。"""
    from chat_support import OLD_NAME
    from test_pipe_flow import pipe_toml, stage_toml

    from pipe_in.pipe import specs as pipe_specs

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    project = tmp_path / "app"
    folder = project / OLD_DIR / "pipes" / f"{OLD_NAME}-x"
    folder.mkdir(parents=True)
    (folder / "pipe.toml").write_text(pipe_toml(stage_toml("a", "", access="code")), encoding="utf-8")
    found = pd.find_pipe("x", None, project=project)
    assert found is not None
    cfg = load_config(project, None, auto_approve=True).for_pipe(pd.load_pipe(found).name, own_work_dir=True)
    spec = pipe_specs.build_pipe_specs(cfg, pd.load_pipe(found))["a"]
    assert spec.can_write(f"{cfg.rel(cfg.work_dir)}/a.md") is True
    assert spec.can_write(f"{OLD_DIR}/x") is False
    assert spec.can_write(MCP) is False
    assert spec.can_write("src/app.py") is True


def test_d0086_ac10_protected_pathsに書いても読めて説明に1回(tmp_path):
    """D0086-AC-10: 利用者が protected_paths に .mcp.json を書いていても今までどおり読め、止まり、重複は説明の文に1回だけ出る
    （既定の一覧の中。利用者の分として別に出ない）。"""
    (tmp_path / "pipeline.toml").write_text(f'[pipeline]\nprotected_paths = ["{MCP}", "tests/arch/*"]\n', encoding="utf-8")
    cfg = load_config(tmp_path, None)
    assert cfg.protected_paths == [MCP, "tests/arch/*"]
    out = protect({"s": permissive_spec()}, cfg)["s"]
    assert out.can_write(MCP) is False and out.can_write("tests/arch/a.py") is False
    hint = out.write_scope_hint
    assert hint.count(MCP) == 1, hint
    default_part = hint.split(" と、protected_paths の")[0]
    assert MCP in default_part, f"既定の一覧に {MCP} が出ない: {hint}"
