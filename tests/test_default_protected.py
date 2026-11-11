"""D0084：SDK の道の守りを、会話の道と同じ範囲にそろえる。

`.claude/`・`.git/`・`.pipe-in/`・`pipeline.toml`（と前の版の置き場所）は、pipeline.toml の protected_paths を書かなくても、
開発フローの全段とパイプの access のどの種類の段でも書けない。守りの部品（guard.py・bashwrite.py）は変えず、
engine/spec.py の protect() が渡す can_write と説明の文だけを確かめる。

SDK は呼ばない（段の判断の関数 check_tool を直接呼ぶ）。ファイルは tmp_path の中だけに作り、リポジトリの実物には書かない。
前の版の置き場所の名前は、文字のまま書かず chat_support.OLD_NAME から作る。
"""

from __future__ import annotations

import fnmatch
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from chat_support import OLD_NAME, Run
from chat_support import pipe_toml as chat_pipe_toml
from chat_support import stage_toml as chat_stage_toml
from guard_matrix import COLUMNS, EXPECT
from test_pipe_flow import make_pipe, pipe_toml, stage_toml
from test_reply_guard import permissive_spec

from pipe_in.dev import specs as dev_specs
from pipe_in.engine import spec as spec_mod
from pipe_in.engine.bashwrite import BashState
from pipe_in.engine.config import Config, load_config
from pipe_in.engine.guard import check_tool
from pipe_in.engine.spec import StageSpec, protect
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as pipe_specs
from pipe_in.pipe.chat_record import chat_specs
from pipe_in.pipe.lint import lint_pipe

OLD_DIR = "." + OLD_NAME  # 前の版の置き場所
ROOT = Path(__file__).resolve().parents[1]

# 守る場所（書こうとする先）。.git は worktree でファイルになる .git 自身
PLACES = [".claude/settings.json", ".git/config", ".pipe-in/x", "pipeline.toml", f"{OLD_DIR}/x", "sub/.claude/x", ".git"]
WRITE_TOOLS = [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")]

TOML_VARIANTS = {"pipeline.toml なし": None, "protected_paths 空": "[pipeline]\nprotected_paths = []\n"}

DEV_KINDS = ["dev-requirements", "dev-design", "dev-red", "dev-implement", "dev-test"]
DEV_BASH = ["dev-red", "dev-implement", "dev-test"]
# パイプの段の種類 → (access, 段に足す行)。docs-in-* は docs_dir が守る場所と重なる定義（W7 の対象）
PIPE_KINDS: dict[str, tuple[str, str]] = {
    "pipe-read": ("read", ""),
    "pipe-docs": ("docs", 'docs_dir = "docs/out"\n'),
    "pipe-docs-in-claude": ("docs", 'docs_dir = ".claude"\n'),
    "pipe-docs-in-pipe-in": ("docs", 'docs_dir = ".pipe-in"\n'),
    "pipe-tests": ("tests", ""),
    "pipe-code": ("code", ""),
}
ALL_KINDS = DEV_KINDS + list(PIPE_KINDS)
BASH_KINDS = DEV_BASH + list(PIPE_KINDS)  # Bash を許す段（パイプの段は bash = true にする）


class Env:
    """1つの段の判断を呼ぶ小さな入れ物。Bash の覚え（cd）は同じ Env の呼び出しの間で続く。"""

    def __init__(self, project: Path, cfg: Config, spec: StageSpec, links: bool):
        self.project = project
        self.cfg = cfg
        self.spec = spec
        self.links = links
        self.state = BashState.new(project)

    def __call__(self, tool: str, **inp: Any) -> str | None:
        s = self.spec
        return check_tool(
            tool, inp, project_dir=self.cfg.project_dir, can_write=s.can_write, allow_bash=s.allow_bash,
            write_scope_hint=s.write_scope_hint, allowed_tools=s.allowed_tools, fetch_domains=s.fetch_domains, bash_state=self.state,
        )  # fmt: skip


def lay_out(project: Path) -> bool:
    """守る場所のフォルダと、そこを指すリンクを作る。リンクを作れない環境では False（そのケースだけ skip する）。"""
    for d in (".claude", ".git", ".pipe-in", OLD_DIR, "sub/.claude", "src", "tests", "docs"):
        (project / d).mkdir(parents=True, exist_ok=True)
    (project / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    try:
        (project / "src" / "link.json").symlink_to(project / ".claude" / "settings.json")
        (project / "src" / "dl").symlink_to(project / ".claude", target_is_directory=True)
        (project / "src" / "gl").symlink_to(project / ".git", target_is_directory=True)
        (project / "src" / "pl").symlink_to(project / ".pipe-in", target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


def build(tmp_path: Path, kind: str, variant: str = "pipeline.toml なし", toml: str | None = None) -> Env:
    project = tmp_path / "app"
    project.mkdir()
    links = lay_out(project)
    text = toml if toml is not None else TOML_VARIANTS[variant]
    if text is not None:
        (project / "pipeline.toml").write_text(text, encoding="utf-8")
    cfg = load_config(project, None, auto_approve=True)
    if kind.startswith("dev-"):
        return Env(project, cfg, dev_specs.build_specs(cfg)[kind[4:]], links)
    access, extra = PIPE_KINDS[kind]
    pipe = make_pipe(project, pipe_toml(stage_toml("a", extra + "bash = true\n", access=access)))
    cfg = cfg.for_pipe(pipe.name, own_work_dir=True)
    return Env(project, cfg, pipe_specs.build_pipe_specs(cfg, pipe)["a"], links)


def abs_of(env: Env, rel: str) -> str:
    return str(env.project / rel)


# ---- AC-01：Write・Edit・MultiEdit・NotebookEdit ------------------------------------------------------


@pytest.mark.parametrize("tool,key", WRITE_TOOLS)
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("variant", list(TOML_VARIANTS))
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0084_ac01_既定の場所はどの段でも書けない(tmp_path, kind, variant, place, tool, key):
    """D0084-AC-01: pipeline.toml が無い・protected_paths が空でも、開発フローの全段とパイプの access のどの種類の段でも、
    .claude/・.git/・.pipe-in/・pipeline.toml・前の版の置き場所・入れ子の .claude/ への Write・Edit・MultiEdit・NotebookEdit が止まる。"""
    env = build(tmp_path, kind, variant)
    for form, path in (("絶対パス", abs_of(env, place)), ("相対パス", place)):
        assert env(tool, **{key: path}) is not None, f"{kind}・{variant}・{tool}・{form} で {place} に書けてしまう"


# ---- AC-02：Bash の書き込み・すり抜けの形 -------------------------------------------------------------

BASH_FORMS = [
    "echo x > {t}",
    "echo x >> {t}",
    "echo x | tee {t}",
    "tee {t}",
    "cp src/a.py {t}",
    "mv src/a.py {t}",
    "sed -i s/a/b/ {t}",
    "touch {t}",
    "rm {t}",
    "truncate -s 0 {t}",
    "python -c \"open('{t}','w').write('x')\"",
    "node -e \"require('fs').writeFileSync('{t}','x')\"",
    "bash -c 'echo x > {t}'",
]


@pytest.mark.parametrize("form", BASH_FORMS)
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0084_ac02_bashの書き込みは既定の場所で止まる(tmp_path, kind, place, form):
    """D0084-AC-02: Bash の書き込み（> >> tee cp mv sed -i touch rm truncate python -c node -e bash -c）が、設定なしで既定の場所に対して止まる。"""
    env = build(tmp_path, kind)
    assert env.spec.allow_bash
    cmd = form.format(t=place)
    assert env("Bash", command=cmd) is not None, f"{kind}: {cmd} が通ってしまう"


SLIP_TARGETS = [
    "src/../{p}",
    "./{p}",
    "{abs}/{p}",
    "{abs}/src/../{p}",
    "docs/../src/../{p}",
]


@pytest.mark.parametrize("target", SLIP_TARGETS)
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0084_ac02_すり抜けの形でも止まる_dotdotと絶対パス(tmp_path, kind, place, target):
    """D0084-AC-02: .. を含むパス・./・絶対パスでも、Bash の書き込みが既定の場所で止まる。"""
    env = build(tmp_path, kind)
    t = target.format(p=place, abs=env.project)
    for cmd in (f"echo x > {t}", f"cp src/a.py {t}"):
        assert env("Bash", command=cmd) is not None, f"{kind}: {cmd}"


@pytest.mark.parametrize("target", SLIP_TARGETS)
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0084_ac02_すり抜けの形でも止まる_Writeの_dotdot(tmp_path, kind, place, target):
    """D0084-AC-02: Write のパスに .. や ./ を含めても止まる（絶対パス・相対パス）。"""
    env = build(tmp_path, kind)
    t = target.format(p=place, abs=env.project)
    assert env("Write", file_path=t, content="x") is not None, f"{kind}: {t}"


LINKS = [
    ("src/link.json", ".claude/settings.json を指すファイル"),
    ("src/dl/settings.json", ".claude/ を指すフォルダの下"),
    ("src/gl/config", ".git/ を指すフォルダの下"),
    ("src/pl/x", ".pipe-in/ を指すフォルダの下"),
]


@pytest.mark.parametrize("link,_why", LINKS)
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0084_ac02_リンクを経た道でも止まる(tmp_path, kind, link, _why):
    """D0084-AC-02: リンクを経た道（既定の場所を指すファイル・フォルダを通る書き込み）でも、Write と Bash が止まる。"""
    env = build(tmp_path, kind)
    if not env.links:
        pytest.skip("この環境ではリンクを作れない")
    assert env("Write", file_path=abs_of(env, link), content="x") is not None, f"{kind}: Write {link}"
    if env.spec.allow_bash:
        for cmd in (f"echo x > {link}", f"cp src/a.py {link}", f"touch {link}"):
            assert env("Bash", command=cmd) is not None, f"{kind}: {cmd}"


CD_CASES = [
    (["cd .claude", "echo x > settings.json"], ".claude"),
    (["cd .git", "echo x > config"], ".git"),
    (["cd .pipe-in", "touch x"], ".pipe-in"),
    ([f"cd {OLD_DIR}", "echo x > x"], "前の版の置き場所"),
    (["cd sub/.claude", "echo x > x"], "入れ子の .claude"),
    (["cd src", "echo x > ../.claude/settings.json"], "cd のあとの .."),
    (["cd .claude && echo x > settings.json"], "1つの命令の中"),
]


@pytest.mark.parametrize("cmds,_why", CD_CASES, ids=[c[1] for c in CD_CASES])
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0084_ac02_cdをまたぐ相対パスでも止まる(tmp_path, kind, cmds, _why):
    """D0084-AC-02: cd で既定の場所に入ったあとの相対パスの書き込みも止まる（別の呼び出しをまたいで BashState が覚える）。"""
    env = build(tmp_path, kind)
    results = [env("Bash", command=c) for c in cmds]
    assert results[-1] is not None, f"{kind}: {cmds} の最後が通ってしまう"


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("kind", BASH_KINDS)
def test_d0084_ac02_コマンド置換は道具ごと止まる(tmp_path, kind, place):
    """D0084-AC-02: $(…) を含む書き込み先は、これまでどおり読み取れず、道具ごと止まる（今のまま通る。守る）。"""
    env = build(tmp_path, kind)
    assert env("Bash", command=f"echo x > $(echo {place})") is not None


# ---- AC-03：比較の表 ----------------------------------------------------------------------------------

# 4か所に当たる書き込みの行（設計 7. の18行と、設計が「もう D」と書いたが実際は A だった bypass-link-pipe-prompt。
# リンクが .claude/settings.json に解決されるため）。sdk の列を「許す → 止める」に直した行
FOUR_PLACE_ROWS = [
    "write-dotclaude", "write-dotgit", "write-dotpipein", "write-pipelinetoml", "bypass-rel", "bypass-dotdot-abs", "bypass-dotdot-rel",
    "bypass-link-src", "bypass-edit", "bypass-multiedit", "bypass-notebookedit", "bypass-subagent-write", "bypass-bash-redirect",
    "bypass-bash-tee", "bypass-bash-cp", "bypass-bash-sed-i", "bypass-bash-python-c", "bypass-bash-bash-c", "bypass-link-pipe-prompt",
]  # fmt: skip


def test_d0084_ac03_sdkとsdk_protectedは4か所の行で同じ():
    """D0084-AC-03: 比較の表（tests/guard_matrix.py）で、sdk と sdk_protected の列が 4 か所の行で同じ、かつ止める（D）。
    PowerShell・MCP・Agent・Task・Skill の行は変わらない（表の照合は tests/test_guard_matrix.py が見る）。"""
    sdk, prot = COLUMNS.index("sdk"), COLUMNS.index("sdk_protected")
    for row in FOUR_PLACE_ROWS:
        assert EXPECT[row][sdk] == EXPECT[row][prot] == "D", row
    # 4か所に当たらない行は、sdk の列が変わっていない
    assert EXPECT["skill"][sdk] == "A" and EXPECT["agent-listed"][sdk] == "A" and EXPECT["task-listed"][sdk] == "A"
    assert EXPECT["bypass-powershell"][sdk] == "D" and EXPECT["bypass-mcp"][sdk] == "D" and EXPECT["bypass-bash-subst"][sdk] == "D"
    assert EXPECT["write-code-ok"][sdk] == "A" and EXPECT["bash-git-add"][sdk] == "A" and EXPECT["bash-git-push"][sdk] == "D"


# ---- AC-04：会話の道は減らない ------------------------------------------------------------------------

OLD_EXTRA = [".claude/settings.json", "sub/.claude/x", ".git/config", ".pipe-in/x", "pipeline.toml", ".pipe-in/pipes/pipe-in-hp/pipe.toml"]


def chat_env(tmp_path: Path, access: str) -> Env:
    project = tmp_path / "app"
    project.mkdir()
    lay_out(project)
    r = Run(project)
    r.make(chat_pipe_toml(chat_stage_toml("s", access=access, output="out.md", docs_dir="docs/out" if access == "docs" else None, extra="bash = true\n")))
    cfg = load_config(r.project).for_pipe(r.pipe, own_work_dir=True)
    spec = chat_specs(cfg, pd.load_pipe(r.pipe_dir))["s"]
    return Env(r.project, cfg, spec, True)


@pytest.mark.parametrize("access", ["read", "docs", "tests", "code"])
@pytest.mark.parametrize("place", OLD_EXTRA)
def test_d0084_ac04_会話の道の旧一覧は今も止まる(tmp_path, access, place):
    """D0084-AC-04: 会話の道（chat_specs）で今まで止まっていた形（旧 EXTRA_PROTECTED の5つとパイプのフォルダ）は、今も止まる。
    chat_specs が足すのをやめて protect() が足す形になっても、止まる場所は減らない。"""
    env = chat_env(tmp_path, access)
    for tool, key in WRITE_TOOLS:
        assert env(tool, **{key: abs_of(env, place)}) is not None, f"{access}・{tool}・{place}"
    assert env("Bash", command=f"echo x > {place}") is not None


@pytest.mark.parametrize("access", ["read", "docs", "tests", "code"])
def test_d0084_ac04_会話の道でも前の版の置き場所は止まり説明は1回だけ(tmp_path, access):
    """D0084-AC-04（要件の「動きが変わる場面」6）: 前の版の置き場所は会話の道でも新しく止まる。説明の文に既定の場所が二重に出ず、
    会話の道の説明（記録・.claude/・パイプのフォルダは書けません）は残る。"""
    env = chat_env(tmp_path, access)
    assert env("Write", file_path=abs_of(env, f"{OLD_DIR}/x"), content="x") is not None
    hint = env.spec.write_scope_hint
    assert hint.count("既定で守る場所") == 1, hint
    assert "（記録・.claude/・パイプのフォルダは書けません）" in hint


# ---- AC-05：利用者の protected_paths ---------------------------------------------------------------


def test_d0084_ac05_利用者のprotected_pathsも止まり説明は1回だけ(tmp_path):
    """D0084-AC-05: 利用者が protected_paths に書いた場所は、これまでどおり止まる。既定と同じ文字列を重ねて書いても、
    説明の文が変わらない（同じものが2回出ない）。別の場所を書けば、その場所が説明に1回出る。"""
    cfg = replace(load_config(tmp_path, None), protected_paths=[])
    base = protect({"s": permissive_spec()}, cfg)["s"]
    dup = protect({"s": permissive_spec()}, replace(cfg, protected_paths=[".claude/*", "pipeline.toml"]))["s"]
    assert dup.write_scope_hint == base.write_scope_hint, "既定と同じ文字列を足しても説明は変わらない"
    assert dup.can_write(".claude/settings.json") is False and dup.can_write("src/a.py") is True
    extra = protect({"s": permissive_spec()}, replace(cfg, protected_paths=["tests/arch/*", ".claude/*"]))["s"]
    assert extra.can_write("tests/arch/a.py") is False and extra.can_write(".claude/x") is False
    assert extra.can_write("tests/test_a.py") is True and extra.can_write("src/a.py") is True
    assert extra.write_scope_hint.count("tests/arch/*") == 1 and extra.write_scope_hint.count("既定で守る場所") == 1, extra.write_scope_hint
    assert extra.write_scope_hint.startswith("どこでも")


@pytest.mark.parametrize("kind", ["dev-implement", "pipe-code"])
def test_d0084_ac05_pipeline_tomlに書いた場所は段でも止まる(tmp_path, kind):
    """D0084-AC-05: pipeline.toml の protected_paths に書いた場所は、開発フローの段でもパイプの段でも止まる（既定の場所と一緒に）。"""
    env = build(tmp_path, kind, toml='[pipeline]\nprotected_paths = ["tests/arch/*", ".claude/*"]\n')
    assert env.cfg.protected_paths == ["tests/arch/*", ".claude/*"]
    assert env("Bash", command="echo x > tests/arch/a.py") is not None
    assert env("Write", file_path=abs_of(env, ".git/config"), content="x") is not None
    assert env("Write", file_path=abs_of(env, "src/app.py"), content="x") is None


# ---- AC-06：許す側 ------------------------------------------------------------------------------------

CODE_OK = ["src/app.py", ".github/workflows/ci.yml", ".github/x", ".gitignore", ".gitattributes", "docs/guide/x.md", "video/a.js", "README.md"]
CODE_KINDS = ["dev-implement", "pipe-code"]


@pytest.mark.parametrize("variant", list(TOML_VARIANTS))
@pytest.mark.parametrize("rel", CODE_OK)
@pytest.mark.parametrize("kind", CODE_KINDS)
def test_d0084_ac06_ふつうの書き込みは通る(tmp_path, kind, rel, variant):
    """D0084-AC-06: ふつうのコード・成果物のほかの文書・.github/・.gitignore・.gitattributes・docs/・video/ への書き込みは今のまま通る
    （.git/* の守りが .github/x や .gitignore を巻き込まない）。今のまま通る。守る。"""
    env = build(tmp_path, kind, variant)
    assert env("Write", file_path=abs_of(env, rel), content="x") is None, rel
    assert env("Edit", file_path=rel, old_string="a", new_string="b") is None, rel
    assert env("Bash", command=f"echo x > {rel}") is None, rel
    assert env("Bash", command=f"touch {rel}") is None, rel


@pytest.mark.parametrize(
    "kind,rel",
    [("dev-red", "tests/test_a.py"), ("dev-test", "tests/test_a.py"), ("pipe-tests", "tests/test_a.py"), ("pipe-docs", "docs/out/a.md"),
     ("pipe-docs", "docs/out/sub/b.md")],
)  # fmt: skip
def test_d0084_ac06_テストと文書の段の書ける範囲は変わらない(tmp_path, kind, rel):
    """D0084-AC-06: テストを書く段のテストファイル、docs の段の docs_dir の下は、今のまま通る（守る）。"""
    env = build(tmp_path, kind)
    assert env("Write", file_path=abs_of(env, rel), content="x") is None


# ---- AC-07：git の通常の操作 -------------------------------------------------------------------------


@pytest.mark.parametrize("cmd", ["git add src/app.py", "git add src/app.py tests/test_a.py", "git commit -m x", "git status", "git diff", "git diff --cached"])
@pytest.mark.parametrize("kind", ["dev-implement", "dev-red", "pipe-code"])
def test_d0084_ac07_git_add_commit_status_diffは通る(tmp_path, kind, cmd):
    """D0084-AC-07: Bash を許した段の git add・commit・status・diff は、.git/* を守っても今のまま通る（Bash の書き込みとして止まらない）。"""
    env = build(tmp_path, kind)
    assert env("Bash", command=cmd) is None, cmd


@pytest.mark.parametrize("cmd", ["git push origin main", "git push", "git checkout main", "git reset --hard"])
@pytest.mark.parametrize("kind", ["dev-implement", "pipe-code"])
def test_d0084_ac07_git_pushとcheckoutは別の規則で止まる(tmp_path, kind, cmd):
    """D0084-AC-07: git push・checkout などは、これまでどおり別の規則で止まる（今のまま通る。守る）。"""
    env = build(tmp_path, kind)
    assert env("Bash", command=cmd) is not None, cmd


# ---- AC-08：ひな形と見本 -----------------------------------------------------------------------------

TEMPLATE_NAMES = ["dev", "diagrams", "spec-qa", "spec-review", "review-quorum"]
EXAMPLE_PIPES = [(n, ROOT / "examples" / n / "pipes" / f"pipe-in-{n}") for n in ("diagrams", "spec-qa", "research", "video")]
FILL = {"name": "x", "test_command": "pytest", "source_dirs": "プロジェクト全体", "diagrams_dir": "docs/diagrams", "docs_hint": "プロジェクトの中"}
ROOTS = (".claude", ".git", ".pipe-in", OLD_DIR, "pipeline.toml")


def render(template: Path, dest: Path) -> Path:
    from pipe_in_generator.render import render_template

    (dest / "prompts").mkdir(parents=True)
    for src in sorted(template.glob("prompts/*.md")):
        (dest / "prompts" / src.name).write_text(render_template(src.read_text(encoding="utf-8"), FILL, toml=False), encoding="utf-8")
    (dest / "pipe.toml").write_text(render_template((template / "pipe.toml").read_text(encoding="utf-8"), FILL, toml=True), encoding="utf-8")
    return dest


def under_roots(path: str) -> bool:
    p = path.lstrip("./")
    return any(p == r or p.startswith(r + "/") for r in ROOTS) or "/.claude/" in "/" + p


def assert_pipe_outside(pipe_dir: Path, project: Path) -> None:
    pipe = pd.load_pipe(pipe_dir)
    assert pd.check_pipe(pipe, project) == []
    assert lint_pipe(pipe) == [], "警告（W7 を含む）が出ない"
    if pipe.kind == "dev":
        return
    cfg = load_config(project, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)
    work = cfg.rel(cfg.work_dir)
    specs = pipe_specs.build_pipe_specs(cfg, pipe)
    for s in pipe.stages:
        assert not under_roots(s.output), (s.name, s.output)
        assert specs[s.name].can_write(f"{work}/{s.output}") is True, f"{s.name}: 成果物 {work}/{s.output} が書けない"
        if s.access == "docs":
            assert not under_roots(s.docs_dir or ""), (s.name, s.docs_dir)
            if not s.writes:  # writes があるときは、docs_dir の中をさらに絞るので下で見る
                assert specs[s.name].can_write(f"{s.docs_dir}/x.md") is True, f"{s.name}: docs_dir の下が書けない"
        for g in s.writes:
            if s.access == "docs":
                assert specs[s.name].can_write(g.replace("*", "x")) is True, f"{s.name}: writes「{g}」が書けない"
        for g in s.writes:
            assert not under_roots(g.replace("*", "x")), (s.name, g)


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_d0084_ac08_ひな形は守る場所の外(tmp_path, name):
    """D0084-AC-08: ひな形（generator/templates/）5つは、定義を変えずに check_pipe が通り、警告が出ず、段の書き込み（成果物・docs_dir）が通る。
    docs_dir・writes・output が既定の守る場所の外にある。今のまま通る。守る。"""
    project = tmp_path / "app"
    project.mkdir()
    pipe_dir = render(ROOT / "generator" / "templates" / name, tmp_path / "pipe-in-x")
    assert_pipe_outside(pipe_dir, project)


@pytest.mark.parametrize("name,pipe_dir", EXAMPLE_PIPES, ids=[n for n, _ in EXAMPLE_PIPES])
def test_d0084_ac08_見本のパイプは守る場所の外(tmp_path, name, pipe_dir):
    """D0084-AC-08: 見本（examples/）のパイプは、定義を変えずに check_pipe が通り、警告が出ず、段の書き込みが通る。今のまま通る。守る。"""
    project = tmp_path / "app"
    project.mkdir()
    assert_pipe_outside(pipe_dir, project)


def test_d0084_ac08_見本のtruncateは設定が読め開発フローの書き込みが通る(tmp_path):
    """D0084-AC-08: 見本 examples/truncate の pipeline.toml が読め、work_dir が守る場所と重ならず、実装の段の製品コードとテストの段のテストが書ける。
    今のまま通る。守る。"""
    cfg = load_config(ROOT / "examples" / "truncate", None, auto_approve=True)
    assert spec_mod.work_dir_conflict(cfg) is None
    specs = dev_specs.build_specs(cfg)
    assert specs["implement"].can_write("src/textutil.py") is True
    assert specs["red"].can_write("tests/test_textutil.py") is True
    assert specs["implement"].can_write(".claude/settings.json") is False


# ---- AC-09：成果物と返事の場所 ----------------------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0084_ac09_成果物と返事の扱いは変わらない(tmp_path, kind):
    """D0084-AC-09: 段の成果物（work_dir の下）は書け、返事の場所（work_dir の reply.json）は書けない。今のまま通る。守る。"""
    env = build(tmp_path, kind)
    work = env.cfg.rel(env.cfg.work_dir)
    output = env.spec.output
    assert output
    assert env("Write", file_path=abs_of(env, f"{work}/{output}"), content="x") is None
    assert env("Write", file_path=abs_of(env, f"{work}/reply.json"), content="x") is not None


# ---- AC-10：古い形 -----------------------------------------------------------------------------------


def test_d0084_ac10_protected_pathsだけの古い設定を読める(tmp_path):
    """D0084-AC-10: protected_paths だけを書いた今までの pipeline.toml はそのまま読め、Config の項目は増えず、protect() で既定の場所が足される。"""
    (tmp_path / "pipeline.toml").write_text('[pipeline]\nprotected_paths = ["tests/arch/*"]\n', encoding="utf-8")
    cfg = load_config(tmp_path, None)
    assert cfg.protected_paths == ["tests/arch/*"], "読み方は変えない（既定は読む側で足さない）"
    out = protect({"s": permissive_spec()}, cfg)["s"]
    assert out.can_write("tests/arch/a.py") is False
    for place in PLACES:
        assert out.can_write(place) is False, place
    assert out.can_write("src/app.py") is True


def test_d0084_ac10_pipeline_tomlが無くても守る(tmp_path):
    """D0084-AC-10: pipeline.toml が無くても（protected_paths の既定は空のまま）、既定の場所を守る。"""
    cfg = load_config(tmp_path, None)
    assert cfg.protected_paths == []
    out = protect({"s": permissive_spec()}, cfg)["s"]
    for place in PLACES:
        assert out.can_write(place) is False, place
    for ok in ("src/app.py", ".github/x", ".gitignore", ".gitattributes", "docs/a.md", "tests/test_a.py"):
        assert out.can_write(ok) is True, ok


def test_d0084_ac10_既定の定数は決めた7つ():
    """D0084-AC-10・FR-01（D0087 で7つから8つ）: 既定で守る場所の定数は、.claude/*・*/.claude/*・.git/*・.git・.pipe-in/*・pipeline.toml・.mcp.json（D0087）・前の版の置き場所の8つ（順は問わない）。"""
    assert isinstance(spec_mod.DEFAULT_PROTECTED_PATHS, tuple)
    want = [".claude/*", "*/.claude/*", ".git/*", ".git", ".pipe-in/*", "pipeline.toml", ".mcp.json", f"{OLD_DIR}/*"]
    assert sorted(spec_mod.DEFAULT_PROTECTED_PATHS) == sorted(want)


def test_d0084_ac10_前の版の置き場所のパイプを読んで流せる(tmp_path, monkeypatch):
    """D0084-AC-10: 前の版の置き場所のパイプを読んで流す動き（migrate.md）は変わらない：パイプが見つかり、段の成果物は書け、
    前の版の置き場所そのものへの書き込みは止まる。"""
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    project = tmp_path / "app"
    folder = project / OLD_DIR / "pipes" / f"{OLD_NAME}-x"
    folder.mkdir(parents=True)
    (folder / "pipe.toml").write_text(pipe_toml(stage_toml("a", "", access="code")), encoding="utf-8")
    found = pd.find_pipe("x", None, project=project)
    assert found is not None and found.resolve() == folder.resolve()
    pipe = pd.load_pipe(found)
    cfg = load_config(project, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)
    spec = pipe_specs.build_pipe_specs(cfg, pipe)["a"]
    assert spec.can_write(f"{cfg.rel(cfg.work_dir)}/a.md") is True
    assert spec.can_write(f"{OLD_DIR}/pipes/{OLD_NAME}-y/pipe.toml") is False, "読んでいるパイプのフォルダ以外の前の版の置き場所も書けない"
    assert spec.can_write(f"{OLD_DIR}/x") is False
    assert spec.can_write("src/app.py") is True


# ---- AC-11：止めた理由の文 --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_d0084_ac11_止めた理由に既定で守る場所が出る(tmp_path, kind):
    """D0084-AC-11: .claude/settings.json に書こうとして止まったとき、止めた理由の文に、書ける範囲の説明として「既定で守る場所」が出る。"""
    env = build(tmp_path, kind)
    reason = env("Write", file_path=abs_of(env, ".claude/settings.json"), content="{}")
    assert reason, "止まるはず"
    assert "既定で守る場所" in reason, reason


def test_d0084_ac11_説明の文は全段に1回ずつ付く(tmp_path):
    """D0084-AC-11・FR-04: 書ける範囲の説明（write_scope_hint）に、既定で守る場所が全段に1回だけ付き、元の文で始まる。"""
    cfg = load_config(tmp_path, None)
    out = protect({"s": permissive_spec(), "t": permissive_spec("t")}, cfg)
    for spec in out.values():
        assert spec.write_scope_hint.startswith("どこでも")
        assert spec.write_scope_hint.count("既定で守る場所") == 1
        for g in spec_mod.DEFAULT_PROTECTED_PATHS:
            assert g in spec.write_scope_hint


# ---- AC-12：pipe-in-gen check の警告（W7） ---------------------------------------------------------


def pipe_with(tmp_path: Path, access: str, extra: str) -> pd.PipeDef:
    d = tmp_path / "pipes" / "pipe-in-w"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(chat_pipe_toml(chat_stage_toml("a", access=access, output="a.md", extra=extra)), encoding="utf-8")
    return pd.load_pipe(d)


def w7(warnings: list[str]) -> list[str]:
    return [w for w in warnings if "既定で守る場所" in w]


OVERLAP = [
    ("docs", 'docs_dir = ".claude"\n'),
    ("docs", 'docs_dir = ".pipe-in/x"\n'),
    ("docs", 'docs_dir = ".git"\n'),
    ("docs", 'docs_dir = "."\n'),
    ("code", 'writes = [".pipe-in/x/*"]\n'),
    ("code", 'writes = [".claude/*"]\n'),
    ("code", 'writes = [".git/hooks/*"]\n'),
    ("code", 'writes = ["pipeline.toml"]\n'),
    ("code", f'writes = ["{OLD_DIR}/*"]\n'),
]
NO_OVERLAP = [
    ("docs", 'docs_dir = "docs/out"\n'),
    ("docs", 'docs_dir = ".github"\n'),
    ("docs", 'docs_dir = "docs"\n'),
    ("code", 'writes = ["src/*"]\n'),
    ("code", 'writes = ["*.md"]\n'),
    ("code", 'writes = [".github/*", ".gitignore"]\n'),
    ("code", 'writes = ["docs/**"]\n'),
    ("code", ""),
]


@pytest.mark.parametrize("access,extra", OVERLAP, ids=[e.strip() for _, e in OVERLAP])
def test_d0084_ac12_重なると警告が出る(tmp_path, access, extra):
    """D0084-AC-12: パイプの docs_dir・writes が既定で守る場所と重なるとき、lint_pipe が警告（W7）を出す。段の番号・名前と、直し方が文に出る。"""
    found = w7(lint_pipe(pipe_with(tmp_path, access, extra)))
    assert len(found) == 1, found
    assert "段 1" in found[0] and "（a）" in found[0]


@pytest.mark.parametrize("access,extra", NO_OVERLAP, ids=[e.strip() or "なし" for _, e in NO_OVERLAP])
def test_d0084_ac12_重ならなければ出ない(tmp_path, access, extra):
    """D0084-AC-12: 重ならない docs_dir・writes（.github/・.gitignore・先頭がワイルドカードの glob を含む）には警告が出ない。今のまま通る。守る。"""
    assert w7(lint_pipe(pipe_with(tmp_path, access, extra))) == []


def test_d0084_ac12_警告でも終了コードは変わらない(tmp_path, capsys):
    """D0084-AC-12: 重なっていても pipe-in-gen check の終了コードは 0 のまま（誤りにしない）。出力に警告が出る。"""
    from pipe_in_generator.cli import main as gen_main

    pipe_with(tmp_path, "docs", 'docs_dir = ".claude"\n')
    code = gen_main(["check", "w", "--pipes-dir", str(tmp_path / "pipes"), "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "既定で守る場所" in out, out


def test_d0084_ac12_重ならないパイプの検査には出ない(tmp_path, capsys):
    """D0084-AC-12: 重ならないパイプでは pipe-in-gen check の出力に警告が出ない（今のまま通る。守る）。"""
    from pipe_in_generator.cli import main as gen_main

    pipe_with(tmp_path, "docs", 'docs_dir = "docs/out"\n')
    code = gen_main(["check", "w", "--pipes-dir", str(tmp_path / "pipes"), "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "既定で守る場所" not in out, out


# ---- AC-13：work_dir の検査 -------------------------------------------------------------------------

CONFLICT = [".pipe-in/runs", ".", ".claude/x", ".git", ".pipe-in", "pipeline.toml", f"{OLD_DIR}/runs"]
FINE = ["docs/pipeline", "build/records", "out", ".github/records"]


def cfg_with_work_dir(project: Path, work_dir: str) -> Config:
    project.mkdir(parents=True, exist_ok=True)
    (project / "pipeline.toml").write_text(f'[pipeline]\nwork_dir = "{work_dir}"\n', encoding="utf-8")
    return load_config(project, None, auto_approve=True)


@pytest.mark.parametrize("work_dir", CONFLICT)
def test_d0084_ac13_work_dir_conflictは重なりを文で返す(tmp_path, work_dir):
    """D0084-AC-13: work_dir が守る場所の中か、守る場所を含む（. を含む）とき、work_dir_conflict が直し方つきの文を返す。"""
    msg = spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", work_dir))
    assert msg, work_dir
    assert "work_dir" in msg and "docs/pipeline" in msg, msg


@pytest.mark.parametrize("work_dir", FINE)
def test_d0084_ac13_ふつうのwork_dirは止まらない(tmp_path, work_dir):
    """D0084-AC-13: 既定の docs/pipeline と、これまで動いていた work_dir（build/records など）では None を返す（影響を受けない）。"""
    assert spec_mod.work_dir_conflict(cfg_with_work_dir(tmp_path / "app", work_dir)) is None


class Started(Exception):
    """段を流す段階まで進んだ（止まらなかった）ときに投げる偽物の目印。"""


def cli_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, work_dir: str | None) -> Path:
    from pipe_in import cli

    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))

    def no_run(*a: Any, **k: Any) -> Any:
        raise Started

    monkeypatch.setattr(cli, "pipeline_for", no_run)
    project = tmp_path / "app"
    project.mkdir()
    if work_dir is not None:
        (project / "pipeline.toml").write_text(f'[pipeline]\nwork_dir = "{work_dir}"\n', encoding="utf-8")
    d = project / ".pipe-in" / "pipes" / "pipe-in-p"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(chat_pipe_toml(chat_stage_toml("s", access="read", output="out.md")), encoding="utf-8")
    return project


ENTRANCES = {
    "pipe-in --pipe": ["--pipe", "p", "--text", "x", "--yes"],
    "pipe-in（開発フロー）": ["--text", "x", "--yes"],
    "--review": ["--pipe", "p", "--review", "approve"],
    "--from": ["--pipe", "p", "--from", "s"],
}


@pytest.mark.parametrize("entrance", list(ENTRANCES))
@pytest.mark.parametrize("work_dir", [".pipe-in/runs", ".", ".claude/x"])
def test_d0084_ac13_work_dirが守る場所と重なると流す前に止まる_pipe_in(tmp_path, monkeypatch, work_dir, entrance):
    """D0084-AC-13: work_dir が守る場所と重なると、pipe-in は段を流す前に止まり（流す入口に着かない）、止める文に直し方が出る。
    pipe-in・開発フロー・--review・--from のどの入口でも。"""
    from pipe_in import cli

    project = cli_project(tmp_path, monkeypatch, work_dir)
    try:
        cli.main(["--project", str(project), *ENTRANCES[entrance]])
    except Started:
        pytest.fail("段を流す入口まで進んでしまった（始める前に止まっていない）")
    except SystemExit as e:
        msg = str(e.code)
        assert "work_dir" in msg and "docs/pipeline" in msg, msg
        assert e.code not in (0, None)
    else:
        pytest.fail("止まらなかった")


@pytest.mark.parametrize("entrance", list(ENTRANCES))
@pytest.mark.parametrize("work_dir", [None, "docs/pipeline", "build/records"])
def test_d0084_ac13_ふつうのwork_dirでは流す入口まで進む_pipe_in(tmp_path, monkeypatch, work_dir, entrance):
    """D0084-AC-13: 既定の docs/pipeline と、これまで動いていた work_dir では、検査に止められず流す入口（pipeline_for）まで進む。今のまま通る。守る。"""
    from pipe_in import cli

    project = cli_project(tmp_path, monkeypatch, work_dir)
    with pytest.raises(Started):
        cli.main(["--project", str(project), *ENTRANCES[entrance]])


@pytest.mark.parametrize("work_dir", [".pipe-in/runs", ".", ".claude/x"])
def test_d0084_ac13_work_dirが守る場所と重なると流す前に止まる_chat_start(tmp_path, work_dir):
    """D0084-AC-13: 会話の道の chat start も、work_dir が守る場所と重なると始める前に断り（ok が false・終了コードは 0 でない）、記録を作らない。文に直し方が出る。"""
    project = tmp_path / "app"
    project.mkdir()
    r = Run(project)
    r.make(chat_pipe_toml(chat_stage_toml("s", access="read", output="out.md")))
    (project / "pipeline.toml").write_text(f'[pipeline]\nwork_dir = "{work_dir}"\n', encoding="utf-8")
    out = r.start()
    assert out["ok"] is False and r.code != 0, out
    assert "work_dir" in out["message"] and "docs/pipeline" in out["message"], out
    assert not (project / ".pipe-in" / "runs").exists()
    assert not list(project.rglob("state.json"))


def test_d0084_ac13_ふつうのwork_dirでは_chat_startが始められる(tmp_path):
    """D0084-AC-13: 既定の work_dir では chat start がこれまでどおり始められる（今のまま通る。守る）。"""
    r = Run(tmp_path / "app")
    r.project.mkdir()
    r.make(chat_pipe_toml(chat_stage_toml("s", access="read", output="out.md")))
    assert r.start()["ok"] is True


# ---- 補助の自己検査 -----------------------------------------------------------------------------------


def test_既定の定数は守る場所だけに当たり_github_gitignoreには当たらない():
    """D0084-AC-06（定数そのものの確認）: 定数の glob が .github/x・.gitignore・.gitattributes・docs/ に当たらず、守る場所には当たる。
    定数が空の間は『当たる』側が落ちる（赤）。"""
    globs = spec_mod.DEFAULT_PROTECTED_PATHS
    for ok in (".github/x", ".gitignore", ".gitattributes", "docs/a.md", "src/app.py", "sub/pipeline.toml"):
        assert not any(fnmatch.fnmatch(ok, g) for g in globs), ok
    for place in PLACES:
        assert any(fnmatch.fnmatch(place, g) for g in globs), place
