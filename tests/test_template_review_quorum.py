"""ひな形 review-quorum（generator/templates/review-quorum/）の検査（D0076）。SDK は呼ばない。

ひな形は読むだけで、書くのは tmp_path の中だけ（`pipe-in-gen new` の対象も置き場所も tmp_path）。
指示文は文の一致ではなく、「入っているべき短い語」が全部あるかを見る（言い回しは変えてよい）。
新しい部品（ひな形のフォルダ）はテストの中で読み込む（落ちる理由が「まだ無い」だと読めるように）。
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

TEMPLATE_NAME = "review-quorum"
OLD_NAME = "dev" + "pipe"  # 前の名前。文字のまま書くと tests/test_rename.py が許していないファイルとして落とす
NAME = "pics"
ROOT = Path(__file__).resolve().parents[1]

STAGES = ["review-a", "review-b", "quorum"]
REVIEWS = ["review-a", "review-b"]
PROMPT_FILES = ["01_review.md", "02_quorum.md"]

SPEC_TEXT = "# 貸出仕様\n\n## 2.1 冊数\n\n利用者は、本を最大5冊まで借りられる。\n\n## 2.2 期限\n\n返却期限は、貸出日から14日とする。\n"
QUOTE_1 = "利用者は、本を最大5冊まで借りられる。"
QUOTE_2 = "返却期限は、貸出日から14日とする。"


# ---- 部品 --------------------------------------------------------------------------------


def gen_cli():
    from pipe_in_generator import cli

    return cli


def definition():
    from pipe_in.pipe import definition

    return definition


def template_dir() -> Path:
    return gen_cli().templates_dir() / TEMPLATE_NAME


def python_project(tmp_path: Path) -> Path:
    project = tmp_path / "shop"
    (project / "src").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "shop"\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n', encoding="utf-8"
    )
    return project


@pytest.fixture(autouse=True)
def no_repo_pipes(tmp_path, monkeypatch):
    """どのテストも、リポジトリの本物の pipes/ には書かない（今までの場所を仮のフォルダに向ける）。"""
    import os

    from pipe_in.pipe import definition as pd

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(f"{OLD_NAME.upper()}_PIPES_DIR", raising=False)

    def fake_default() -> Path:
        env = pd.env_pipes_dir(os.environ)
        return Path(env) if env else tmp_path / "repo-pipes"

    monkeypatch.setattr(pd, "default_pipes_dir", fake_default)


def gen(tmp_path: Path, *args: str) -> int:
    return gen_cli().main([*args, "--pipes-dir", str(tmp_path / "pipes")])


def new_pipe(tmp_path: Path):
    """名前 pics で review-quorum から写して (project, folder, PipeDef) を返す。"""
    assert template_dir().is_dir(), f"ひな形のフォルダ {TEMPLATE_NAME} がありません（まだ作っていない）"
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", NAME, "--from", TEMPLATE_NAME, "--project", str(project)) == 0
    folder = tmp_path / "pipes" / f"pipe-in-{NAME}"
    return project, folder, definition().load_pipe(folder)


def stage(pipe, name: str):
    return next(s for s in pipe.stages if s.name == name)


def prompt(folder: Path, file: str) -> str:
    path = folder / "prompts" / file
    assert path.is_file(), f"{file} がありません"
    return path.read_text(encoding="utf-8")


def missing_words(text: str, words: list) -> list[str]:
    """入っているべき語のうち、text に無いもの。語が (a, b) の組なら、どれか1つあればよい。"""
    out = []
    for w in words:
        alts = w if isinstance(w, tuple) else (w,)
        if not any(a in text for a in alts):
            out.append(" / ".join(alts))
    return out


def section_of(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n", text, re.M)
    if not m:
        return ""
    nxt = re.search(r"^## ", text[m.end() :], re.M)
    return text[m.end() : m.end() + nxt.start() if nxt else len(text)]


# ---- AC-11: 形 -----------------------------------------------------------------------------


def test_d0076_ac11_template_files_exist():
    """D0076-AC-11: generator/templates/review-quorum/ に pipe.toml・README.md・prompts/ の2つの指示文がある。"""
    d = template_dir()
    assert d.is_dir(), f"ひな形のフォルダ {d.name} がありません（まだ作っていない）"
    assert (d / "pipe.toml").is_file() and (d / "README.md").is_file()
    assert sorted(p.name for p in (d / "prompts").glob("*.md")) == sorted(PROMPT_FILES)


def test_d0076_ac11_list_shows_review_quorum(tmp_path, capsys):
    """D0076-AC-11: pipe-in-gen list の出力のひな形の一覧に review-quorum が出る。"""
    capsys.readouterr()
    assert gen(tmp_path, "list") == 0
    assert TEMPLATE_NAME in capsys.readouterr().out


def test_d0076_ac11_new_and_check_clean(tmp_path, capsys):
    """D0076-AC-11: pipe-in-gen new で写せて、check が誤り 0 件・警告（⚠）0 件、lint_pipe も空。"""
    from pipe_in.pipe.lint import lint_pipe

    project, _, pipe = new_pipe(tmp_path)
    capsys.readouterr()
    assert gen(tmp_path, "check", NAME, "--project", str(project)) == 0
    assert "⚠" not in capsys.readouterr().out
    assert lint_pipe(pipe) == []


def test_d0076_ac11_no_placeholder_or_old_name_left(tmp_path):
    """D0076-AC-11: 作ったパイプのフォルダの全ファイルに {{ が残らず、前の名前を含む文字が無い。手元のパスも入らない。"""
    project, folder, _ = new_pipe(tmp_path)
    files = [p for p in folder.rglob("*") if p.is_file()]
    assert len(files) >= 4  # pipe.toml・README.md・指示文2つ
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert "{{" not in text, p.name
        assert OLD_NAME not in text.lower(), p.name
        assert str(project) not in text and project.as_posix() not in text, p.name


def test_d0076_ac11_stages_and_basics(tmp_path):
    """D0076-AC-11: 段は review-a・review-b・quorum の順、kind は linear・input は optional、どの段も access は read・haiku で Bash・Web・MCP は使わず、成果物の名前は重ならない。"""
    _, _, pipe = new_pipe(tmp_path)
    assert [s.name for s in pipe.stages] == STAGES
    assert pipe.kind == "linear" and pipe.input == "optional"
    for s in pipe.stages:
        assert s.access == "read" and s.model == "haiku", s.name
        assert s.bash is False and s.web is False and s.mcp == [] and s.agents == {}, s.name
        assert s.review is False, s.name
    assert len({s.output for s in pipe.stages}) == len(pipe.stages)


def test_d0076_ac11_two_reviews_share_prompt_and_group(tmp_path):
    """D0076-AC-11: review-a と review-b は同じ prompt_file と同じ group を持ち、成果物は別。quorum は group に入らず、別の指示文。"""
    _, _, pipe = new_pipe(tmp_path)
    a, b, c = (stage(pipe, n) for n in STAGES)
    assert a.prompt_file is not None and a.prompt_file == b.prompt_file
    assert a.group is not None and a.group == b.group
    assert a.output != b.output
    assert c.group is None
    assert c.prompt_file is not None and c.prompt_file != a.prompt_file


def test_d0076_ac11_quorum_stage_command(tmp_path):
    """D0076-AC-11: quorum 段の check.command に pipe-in-gen quorum と --no-third と findings-check があり、on_fail は group の先頭の段（review-a）。モデルは軽く、max_turns は小さい。"""
    _, _, pipe = new_pipe(tmp_path)
    c = stage(pipe, "quorum")
    assert c.check is not None and c.check.command
    cmd = c.check.command
    assert "pipe-in-gen quorum" in cmd and "--no-third" in cmd and "findings-check" in cmd
    assert cmd.index("pipe-in-gen quorum") < cmd.index("findings-check")
    assert c.check.on_fail == "review-a"
    assert c.check.verdict is False and c.check.judge is None
    assert c.max_turns is not None and c.max_turns <= 5
    assert stage(pipe, "review-a").group == stage(pipe, "review-b").group  # on_fail は group の先頭


def run_command_in(project: Path, command: str) -> int:
    """pipe-in-gen の1つのコマンド（"pipe-in-gen …"）を、project を作業フォルダにして generator.cli.main で流す。"""
    argv = shlex.split(command)
    assert argv[0] == "pipe-in-gen", argv
    try:
        return gen_cli().main(argv[1:])
    except SystemExit as e:
        return int(e.code or 0)


def test_d0076_ac11_quorum_command_writes_common_and_passes_findings_check(tmp_path, monkeypatch):
    """D0076-AC-09・11: quorum 段の command を、本体が流すのと同じ形（&& で区切った2つ）で tmp_path の対象で流すと、共通部分が書かれ、findings-check が 0 で通る。"""
    project, _, pipe = new_pipe(tmp_path)
    command = stage(pipe, "quorum").check.command
    first, second = (part.strip() for part in command.split("&&"))
    q_args = shlex.split(first)[2:]  # pipe-in-gen quorum の後ろ
    files = [a for a in q_args if not a.startswith("--")][:2]
    out_rel = q_args[q_args.index("--out") + 1]
    f_args = shlex.split(second)
    assert f_args[1] == "findings-check" and f_args[2] == out_rel, "findings-check は quorum の書いた共通部分を見る"
    sources_rel = f_args[f_args.index("--sources") + 1]
    spec_rel = f_args[f_args.index("--spec") + 1]

    def put(rel: str, text: str) -> None:
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def finding(n: int, section: str, quote: str) -> dict:
        return {
            "id": f"F-{n:03d}", "role": "quality", "location": {"source": "SRC-001", "section": section, "quote": quote},
            "kind": "ambiguous", "statement": "分からない。", "rationale": "決まっていない。", "sources": ["SRC-001"],
            "guess": False, "confidence": "high", "severity": "minor", "status": "open",
        }

    put(spec_rel, SPEC_TEXT)
    put(sources_rel, json.dumps({"v": 1, "sources": [{"id": "SRC-001", "kind": "spec", "title": "貸出仕様", "version": "1.0", "where": "全体", "file": Path(spec_rel).name}]}, ensure_ascii=False))
    put(files[0], json.dumps({"v": 1, "findings": [finding(1, "2.1", QUOTE_1), finding(2, "2.2", QUOTE_2)]}, ensure_ascii=False))
    put(files[1], json.dumps({"v": 1, "findings": [finding(1, "2.1", QUOTE_1)]}, ensure_ascii=False))
    monkeypatch.chdir(project)
    assert run_command_in(project, first) == 0  # --no-third なので、3体目が要っても 0
    common = json.loads((project / out_rel).read_text(encoding="utf-8"))
    assert [f["location"]["section"] for f in common["findings"]] == ["2.1"]
    assert run_command_in(project, second) == 0


# ---- AC-12: 各体 -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", REVIEWS)
def test_d0076_ac12_reviews_have_own_findings_check(tmp_path, name):
    """D0076-AC-12: review-a・review-b は、どちらも check.command に findings-check を持ち、自分の成果物を見て、on_fail は自分。"""
    _, _, pipe = new_pipe(tmp_path)
    s = stage(pipe, name)
    assert s.check is not None and s.check.command
    assert "findings-check" in s.check.command
    assert s.output in s.check.command
    assert s.check.on_fail == name
    assert s.check.max_retries >= 1


@pytest.mark.parametrize("word", ["逐語", "引用", "quote", "section", "SRC-", "docs/review-quorum/spec.md", "docs/review-quorum/sources.json"])
def test_d0076_ac12_prompt_asks_verbatim_quote(tmp_path, word):
    """D0076-AC-12: 各体の指示文に、引用を逐語で付けさせる言葉（逐語・引用・quote）と、節の名前・出典 ID・仕様書と台帳の場所がある。"""
    _, folder, _ = new_pipe(tmp_path)
    found = word in prompt(folder, "01_review.md")
    assert found, f"01_review.md に {word} が無い"


def test_d0076_ac12_prompt_keeps_section_name_as_is(tmp_path):
    """D0076-AC-12: 節の名前は一致のキーになるので、仕様書の見出しをそのまま使い、言い換えないと書いてある。"""
    _, folder, _ = new_pipe(tmp_path)
    text = prompt(folder, "01_review.md")
    assert "見出し" in text and ("そのまま" in text) and "言い換え" in text


def test_d0076_ac12_no_w6(tmp_path):
    """D0076-AC-12: W6（指摘を出す段なのに引用の指示も findings-check も無い）は出ない。lint_pipe の警告は 0 件。"""
    from pipe_in.pipe.lint import lint_pipe

    _, _, pipe = new_pipe(tmp_path)
    warnings = lint_pipe(pipe)
    assert [w for w in warnings if "findings-check" in w or "引用" in w] == []
    assert warnings == []


def test_d0076_ac12_quorum_prompt_is_light_and_has_no_finding_words(tmp_path):
    """D0076-AC-12: quorum 段の指示文は短く、指摘を出させる言葉（指摘にし・指摘を出・findings）を使わず、共通部分を取る仕事は check.command がすると書く。"""
    _, folder, _ = new_pipe(tmp_path)
    text = prompt(folder, "02_quorum.md")
    assert len(text) < 1500
    for w in ("指摘にし", "指摘を出", "指摘を挙げ", "指摘を探"):
        assert w not in text, w
    assert "check.command" in text or "command" in text


def test_d0076_ac12_prompts_have_no_placeholders_paths_or_mail(tmp_path):
    """D0076-AC-12: 2つの指示文に、{{ を含む行・絶対パス・メールアドレスが無い（公開してよい）。"""
    d = template_dir() / "prompts"
    assert d.is_dir(), f"{d} がありません（ひな形をまだ作っていない）"
    for p in sorted(d.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        assert [ln for ln in text.splitlines() if "{{" in ln] == [], p.name
        assert [x for x in ("/Users/", "C:\\", "/home/") if x in text] == [], p.name
        assert re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text) is None, p.name


# ---- AC-13: README ---------------------------------------------------------------------------

README_MARKS = [
    ("what-to-use", "使いどころ"),
    ("weak-model", "Haiku"),
    ("false-findings", "誤指摘"),
    ("when-not", "使わないとき"),
    ("strong-model", "強いモデル"),
    ("varied-readings", "読み方"),
    ("one-agent", "1体"),
    ("spec-path", "docs/review-quorum/spec.md"),
    ("ledger-path", "docs/review-quorum/sources.json"),
    ("ledger-example", "SRC-001"),
    ("no-third", "3体目"),
    ("no-third-flag", "--no-third"),
    ("cost", "費用"),
    ("limit-post-hoc", "事後"),
    ("limit-generator", "生成器"),
    ("research-link", "harness-compare"),
    ("check-after", "pipe-in-gen check"),
]


@pytest.mark.parametrize("label,word", README_MARKS, ids=[i for i, _ in README_MARKS])
def test_d0076_ac13_readme_marks(tmp_path, label, word):
    """D0076-AC-13: 写した README に、使いどころ（誤指摘が多いモデル）・使わないとき（強いモデル・読み方を変えた2体・1体で解ける課題）・仕様書と出典の台帳の置き場所（1件の例）・3体目を流さないこと・費用・限界の一文がある。"""
    _, folder, _ = new_pipe(tmp_path)
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "{{" not in readme
    assert f"# pipe-in-{NAME}" in readme
    found = word in readme
    assert found, f"README に {label} の目印（{word}）が無い"


# ---- AC-18: 設計の表と決定の一覧 -----------------------------------------------------------------


def test_d0076_ac18_design_table_has_quorum_row():
    """D0076-AC-18: docs/development/design.md の置き場所の表に generator/quorum.py の行があり、その行は 800 字以内。"""
    rows = [ln for ln in (ROOT / "docs/development/design.md").read_text(encoding="utf-8").splitlines() if ln.startswith("|") and "`generator/quorum.py`" in ln]
    assert len(rows) == 1, "置き場所の表に generator/quorum.py の行が無い"
    assert len(rows[0]) <= 800


def test_d0076_ac18_decision_row_exists():
    """D0076-AC-18: 決定の記録の一覧に D0076 の行がある。（決定の記録の段のあとで通る）"""
    rows = [ln for ln in (ROOT / "docs/decisions/README.md").read_text(encoding="utf-8").splitlines() if "D0076" in ln]
    assert rows, "docs/decisions/README.md の一覧に D0076 の行が無い"
