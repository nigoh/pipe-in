"""D0079：段のエージェントが返事のファイル（実行のフォルダの reply.json）を書いて自分を承認できないこと。

書き込みの守り（guard.py の check_tool と、Bash の書き込みの判定）は変えず、engine/spec.py の protect() が、
どの段の書き込み範囲からも返事の場所を外す。開発フローの全段とパイプの段（access が何でも・writes が何でも・docs_dir が work_dir を含んでも）、
Bash・Write・Edit の書き込みの形、Agent・Task・PowerShell・MCP の道を、すり抜けの道としてパラメータ化して並べる。

「止まらない形」（フォルダごとの写し cp -r・rsync -a とスクリプトの実行 python x.py）は、今の守りの限界として
決定の記録と docs/guide/safety.md に書く。ここではテストにしない（xfail も使わない）。
SDK を呼ばない。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_pipe_flow import make_pipe, pipe_toml, stage_toml
from test_pipeline import make_cfg

from pipe_in.dev import specs as dev_specs
from pipe_in.engine.config import Config, load_config
from pipe_in.engine.guard import check_tool
from pipe_in.engine.spec import StageSpec, protect
from pipe_in.pipe import specs as pipe_specs

DEV_STAGES = ["requirements", "design", "red", "implement", "test"]
DEV_BASH_STAGES = ["red", "implement", "test"]  # Bash を許す段（ほかの段は Bash そのものが使えない）
DOMAINS = ["domain_dir なし", "domain_dir が work_dir を含む（docs）", "domain_dir が work_dir と同じ"]


def dev_cfg(tmp_path: Path, domain: str) -> Config:
    cfg = make_cfg(tmp_path)
    if domain == DOMAINS[1]:
        return replace(cfg, domain_dir=cfg.project_dir / "docs")
    if domain == DOMAINS[2]:
        return replace(cfg, domain_dir=cfg.work_dir)
    return cfg


def guard(cfg: Config, spec: StageSpec):
    def check(tool: str, **inp: Any) -> str | None:
        return check_tool(
            tool, inp, project_dir=cfg.project_dir, can_write=spec.can_write,
            allow_bash=spec.allow_bash, write_scope_hint=spec.write_scope_hint,
            allowed_tools=spec.allowed_tools,
        )  # fmt: skip

    return check


# 返事の場所 {d}/reply.json への、Write・Edit のパスの書き方（{d} は実行のフォルダ。プロジェクトからの相対）
PATH_FORMS = [
    "{d}/reply.json",
    "./{d}/reply.json",
    "{d}/../{name}/reply.json",
    "{d}/./reply.json",
    "{d}/REPLY.JSON",
    "{d}/Reply.Json",
    "{abs}/{d}/reply.json",
]

# Bash の書き込みの形（設計の「止まる形」。{d} は実行のフォルダ）
BASH_FORMS = [
    "echo x > {d}/reply.json",
    "echo x >> {d}/reply.json",
    "echo x > {d}/REPLY.JSON",
    "echo x > {d}/Reply.Json",
    "echo x > ./{d}/reply.json",
    "echo x > {d}/../{name}/reply.json",
    "cp src/a.json {d}/reply.json",
    "cp other/reply.json {d}/",
    "mv {d}/tmp.json {d}/reply.json",
    "mv {d}/other/reply.json {d}/",
    "echo x | tee {d}/reply.json",
    "touch {d}/reply.json",
    "ln -s ../../src/a.json {d}/reply.json",
    "dd if=src/a.json of={d}/reply.json",
    "install -m 644 src/a.json {d}/reply.json",
    "python -c \"open('{d}/reply.json','w').write('x')\"",
    "cd {d} && echo x > reply.json",
    "echo x > {d}/reply.json && echo y > {d}/other.md",
    "echo y > {d}/other.md; echo x > {d}/reply.json",
]


def fill(form: str, cfg: Config) -> str:
    d = cfg.rel(cfg.work_dir)
    return form.format(d=d, name=cfg.work_dir.name, abs=str(cfg.project_dir))


# ---- AC-26：開発フローの全段 --------------------------------------------------------------------------------


@pytest.mark.parametrize("form", PATH_FORMS)
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("stage", DEV_STAGES)
def test_開発フローの全段で返事の場所に書けない_Write_Edit(tmp_path: Path, stage: str, domain: str, tool: str, form: str):
    """D0079-AC-26: 開発フローの全段（要件定義・設計・テスト先行・実装・検証）の書き込み範囲に、返事の場所（実行のフォルダの reply.json）は入らない。
    Write・Edit・MultiEdit で、パスの書き方（./・..・大文字小文字違い・絶対パス）を変えて試して、すべて止まる。
    設計の段は domain_dir が work_dir を含む設定だと、今は書ける（この穴を protect() が塞ぐ）。"""
    cfg = dev_cfg(tmp_path, domain)
    check = guard(cfg, dev_specs.build_specs(cfg)[stage])
    assert check(tool, file_path=fill(form, cfg)) is not None, f"{stage}・{domain} で {tool} が返事の場所に書けてしまう"


@pytest.mark.parametrize("form", BASH_FORMS)
@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("stage", DEV_BASH_STAGES)
def test_開発フローの全段で返事の場所に書けない_Bash(tmp_path: Path, stage: str, domain: str, form: str):
    """D0079-AC-26: Bash を許す段（テスト先行・実装・検証）で、リダイレクト（>・>>）・cp・mv・tee・touch・ln -s・dd of=・install・
    python -c の open・cd を挟んだ形・./ や .. を挟んだ形で返事の場所に書こうとすると、止まる。"""
    cfg = dev_cfg(tmp_path, domain)
    check = guard(cfg, dev_specs.build_specs(cfg)[stage])
    assert check("Bash", command=fill(form, cfg)) is not None, f"{stage}・{domain} で Bash が返事の場所に書けてしまう: {fill(form, cfg)}"


def test_Bash_を許さない段は_Bash_そのものが使えない(tmp_path: Path):
    """D0079-AC-26: 要件定義・設計の段は Bash を使えない（Bash の形で返事の場所に書く道が、そもそも無い。今のまま通る。守る）。"""
    cfg = dev_cfg(tmp_path, DOMAINS[1])
    specs = dev_specs.build_specs(cfg)
    for stage in ("requirements", "design"):
        assert guard(cfg, specs[stage])("Bash", command=fill("echo x > {d}/reply.json", cfg)) is not None


@pytest.mark.parametrize(
    "stage,rel",
    [
        ("requirements", "{d}/01_requirements.md"),
        ("design", "{d}/02_design.md"),
        ("design", "docs/glossary.md"),
        ("design", "{d}/reply.json.bak"),
        ("red", "{d}/03_red_tests.md"),
        ("red", "tests/test_new.py"),
        ("implement", "{d}/04_implementation.md"),
        ("implement", "src/app.py"),
        ("test", "{d}/05_test_report.md"),
        ("test", "tests/test_new.py"),
    ],
)
def test_返事の場所以外の書ける範囲は変わらない(tmp_path: Path, stage: str, rel: str):
    """D0079-AC-26: reply.json.bak とほかの名前は止まらない：各段が今書けるもの（自分の文書・テスト・製品コード・設計の段のドメイン文書）は
    今までどおり書ける（domain_dir が work_dir を含む設定で。今のまま通る。守る）。"""
    cfg = dev_cfg(tmp_path, DOMAINS[1])
    check = guard(cfg, dev_specs.build_specs(cfg)[stage])
    assert check("Write", file_path=fill(rel, cfg)) is None


# ---- AC-27：パイプの段 -------------------------------------------------------------------------------------

ACCESSES = ["read", "docs", "tests", "code"]
WRITES = [None, ["docs/**"], ["**"], ["docs/pipeline/*"]]
FOLDERS = ["共有の実行のフォルダ（work_dir）", "パイプのフォルダ（work_dir/パイプ名）"]


def pipe_stage_spec(tmp_path: Path, access: str, writes: list[str] | None, folder: str, *, bash: bool) -> tuple[Config, StageSpec]:
    extra = "bash = true\n" if bash else ""
    if access == "docs":
        extra += 'docs_dir = "docs"\n'
    if writes is not None and access != "read":
        extra += "writes = [" + ", ".join(f'"{w}"' for w in writes) + "]\n"
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", extra, access=access)))
    own = folder == FOLDERS[1]
    cfg = load_config(tmp_path, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=own)
    return cfg, pipe_specs.build_pipe_specs(cfg, pipe)["a"]


@pytest.mark.parametrize("form", PATH_FORMS)
@pytest.mark.parametrize("folder", FOLDERS)
@pytest.mark.parametrize("writes", WRITES, ids=["writes なし", "writes docs/**", "writes **", "writes docs/pipeline/*"])
@pytest.mark.parametrize("access", ACCESSES)
def test_パイプの段は_access_と_writes_と_docs_dir_が何でも返事の場所に書けない_Write(tmp_path: Path, access: str, writes, folder: str, form: str):
    """D0079-AC-27: パイプの段は access が 読むだけ・docs・tests・code のどれでも、writes の glob が何であっても、
    docs_dir が work_dir を含んでいても（docs_dir = "docs"）、返事の場所には書けない。パイプの実行のフォルダ（work_dir/パイプ名）の場所も同じ。
    パスの書き方（./・..・大文字小文字違い・絶対パス）を変えても止まる。access = "docs" は今は書ける（この穴を protect() が塞ぐ）。"""
    cfg, spec = pipe_stage_spec(tmp_path, access, writes, folder, bash=False)
    check = guard(cfg, spec)
    assert check("Write", file_path=fill(form, cfg)) is not None, f"access={access}・{folder} で返事の場所に書けてしまう"


@pytest.mark.parametrize("form", BASH_FORMS)
@pytest.mark.parametrize("folder", FOLDERS)
@pytest.mark.parametrize("access", ["docs", "tests", "code"])
def test_パイプの段は_Bash_でも返事の場所に書けない(tmp_path: Path, access: str, folder: str, form: str):
    """D0079-AC-27: Bash を許したパイプの段（access = docs・tests・code。docs_dir = "docs"）が、リダイレクト・cp・mv・tee・touch・ln -s・
    dd of=・install・python -c の open・cd を挟んだ形で返事の場所に書こうとしても、止まる。"""
    cfg, spec = pipe_stage_spec(tmp_path, access, None, folder, bash=True)
    command = fill(form, cfg)
    assert guard(cfg, spec)("Bash", command=command) is not None, f"access={access}・{folder} で Bash が返事の場所に書けてしまう: {command}"


@pytest.mark.parametrize("folder", FOLDERS)
def test_パイプの段の返事の場所以外の書ける範囲は変わらない(tmp_path: Path, folder: str):
    """D0079-AC-27: access = "docs" の段が書けるもの（自分の成果物と docs_dir の下の文書。reply.json.bak を含む）は今までどおり書ける
    （今のまま通る。守る）。"""
    cfg, spec = pipe_stage_spec(tmp_path, "docs", None, folder, bash=False)
    check = guard(cfg, spec)
    d = cfg.rel(cfg.work_dir)
    for rel in (f"{d}/a.md", f"{d}/reply.json.bak", "docs/notes/図.md"):
        assert check("Write", file_path=rel) is None, rel


# ---- AC-28：Agent・Task・PowerShell・MCP の道 -----------------------------------------------------------------


def other_routes(path: str) -> list[tuple[str, dict[str, Any]]]:
    background_off = {"description": "書く", "prompt": f"{path} に書いて", "run_in_background": False}
    return [
        ("PowerShell", {"command": f"Set-Content {path} x"}),
        ("Agent", dict(background_off)),
        ("Task", dict(background_off)),
        ("mcp__fs__write_file", {"path": path, "content": "x"}),
        ("mcp__filesystem__edit_file", {"path": path}),
    ]


@pytest.mark.parametrize("stage", DEV_STAGES)
def test_Agent_Task_PowerShell_MCP_を許さない段ではその道から返事を書けない_開発フロー(tmp_path: Path, stage: str):
    """D0079-AC-28: 段が Agent・Task・PowerShell・MCP を許していないとき（開発フローの全段）、それらの道からも返事の場所を書けない
    （今の「許すものの一覧」で止まる。今のまま通る。守る）。"""
    cfg = dev_cfg(tmp_path, DOMAINS[1])
    spec = dev_specs.build_specs(cfg)[stage]
    check = guard(cfg, spec)
    for tool, inp in other_routes(fill("{d}/reply.json", cfg)):
        assert check(tool, **inp) is not None, f"{stage} で {tool} が通る"


@pytest.mark.parametrize("access", ACCESSES)
def test_Agent_Task_PowerShell_MCP_を許さない段ではその道から返事を書けない_パイプ(tmp_path: Path, access: str):
    """D0079-AC-28: パイプの段（agents・mcp を持たない）でも、Agent・Task・PowerShell・MCP の道から返事の場所を書けない
    （今のまま通る。守る）。"""
    cfg, spec = pipe_stage_spec(tmp_path, access, None, FOLDERS[1], bash=True)
    check = guard(cfg, spec)
    for tool, inp in other_routes(fill("{d}/reply.json", cfg)):
        assert check(tool, **inp) is not None, f"access={access} で {tool} が通る"


# ---- AC-29：書けないものに足すだけ ---------------------------------------------------------------------------


def permissive_spec(name: str = "s") -> StageSpec:
    return StageSpec(
        name=name, label="試し", allowed_tools=[], disallowed_tools=[], allow_bash=False,
        can_write=lambda rel: True, write_scope_hint="どこでも", system_append="",
    )  # fmt: skip


def test_protect_は返事の場所だけを書けないものに足す(tmp_path: Path):
    """D0079-AC-26: protect() は、何でも書ける段でも、返事の場所（work_dir の reply.json。大文字小文字違いを含む）だけを書けなくする。
    ほかのパス（reply.json.bak・別のフォルダの reply.json・work_dir の別のファイル）は書けるまま。protected_paths が無ければ hint も変えない。"""
    cfg = make_cfg(tmp_path)
    spec = permissive_spec()
    out = protect({"s": spec}, cfg)["s"]
    d = cfg.rel(cfg.work_dir)
    for blocked in (f"{d}/reply.json", f"{d}/REPLY.JSON", f"{d}/Reply.Json"):
        assert out.can_write(blocked) is False, blocked
    for allowed in (f"{d}/reply.json.bak", f"{d}/x/reply.json", f"{d}/state.json", "docs/reply.json", "src/reply.json", "reply.json"):
        assert out.can_write(allowed) is True, allowed
    assert out.write_scope_hint == "どこでも"


def test_protect_は_protected_paths_と一緒でも返事の場所を塞ぐ(tmp_path: Path):
    """D0079-AC-26: protected_paths を設定していても、返事の場所は書けない。protected_paths の守り（hint の付記）は今までどおり。"""
    cfg = replace(make_cfg(tmp_path), protected_paths=["tests/arch/*"])
    out = protect({"s": permissive_spec()}, cfg)["s"]
    d = cfg.rel(cfg.work_dir)
    assert out.can_write(f"{d}/reply.json") is False
    assert out.can_write("tests/arch/a.py") is False
    assert out.can_write("tests/test_a.py") is True
    assert "tests/arch/*" in out.write_scope_hint


SAMPLE_PATHS = [
    "src/app.py", "src/reply.json", "tests/test_a.py", "tests/arch/test_layers.py", "docs/glossary.md", "docs/notes/図.md",
    "docs/pipeline/00_input.md", "docs/pipeline/01_requirements.md", "docs/pipeline/02_design.md", "docs/pipeline/03_red_tests.md",
    "docs/pipeline/04_implementation.md", "docs/pipeline/05_test_report.md", "docs/pipeline/99_summary.md", "docs/pipeline/state.json",
    "docs/pipeline/reply.json", "docs/pipeline/REPLY.JSON", "docs/pipeline/reply.json.bak", "docs/pipeline/a.md",
    "docs/pipeline/p/a.md", "docs/pipeline/p/reply.json", "docs/pipeline/p/state.json", "reply.json", "pipes/pipe-in-p/pipe.toml", "README.md",
]  # fmt: skip


@pytest.mark.parametrize("protected", [[], ["tests/arch/*"]], ids=["protected_paths なし", "protected_paths あり"])
@pytest.mark.parametrize("domain", DOMAINS)
def test_返事の場所は書けないものに足すだけで書ける範囲は広がらない_開発フロー(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, domain: str, protected: list[str]):
    """D0079-AC-29: protect の前後で、見本のパス一式の can_write が「後 ⇒ 前」（書けるようになるパスが無い）。
    protected_paths が無ければ hint は変わらない。止める範囲は狭まらない（今のまま通る。守る）。"""
    cfg = replace(dev_cfg(tmp_path, domain), protected_paths=protected)
    after = dev_specs.build_specs(cfg)
    with monkeypatch.context() as mp:
        mp.setattr(dev_specs, "protect", lambda specs, c: specs)
        before = dev_specs.build_specs(cfg)
    for stage in DEV_STAGES:
        widened = [p for p in SAMPLE_PATHS if after[stage].can_write(p) and not before[stage].can_write(p)]
        assert widened == [], f"{stage}: 書けるようになったパス {widened}"
        if not protected:
            assert after[stage].write_scope_hint == before[stage].write_scope_hint


@pytest.mark.parametrize("access", ACCESSES)
def test_返事の場所は書けないものに足すだけで書ける範囲は広がらない_パイプ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str):
    """D0079-AC-29: パイプの段も同じ：protect の前後で、見本のパス一式の can_write が「後 ⇒ 前」。hint は変わらない
    （今のまま通る。守る）。"""
    cfg, after = pipe_stage_spec(tmp_path, access, None, FOLDERS[1], bash=True)
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", 'docs_dir = "docs"\nbash = true\n' if access == "docs" else "bash = true\n", access=access)))
    with monkeypatch.context() as mp:
        mp.setattr(pipe_specs, "protect", lambda specs, c: specs)
        before = pipe_specs.build_pipe_specs(cfg, pipe)["a"]
    widened = [p for p in SAMPLE_PATHS if after.can_write(p) and not before.can_write(p)]
    assert widened == [], f"書けるようになったパス {widened}"
    assert after.write_scope_hint == before.write_scope_hint
