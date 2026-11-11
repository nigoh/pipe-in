"""D0088 (1)：プラグインのフック（generator/guard_hook.py）が、書き込み先のリンクの先をたどって判断する。

pipe-builder の書き込みは、パイプのフォルダ（…/pipes/pipe-in-<名前>/ か、環境変数の置き場所の下）の
pipe.toml・README.md・prompts/*.md だけ。書ける場所の中のリンクが外（.claude/settings.json など）を指すときは止める。
判断の形は「文字の上の判断（今のまま）と、たどった判断の両方が通るときだけ通す」（狭めない）。
ファイルとリンクは tmp_path の中だけに作る。SDK は呼ばない。
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from symlink_support import link_or_skip


def hook():
    from pipe_in_generator import guard_hook

    return guard_hook


BUILDER = "pipe-in:pipe-builder"
OLD_NAME = "dev" + "pipe"  # 前の版の名前（tests/test_rename.py に掛からないよう、つなげて書く）
ENV_NAMES = {"new": "PIPE_IN_PIPES_DIR", "old": OLD_NAME.upper() + "_PIPES_DIR"}
PREFIXES = ("pipe-in-", OLD_NAME + "-")
# （環境変数の種類, パイプのフォルダ名の頭）。None は環境変数なしで、途中一致（…/pipes/pipe-in-<名前>/）の道
CASES = [(env, prefix) for env in (None, "new", "old") for prefix in PREFIXES]
CASE_IDS = [f"{env or 'mid'}-{prefix}" for env, prefix in CASES]
TOOLS = ["Write", "Edit", "MultiEdit"]


class Lay:
    """プロジェクトと、パイプの置き場所（base）、その中のパイプ x と y。env が None なら base は <project>/.pipe-in/pipes。"""

    def __init__(self, tmp_path: Path, env: str | None, prefix: str, *, prompts: bool = True, pipe_x: bool = True):
        self.tmp = tmp_path
        self.root = tmp_path / "proj"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("x\n", encoding="utf-8")
        self.env = env
        self.prefix = prefix
        self.base = self.root / ".pipe-in" / "pipes" if env is None else tmp_path / "place"
        self.x = self.base / f"{prefix}x"
        self.y = self.base / f"{prefix}y"
        for p in ((self.x,) if pipe_x else ()) + (self.y,):
            p.mkdir(parents=True)
            (p / "pipe.toml").write_text("x\n", encoding="utf-8")
            (p / "README.md").write_text("x\n", encoding="utf-8")
            if prompts or p is self.y:
                (p / "prompts").mkdir()
                (p / "prompts" / "a.md").write_text("x\n", encoding="utf-8")

    @property
    def pipes_env(self) -> list[str] | None:
        if self.env is None:
            return None
        return hook().env_pipes_dirs({ENV_NAMES[self.env]: str(self.base)})

    def verdict(self, path: str | Path, tool: str = "Write", cwd: str | Path | None = None):
        payload = {
            "tool_name": tool,
            "tool_input": {"file_path": str(path)},
            "cwd": str(cwd if cwd is not None else self.root),
            "agent_type": BUILDER,
        }
        return hook().decide(payload, pipes_env=self.pipes_env)


def denied(reason) -> bool:
    return isinstance(reason, str) and bool(reason)


# ---- AC-01：リンクが .claude/settings.json を指すとき止まる -----------------------------------------------------


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac01_link_in_prompts_to_settings_denied(tmp_path, env, prefix, tool):
    """D0088-AC-01: パイプの prompts/link.md が .claude/settings.json を指すリンクのとき、Write・Edit・MultiEdit は止まる
    （途中一致の道と、PIPE_IN_PIPES_DIR・前の版の環境変数の道。パイプのフォルダ名は新旧どちらの頭でも）。
    文字の上の判断は通るが、リンクをたどった判断が止めるので、全体は止まる。"""
    lay = Lay(tmp_path, env, prefix)
    link_or_skip(lay.x / "prompts" / "link.md", lay.root / ".claude" / "settings.json")
    assert denied(lay.verdict(lay.x / "prompts" / "link.md", tool))


# ---- AC-02：リンクでない、ふつうの書ける場所は今のまま ------------------------------------------------------------


@pytest.mark.parametrize("rel", ["pipe.toml", "README.md", "prompts/a.md", "prompts/new.md"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac02_plain_writable_still_allowed(tmp_path, env, prefix, rel):
    """D0088-AC-02: リンクでない pipe.toml・README.md・prompts/*.md（まだ無い新しいファイルも）は通る（リンクをたどる判断を足しても、狭めない）。"""
    lay = Lay(tmp_path, env, prefix)
    for tool in TOOLS:
        assert lay.verdict(lay.x / rel, tool) is None, (tool, rel)


@pytest.mark.parametrize("which", ["run.py", "prompts/x/a.md", "prompts/a.txt", "prompts/.md", "src", "base-readme", "other-dir", "wrong-name"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac02_plain_not_writable_still_denied(tmp_path, env, prefix, which):
    """D0088-AC-02: pipe.toml 以外・prompts/ の下の入れ子・パイプのフォルダの外は、今のまま止まる（今のまま通る。守る）。"""
    lay = Lay(tmp_path, env, prefix)
    paths = {
        "run.py": lay.x / "run.py",
        "prompts/x/a.md": lay.x / "prompts" / "x" / "a.md",
        "prompts/a.txt": lay.x / "prompts" / "a.txt",
        "prompts/.md": lay.x / "prompts" / ".md",
        "src": lay.root / "src" / "app.py",
        "base-readme": lay.base / "README.md",
        "other-dir": lay.base / "other-dir" / "pipe.toml",
        "wrong-name": lay.base / "pipe-x" / "pipe.toml",
    }
    for tool in TOOLS:
        assert denied(lay.verdict(paths[which], tool)), (tool, which)


# ---- AC-03：書ける場所の中を指すリンクは通る --------------------------------------------------------------------


@pytest.mark.parametrize("target", ["own-toml", "other-pipe-toml"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac03_link_to_writable_inside_allowed(tmp_path, env, prefix, target):
    """D0088-AC-03: prompts/l.md が、同じパイプの pipe.toml か、同じ置き場所の別のパイプの pipe.toml を指すときは通る
    （文字の上もたどった先も、書ける場所の中。今のまま通る。直したあとも通ること）。"""
    lay = Lay(tmp_path, env, prefix)
    dest = lay.x / "pipe.toml" if target == "own-toml" else lay.y / "pipe.toml"
    link_or_skip(lay.x / "prompts" / "l.md", dest)
    for tool in TOOLS:
        assert lay.verdict(lay.x / "prompts" / "l.md", tool) is None, tool


# ---- AC-04：置き場所・基準がリンクでも、決まったファイルは今のまま通る ---------------------------------------------


@pytest.mark.parametrize("prefix", PREFIXES)
def test_d0088_ac04_pipes_dir_is_link_allowed(tmp_path, prefix):
    """D0088-AC-04: パイプの置き場所（.pipe-in/pipes）が、名前が pipes でないフォルダ（shared/pipe-set）へのリンクのとき、
    その下の決まったファイルは通り、pipe.toml 以外は止まる（今のまま。基準の側もたどって比べるので、直したあとも通ること）。"""
    root = tmp_path / "proj"
    real = root / "shared" / "pipe-set" / f"{prefix}x"
    (real / "prompts").mkdir(parents=True)
    (real / "pipe.toml").write_text("x\n", encoding="utf-8")
    link_or_skip(root / ".pipe-in" / "pipes", root / "shared" / "pipe-set", directory=True)
    pipe = root / ".pipe-in" / "pipes" / f"{prefix}x"
    payload = lambda p, tool: {"tool_name": tool, "tool_input": {"file_path": str(p)}, "cwd": str(root), "agent_type": BUILDER}  # noqa: E731
    for tool in TOOLS:
        for rel in ("pipe.toml", "README.md", "prompts/a.md", "prompts/new.md"):
            assert hook().decide(payload(pipe / rel, tool), pipes_env=None) is None, (tool, rel)
        assert denied(hook().decide(payload(pipe / "run.py", tool), pipes_env=None)), tool


@pytest.mark.parametrize("env", ["new", "old"])
@pytest.mark.parametrize("prefix", PREFIXES)
def test_d0088_ac04_env_dir_is_link_allowed(tmp_path, env, prefix):
    """D0088-AC-04: 環境変数の置き場所そのものがリンクのとき、その下の決まったファイルは今のまま通る（直したあとも通ること）。"""
    real = tmp_path / "real_place" / f"{prefix}x"
    (real / "prompts").mkdir(parents=True)
    link_or_skip(tmp_path / "alias_place", tmp_path / "real_place", directory=True)
    pipes_env = hook().env_pipes_dirs({ENV_NAMES[env]: str(tmp_path / "alias_place")})
    assert pipes_env == [str(tmp_path / "alias_place")]
    for tool in TOOLS:
        for rel in ("pipe.toml", "README.md", "prompts/a.md"):
            payload = {"tool_name": tool, "tool_input": {"file_path": str(tmp_path / "alias_place" / f"{prefix}x" / rel)}, "cwd": str(tmp_path), "agent_type": BUILDER}
            assert hook().decide(payload, pipes_env=pipes_env) is None, (tool, rel)


@pytest.mark.parametrize("form", ["cwd-link-relative", "cwd-link-abs-link", "cwd-link-abs-real", "cwd-real-abs-link"])
def test_d0088_ac04_cwd_and_file_path_via_link_allowed(tmp_path, form):
    """D0088-AC-04: プロジェクトのフォルダがリンクの先にあるとき（cwd と file_path の片方だけ、または両方がリンクを経た形）も、今のまま通る
    （/tmp → /private/tmp の形。直したあとも通ること）。"""
    real_root = tmp_path / "real_root"
    (real_root / ".pipe-in" / "pipes" / "pipe-in-x" / "prompts").mkdir(parents=True)
    link_or_skip(tmp_path / "link_root", real_root, directory=True)
    rel = ".pipe-in/pipes/pipe-in-x/prompts/a.md"
    cwd, file_path = {
        "cwd-link-relative": (tmp_path / "link_root", rel),
        "cwd-link-abs-link": (tmp_path / "link_root", str(tmp_path / "link_root" / rel)),
        "cwd-link-abs-real": (tmp_path / "link_root", str(real_root / rel)),
        "cwd-real-abs-link": (real_root, str(tmp_path / "link_root" / rel)),
    }[form]
    for tool in TOOLS:
        payload = {"tool_name": tool, "tool_input": {"file_path": file_path}, "cwd": str(cwd), "agent_type": BUILDER}
        assert hook().decide(payload, pipes_env=None) is None, (tool, form)


# ---- AC-05：外を指すリンクは止まる -------------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["src-app", "outside-file", "other-place-pipe"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac05_link_outside_denied(tmp_path, env, prefix, target):
    """D0088-AC-05: prompts/l.md が src/app.py・パイプの置き場所の外のファイル・別の置き場所のパイプを指すリンクのとき、止まる。"""
    lay = Lay(tmp_path, env, prefix)
    elsewhere = tmp_path / "elsewhere" / "pipes" / f"{prefix}z" / "prompts"
    elsewhere.mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    dest = {
        "src-app": lay.root / "src" / "app.py",
        "outside-file": tmp_path / "outside" / "x.md",
        "other-place-pipe": elsewhere / "a.md",
    }[target]
    link_or_skip(lay.x / "prompts" / "l.md", dest)
    for tool in TOOLS:
        assert denied(lay.verdict(lay.x / "prompts" / "l.md", tool)), (tool, target)


@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac05_dir_link_outside_denied(tmp_path, env, prefix):
    """D0088-AC-05: 途中のフォルダがリンクで外を指す形（prompts 自体が外のフォルダを指す）は、その下の a.md への書き込みが止まる。"""
    lay = Lay(tmp_path, env, prefix, prompts=False)
    (tmp_path / "outside_dir").mkdir()
    link_or_skip(lay.x / "prompts", tmp_path / "outside_dir", directory=True)
    for tool in TOOLS:
        assert denied(lay.verdict(lay.x / "prompts" / "a.md", tool)), tool


@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac05_pipe_dir_link_outside_denied(tmp_path, env, prefix):
    """D0088-AC-05: 置き場所の中の pipe-in-<名前> 自体が、置き場所の外のフォルダを指すリンクのとき、その下の決まったファイルへの書き込みは止まる。"""
    lay = Lay(tmp_path, env, prefix)
    (tmp_path / "outside_pipe" / "prompts").mkdir(parents=True)
    link_or_skip(lay.base / f"{prefix}z", tmp_path / "outside_pipe", directory=True)
    for tool in TOOLS:
        for rel in ("pipe.toml", "prompts/a.md"):
            assert denied(lay.verdict(lay.base / f"{prefix}z" / rel, tool)), (tool, rel)


# ---- AC-06：壊れたリンク・輪のリンクは止まり、フックは落ちない -------------------------------------------------------


@pytest.mark.parametrize("target", ["missing-inside", "missing-outside"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac06_broken_link_denied(tmp_path, env, prefix, target):
    """D0088-AC-06: 壊れたリンク（先がまだ無い）は止まる。先が書ける場所の中（pipe の missing.toml）でも外でも止める（設計：一律止める。安全側）。"""
    lay = Lay(tmp_path, env, prefix)
    dest = lay.x / "missing.toml" if target == "missing-inside" else tmp_path / "ghost" / "none.md"
    link_or_skip(lay.x / "prompts" / "l.md", dest)
    for tool in TOOLS:
        assert denied(lay.verdict(lay.x / "prompts" / "l.md", tool)), (tool, target)


@pytest.mark.parametrize("shape", ["self", "pair"])
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac06_loop_link_denied(tmp_path, env, prefix, shape):
    """D0088-AC-06: 輪になったリンク（自分自身を指す・a と b が互いを指す）は止まり、例外を出さずに理由の文を返す。"""
    lay = Lay(tmp_path, env, prefix)
    prompts = lay.x / "prompts"
    if shape == "self":
        link_or_skip(prompts / "l.md", prompts / "l.md")
        target = prompts / "l.md"
    else:
        link_or_skip(prompts / "p.md", prompts / "q.md")
        link_or_skip(prompts / "q.md", prompts / "p.md")
        target = prompts / "p.md"
    for tool in TOOLS:
        assert denied(lay.verdict(target, tool)), (tool, shape)


@pytest.mark.parametrize("env", [None, "new"])
def test_d0088_ac06_main_does_not_raise(tmp_path, monkeypatch, env):
    """D0088-AC-06: 先をたどる関数（os.path.realpath）が例外を出しても、decide は理由の文を返し（落ちない）、main は終了コード 0 で deny の JSON を出す。
    たどれないときは止める側に倒す。ふつうの書ける場所への書き込みでも、たどれなければ止める。"""
    lay = Lay(tmp_path, env, "pipe-in-")
    target = lay.x / "pipe.toml"
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(target)}, "cwd": str(lay.root), "agent_type": BUILDER}

    def boom(*args, **kwargs):
        raise OSError("たどれない")

    with monkeypatch.context() as m:
        m.setattr(os.path, "realpath", boom)
        reason = hook().decide(payload, pipes_env=lay.pipes_env)
        assert denied(reason)
        for name in ENV_NAMES.values():
            m.delenv(name, raising=False)
        if env is not None:
            m.setenv(ENV_NAMES[env], str(lay.base))
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        m.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8"))
        m.setattr("sys.stdout", out)
        code = hook().main()
        out.flush()
        data = out.buffer.getvalue()
    assert code == 0
    assert json.loads(data.decode("utf-8"))["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---- AC-07：区切り・大文字小文字 -------------------------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="Windows では \\ が区切りなので別のテスト（junction は実機）")
@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac07_backslash_path_unchanged(tmp_path, env, prefix):
    """D0088-AC-07: Linux では \\ は名前の一部に見える。\\ を含む文字列の判断は今と同じ（止まる）で、たどる前もあとも変わらない（今のまま通る。守る）。"""
    lay = Lay(tmp_path, env, prefix)
    for tail in ("\\prompts\\a.md", "\\pipe.toml"):
        assert denied(lay.verdict(str(lay.x) + tail)), tail
    assert denied(lay.verdict(str(lay.x / "prompts") + "\\a.md"))
    assert denied(lay.verdict(str(lay.base) + "\\" + prefix + "x\\pipe.toml"))


@pytest.mark.skipif(os.name != "nt", reason="Windows でだけ：区切りと大文字小文字は normcase で比べる")
@pytest.mark.parametrize("env", ["new", "old"])
def test_d0088_ac07_case_only_difference_windows(tmp_path, env):
    """D0088-AC-07（Windows でだけ）: / 区切りの書き方と、置き場所の部分だけ大文字小文字の違う書き方でも、判断は変わらない。junction は実機で確かめる。"""
    lay = Lay(tmp_path, env, "pipe-in-")
    plain = lay.x / "pipe.toml"
    assert lay.verdict(str(plain).replace("\\", "/")) is None
    upper_base = str(lay.base).upper()
    assert lay.verdict(upper_base + "\\pipe-in-x\\pipe.toml") is None
    assert denied(lay.verdict(upper_base + "\\pipe-in-x\\run.py"))


# ---- AC-15：守りを狭めていない -----------------------------------------------------------------------------------


def _old_check_write(file_path, cwd, pipes_env) -> bool:
    """リンクをたどる前の判断の写し（止めるなら True）。書き込み先が書ける場所の文字の上の形かだけを見る。"""
    import re

    h = hook()
    if not isinstance(file_path, str) or not file_path.strip():
        return True
    if ".." in re.split(r"[\\/]", file_path):
        return True
    full = os.path.normpath(file_path if os.path.isabs(file_path) else os.path.join(cwd or os.getcwd(), file_path))
    parts = Path(full).parts
    for i, part in enumerate(parts[:-2]):
        if part == "pipes" and h.PIPE_DIR.fullmatch(parts[i + 1]) and h._in_pipe(parts[i + 2 :]):
            return False
    for env in h._env_list(pipes_env):
        base = os.path.normpath(os.path.abspath(os.path.expanduser(env)))
        if os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
            rest = Path(os.path.relpath(full, base)).parts
            if rest and h.PIPE_DIR.fullmatch(rest[0]) and h._in_pipe(rest[1:]):
                return False
    return True


@pytest.mark.parametrize("env,prefix", CASES, ids=CASE_IDS)
def test_d0088_ac15_plugin_never_widens(tmp_path, env, prefix):
    """D0088-AC-15: 今の判断（写し）が止める入力は、リンクが絡んでも、たどったあとも止まる（.. ・基準の外・フォルダ名の違い・pipe.toml 以外・
    入れ子・止まる所から書ける所を指すリンク）。リンクの無い入力は、止める・通すの結果が今と同じ（今のまま通る。守る）。"""
    lay = Lay(tmp_path, env, prefix)
    link_or_skip(lay.root / ".claude" / "l.md", lay.x / "pipe.toml")
    link_or_skip(lay.root / "src" / "l.md", lay.x / "prompts" / "a.md")
    link_or_skip(lay.base / "stray.md", lay.x / "README.md")
    plain = [
        str(lay.x / "prompts" / ".." / ".." / "src" / "app.py"),
        str(lay.x) + "/../" + prefix + "y/pipe.toml",
        str(lay.root / "src" / "app.py"),
        str(lay.root / ".claude" / "settings.json"),
        str(lay.base / "README.md"),
        str(lay.tmp / "x" / "pipe.toml"),
        str(lay.base / "pipe-x" / "pipe.toml"),
        str(lay.base / "in-x" / "pipe.toml"),
        str(lay.base / f"{prefix.upper()}x" / "pipe.toml"),
        str(lay.x / "run.py"),
        str(lay.x / "prompts" / "x" / "a.md"),
        str(lay.x / "prompts" / "a.txt"),
        "pipe.toml",
        "prompts/a.md",
        "",
        str(lay.x / "pipe.toml"),
        str(lay.x / "README.md"),
        str(lay.x / "prompts" / "a.md"),
        str(lay.x / "prompts" / "new.md"),
    ]
    linked = [str(lay.root / ".claude" / "l.md"), str(lay.root / "src" / "l.md"), str(lay.base / "stray.md")]
    for fp in plain:
        was_denied = _old_check_write(fp, str(lay.root), lay.pipes_env)
        assert denied(lay.verdict(fp)) == was_denied, f"リンクの無い入力で結果が変わった: {fp!r}（今まで止める={was_denied}）"
    for fp in linked:
        assert _old_check_write(fp, str(lay.root), lay.pipes_env), "前提：リンクの置き場所は今の判断で止まる"
        assert denied(lay.verdict(fp)), f"今まで止まっていた入力が、リンクで通るようになった: {fp}"


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Bash", {"command": "echo x > .claude/settings.json"}),
        ("Bash", {"command": "cp src/app.py .claude/settings.json"}),
        ("PowerShell", {"command": "Set-Content .claude/settings.json x"}),
        ("mcp__x__y", {}),
        ("Agent", {"prompt": "x"}),
        ("Task", {"prompt": "x"}),
        ("NotebookEdit", {"notebook_path": ".claude/a.ipynb"}),
    ],
)
def test_d0088_ac15_other_roads_still_denied(tmp_path, tool, tool_input):
    """D0088-AC-15: Bash の書き込み・PowerShell・MCP・サブエージェント・ノートブックの道は、リンクのある置き場所でも止まる（今のまま通る。守る）。"""
    lay = Lay(tmp_path, None, "pipe-in-")
    link_or_skip(lay.x / "prompts" / "link.md", lay.root / ".claude" / "settings.json")
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(lay.root), "agent_type": BUILDER}
    assert denied(hook().decide(payload, pipes_env=None)), tool
