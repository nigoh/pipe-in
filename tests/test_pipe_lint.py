"""パイプの警告（pipe_in.pipe.lint の lint_pipe）：D0038。SDK は呼ばない。

定義は tmp_path に pipe.toml と prompts/ を書いて load_pipe で作る（リポジトリの実物には書かない）。
新しい部品（lint）はテストの中で読み込む（落ちる理由が「まだ無い」だと読めるように）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ["dev", "diagrams", "spec-qa"]


def lint():
    from pipe_in.pipe import lint as lint_mod

    return lint_mod.lint_pipe


def stage_toml(
    name: str,
    *,
    access: str = "read",
    bash: bool = False,
    prompt: str = "調べて、結果を成果物に書いてください。",
    command: str | None = None,
    verdict: bool = False,
    on_fail: str | None = None,
    has_check: bool = False,
) -> str:
    lines = [
        "[[stages]]",
        f'name = "{name}"',
        f'label = "{name} の段"',
        f'output = "{name}.md"',
        f'access = "{access}"',
        f"prompt = {json.dumps(prompt, ensure_ascii=False)}",
    ]
    if access == "docs":
        lines.append('docs_dir = "work"')
    if bash:
        lines.append("bash = true")
    if has_check or command or verdict or on_fail:
        lines.append("[stages.check]")
        if verdict:
            lines.append("verdict = true")
        if command:
            lines.append(f"command = {json.dumps(command)}")
        if on_fail:
            lines.append(f'on_fail = "{on_fail}"')
    return "\n".join(lines) + "\n"


def make_pipe(tmp_path: Path, stages: list[str], *, folder: str = "pipe-in-lt", base: Path | None = None):
    from pipe_in.pipe.definition import load_pipe

    d = (base or tmp_path) / folder
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text('[pipe]\nkind = "linear"\nlabel = "x"\n\n' + "\n".join(stages), encoding="utf-8")
    return load_pipe(d)


def project(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir(exist_ok=True)
    return p


# ---- AC-01・AC-02: W1 ------------------------------------------------------------------

WRITE_WORDS = ["書き出", "書き込", "保存", "取り出", "置き場所", "下書き", "試作", "出力先", "mkdir", "ファイルを作", "描"]


@pytest.mark.parametrize("word", WRITE_WORDS)
def test_w1_read_bash_with_write_words(tmp_path, word):
    """D0038-AC-01: access = "read" で bash = true の段の指示文に、書き込みを思わせる言葉があると警告が1件。段の名前と access = "docs" を含む。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", bash=True, prompt=f"結果の{word}をしてください。")])
    warnings = lint()(pipe)
    assert len(warnings) == 1
    assert "probe" in warnings[0] and 'access = "docs"' in warnings[0]


def test_w1_reads_prompt_file(tmp_path):
    """D0038-AC-01: 指示文を prompt_file に書いたときも読む。"""
    d = tmp_path / "pipe-in-lt"
    (d / "prompts").mkdir(parents=True)
    (d / "prompts" / "a.md").write_text("下書きを置き場所に保存します。", encoding="utf-8")
    (d / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\n'
        'access = "read"\nbash = true\nprompt_file = "prompts/a.md"\n',
        encoding="utf-8",
    )
    from pipe_in.pipe.definition import load_pipe

    warnings = lint()(load_pipe(d))
    assert len(warnings) == 1 and 'access = "docs"' in warnings[0]


def test_w1_not_raised_without_write_words(tmp_path):
    """D0038-AC-02: 同じ形でも、指示文に書き込みを思わせる言葉が無ければ出さない。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", bash=True, prompt="テストの結果を読んで、問題点を成果物にまとめてください。")])
    assert lint()(pipe) == []


@pytest.mark.parametrize(
    "access,bash",
    [("read", False), ("docs", True), ("tests", True), ("code", True)],
)
def test_w1_not_raised_for_other_forms(tmp_path, access, bash):
    """D0038-AC-02: bash = true でない read の段・docs / tests / code で bash = true の段には、書き込みの言葉があっても W1 を出さない。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", access=access, bash=bash, prompt="下書きを保存して、置き場所に描き出す。")])
    assert lint()(pipe) == []


# ---- AC-03・AC-04: W3 ------------------------------------------------------------------


def test_w3_tests_stage_without_bash_before_check_command(tmp_path):
    """D0038-AC-03: tests で bash なしの段のあとに check.command を持つ段があると、警告が1件。"""
    pipe = make_pipe(
        tmp_path,
        [
            stage_toml("red", access="tests"),
            stage_toml("impl", access="code", bash=True, command="pytest -q"),
        ],
    )
    warnings = lint()(pipe)
    assert len(warnings) == 1
    assert "red" in warnings[0] and "bash = true" in warnings[0] and "impl" in warnings[0]


@pytest.mark.parametrize(
    "case",
    ["tests-has-bash", "no-later-command", "command-in-earlier-stage", "command-in-same-stage"],
)
def test_w3_not_raised_when_bash_or_no_later_command(tmp_path, case):
    """D0038-AC-04: tests の段が bash = true のとき・あとに check.command が無いとき・check.command が前の段にあるとき・同じ段にあるときは出さない。"""
    if case == "tests-has-bash":
        stages = [stage_toml("red", access="tests", bash=True), stage_toml("impl", access="code", bash=True, command="pytest -q")]
    elif case == "no-later-command":
        stages = [stage_toml("red", access="tests"), stage_toml("impl", access="code", bash=True, verdict=True)]
    elif case == "command-in-earlier-stage":
        stages = [stage_toml("impl", access="code", bash=True, command="pytest -q"), stage_toml("red", access="tests")]
    else:
        stages = [stage_toml("red", access="tests", command="pytest -q")]
    assert lint()(make_pipe(tmp_path, stages)) == []


# ---- AC-05: W5 -------------------------------------------------------------------------


def test_w5_on_fail_to_read_stage(tmp_path):
    """D0038-AC-05: on_fail が別の段を指し、その段が access = "read" なら警告が1件（先の名前つき）。"""
    pipe = make_pipe(
        tmp_path,
        [
            stage_toml("survey", access="read"),
            stage_toml("verify", access="read", verdict=True, on_fail="survey"),
        ],
    )
    warnings = lint()(pipe)
    assert len(warnings) == 1
    assert "verify" in warnings[0] and "survey" in warnings[0] and 'access = "read"' in warnings[0]


@pytest.mark.parametrize("target_access", ["docs", "tests", "code"])
def test_w5_not_raised_for_writable_self_or_missing(tmp_path, target_access):
    """D0038-AC-05: 先が docs・tests・code の段・on_fail を省いたとき・自分を指すとき・check が無いときは出さない。"""
    writable = make_pipe(
        tmp_path / "a",
        [stage_toml("fix", access=target_access), stage_toml("verify", verdict=True, on_fail="fix")],
    )
    assert lint()(writable) == []
    no_on_fail = make_pipe(tmp_path / "b", [stage_toml("first"), stage_toml("verify", verdict=True)])
    assert lint()(no_on_fail) == []
    to_self = make_pipe(tmp_path / "c", [stage_toml("first"), stage_toml("verify", verdict=True, on_fail="verify")])
    assert lint()(to_self) == []
    no_check = make_pipe(tmp_path / "d", [stage_toml("first"), stage_toml("verify")])
    assert lint()(no_check) == []


# ---- AC-09: ひな形・見本 ---------------------------------------------------------------


@pytest.fixture
def isolate_pipes(tmp_path, monkeypatch):
    """gen new が本物の pipes/ を見ないようにする（test_generator.py の no_repo_pipes と同じ）。"""
    import os

    from pipe_in.pipe import definition as pd

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.setattr(pd, "default_pipes_dir", lambda: Path(os.environ["PIPE_IN_PIPES_DIR"]) if os.environ.get("PIPE_IN_PIPES_DIR") else tmp_path / "repo-pipes")


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_have_no_warnings(tmp_path, isolate_pipes, name):
    """D0038-AC-09: ひな形 dev・diagrams・spec-qa は警告 0 件。"""
    from pipe_in.pipe.definition import load_pipe
    from pipe_in_generator import cli

    proj = project(tmp_path)
    assert cli.main(["new", f"my-{name}", "--from", name, "--project", str(proj), "--pipes-dir", str(tmp_path / "pipes")]) == 0
    pipe = load_pipe(tmp_path / "pipes" / f"pipe-in-my-{name}")
    assert lint()(pipe) == []


def test_video_example_has_no_warnings():
    """D0038-AC-09: examples/video の見本は、verify 段を access = "docs" に直したあとなので、警告 0 件（W1 は当たらない）。"""
    from pipe_in.pipe.definition import load_pipe

    pipe = load_pipe(ROOT / "examples" / "video" / "pipes" / "pipe-in-video")
    assert [s.name for s in pipe.stages][-1] == "verify"
    assert lint()(pipe) == []


def test_video_example_old_verify_form_gets_one_w1(tmp_path):
    """D0038-AC-09: 直す前の形（verify が read・bash・「取り出し」「置き場所」の指示）なら W1 が verify の1件だけ。"""
    pipe = make_pipe(
        tmp_path,
        [
            stage_toml("render", access="docs", bash=True),
            stage_toml(
                "verify",
                access="read",
                bash=True,
                prompt="こまを取り出して、置き場所に並べる。",
                verdict=True,
                on_fail="render",
            ),
        ],
    )
    warnings = lint()(pipe)
    assert len(warnings) == 1 and "verify" in warnings[0]


# ---- AC-10・AC-11 ----------------------------------------------------------------------


def test_lint_does_not_change_check_pipe(tmp_path):
    """D0038-AC-10: 警告のある定義でも、check_pipe の返り値は誤りなし（[]）のまま。"""
    from pipe_in.pipe.definition import check_pipe

    proj = project(tmp_path)
    pipe = make_pipe(
        tmp_path,
        [
            stage_toml("a", bash=True, prompt="下書きを保存する"),
            stage_toml("red", access="tests"),
            stage_toml("verify", verdict=True, on_fail="a", command="pytest -q"),
        ],
    )
    assert len(lint()(pipe)) == 3  # W1・W3・W5 が1件ずつ
    assert check_pipe(pipe, proj) == []


def test_lint_tolerates_unreadable_prompt(tmp_path):
    """D0038-AC-10: 指示ファイルが読めない（UTF-8 でない）ときも落ちず、その段の W1 は出さない。"""
    from pipe_in.pipe.definition import load_pipe

    d = tmp_path / "pipe-in-lt"
    (d / "prompts").mkdir(parents=True)
    (d / "prompts" / "a.md").write_bytes(b"\xff\xfe\x00\x80")
    (d / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\n'
        'access = "read"\nbash = true\nprompt_file = "prompts/a.md"\n',
        encoding="utf-8",
    )
    assert lint()(load_pipe(d)) == []


# 前の版の名前（AC-11）のパイプの警告は、古い名前を書いてよい tests/test_generator.py の
# test_legacy_named_pipe_gets_same_warnings にある（tests/test_rename.py が古い名前の出るファイルを絞っている）。


def test_warnings_start_with_stage_index_and_name(tmp_path):
    """D0038-AC-01: 警告の文は「段 {i}（{name}）: 」で始まる（check_pipe の誤りと同じ形）。"""
    pipe = make_pipe(tmp_path, [stage_toml("first"), stage_toml("probe", bash=True, prompt="保存する")])
    (w,) = lint()(pipe)
    assert w.startswith("段 2（probe）: ")
