"""D0096-AC-04〜09：会話の道の能力表に足す「段の成果物の名前」の行（pipe_in/pipe/capability.py の PipeStage.output）。

Claude Code は、サブエージェントからの Write で、名前が report・summary・findings・analysis で始まり .md で終わるファイル
（大文字と小文字を区別しない）を断る。会話の道の段はサブエージェント（pipe-stage）で流れるので、その名前の output を持つ段は、
始める前に断る。SDK の道は今までどおり流す（能力表の sdk の列は「効く」のまま）。

SDK は呼ばない（no_sdk）。パイプは tmp_path の下に作り、司会役は外の入口 chat_cmd.main（chat_support.Run）だけを通す。
ひな形と見本（generator/templates/・examples/）は読むだけ。
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
from chat_support import Run, make_pipe, no_sdk, pipe_toml, stage_toml  # noqa: F401
from test_capability import doc_tables, value_items

from pipe_in.engine.config import load_config
from pipe_in.pipe import capability, chat
from pipe_in.pipe import definition as pd
from pipe_in.pipe.capability import REFUSE, WORKS, Row

pytestmark = pytest.mark.usefixtures("no_sdk")

ROOT = Path(__file__).resolve().parent.parent

# 断られる名前と、断られない名前（要件定義の D0096-AC-05・06）
REFUSED_OUTPUTS = ["summary.md", "Report.md", "FINDINGS_x.md", "analysis-1.md"]
ALLOWED_OUTPUTS = ["01_summary.md", "10_report.md", "summary.txt", "my_report.md", "summarize.md"]

# 設計 2.1 の断る文の後ろ半分（理由と直し方）。段の名前と値の後ろに続く
OUTPUT_REASON = (
    "（Claude Code が、サブエージェントからの report・summary・findings・analysis で始まる .md の書き込みを断るため）。"
    "頭に段の順の番号を付けてください（例 01_summary.md）"
)


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def plain_refused(name: str) -> bool:
    """素朴な確かめ（頭が SUBAGENT_REFUSED_HEADS で .md で終わる）。判断の本体は capability.subagent_refused_name で、
    これは判断の本体と別の素朴な形で AC-04 の守りを確かめ、本体の誤りに引きずられないために使う。"""
    base = re.split(r"[\\/]", name)[-1].lower()
    return base.endswith(".md") and base.startswith(capability.SUBAGENT_REFUSED_HEADS)


# ---- AC-04：ひな形と見本の名前（今の作りのままで通る。守る） ---------------------------------------------


def template_and_example_names() -> list[tuple[str, str]]:
    """(pipe.toml の場所, 名前) の並び。output・prompt_file と、同じフォルダの prompts/*.md の名前。"""
    found: list[tuple[str, str]] = []
    tomls = sorted((ROOT / "generator" / "templates").glob("*/pipe.toml")) + sorted((ROOT / "examples").glob("**/pipe.toml"))
    for path in tomls:
        where = path.relative_to(ROOT).as_posix()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for stage in data.get("stages", []):
            for key in ("output", "prompt_file"):
                if isinstance(stage.get(key), str):
                    found.append((where, stage[key]))
        found += [(where, f"prompts/{p.name}") for p in sorted((path.parent / "prompts").glob("*.md"))]
    return found


def test_d0096_ac04_templates_and_examples_avoid_refused_names():
    """D0096-AC-04: ひな形（generator/templates/）と見本（examples/）のパイプの output・prompt_file と prompts/*.md の名前が、
    Claude Code に断られる形に当たらない（今の作りのままで通る。名前の決まりを守り続けるための検査）。"""
    names = template_and_example_names()
    assert len(names) > 20, f"ひな形と見本から名前を読めていない: {names}"
    bad = [(where, n) for where, n in names if capability.subagent_refused_name(n) or plain_refused(n)]
    assert bad == []


# ---- AC-05：断る名前（会話の道） ------------------------------------------------------------------------


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "start"])
@pytest.mark.parametrize("output", REFUSED_OUTPUTS)
def test_d0096_ac05_chat_start_refuses_refused_output_names(tmp_path, output, dry_run):
    """D0096-AC-05: 成果物の名前が summary.md・Report.md・FINDINGS_x.md・analysis-1.md の段を持つパイプは、
    chat start（--dry-run でも）が ok: false・終了コード 1 で断り、文に段の名前・値・直し方（頭に番号。例 01_summary.md）が入る。
    check_pipe の誤りではなく能力表で断る。作業フォルダには何も増えない。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("digest", output=output)))  # check_pipe は通る（make が確かめる）
    before = files(tmp_path)
    out = r.start(*(["--dry-run"] if dry_run else []))
    assert r.code == 1 and out["ok"] is False, out
    message = out["message"]
    assert "誤りがあります" not in message, message
    assert "会話の中では流せない形があります" in message, message
    assert f"段「digest」のoutput（{output}）" in message, message
    assert "番号" in message and "01_summary.md" in message, message
    assert files(tmp_path) == before


@pytest.mark.parametrize(
    "value",
    ["summary.md", "Report.md", "FINDINGS_x.md", "analysis-1.md", "summary.MD", "reportX.md", "docs/summary.md", "docs\\Report.md"],
)
def test_d0096_ac05_refused_name_judgment_true(value):
    """D0096-AC-05: 名前の判断 subagent_refused_name は、名前（最後の / か \\ の後ろ）の頭が report・summary・findings・analysis で
    .md で終わるとき真（大文字と小文字を区別しない）。"""
    assert capability.subagent_refused_name(value) is True


# ---- AC-06：断らない名前 ------------------------------------------------------------------------------


@pytest.mark.parametrize("output", ALLOWED_OUTPUTS)
def test_d0096_ac06_other_names_are_not_refused(tmp_path, output):
    """D0096-AC-06: 成果物の名前が 01_summary.md・10_report.md・summary.txt・my_report.md・summarize.md の段は、
    会話の道で断られない（unsupported が空で、chat start --dry-run が通る）。今の作りのままで通る（断らない側を守る）。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("digest", output=output)))
    pipe = pd.load_pipe(r.pipe_dir)
    assert chat.unsupported(pipe, load_config(tmp_path)) == []
    out = r.start("--dry-run")
    assert r.code == 0 and out["ok"] is True, out


@pytest.mark.parametrize(
    "value",
    [
        "01_summary.md",
        "10_report.md",
        "summary.txt",
        "summary.md.txt",
        "my_report.md",
        "summarize.md",
        "report",
        "analysi.md",
        "",
        "docs/01_summary.md",
        "summary/01_x.md",
        None,
        3,
        ["summary.md"],
    ],
)
def test_d0096_ac06_refused_name_judgment_false(value):
    """D0096-AC-06: 名前の判断は、頭に番号のある名前・.md で終わらない名前・頭が 4 つの語でない名前・空・文字でない値では偽。
    判断を書いたあとも、これらが偽のままであることを守る。"""
    assert capability.subagent_refused_name(value) is False


# ---- AC-07：SDK の道は今までどおり ------------------------------------------------------------------------


def test_d0096_ac07_sdk_side_keeps_working(tmp_path):
    """D0096-AC-07: summary.md の段を持つパイプは、check_pipe が誤りを返さず、能力表の sdk の列で断られない（refusals(actor="sdk") が空）。
    能力表の PipeStage.output の行の sdk は「効く」のまま。今の作りのままで通る（SDK の道を狭めないことを守る）。"""
    d = make_pipe(tmp_path, pipe_toml(stage_toml("summary", output="summary.md")))
    pipe = pd.load_pipe(d)
    assert pd.check_pipe(pipe, tmp_path.resolve()) == []
    assert capability.refusals(pipe, load_config(tmp_path), None, actor="sdk") == []
    rows = [r for r in capability.TABLE if r.key == "PipeStage.output"]
    assert len(rows) == 1 and rows[0].sdk == WORKS


# ---- AC-08：能力表の行の形と、文の位置 ----------------------------------------------------------------------


def output_row() -> Row:
    rows = [r for r in capability.TABLE if r.key == "PipeStage.output"]
    assert len(rows) == 1, "PipeStage.output の行が 1 つではない"
    return rows[0]


def test_d0096_ac08_output_row_shape():
    """D0096-AC-08: PipeStage.output の行は、sdk が効く・chat が断る・scope が stage・path が ("output",)・判断が subagent_report_name で、
    理由・注記・{stage} と {value} を持つ断る文がある。判断の種類は VALUE_TESTS にあり、行は段の断る行の最後（max_budget_usd の次）。"""
    r = output_row()
    assert (r.sdk, r.chat, r.scope, r.path, r.test) == (WORKS, REFUSE, "stage", ("output",), "subagent_report_name")
    assert r.reason.strip() and r.caveat.strip()
    assert "{stage}" in r.sentence and "{value}" in r.sentence
    assert "subagent_report_name" in capability.VALUE_TESTS
    keys = [x.key for x in capability.TABLE]
    assert keys.index("PipeStage.output") == keys.index("PipeStage.max_budget_usd") + 1
    stage_refuse = [x.key for x in capability.TABLE if x.scope == "stage" and x.chat == REFUSE]
    assert stage_refuse[-1] == "PipeStage.output"


def test_d0096_ac08_output_sentence_is_last_in_stage(tmp_path):
    """D0096-AC-08: 成果物の名前の断る文は、段ごとの文の最後（max_budget_usd の次）に出て、値（output の文字）が入る。
    ほかの段の文の並びと中身は今のまま（今の断る文は 1 文字も変わらない）。"""
    toml = pipe_toml(
        stage_toml("first", output="summary.md", extra='group = "g"\nmax_budget_usd = 2.0\n'),
        stage_toml("second", output="Report.md", extra="web = true\n"),
    )
    d = make_pipe(tmp_path, toml, valid=False)
    pipe, cfg = pd.load_pipe(d), load_config(tmp_path)
    assert chat.unsupported(pipe, cfg) == [
        "段「first」のgroup（並列の段）は、会話の中では流せません",
        "段「first」のmax_budget_usd（費用の上限）は、会話の中では守れないので流せません",
        "段「first」のoutput（summary.md）は、会話の中では流せません" + OUTPUT_REASON,
        "段「second」のweb（Web の道具）は、会話の中では流せません",
        "段「second」のoutput（Report.md）は、会話の中では流せません" + OUTPUT_REASON,
    ]


@dataclass
class FakeThing:
    a: int = 0
    b: int = 0


def refuse_row(key: str, test: str) -> Row:
    return Row(key, WORKS, REFUSE, reason="理由", scope="stage", path=("a",), test=test, sentence="段「{stage}」は断ります")


def test_d0096_ac08_check_table_reports_unknown_test():
    """D0096-AC-08: 検査そのものの確かめ。check_table は、知らない判断の種類（magic）を「知らない test: <鍵>（<test>）」と報告し、
    truthy・not_none・ne:<値>・subagent_report_name では報告しない。"""
    plain = Row("FakeThing.b", WORKS, WORKS)
    problems = capability.check_table((refuse_row("FakeThing.a", "magic"), plain), (FakeThing,), extra_keys=())
    assert "知らない test: FakeThing.a（magic）" in problems, problems
    for test in ("truthy", "not_none", "ne:linear", "subagent_report_name"):
        assert capability.check_table((refuse_row("FakeThing.a", test), plain), (FakeThing,), extra_keys=()) == [], test


# ---- AC-08：chat.py は値の形で断る項目を条件の中で読まない -----------------------------------------------------

STRING_METHODS = {"startswith", "endswith", "lower", "upper", "casefold"}


def _reads(node: ast.AST, names: set[str]) -> list[str]:
    """node の下で、項目名を属性（X.output）か getattr / hasattr の 2 つ目の文字列で読む所。"""
    found: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr in names:
            found.append(f".{n.attr}")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "hasattr"):
            arg = n.args[1] if len(n.args) > 1 else None
            if isinstance(arg, ast.Constant) and arg.value in names:
                found.append(f"{n.func.id}(..., {arg.value!r})")
    return found


def value_items_in_conditions(source: str, names: set[str]) -> list[str]:
    """条件（if・while・条件式・assert の判定、内包表記の if、match の対象と case の guard）の中で項目名を読む所と、
    どこであれ X.<項目>.startswith / endswith / lower / upper / casefold の形（変数に入れてから条件にする道を塞ぐ）。"""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        tests: list[ast.AST] = []
        if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            tests.append(node.test)
        elif isinstance(node, ast.comprehension):
            tests += node.ifs
        elif isinstance(node, ast.Match):
            tests.append(node.subject)
        elif isinstance(node, ast.match_case) and node.guard is not None:
            tests.append(node.guard)
        for t in tests:
            found += [f"条件の中で {x}（{getattr(t, 'lineno', '?')} 行目）" for x in _reads(t, names)]
        if isinstance(node, ast.Attribute) and node.attr in STRING_METHODS:
            inner = node.value
            if isinstance(inner, ast.Attribute) and inner.attr in names:
                found.append(f".{inner.attr}.{node.attr}（{node.lineno} 行目）")
    return found


def test_d0096_ac08_chat_py_does_not_branch_on_value_items():
    """D0096-AC-08: 値の形で断る項目（表から取る。今は output）を、pipe_in/pipe/chat.py が条件の中で読まず、名前の形も調べない。
    断るかどうかは能力表だけが決める（D0082）。D0082-AC-10 の属性の検査からこの項目を除いた代わりの検査。"""
    items = value_items()
    assert "output" in items, f"値の形で断る項目を表から取れない: {sorted(items)}"
    source = (ROOT / "pipe_in" / "pipe" / "chat.py").read_text(encoding="utf-8")
    assert value_items_in_conditions(source, items) == []


@pytest.mark.parametrize(
    "source",
    [
        'def f(s):\n    if s.output.lower().startswith("summary"):\n        pass\n',
        "def f(st):\n    return [s for s in st if s.output]\n",
        'def f(s):\n    ok = s.output.endswith(".md")\n    return ok\n',
        'def f(s):\n    while getattr(s, "output"):\n        break\n',
        "def f(s):\n    return 1 if s.output else 2\n",
        "def f(s):\n    assert s.output\n",
        "def f(s):\n    match s.output:\n        case _:\n            pass\n",
        "def f(s, x):\n    match x:\n        case 1 if s.output:\n            pass\n",
        "def f(s):\n    name = s.output.casefold()\n    return name\n",
    ],
    ids=["if-method", "comprehension-if", "endswith", "while-getattr", "ifexp", "assert", "match-subject", "case-guard", "casefold"],
)
def test_d0096_ac08_condition_finder_catches_branch(source):
    """D0096-AC-08: 検査そのものの確かめ。偽の chat.py の文字の、条件の中で output を読む所・名前の形を調べる所を見つける。"""
    assert value_items_in_conditions(source, {"output"}), source


@pytest.mark.parametrize(
    "source",
    [
        'def f(s):\n    return {"output": s.output}\n',
        "def f(ps):\n    return g(ps.output)\n",
        'def f(s):\n    if s.get("output"):\n        pass\n',
        'def f(s, c):\n    return {"a": s.output, **({"c": 1} if c else {})}\n',
        "def f(s):\n    if s.name:\n        return s.output\n",
    ],
    ids=["dict-value", "call-arg", "dict-get", "ifexp-body", "if-body"],
)
def test_d0096_ac08_condition_finder_ignores_plain_reads(source):
    """D0096-AC-08: 検査そのものの確かめ。段の表・成果物の場所に値を読むだけの所（{"output": s.output}・f(ps.output)・条件の本体）は見つけない。"""
    assert value_items_in_conditions(source, {"output"}) == []


# ---- AC-09：docs/guide/pipes.md の断る表 ---------------------------------------------------------------------


def test_d0096_ac09_pipes_md_refuse_table_has_output():
    """D0096-AC-09: docs/guide/pipes.md の「会話の中で流すとき」の断る表に output の行があり、断られる形（4 つの語・.md）と、
    サブエージェントの書き込みを断る理由・直し方（頭に番号）が書かれている。能力表の「断る」にも output がある
    （2 つの集合が同じことは D0082-AC-08 のテストが見る）。"""
    text = (ROOT / "docs" / "guide" / "pipes.md").read_text(encoding="utf-8")
    refuse, _ = doc_tables(text)
    assert "output" in refuse, f"断る表に output が無い: {sorted(refuse)}"
    assert "PipeStage.output" in capability.keys_with(REFUSE)
    m = re.search(r"^## 会話の中で流すとき\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, "「会話の中で流すとき」の節を読めない"
    rows = [ln for ln in m.group(1).splitlines() if ln.startswith("| `output`")]
    assert len(rows) == 1, "断る表に output の行が 1 つではない"
    missing = [w for w in [*capability.SUBAGENT_REFUSED_HEADS, ".md", "サブエージェント", "番号"] if w not in rows[0]]
    assert missing == []
