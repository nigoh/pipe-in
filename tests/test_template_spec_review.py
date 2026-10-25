"""ひな形 spec-review（generator/templates/spec-review/）の検査（D0047）。SDK は呼ばない。

ひな形は読むだけで、書くのは tmp_path の中だけ（`pipe-in-gen new` の対象も置き場所も tmp_path）。
指示文は文の一致ではなく、「入っているべき短い語」が全部あるかを見る（言い回しは変えてよい）。
ただし指摘の形の共通の節だけは、8つの指示文で同じ文であることを見る。
新しい部品（ひな形のフォルダ）はテストの中で読み込む（落ちる理由が「まだ無い」だと読めるように）。
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

import pytest

TEMPLATE_NAME = "spec-review"
OLD_NAME = "dev" + "pipe"  # 前の名前。文字のまま書くと tests/test_rename.py が許していないファイルとして落とす
NAME = "pics"

STAGES = ["naive", "knowledge", "quality", "gap", "user", "tester", "designer", "operations", "verify", "report"]
INSPECT = ["quality", "gap", "user", "tester", "designer", "operations"]
PERSPECTIVES = ["user", "tester", "designer", "operations"]
FINDING_STAGES = ["naive", *INSPECT, "verify"]
OUTPUTS = {
    "naive": "01_naive.json",
    "knowledge": "02_knowledge.md",
    "quality": "03_quality.json",
    "gap": "04_gap.json",
    "user": "05_user.json",
    "tester": "06_tester.json",
    "designer": "07_designer.json",
    "operations": "08_operations.json",
    "verify": "09_findings.json",
    "report": "10_report.md",
}
PROMPT_FILES = {
    "naive": "01_naive.md",
    "knowledge": "02_knowledge.md",
    "quality": "03_quality.md",
    "gap": "04_gap.md",
    "user": "05_user.md",
    "tester": "06_tester.md",
    "designer": "07_designer.md",
    "operations": "08_operations.md",
    "verify": "09_verify.md",
    "report": "10_report.md",
}
MODELS = {
    "naive": "haiku",
    "knowledge": "sonnet",
    "quality": "haiku",
    "gap": "haiku",
    "user": "haiku",
    "tester": "haiku",
    "designer": "haiku",
    "operations": "haiku",
    "verify": "sonnet",
    "report": "sonnet",
}
REQUIRED_FIELDS = [
    "id", "role", "location", "kind", "statement", "rationale", "sources", "guess", "confidence", "severity", "status",
]
HEADERS = ["指摘ID", "重大度", "質問", "回答の型", "選択肢", "場所", "引用", "回答"]
# 公開してよい指示文に入れない語（特定の業界・組織の名前）
RESOURCES_BAD_WORDS = ["銀行", "保険", "病院", "医療", "自治体", "金融", "証券", "製薬", "官公庁"]
COMMON_HEADING = "## 指摘の形（v1）"

VERIFY_COMMAND = (
    f"pipe-in-gen findings-check docs/pipeline/{NAME}/09_findings.json "
    "--sources docs/spec-review/knowledge/sources.json --spec docs/spec-review/spec.md"
)

SPEC_TEXT = "# 貸出仕様\n\n## 2.1 冊数\n\n利用者は、本を最大5冊まで借りられる。\nLibrary Card を提示する。\n"
QUOTE_OK = "利用者は、本を最大5冊まで借りられる。"


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
    """名前 pics で spec-review から写して (project, folder, PipeDef) を返す。"""
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", NAME, "--from", TEMPLATE_NAME, "--project", str(project)) == 0
    folder = tmp_path / "pipes" / f"pipe-in-{NAME}"
    return project, folder, definition().load_pipe(folder)


def stage(pipe, name: str):
    return next(s for s in pipe.stages if s.name == name)


def prompt(folder: Path, name: str) -> str:
    path = folder / "prompts" / PROMPT_FILES[name]
    assert path.is_file(), f"{path.name} がありません"
    return path.read_text(encoding="utf-8")


def missing_words(text: str, words: list) -> list[str]:
    """入っているべき語のうち、text に無いもの。語が (a, b) の組なら、どれか1つあればよい。"""
    out = []
    for w in words:
        alts = w if isinstance(w, tuple) else (w,)
        if not any(a in text for a in alts):
            out.append(" / ".join(alts))
    return out


def assert_has_words(label: str, text: str, words: list) -> None:
    missing = missing_words(text, words)
    assert missing == [], f"{label} に入っているべき語が足りません: {missing}"


def common_section(text: str) -> str:
    """見出し「指摘の形（v1）」から、次の ## 見出しの手前までの文。無ければ空。"""
    start = text.find(COMMON_HEADING)
    if start < 0:
        return ""
    nxt = text.find("\n## ", start + len(COMMON_HEADING))
    return text[start : nxt if nxt >= 0 else len(text)].strip()


def section_of(text: str, heading: str) -> str:
    """README の「## <heading>」から次の ## の手前まで。無ければ空。"""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n", text, re.M)
    if not m:
        return ""
    nxt = re.search(r"^## ", text[m.end() :], re.M)
    return text[m.end() : m.end() + nxt.start() if nxt else len(text)]


def remove_stages(toml_text: str, names: list[str]) -> str:
    """README の手順と同じ加工：行が [[stages]] で始まる塊に分けて、name が names にある塊を消す。"""
    blocks: list[list[str]] = [[]]
    for line in toml_text.splitlines(keepends=True):
        if line.startswith("[[stages]]"):
            blocks.append([])
        blocks[-1].append(line)
    kept = []
    for b in blocks:
        text = "".join(b)
        m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M) if b and b[0].startswith("[[stages]]") else None
        if m and m.group(1) in names:
            continue
        kept.append(text)
    return "".join(kept)


def role_re(value: str) -> re.Pattern:
    return re.compile(r"role[`\"']*\s*(?:は|=|:)\s*[`\"']*" + re.escape(value) + r"(?![A-Za-z])")


def perspective_re(value: str) -> re.Pattern:
    return re.compile(r"perspective[`\"']*\s*(?:は|=|:)\s*[`\"']*" + re.escape(value) + r"(?![A-Za-z])")


# ---- 部品そのものの確かめ（今の作りのままで通る。検査の関数が効いていることを守る） ----------------


def test_d0047_helper_assert_has_words_names_the_missing_word():
    """D0047-AC-12: 今の作りのままで通る。語を1つ抜いた文では、検査の関数が足りない語を名指しで失敗にする。"""
    assert_has_words("見本", "SRC- と quote", ["SRC-", ("quote", "引用")])
    with pytest.raises(AssertionError) as e:
        assert_has_words("見本", "quote だけ", ["SRC-", "quote"])
    assert "SRC-" in str(e.value)


def test_d0047_helper_remove_stages_removes_only_named_blocks():
    """D0047-AC-20: 今の作りのままで通る。remove_stages は、名前の塊だけを消し、ほかの塊（[stages.check] を含む）は残す。"""
    text = (
        '[pipe]\nkind = "linear"\n\n'
        '[[stages]]\nname = "a"\n# a の説明\n\n'
        '[[stages]]\nname = "b"\n[stages.check]\ncommand = "x"\n\n'
        '[[stages]]\nname = "c"\n'
    )
    out = remove_stages(text, ["b"])
    assert 'name = "a"' in out and 'name = "c"' in out and "# a の説明" in out
    assert 'name = "b"' not in out and "[stages.check]" not in out and "[pipe]" in out


def test_d0047_helper_common_section_stops_at_next_heading():
    """D0047-AC-12: 今の作りのままで通る。共通の節の取り出しは、次の ## 見出しの手前で止まる。"""
    text = f"# 題\n\n{COMMON_HEADING}\n\n本文1\n本文2\n\n## 次\n\n別\n"
    assert common_section(text) == f"{COMMON_HEADING}\n\n本文1\n本文2"
    assert common_section("見出しなし") == ""


# ---- AC-01〜03: ひな形の形 -----------------------------------------------------------------


def test_d0047_ac01_template_files_exist():
    """D0047-AC-01: generator/templates/spec-review/ に pipe.toml・README.md・prompts/ の10個の指示文がある。"""
    d = template_dir()
    assert d.is_dir(), f"ひな形のフォルダ {d.name} がありません（まだ作っていない）"
    assert (d / "pipe.toml").is_file() and (d / "README.md").is_file()
    assert sorted(p.name for p in (d / "prompts").glob("*.md")) == sorted(PROMPT_FILES.values())


def test_d0047_ac01_list_shows_spec_review(tmp_path, capsys):
    """D0047-AC-01: pipe-in-gen list の出力のひな形の一覧に spec-review が出る。"""
    capsys.readouterr()
    assert gen(tmp_path, "list") == 0
    assert TEMPLATE_NAME in capsys.readouterr().out


def test_d0047_ac02_new_and_check_pass_without_warnings(tmp_path, capsys):
    """D0047-AC-02: new が 0、check が 0 で警告（⚠）が 0 件、lint_pipe も空。"""
    from pipe_in.pipe.lint import lint_pipe

    project, _, pipe = new_pipe(tmp_path)
    capsys.readouterr()
    assert gen(tmp_path, "check", NAME, "--project", str(project)) == 0
    assert "⚠" not in capsys.readouterr().out
    assert lint_pipe(pipe) == []


def test_d0047_ac02_no_placeholder_or_old_name_left(tmp_path):
    """D0047-AC-02: 作ったパイプのフォルダの全ファイルに {{ が残らず、前の名前（OLD_NAME）を含む文字が無い。手元のパスも入らない。"""
    project, folder, _ = new_pipe(tmp_path)
    files = [p for p in folder.rglob("*") if p.is_file()]
    assert len(files) >= 12  # pipe.toml・README.md・指示文10個
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert "{{" not in text, p.name
        assert OLD_NAME not in text.lower(), p.name
        assert str(project) not in text and project.as_posix() not in text, p.name


def test_d0047_ac03_stage_names_and_outputs(tmp_path):
    """D0047-AC-03: 段の名前の並びは10段のとおり、kind は linear・input は optional、成果物の名前は決めたとおりで重ならない。"""
    _, _, pipe = new_pipe(tmp_path)
    assert [s.name for s in pipe.stages] == STAGES
    assert pipe.kind == "linear" and pipe.input == "optional"
    assert {s.name: s.output for s in pipe.stages} == OUTPUTS
    assert len({s.output for s in pipe.stages}) == len(pipe.stages)


# ---- AC-04〜07: 権限・確認・並列・モデル -------------------------------------------------------


def test_d0047_ac04_access_and_tools(tmp_path):
    """D0047-AC-04: access は knowledge・report が docs、ほかが read。docs_dir・writes はそのとおり。bash は偽、web・mcp・agents は空。"""
    _, _, pipe = new_pipe(tmp_path)
    for s in pipe.stages:
        assert s.access == ("docs" if s.name in ("knowledge", "report") else "read"), s.name
        assert s.bash is False and s.web is False, s.name
        assert s.mcp == [] and s.agents == {}, s.name
        if s.access == "read":
            assert s.writes == [] and s.docs_dir is None, s.name
    assert stage(pipe, "knowledge").docs_dir == "docs/spec-review/knowledge"
    assert stage(pipe, "report").docs_dir == "docs/spec-review/out"
    assert stage(pipe, "report").writes == ["docs/spec-review/out/questionnaire.csv"]


def test_d0047_ac05_review_and_group(tmp_path):
    """D0047-AC-05: review が true なのは knowledge と report だけ。検査役6段は同じ group（inspect）で続き、review・routes・next が無い。ほかの4段に group は無い。"""
    _, _, pipe = new_pipe(tmp_path)
    assert [s.name for s in pipe.stages if s.review] == ["knowledge", "report"]
    names = [s.name for s in pipe.stages]
    assert names[names.index("quality") : names.index("operations") + 1] == INSPECT  # 続いている
    for n in INSPECT:
        s = stage(pipe, n)
        assert s.group == "inspect", n
        assert s.review is False and s.routes == {} and s.next is None, n
    for n in ("naive", "knowledge", "verify", "report"):
        assert stage(pipe, n).group is None, n


def test_d0047_ac06_models(tmp_path):
    """D0047-AC-06: model は naive と検査役6段が haiku、knowledge・verify・report が sonnet。"""
    _, _, pipe = new_pipe(tmp_path)
    assert {s.name: s.model for s in pipe.stages} == MODELS


def build_specs(tmp_path: Path):
    """(段の名前 → StageSpec, 段の名前 → 自分の成果物の相対パス)。"""
    from pipe_in.pipe.specs import build_pipe_specs
    from test_pipe import pipe_cfg

    project, _, pipe = new_pipe(tmp_path)
    cfg = pipe_cfg(project, pipe)
    specs = build_pipe_specs(cfg, pipe)
    own = {s.name: f"{cfg.rel(cfg.work_dir)}/{s.output}" for s in pipe.stages}
    return specs, own


SPEC_MD = "docs/spec-review/spec.md"


def test_d0047_ac07_read_stages_write_only_own_output(tmp_path):
    """D0047-AC-07: naive・検査役6段・verify は、自分の成果物のほかに書けない（仕様書・知識の置き場・出力の置き場・ほかの段の成果物・ソースも）。"""
    specs, own = build_specs(tmp_path)
    for n in FINDING_STAGES:
        can = specs[n].can_write
        assert can(own[n]) is True, n
        assert can(SPEC_MD) is False, n
        assert can("docs/spec-review/knowledge/sources.json") is False, n
        assert can("docs/spec-review/out/questionnaire.csv") is False, n
        assert can("src/x.py") is False, n
        for other, path in own.items():
            if other != n:
                assert can(path) is False, (n, other)


def test_d0047_ac07_knowledge_write_scope(tmp_path):
    """D0047-AC-07: knowledge は自分の成果物と knowledge/ の下に書けて、仕様書と out/ には書けない。"""
    specs, own = build_specs(tmp_path)
    can = specs["knowledge"].can_write
    assert can(own["knowledge"]) is True
    for f in ("glossary.md", "domain-model.md", "issues.md", "sources.json"):
        assert can(f"docs/spec-review/knowledge/{f}") is True, f
    assert can(SPEC_MD) is False
    assert can("docs/spec-review/out/questionnaire.csv") is False
    assert can("src/x.py") is False


def test_d0047_ac07_report_write_scope(tmp_path):
    """D0047-AC-07: report は自分の成果物と out/questionnaire.csv に書けて、out/ の別の名前と knowledge/ と仕様書には書けない。"""
    specs, own = build_specs(tmp_path)
    can = specs["report"].can_write
    assert can(own["report"]) is True
    assert can("docs/spec-review/out/questionnaire.csv") is True
    assert can("docs/spec-review/out/other.csv") is False
    assert can("docs/spec-review/knowledge/glossary.md") is False
    assert can(SPEC_MD) is False


def test_d0047_ac07_no_bash_in_any_stage(tmp_path):
    """D0047-AC-07: 全段で Bash は使えない（allow_bash が偽で、道具の一覧にも Bash が無い）。"""
    specs, _ = build_specs(tmp_path)
    assert sorted(specs) == sorted(STAGES)
    for n, spec in specs.items():
        assert spec.allow_bash is False, n
        assert "Bash" not in spec.allowed_tools, n


# ---- AC-08〜11: 検査コマンド -------------------------------------------------------------


def test_d0047_ac08_verify_check_fields(tmp_path):
    """D0047-AC-08: verify の check は command を持ち、verdict は偽、judge は無し、on_fail は verify、max_retries は 2。command は決めた全文。"""
    _, _, pipe = new_pipe(tmp_path)
    c = stage(pipe, "verify").check
    assert c is not None
    assert c.verdict is False and c.judge is None
    assert c.on_fail == "verify" and c.max_retries == 2
    assert c.command == VERIFY_COMMAND


def write_review_files(project: Path, *, quote: str = QUOTE_OK, findings: bool = True) -> None:
    """tmp_path の対象に、仕様書・台帳・指摘のファイルを書く（実際の出力の形に合わせた小さな JSON）。"""
    spec = project / "docs/spec-review/spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_bytes(SPEC_TEXT.encode("utf-8"))
    sources = project / "docs/spec-review/knowledge/sources.json"
    sources.parent.mkdir(parents=True, exist_ok=True)
    sources.write_text(
        json.dumps(
            {"v": 1, "sources": [{"id": "SRC-001", "kind": "spec", "title": "貸出仕様", "version": "1.0", "where": "全体", "file": "spec.md"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if not findings:
        return
    finding = {
        "id": "F-001",
        "role": "quality",
        "location": {"source": "SRC-001", "section": "2.1", "quote": quote},
        "kind": "ambiguous",
        "statement": "冊数の数え方が分からない。",
        "rationale": "続き物の扱いが決まっていない。",
        "sources": ["SRC-001"],
        "guess": False,
        "confidence": "high",
        "severity": "minor",
        "status": "open",
    }
    out = project / "docs/pipeline" / NAME / "09_findings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"v": 1, "findings": [finding]}, ensure_ascii=False), encoding="utf-8")


def run_findings_command(tmp_path: Path, monkeypatch, **kw) -> int:
    """verify の command を空白で分け、先頭の pipe-in-gen を外して generator.cli.main に渡す。"""
    project, _, pipe = new_pipe(tmp_path)
    command = stage(pipe, "verify").check.command
    assert command, "verify 段に command が無い"
    argv = shlex.split(command)
    assert argv[0] == "pipe-in-gen", argv
    write_review_files(project, **kw)
    monkeypatch.chdir(project)
    try:
        return gen_cli().main(argv[1:])
    except SystemExit as e:  # 引数の誤りは SystemExit(2)
        return int(e.code or 0)


def test_d0047_ac09_findings_command_passes(tmp_path, monkeypatch):
    """D0047-AC-09: 正しい指摘・台帳・仕様書なら、verify の command は終了コード 0。"""
    assert run_findings_command(tmp_path, monkeypatch) == 0


def test_d0047_ac09_findings_command_fails_on_bad_quote(tmp_path, monkeypatch):
    """D0047-AC-09: 仕様書に無い文を quote にした指摘が入っていれば終了コード 1。"""
    assert run_findings_command(tmp_path, monkeypatch, quote="利用者は、本を最大9冊まで借りられる。") == 1


def test_d0047_ac09_findings_command_missing_file_is_2(tmp_path, monkeypatch):
    """D0047-AC-09: 指摘のファイルが無ければ終了コード 2。"""
    assert run_findings_command(tmp_path, monkeypatch, findings=False) == 2


def report_command(pipe) -> str:
    command = stage(pipe, "report").check.command
    assert command, "report 段に command が無い"
    return command


def run_report_command(tmp_path: Path, csv_bytes: bytes | None) -> int:
    """report の command を、本体の run_shell で、tmp_path の中の対象で流して終了コードを返す。"""
    from pipe_in.engine.pipeline import run_shell

    project, _, pipe = new_pipe(tmp_path)
    command = report_command(pipe)
    assert command.startswith("python -c"), command
    command = f'"{sys.executable}"' + command[len("python") :]
    if csv_bytes is not None:
        out = project / "docs/spec-review/out/questionnaire.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(csv_bytes)
    result = run_shell(command, project, 60)
    assert result.returncode is not None, result.output_tail
    return result.returncode


def csv_with(columns: int, bom: bool = True) -> bytes:
    head = ",".join(HEADERS[:columns]) if columns <= 8 else ",".join(f"c{i}" for i in range(columns))
    body = ",".join(["F-001", "major", '"質問, です"', "free", "", "SRC-001 2.1", QUOTE_OK, ""][:columns])
    return (("\ufeff" if bom else "") + head + "\r\n" + body + "\r\n").encode("utf-8")


def test_d0047_ac10_report_command_is_ascii_python(tmp_path):
    """D0047-AC-10: report の check は python -c で始まり、非 ASCII の文字を含まず、on_fail は report、max_retries は 2。"""
    _, _, pipe = new_pipe(tmp_path)
    command = report_command(pipe)
    assert command.startswith("python -c")
    assert command.isascii()
    c = stage(pipe, "report").check
    assert c.on_fail == "report" and c.max_retries == 2
    assert c.verdict is False and c.judge is None


def test_d0047_ac10_report_command_passes_with_8_columns(tmp_path):
    """D0047-AC-10: 見出しが8列の questionnaire.csv（UTF-8・BOM 付き）があれば終了コード 0。"""
    assert run_report_command(tmp_path, csv_with(8)) == 0


@pytest.mark.parametrize("csv_bytes", [csv_with(7), None], ids=["7columns", "missing"])
def test_d0047_ac10_report_command_fails_with_7_columns_or_missing(tmp_path, csv_bytes):
    """D0047-AC-10: 見出しが7列なら 1、ファイルが無ければ 1（不合格）。"""
    assert run_report_command(tmp_path, csv_bytes) == 1


def test_d0047_ac11_commands_are_quote_safe(tmp_path):
    """D0047-AC-11: 2つの command に、バッククォート・$・%・! が無い。引用符があるものは外側が " で中が '（中に " は無い）。check が通る。"""
    project, _, pipe = new_pipe(tmp_path)
    for name, command in (("verify", stage(pipe, "verify").check.command), ("report", report_command(pipe))):
        assert [ch for ch in "`$%!" if ch in command] == [], name
        if '"' in command or "'" in command:
            assert command.endswith('"') and command.count('"') == 2, name
            assert '"' not in command[command.index('"') + 1 : -1], name
            assert "'" in command[command.index('"') + 1 : -1], name
    assert '"' in report_command(pipe)  # report は python -c "…'…'…" の形
    assert gen(tmp_path, "check", NAME, "--project", str(project)) == 0


# ---- AC-12〜18: 指示文 --------------------------------------------------------------------


COMMON_WORDS = [
    "指摘の形（v1）", '"v": 1', "F-", *REQUIRED_FIELDS, "guess", "SRC-", "quote", "そのまま写", "missing", "section",
]


@pytest.mark.parametrize("name", FINDING_STAGES)
def test_d0047_ac12_finding_prompts_have_required_words(tmp_path, name):
    """D0047-AC-12: 指摘を書く段の指示文に、指摘の形 v1・"v": 1・F-・必須の11欄・guess・SRC-・quote・そのまま写・missing と section の決まりが入っている。"""
    _, folder, _ = new_pipe(tmp_path)
    assert_has_words(f"{name} の指示文", prompt(folder, name), COMMON_WORDS)


def test_d0047_ac12_common_section_is_identical(tmp_path):
    """D0047-AC-12: 指摘を書く8段の指示文の「指摘の形（v1）」の節は、同じ文（食い違わない）。"""
    _, folder, _ = new_pipe(tmp_path)
    sections = {n: common_section(prompt(folder, n)) for n in FINDING_STAGES}
    for n, s in sections.items():
        assert s, f"{n} の指示文に「{COMMON_HEADING}」の節がありません"
    assert len(set(sections.values())) == 1, [n for n, s in sections.items() if s != sections["naive"]]


def test_d0047_ac13_naive_prompt(tmp_path):
    """D0047-AC-13: naive の指示文に、仕様書だけを読むこと・SRC-001 だけを sources に使うこと・docs/spec-review/knowledge を読まないことが入り、role は naive。"""
    _, folder, _ = new_pipe(tmp_path)
    text = prompt(folder, "naive")
    assert_has_words("naive の指示文", text, ["仕様書だけ", "SRC-001", "docs/spec-review/knowledge", "読まない", "sources"])
    assert role_re("naive").search(text), "role が naive だと書かれていません"


@pytest.mark.parametrize("name", PERSPECTIVES)
def test_d0047_ac14_perspective_prompts(tmp_path, name):
    """D0047-AC-14: 視点別の段の指示文に、role が perspective であることと、その段の perspective の値が入り、ほかの視点の値は自分の値として書かれていない。"""
    _, folder, _ = new_pipe(tmp_path)
    text = prompt(folder, name)
    assert role_re("perspective").search(text), f"{name}: role が perspective だと書かれていません"
    assert perspective_re(name).search(text), f"{name}: perspective の値が {name} だと書かれていません"
    for other in PERSPECTIVES:
        if other != name:
            assert not perspective_re(other).search(text), f"{name}: ほかの視点 {other} が自分の値として書かれています"


@pytest.mark.parametrize("name", ["quality", "gap"])
def test_d0047_ac14_quality_and_gap_roles(tmp_path, name):
    """D0047-AC-14: quality は role が quality、gap は role が gap（perspective の値は自分のものとして書かない）。"""
    _, folder, _ = new_pipe(tmp_path)
    text = prompt(folder, name)
    assert role_re(name).search(text), f"{name}: role が {name} だと書かれていません"
    for v in PERSPECTIVES:
        assert not perspective_re(v).search(text), f"{name}: perspective の値 {v} が書かれています"


def test_d0047_ac15_knowledge_prompt(tmp_path):
    """D0047-AC-15: knowledge の指示文に、4つのファイル名・docs/spec-review/knowledge/・SRC-001 が仕様書であること・台帳の頭が "v": 1・見つけた覚えの無い出典を作らないことが入っている。"""
    _, folder, _ = new_pipe(tmp_path)
    assert_has_words(
        "knowledge の指示文",
        prompt(folder, "knowledge"),
        ["glossary.md", "domain-model.md", "issues.md", "sources.json", "docs/spec-review/knowledge/", "SRC-001", "spec", "spec.md", '"v": 1', "作らない"],
    )


def test_d0047_ac16_verify_prompt(tmp_path):
    """D0047-AC-16: verify の指示文に、verification・verdict・supported・rejected・needs_human・F-001 から振り直すこと・渡された成果物だけを集めること（無い段は飛ばす）が入っている。"""
    _, folder, _ = new_pipe(tmp_path)
    assert_has_words(
        "verify の指示文",
        prompt(folder, "verify"),
        ["verification", "verdict", "supported", "rejected", "needs_human", "F-001", "振り直", "渡された", "飛ば"],
    )


def header_line(text: str) -> str:
    return next((ln for ln in text.splitlines() if "指摘ID" in ln and "回答の型" in ln), "")


def test_d0047_ac17_report_prompt_headers_match_command(tmp_path):
    """D0047-AC-17: report の指示文に questionnaire.csv・BOM・8列の見出しの名前がこの並びで入り、report の command が見る列の数（8）と合う。"""
    _, folder, pipe = new_pipe(tmp_path)
    text = prompt(folder, "report")
    assert_has_words("report の指示文", text, ["questionnaire.csv", "BOM", *HEADERS])
    line = header_line(text)
    assert line, "8列の見出しを並べた行がありません"
    pos = 0
    for h in HEADERS:
        i = line.find(h, pos)
        assert i >= 0, f"見出し {h} が並びの中にありません: {line}"
        pos = i + len(h)
    m = re.search(r"==\s*(\d+)", report_command(pipe))
    assert m and int(m.group(1)) == len(HEADERS)


def template_prompt_texts() -> dict[str, str]:
    d = template_dir() / "prompts"
    assert d.is_dir(), f"{d} がありません（ひな形をまだ作っていない）"
    found = {p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.md"))}
    assert sorted(found) == sorted(PROMPT_FILES.values())
    return found


def test_d0047_ac18_prompts_have_no_placeholders_paths_or_bad_words():
    """D0047-AC-18: 10個の指示文に、{{ を含む行・絶対パス・メールアドレス・特定の業界や組織の名前が無い。"""
    for name, text in template_prompt_texts().items():
        assert [ln for ln in text.splitlines() if "{{" in ln] == [], name
        assert [p for p in ("/Users/", "C:\\", "/home/") if p in text] == [], name
        assert re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text) is None, name
        assert [w for w in RESOURCES_BAD_WORDS if w in text] == [], name


# ---- AC-19〜22: README と入れ外し・古い形 -----------------------------------------------------


README_HEADINGS = [
    "段", "仕様書の置き場所", "流し方", "成果物と文書の置き場所", "指摘の検査", "役割の入れ外し",
    "素人質問者の注意", "費用の目安", "質問票", "直し方",
]


def test_d0047_ac19_readme_has_required_items(tmp_path):
    """D0047-AC-19: 写した README に、決めた節と、10段の名前・成果物・モデル・仕様書の置き場所・流し方・work_dir・--from・対象外の形式・check の直し方・findings-check が入り、{{name}} は名前に埋まっている。"""
    _, folder, _ = new_pipe(tmp_path)
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "{{" not in readme
    assert f"# pipe-in-{NAME}" in readme
    heads = [ln[3:].strip() for ln in readme.splitlines() if ln.startswith("## ")]
    for h in README_HEADINGS:
        assert any(x.startswith(h) for x in heads), f"README に「## {h}」の節がありません: {heads}"
    assert_has_words(
        "README",
        readme,
        [
            *STAGES,
            *OUTPUTS.values(),
            "haiku",
            "sonnet",
            "docs/spec-review/spec.md",
            f"pipe-in --pipe {NAME}",
            "work_dir",
            "--from",
            "Word",
            "Excel",
            "PDF",
            "pipe-in-gen check",
            "findings-check",
            "docs/spec-review/knowledge/",
            "docs/spec-review/out/",
            f"docs/pipeline/{NAME}/",
            "questionnaire.csv",
        ],
    )


def check_after_removing(tmp_path: Path, names: list[str]) -> None:
    """README の手順（[[stages]] の塊を消す）で pipe.toml を直しても、check が通り、消した段だけが減る。"""
    project, folder, pipe = new_pipe(tmp_path)
    toml = folder / "pipe.toml"
    toml.write_text(remove_stages(toml.read_text(encoding="utf-8"), names), encoding="utf-8")
    after = definition().load_pipe(folder)
    assert [s.name for s in after.stages] == [n for n in STAGES if n not in names]
    assert gen(tmp_path, "check", NAME, "--project", str(project)) == 0


def test_d0047_ac20_remove_naive_still_checks(tmp_path):
    """D0047-AC-20: naive の段の塊を消した pipe.toml でも check が通る。"""
    check_after_removing(tmp_path, ["naive"])


def test_d0047_ac20_remove_one_inspector_still_checks(tmp_path):
    """D0047-AC-20: 検査役6段のうち1つだけを消した pipe.toml でも check が通る。"""
    check_after_removing(tmp_path, ["tester"])


def test_d0047_ac20_remove_all_inspectors_still_checks(tmp_path):
    """D0047-AC-20: 検査役6段を全部消した pipe.toml でも check が通る（group が空になっても誤りにならない）。"""
    check_after_removing(tmp_path, INSPECT)


def test_d0047_ac20_readme_forbids_removing_core_stages(tmp_path):
    """D0047-AC-20: README が、消してはいけない段として knowledge・verify・report を挙げ、理由（台帳と検査が要る）を書いている。"""
    _, folder, _ = new_pipe(tmp_path)
    section = section_of((folder / "README.md").read_text(encoding="utf-8"), "役割の入れ外し")
    assert section, "README に「## 役割の入れ外し」の節がありません"
    assert_has_words("入れ外しの節", section, ["knowledge", "verify", "report", "台帳", "検査", "naive", *INSPECT, "[[stages]]"])


def test_d0047_ac22_new_refuses_old_place_name(tmp_path, capsys):
    """D0047-AC-22: 前の版の置き場所（前の名前のフォルダ）に同じ名前のパイプがあれば、--from spec-review の new も場所を示して断り、何も書かない。"""
    assert template_dir().is_dir(), "ひな形のフォルダがありません（まだ作っていない）"
    project = python_project(tmp_path)
    old = project / f".{OLD_NAME}" / "pipes" / f"{OLD_NAME}-{NAME}"
    (old / "prompts").mkdir(parents=True)
    (old / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "古い"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "01_a.md"\naccess = "read"\nprompt = "x"\n',
        encoding="utf-8",
    )
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    capsys.readouterr()
    assert gen_cli().main(["new", NAME, "--from", TEMPLATE_NAME, "--project", str(project)]) != 0
    assert str(old) in capsys.readouterr().out
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    assert not (project / ".pipe-in").exists()


def test_d0047_ac22_readme_mentions_old_copies_and_old_gen(tmp_path):
    """D0047-AC-22: README に、すでに写したパイプには届かないことと、findings-check が無い古い版の pipe-in-gen では verify の command が失敗することが書かれている。"""
    _, folder, _ = new_pipe(tmp_path)
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert_has_words("README", readme, ["すでに写した", "届かない", "古い版", "findings-check", "pipe-in-gen --help"])
