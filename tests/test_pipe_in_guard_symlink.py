"""D0087 (2)：開発用のフック（.claude/hooks/pipe_in_guard.py）が、書き込み先と基準のリンクの先をたどって判断する。

フックは tests/guard_matrix.py の dev_hook() と同じく importlib で読んで decide を呼ぶ（フックのファイルは読むだけ）。
判断の形は「文字の上の判断（今のまま）と、たどった判断の両方が通るときだけ通す」（狭めない）。
ファイルとリンクは tmp_path の中だけに作る。SDK は呼ばない。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path

import pytest
from symlink_support import link_or_skip

HOOK = Path(__file__).parents[1] / ".claude" / "hooks" / "pipe_in_guard.py"
TOOLS = ["Write", "Edit", "MultiEdit"]
WRITERS = ("pipe-in-analyst", "pipe-in-tester", "pipe-in-coder", "pipe-in-verifier", "pipe-in-documenter")


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("pipe_in_guard_symlink", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_project(parent: Path, name: str = "proj", *, git_is_file: bool = False) -> Path:
    """git の作業フォルダの形のプロジェクト。守る場所（.claude・.git・.env・ほかの段の記録・tests）と、製品コード（src）がある。"""
    p = parent / name
    for rel in (".claude/settings.json", ".env", "src/app.py", "tests/test_a.py", "docs/pipeline/01_requirements.md", "docs/guide/a.md", "README.md"):
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n", encoding="utf-8")
    if git_is_file:
        (p / ".git").write_text("gitdir: ../.git/worktrees/w\n", encoding="utf-8")
    else:
        (p / ".git").mkdir()
        (p / ".git" / "config").write_text("x\n", encoding="utf-8")
    return p


def payload(agent, tool, file_path, cwd) -> dict:
    p = {"tool_name": tool, "tool_input": {"file_path": str(file_path), "content": "x"}, "cwd": str(cwd)}
    if agent:
        p["agent_type"] = agent
    return p


def verdict(guard, agent, tool, file_path, root, cwd=None):
    return guard.decide(payload(agent, tool, file_path, cwd or root), root=str(root))


def denied(reason) -> bool:
    return isinstance(reason, str) and bool(reason)


# ---- AC-08：リンクで守る場所に書けない ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", TOOLS)
def test_d0087_ac08_coder_link_to_settings_denied(guard, tmp_path, tool):
    """D0087-AC-08: src/link.json が .claude/settings.json を指すリンクのとき、pipe-in-coder の Write・Edit・MultiEdit は止まる。
    今の作りは文字の上だけで判断するので通ってしまう（赤）。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "link.json", p / ".claude" / "settings.json")
    assert denied(verdict(guard, "pipe-in-coder", tool, p / "src" / "link.json", p))


@pytest.mark.parametrize(
    "agent,link,target",
    [
        ("pipe-in-tester", "tests/link.py", "src/app.py"),
        ("pipe-in-tester", "docs/pipeline/03_red_tests.md", "src/app.py"),
        ("pipe-in-analyst", "docs/pipeline/02_design.md", "src/app.py"),
        ("pipe-in-verifier", "docs/pipeline/05_test_report.md", "src/app.py"),
        ("pipe-in-documenter", "docs/guide/link.md", "src/app.py"),
        ("pipe-in-documenter", "docs/development/link.md", ".claude/settings.json"),
    ],
)
@pytest.mark.parametrize("tool", TOOLS)
def test_d0087_ac08_other_roles_link_outside_denied(guard, tmp_path, agent, link, target, tool):
    """D0087-AC-08: tester・analyst・verifier・documenter も、その役の書ける場所の外を指すリンクへの書き込みは止まる。"""
    p = make_project(tmp_path)
    link_or_skip(p / link, p / target)
    assert denied(verdict(guard, agent, tool, p / link, p)), (agent, link)


# ---- AC-09：リンクでない、ふつうの書ける場所は今のまま ------------------------------------------------------------

PLAIN = [
    ("pipe-in-coder", "src/app.py", True),
    ("pipe-in-coder", "src/new_module.py", True),
    ("pipe-in-coder", "docs/guide/new.md", True),
    ("pipe-in-coder", "docs/pipeline/04_implementation.md", True),
    ("pipe-in-coder", "README.md", True),
    ("pipe-in-coder", ".claude/settings.json", False),
    ("pipe-in-coder", ".git/config", False),
    ("pipe-in-coder", ".env", False),
    ("pipe-in-coder", "tests/test_a.py", False),
    ("pipe-in-coder", "docs/pipeline/01_requirements.md", False),
    ("pipe-in-tester", "tests/test_new.py", True),
    ("pipe-in-tester", "tests/test_a.py", True),
    ("pipe-in-tester", "docs/pipeline/03_red_tests.md", True),
    ("pipe-in-tester", "src/app.py", False),
    ("pipe-in-analyst", "docs/pipeline/01_requirements.md", True),
    ("pipe-in-analyst", "docs/pipeline/02_design.md", True),
    ("pipe-in-analyst", "src/app.py", False),
    ("pipe-in-verifier", "docs/pipeline/05_test_report.md", True),
    ("pipe-in-verifier", "src/app.py", False),
    ("pipe-in-documenter", "docs/guide/a.md", True),
    ("pipe-in-documenter", "docs/guide/new.md", True),
    ("pipe-in-documenter", "README.md", True),
    ("pipe-in-documenter", "src/app.py", False),
]


@pytest.mark.parametrize("agent,rel,allowed", PLAIN)
def test_d0087_ac09_plain_writes_unchanged(guard, tmp_path, agent, rel, allowed):
    """D0087-AC-09: リンクでない、ふつうの書き込み（各役の書ける場所、まだ無い新しいファイルも）は今のまま通り、書けない場所は今のまま止まる
    （今のまま通る。守る）。"""
    p = make_project(tmp_path)
    for tool in TOOLS:
        got = verdict(guard, agent, tool, p / rel, p)
        assert (got is None) == allowed, (agent, tool, rel, got)
        rel_arg = verdict(guard, agent, tool, rel, p)  # 相対パスでも同じ
        assert (rel_arg is None) == allowed, (agent, tool, rel, rel_arg)


# ---- AC-10：書ける場所の中を指すリンクは通り、守る場所を指すリンクは止まる -----------------------------------------


def test_d0087_ac10_link_inside_writable_allowed(guard, tmp_path):
    """D0087-AC-10: src/a_link.py が src/app.py を指すリンクのとき、coder は書ける（文字の上もたどった先も書ける場所。今のまま通る。守る）。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "a_link.py", p / "src" / "app.py")
    for tool in TOOLS:
        assert verdict(guard, "pipe-in-coder", tool, p / "src" / "a_link.py", p) is None, tool


@pytest.mark.parametrize("target", [".claude/settings.json", ".git/config", ".env", "docs/pipeline/01_requirements.md", "tests/test_a.py"])
def test_d0087_ac10_link_to_protected_denied(guard, tmp_path, target):
    """D0087-AC-10: 書ける場所の中から、記録（docs/pipeline/ のほかの段）・.claude/・.git/・.env・テストを指すリンクは、coder で止まる。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "l.py", p / target)
    for tool in TOOLS:
        assert denied(verdict(guard, "pipe-in-coder", tool, p / "src" / "l.py", p)), (tool, target)


@pytest.mark.parametrize("folder", [".claude", ".git"])
def test_d0087_ac10_dir_link_to_protected_denied(guard, tmp_path, folder):
    """D0087-AC-10: 途中のフォルダがリンクで守る場所を指す形（src/dl → .claude）も、その下への書き込みが止まる。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "dl", p / folder, directory=True)
    name = "settings.json" if folder == ".claude" else "config"
    assert denied(verdict(guard, "pipe-in-coder", "Write", p / "src" / "dl" / name, p))


@pytest.mark.parametrize("link", [".claude/x.json", ".git/x", "tests/l.py", "docs/pipeline/01_requirements.md"])
def test_d0087_ac10_link_from_protected_to_writable_denied(guard, tmp_path, link):
    """D0087-AC-10: 止まる所から、書ける所（src/app.py）を指すリンクも、coder で止まる（文字の上の判断も残す。両方が通るときだけ通す。
    今のまま止まる。守る）。"""
    p = make_project(tmp_path)
    f = p / link
    if f.exists():
        f.unlink()
    link_or_skip(f, p / "src" / "app.py")
    for tool in TOOLS:
        assert denied(verdict(guard, "pipe-in-coder", tool, f, p)), (tool, link)


# ---- AC-11：worktree・cwd がリンクを経た形 -----------------------------------------------------------------------


def make_worktrees(tmp_path: Path):
    main = make_project(tmp_path, "main")
    wt = make_project(main / ".claude" / "worktrees", "w", git_is_file=True)
    wt2 = make_project(main / ".claude" / "worktrees", "w2", git_is_file=True)
    return main, wt, wt2


def test_d0087_ac11_worktree_root_unchanged(guard, tmp_path):
    """D0087-AC-11: .git がファイルの worktree（主の checkout の .claude/ の中にある）では、基準は worktree 自身のまま。
    worktree の中のふつうの書き込みは通り、.claude/・テスト・worktree の外（主の checkout）は止まる（今のまま通る。守る）。"""
    main, wt, _ = make_worktrees(tmp_path)
    root = guard.project_root(str(wt / "src"), None)
    assert Path(root) == wt
    assert verdict(guard, "pipe-in-coder", "Write", wt / "src" / "new.py", root, cwd=wt) is None
    assert denied(verdict(guard, "pipe-in-coder", "Write", wt / ".claude" / "settings.json", root, cwd=wt))
    assert denied(verdict(guard, "pipe-in-coder", "Write", wt / "tests" / "test_a.py", root, cwd=wt))
    assert denied(verdict(guard, "pipe-in-coder", "Write", main / "src" / "app.py", root, cwd=wt))


@pytest.mark.parametrize("target", ["main-src", "main-claude", "other-worktree"])
def test_d0087_ac11_worktree_link_outside_denied(guard, tmp_path, target):
    """D0087-AC-11: worktree の中のリンクが、worktree の外（主の checkout・ほかの worktree）を指すときは止まる。"""
    main, wt, wt2 = make_worktrees(tmp_path)
    dest = {"main-src": main / "src" / "app.py", "main-claude": main / ".claude" / "settings.json", "other-worktree": wt2 / "src" / "app.py"}[target]
    link_or_skip(wt / "src" / "l.py", dest)
    root = guard.project_root(str(wt), None)
    for tool in TOOLS:
        assert denied(verdict(guard, "pipe-in-coder", tool, wt / "src" / "l.py", root, cwd=wt)), (tool, target)


def test_d0087_ac11_worktree_link_inside_allowed(guard, tmp_path):
    """D0087-AC-11: worktree の中のリンクが worktree の中の書ける場所を指すときは通る。主の checkout の道を回って同じ worktree を指すリンクも通る
    （基準もたどるので、worktree 自身が書ける範囲は変わらない。今のまま通る。守る）。"""
    main, wt, _ = make_worktrees(tmp_path)
    link_or_skip(wt / "src" / "a.py", wt / "src" / "app.py")
    link_or_skip(wt / "src" / "b.py", main / ".claude" / "worktrees" / "w" / "src" / "app.py")
    root = guard.project_root(str(wt), None)
    for name in ("a.py", "b.py"):
        assert verdict(guard, "pipe-in-coder", "Write", wt / "src" / name, root, cwd=wt) is None, name


@pytest.mark.parametrize("form", ["root-link", "path-link", "both-link", "both-real"])
def test_d0087_ac11_cwd_via_link_same_result(guard, tmp_path, form):
    """D0087-AC-11: cwd がリンクを経た形（/tmp → /private/tmp 型）でも、基準と書き込み先が同じ形なら、ふつうの書き込みは通り、守る場所は止まる。
    片方だけがリンクを経た形のときも、守る場所は止まる（今のまま通る。守る）。"""
    real = tmp_path / "real_parent"
    p = make_project(real)
    link_or_skip(tmp_path / "link_parent", real, directory=True)
    via_link = tmp_path / "link_parent" / "proj"
    root = {"root-link": via_link, "path-link": p, "both-link": via_link, "both-real": p}[form]
    base = {"root-link": p, "path-link": via_link, "both-link": via_link, "both-real": p}[form]
    assert guard.project_root(str(root), None) == str(root)
    for tool in TOOLS:
        assert denied(verdict(guard, "pipe-in-coder", tool, base / ".claude" / "settings.json", root, cwd=root)), (form, tool)
        assert denied(verdict(guard, "pipe-in-coder", tool, base / "tests" / "test_a.py", root, cwd=root)), (form, tool)
    if form.startswith("both"):
        for tool in TOOLS:
            assert verdict(guard, "pipe-in-coder", tool, base / "src" / "new.py", root, cwd=root) is None, (form, tool)
            assert verdict(guard, "pipe-in-coder", tool, "src/new.py", root, cwd=root) is None, (form, tool)


def test_d0087_ac11_link_in_link_parent_still_traced(guard, tmp_path):
    """D0087-AC-11: cwd がリンクを経た形のとき、プロジェクトの中のリンクが守る場所を指すなら、それでも止まる。"""
    real = tmp_path / "real_parent"
    p = make_project(real)
    link_or_skip(tmp_path / "link_parent", real, directory=True)
    link_or_skip(p / "src" / "link.json", p / ".claude" / "settings.json")
    via_link = tmp_path / "link_parent" / "proj"
    assert denied(verdict(guard, "pipe-in-coder", "Write", via_link / "src" / "link.json", via_link))


# ---- AC-12：壊れたリンク・輪のリンクは止まり、フックは落ちない -----------------------------------------------------


@pytest.mark.parametrize("shape", ["broken-inside", "broken-outside", "self-loop", "pair-loop"])
@pytest.mark.parametrize("tool", TOOLS)
def test_d0087_ac12_broken_and_loop_denied(guard, tmp_path, shape, tool):
    """D0087-AC-12: 壊れたリンク（先が書ける場所の中でも外でも）と、輪になったリンクは、coder で止まり、例外を出さずに理由の文を返す。"""
    p = make_project(tmp_path)
    src = p / "src"
    if shape == "broken-inside":
        link_or_skip(src / "l.py", src / "missing.py")
    elif shape == "broken-outside":
        link_or_skip(src / "l.py", tmp_path / "ghost" / "x.py")
    elif shape == "self-loop":
        link_or_skip(src / "l.py", src / "l.py")
    else:
        link_or_skip(src / "l.py", src / "m.py")
        link_or_skip(src / "m.py", src / "l.py")
    assert denied(verdict(guard, "pipe-in-coder", tool, src / "l.py", p))


def _run_main(guard, monkeypatch, data: dict) -> tuple[int, bytes]:
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(data).encode("utf-8")), encoding="utf-8"))
    monkeypatch.setattr("sys.stdout", out)
    code = guard.main()
    out.flush()
    return code, out.buffer.getvalue()


@pytest.mark.parametrize("agent", ["pipe-in-coder", "pipe-in-tester"])
def test_d0087_ac12_hook_does_not_crash(guard, tmp_path, monkeypatch, agent):
    """D0087-AC-12: 先をたどる関数（os.path.realpath）が例外を出しても、フックは落ちず、pipe-in-* の書き込みは deny の JSON で止める
    （終了コード 0）。読むだけの道具は通す。"""
    p = make_project(tmp_path)
    rel = "src/new.py" if agent == "pipe-in-coder" else "tests/test_new.py"

    def boom(*args, **kwargs):
        raise OSError("たどれない")

    with monkeypatch.context() as m:
        m.setenv("CLAUDE_PROJECT_DIR", str(p))
        m.setattr(os.path, "realpath", boom)
        code, out = _run_main(guard, m, payload(agent, "Write", p / rel, p))
        assert code == 0
        assert json.loads(out.decode("utf-8"))["hookSpecificOutput"]["permissionDecision"] == "deny"
        code, out = _run_main(guard, m, {**payload(agent, "Read", p / rel, p), "tool_input": {"file_path": str(p / rel)}})
        assert (code, out) == (0, b"")


def test_d0087_ac12_main_caller_unaffected_by_links(guard, tmp_path, monkeypatch):
    """D0087-AC-12: メイン（agent_type 無し）は絞らない相手：壊れたリンク・輪のリンク・守る場所を指すリンクへの書き込みも、今までどおり通し、
    たどる関数が例外を出しても何も出さない（今のまま通る。守る）。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "to_claude.json", p / ".claude" / "settings.json")
    link_or_skip(p / "src" / "broken.py", p / "src" / "missing.py")
    link_or_skip(p / "src" / "loop.py", p / "src" / "loop.py")
    for name in ("to_claude.json", "broken.py", "loop.py"):
        assert verdict(guard, None, "Write", p / "src" / name, p) is None, name

    def boom(*args, **kwargs):
        raise OSError("たどれない")

    with monkeypatch.context() as m:
        m.setattr(os.path, "realpath", boom)
        code, out = _run_main(guard, m, payload(None, "Write", p / "src" / "new.py", p))
    assert (code, out) == (0, b"")


# ---- AC-15：守りを狭めていない -----------------------------------------------------------------------------------


@pytest.mark.parametrize("agent", WRITERS)
def test_d0087_ac15_dev_never_widens(guard, tmp_path, agent):
    """D0087-AC-15: 今の判断（project_path ＋ その役の can_write の写し）が止める入力は、リンクが絡んでも、たどったあとも止まる
    （.. ・基準の外・名前の違い・守る場所を直接指すパス・止まる所から書ける所を指すリンク）。リンクの無い入力は、止める・通すが今と同じ。"""
    p = make_project(tmp_path)
    can_write = guard.AGENTS[agent][0]
    link_or_skip(p / ".claude" / "to_src.py", p / "src" / "app.py")
    link_or_skip(p / "tests" / "to_src.py", p / "src" / "app.py")
    link_or_skip(p / "docs" / "pipeline" / "03_red_tests.md", p / "src" / "app.py")
    link_or_skip(p / ".git" / "to_src", p / "src" / "app.py")
    plain = [
        f"{p}/src/../.claude/settings.json",
        "src/../.claude/settings.json",
        "src\\..\\.claude\\settings.json",
        f"{p}/../outside.txt",
        str(tmp_path / "outside.txt"),
        str(tmp_path / "proj_other" / "src" / "app.py"),
        str(p) + "x/src/app.py",
        ".claude/settings.json",
        str(p / ".git" / "config"),
        str(p / ".env"),
        str(p / "tests" / "test_a.py"),
        str(p / "src" / "app.py"),
        str(p / "src" / "new.py"),
        str(p / "docs" / "pipeline" / "01_requirements.md"),
        str(p / "docs" / "pipeline" / "05_test_report.md"),
        str(p / "docs" / "guide" / "a.md"),
        "",
    ]
    linked = [str(p / ".claude" / "to_src.py"), str(p / "tests" / "to_src.py"), str(p / ".git" / "to_src"), str(p / "docs" / "pipeline" / "03_red_tests.md")]
    def old_denied(fp: str) -> bool:
        rel = guard.project_path(fp, str(p))
        return rel is None or not can_write(rel)

    for fp in plain:
        for tool in TOOLS:
            now = denied(verdict(guard, agent, tool, fp, p))
            assert now == old_denied(fp), f"リンクの無い入力で結果が変わった: {agent} {tool} {fp!r}（今まで止める={old_denied(fp)}）"
    for fp in linked:
        if not old_denied(fp):
            continue  # この役では、リンクの置き場所そのものが書ける場所（たどった先で止まるのは狭める側。広がらない）
        for tool in TOOLS:
            assert denied(verdict(guard, agent, tool, fp, p)), f"今まで止まっていた入力が通るようになった: {agent} {tool} {fp!r}"
    # 絶対パスが基準の外を指す形は、リンクが絡んでも止まる
    assert denied(verdict(guard, agent, "Write", tmp_path / "outside.txt", p))


@pytest.mark.parametrize("agent", ["pipe-in-coder", "pipe-in-tester", "pipe-in-analyst"])
@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Bash", {"command": "echo x > .claude/settings.json"}),
        ("Bash", {"command": "cp src/app.py .claude/settings.json"}),
        ("PowerShell", {"command": "Set-Content .claude/settings.json x"}),
        ("mcp__x__y", {}),
        ("Agent", {"prompt": "x"}),
        ("NotebookEdit", {"notebook_path": ".claude/a.ipynb"}),
    ],
)
def test_d0087_ac15_dev_other_roads_still_denied(guard, tmp_path, agent, tool, tool_input):
    """D0087-AC-15: Bash の書き込み・PowerShell・MCP・サブエージェント・ノートブックの道は、リンクのあるプロジェクトでも止まる（今のまま通る。守る）。"""
    p = make_project(tmp_path)
    link_or_skip(p / "src" / "link.json", p / ".claude" / "settings.json")
    payload_ = {"tool_name": tool, "tool_input": tool_input, "cwd": str(p), "agent_type": agent}
    assert denied(guard.decide(payload_, root=str(p))), (agent, tool)
