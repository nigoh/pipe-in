"""パイプの警告（pipe_in.pipe.lint の lint_pipe）：D0038（W1・W3・W5）と D0053（W6）。SDK は呼ばない。

定義は tmp_path に pipe.toml と prompts/ を書いて load_pipe で作る（リポジトリの実物には書かない）。
新しい部品（lint）はテストの中で読み込む（落ちる理由が「まだ無い」だと読めるように）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ["dev", "diagrams", "spec-qa", "spec-review"]


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
    """D0038-AC-09: ひな形 dev・diagrams・spec-qa・spec-review は警告 0 件。"""
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


# ---- D0053: W6（指摘を出す段に、引用の指示も findings-check も無い） ---------------------------------
#
# 言葉の一覧は、W1 の WRITE_WORDS と同じく、実装の定数を読まずにここへ写して並べる（一覧が勝手に減ったら赤になるように）。

FINDING_WORDS = ["指摘にし", "指摘を出", "指摘を挙げ", "指摘を探", "findings"]
QUOTE_WORDS = ["引用", "逐語", "そのまま写", "quote"]
FINDINGS_CHECK_COMMAND = "pipe-in-gen findings-check f.json --sources s.json --spec spec.md"
FINDING_PROMPT = "仕様書を読んで、問題を1つずつ指摘にします。"


def test_d0053_ac01_w6_read_stage_without_quote_or_check(tmp_path):
    """D0053-AC-01: read の段の指示文に「指摘にします」があり、引用の言葉も findings-check も無いと、警告が1件。「段 1（probe）: 」で始まり、findings-check と「引用」を含む。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", prompt=FINDING_PROMPT)])
    warnings = lint()(pipe)
    assert len(warnings) == 1
    assert warnings[0].startswith("段 1（probe）: ")
    assert "findings-check" in warnings[0] and "引用" in warnings[0]


def test_d0053_ac02_w6_docs_stage(tmp_path):
    """D0053-AC-02: 同じ形で access = "docs" の段でも、警告が1件。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", access="docs", prompt=FINDING_PROMPT)])
    warnings = lint()(pipe)
    assert len(warnings) == 1 and warnings[0].startswith("段 1（probe）: ")


def test_d0053_ac02_w6_reads_prompt_file(tmp_path):
    """D0053-AC-02: 指示文を prompt_file に書いたときも読み、警告が1件。"""
    from pipe_in.pipe.definition import load_pipe

    d = tmp_path / "pipe-in-lt"
    (d / "prompts").mkdir(parents=True)
    (d / "prompts" / "a.md").write_text(FINDING_PROMPT, encoding="utf-8")
    (d / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\n'
        'access = "read"\nprompt_file = "prompts/a.md"\n',
        encoding="utf-8",
    )
    warnings = lint()(load_pipe(d))
    assert len(warnings) == 1 and warnings[0].startswith("段 1（a）: ")


@pytest.mark.parametrize("word", FINDING_WORDS)
def test_d0053_ac03_w6_each_finding_word(tmp_path, word):
    """D0053-AC-03: 「指摘を出す」言葉の一覧のどの言葉でも、警告が1件。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", prompt=f"仕様書を読んで、次の言葉のとおりに進めます：{word}。")])
    warnings = lint()(pipe)
    assert len(warnings) == 1 and "findings-check" in warnings[0]


@pytest.mark.parametrize("word", QUOTE_WORDS)
def test_d0053_ac04_w6_not_raised_with_quote_word(tmp_path, word):
    """D0053-AC-04: 指示文に引用の言葉（引用・逐語・そのまま写・quote のどれか）があれば出さない。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", prompt=f"{FINDING_PROMPT}指摘ごとに、原文の行の{word}を付けます。")])
    assert lint()(pipe) == []


@pytest.mark.parametrize("where", ["earlier-stage", "later-stage", "same-stage"])
def test_d0053_ac05_w6_not_raised_with_findings_check(tmp_path, where):
    """D0053-AC-05: パイプのどれかの段（前の段・あとの段・同じ段）の check.command に findings-check があれば出さない。"""
    if where == "earlier-stage":
        stages = [stage_toml("verify", command=FINDINGS_CHECK_COMMAND), stage_toml("probe", prompt=FINDING_PROMPT)]
    elif where == "later-stage":
        stages = [stage_toml("probe", prompt=FINDING_PROMPT), stage_toml("verify", command=FINDINGS_CHECK_COMMAND)]
    else:
        stages = [stage_toml("probe", prompt=FINDING_PROMPT, command=FINDINGS_CHECK_COMMAND)]
    assert lint()(make_pipe(tmp_path, stages)) == []


@pytest.mark.parametrize("prompt", ["審査の指摘を直してください。", "指摘をまとめてください。", "渡された problems を直す。"])
def test_d0053_ac06_w6_not_raised_for_fixing_or_summarizing(tmp_path, prompt):
    """D0053-AC-06: 指摘を直す・まとめる側の指示文（「審査の指摘を直してください」「指摘をまとめてください」「渡された problems を直す」）には出さない。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", prompt=prompt)])
    assert lint()(pipe) == []


@pytest.mark.parametrize("access", ["tests", "code"])
def test_d0053_ac07_w6_not_raised_for_tests_or_code(tmp_path, access):
    """D0053-AC-07: access = "tests"・"code" の段には、指示文に「指摘にします」があっても出さない。"""
    pipe = make_pipe(tmp_path, [stage_toml("probe", access=access, prompt=FINDING_PROMPT)])
    assert lint()(pipe) == []


def test_d0053_ac08_w6_one_per_stage_in_order(tmp_path):
    """D0053-AC-08: 指摘を出す段が3つあり、どれにも引用の言葉も findings-check も無いと、警告は3件で、段の順に並ぶ。"""
    pipe = make_pipe(tmp_path, [stage_toml(n, prompt=FINDING_PROMPT) for n in ["a", "b", "c"]])
    warnings = lint()(pipe)
    assert len(warnings) == 3
    assert [w.split(": ", 1)[0] for w in warnings] == ["段 1（a）", "段 2（b）", "段 3（c）"]
    assert all("findings-check" in w for w in warnings)


def test_d0053_ac09_w6_tolerates_unreadable_prompt(tmp_path):
    """D0053-AC-09: 指示ファイルが読めない（UTF-8 でない）read の段（bash なし）でも落ちず、その段の W6 は出さない。"""
    from pipe_in.pipe.definition import load_pipe

    d = tmp_path / "pipe-in-lt"
    (d / "prompts").mkdir(parents=True)
    (d / "prompts" / "a.md").write_bytes(b"\xff\xfe\x00\x80")
    (d / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\n'
        'access = "read"\nprompt_file = "prompts/a.md"\n',
        encoding="utf-8",
    )
    assert lint()(load_pipe(d)) == []


def test_d0053_ac10_w6_added_after_existing_warnings(tmp_path):
    """D0053-AC-10: W1・W3・W5 が1件ずつ出る定義（D0038-AC-10 と同じ3段）の最後に、W6 の条件を満たす段を足すと、警告は4件。
    前の3件は足す前の文とそれぞれ等しく、4件目は「段 4（find）: 」で始まる。check_pipe は誤りなし（[]）のまま。"""
    from pipe_in.pipe.definition import check_pipe

    proj = project(tmp_path)
    base = [
        stage_toml("a", bash=True, prompt="下書きを保存する"),
        stage_toml("red", access="tests"),
        stage_toml("verify", verdict=True, on_fail="a", command="pytest -q"),
    ]
    before = lint()(make_pipe(tmp_path / "before", base))
    assert len(before) == 3  # W1・W3・W5 が1件ずつ（足す前）
    pipe = make_pipe(tmp_path / "after", [*base, stage_toml("find", prompt=FINDING_PROMPT)])
    after = lint()(pipe)
    assert len(after) == 4
    assert after[:3] == before
    assert after[3].startswith("段 4（find）: ")
    assert check_pipe(pipe, proj) == []


SPEC_REVIEW_FINDING_PROMPTS = [
    "01_naive.md",
    "03_quality.md",
    "04_gap.md",
    "05_user.md",
    "06_tester.md",
    "07_designer.md",
    "08_operations.md",
]
# 引用の言葉を、W6 の一覧に当たらない別の語に置き換える（順に当てる。「quote」は欄の名前としても出る）
QUOTE_REPLACEMENTS = [("引用", "出どころ"), ("逐語", "文字どおり"), ("そのまま写", "同じに書き"), ("quote", "passage")]


def test_d0053_ac12_spec_review_without_findings_check_gets_w6(tmp_path, isolate_pipes):
    """D0053-AC-12: ひな形 spec-review を写し、verify の findings-check の command を消し、naive と検査役の6段の指示文から引用の言葉を消すと、
    W6 が naive・quality・gap・user・tester・designer・operations の順に7件出る（verify と report は「引用」が残るので当たらない）。"""
    from pipe_in.pipe.definition import load_pipe
    from pipe_in_generator import cli

    proj = project(tmp_path)
    assert cli.main(["new", "my-sr", "--from", "spec-review", "--project", str(proj), "--pipes-dir", str(tmp_path / "pipes")]) == 0
    d = tmp_path / "pipes" / "pipe-in-my-sr"
    toml = (d / "pipe.toml").read_text(encoding="utf-8")
    lines = toml.splitlines()
    replaced = ["verdict = true" if line.startswith('command = "pipe-in-gen findings-check') else line for line in lines]
    assert replaced != lines, "写した pipe.toml に findings-check の command の行が無い"
    (d / "pipe.toml").write_text("\n".join(replaced) + "\n", encoding="utf-8")
    for name in SPEC_REVIEW_FINDING_PROMPTS:
        p = d / "prompts" / name
        text = p.read_text(encoding="utf-8")
        for old, new in QUOTE_REPLACEMENTS:
            text = text.replace(old, new)
        assert not [w for w in QUOTE_WORDS if w in text], name
        p.write_text(text, encoding="utf-8")
    pipe = load_pipe(d)
    assert not any(s.check is not None and s.check.command and "findings-check" in s.check.command for s in pipe.stages)
    warnings = lint()(pipe)
    names = [w.split("（", 1)[1].split("）", 1)[0] for w in warnings]
    assert names == ["naive", "quality", "gap", "user", "tester", "designer", "operations"]
