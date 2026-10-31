"""GitHub の PR と issue のテンプレートと、その決まり（D0055）。

- PR のテンプレート（`.github/pull_request_template.md`）の節・注意書き・Mermaid の見本
- issue forms（`.github/ISSUE_TEMPLATE/bug.yml`・`feature.yml`）と `config.yml`
- 決まりを書いた文書（workflow.md の「7. PR と issue」・specs.md・design.md・CLAUDE.md・SKILL.md）

リポジトリの実物は読むだけで、書かない。SDK とネットワークは使わない。
YAML は依存を足さず、`tests/test_ci_workflow.py` の小さな読み手で読む（範囲の外の書き方は例外になる）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_ci_workflow import YamlUnsupported, parse_yaml
from test_skill_tidy import lacking, line_with, need_section, parse_headings, read_doc

ROOT = Path(__file__).resolve().parents[1]
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
ISSUE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
BUG_FORM = ISSUE_DIR / "bug.yml"
FEATURE_FORM = ISSUE_DIR / "feature.yml"
ISSUE_CONFIG = ISSUE_DIR / "config.yml"
WORKFLOW_MD = ROOT / "docs" / "development" / "workflow.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
SPECS_MD = ROOT / "docs" / "development" / "specs.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
SKILL_MD = ROOT / ".claude" / "skills" / "pipe-in" / "SKILL.md"

PR_SECTIONS = (
    "何を変えたか",
    "なぜ（決定の記録・関わる issue）",
    "受け入れ基準と確かめたテスト",
    "確かめたこと（テスト・手で・実機）",
    "図（任意）",
    "公開してよいかの確認",
)
AREAS = ("本体", "ジェネレーター", "プラグイン", "拡張", "文書")
FORMS = {"bug": BUG_FORM, "feature": FEATURE_FORM}


# ---- 小さな判定（純粋な関数） --------------------------------------------------


def h2_titles(md: str) -> list[str]:
    """2段の見出しの題を上から。``` で囲んだコードの中は数えない。"""
    return [h.title for h in parse_headings(md) if h.depth == 2]


MERMAID_BLOCK = re.compile(r"^```mermaid[^\n]*\n.*?^```[ \t]*$", re.M | re.S)


def mermaid_blocks(md: str) -> list[tuple[int, int]]:
    """```mermaid から閉じの ``` までの位置（始まり・終わり）。"""
    return [(m.start(), m.end()) for m in MERMAID_BLOCK.finditer(md)]


def inside_comment(md: str, start: int, end: int) -> bool:
    """start から end までが、丸ごと1つの HTML コメントの中にあるか。"""
    opened = md.rfind("<!--", 0, start)
    if opened < 0:
        return False
    closed = md.find("-->", opened + len("<!--"))
    return closed >= end


COMMENT_MARK = re.compile(r"<!--|-->")


def comment_mark_problems(md: str) -> list[str]:
    """コメントの始まりと終わりの印が、同じ数で交互に出てくるか（入れ子・閉じ忘れ・余った閉じが無いか）。"""
    problems: list[str] = []
    depth = 0
    for m in COMMENT_MARK.finditer(md):
        line = md.count("\n", 0, m.start()) + 1
        if m.group() == "<!--":
            if depth:
                problems.append(f"{line} 行目：コメントの中でまたコメントが始まる")
            depth += 1
        else:
            if not depth:
                problems.append(f"{line} 行目：始まりの無い閉じの印")
            else:
                depth -= 1
    if depth:
        problems.append("閉じていないコメントがある")
    return problems


ID_CHARS = re.compile(r"[A-Za-z0-9_-]+")


def form_problems(form) -> list[str]:
    """issue form の形の問題を文で返す。空なら守っている。"""
    if not isinstance(form, dict):
        return ["form が対応表になっていない"]
    problems = [f"{key} が無い" for key in ("name", "description", "body") if not form.get(key)]
    body = form.get("body")
    if not body:
        return problems
    if not isinstance(body, list):
        return [*problems, "body が一覧になっていない"]
    seen: set[str] = set()
    for i, item in enumerate(body, 1):
        if not isinstance(item, dict):
            problems.append(f"{i} 番目の欄が対応表になっていない")
            continue
        kind = item.get("type")
        fid = item.get("id")
        if not kind:
            problems.append(f"{i} 番目の欄に type が無い")
        if kind == "markdown":
            if fid:
                problems.append(f"{i} 番目の markdown の欄に id がある（{fid}）")
            continue
        if not fid:
            problems.append(f"{i} 番目の欄（{kind}）に id が無い")
            continue
        if fid in seen:
            problems.append(f"id が重なっている（{fid}）")
        seen.add(fid)
        if not ID_CHARS.fullmatch(str(fid)):
            problems.append(f"id に英数字・-・_ 以外の字がある（{fid}）")
    return problems


def field(form: dict, fid: str, where: str = "form") -> dict:
    """その id の欄。無ければ「欄が無い」でそのテストだけを落とす。"""
    for item in form.get("body") or []:
        if isinstance(item, dict) and item.get("id") == fid:
            return item
    pytest.fail(f"{where} に id「{fid}」の欄が無い", pytrace=False)


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def is_required(item: dict) -> bool:
    return as_dict(item.get("validations")).get("required") == "true"


def load_yaml(path: Path):
    text = read_doc(path)
    try:
        return parse_yaml(text)
    except YamlUnsupported as e:
        pytest.fail(f"{path.relative_to(ROOT).as_posix()} を小さな読み手で読めない：{e}", pytrace=False)


def load_form(name: str) -> dict:
    form = load_yaml(FORMS[name])
    assert isinstance(form, dict), f"{name}.yml が対応表になっていない: {form!r}"
    return form


def pr_template() -> str:
    return read_doc(PR_TEMPLATE)


# ---- AC-01：PR のテンプレートの節 ----------------------------------------------


def test_D0055_AC_01_PRのテンプレートに6つの節がこの順である():
    """D0055-AC-01: PR のテンプレートがあり、2段の見出しが6つの節とちょうど同じ並び。"""
    assert h2_titles(pr_template()) == list(PR_SECTIONS)


def sample_pr(titles) -> str:
    return "<!--\nタイトルの説明\n-->\n\n" + "".join(f"## {t}\n\n本文\n\n" for t in titles)


def test_D0055_AC_01_見本_節の抜けと入れ替えを見つける_守る():
    """D0055-AC-01: 並びの比べは、そろった見本を通し、1つ抜いた見本と2つ入れ替えた見本を違いとして返す。コードの囲みの中の見出しは数えない。（今のまま通る。守る）"""
    good = list(PR_SECTIONS)
    assert h2_titles(sample_pr(good)) == good
    dropped = good[:2] + good[3:]
    assert h2_titles(sample_pr(dropped)) != good
    swapped = [good[1], good[0], *good[2:]]
    assert h2_titles(sample_pr(swapped)) != good
    in_code = sample_pr(good) + "```text\n## 余分な見出し\n```\n"
    assert h2_titles(in_code) == good


# ---- AC-02・03：なぜ・受け入れ基準 --------------------------------------------


def test_D0055_AC_02_なぜの節に決定の記録とissueの場所がある():
    """D0055-AC-02: 「なぜ」の節の本文に、決定の記録の番号（Dnnnn）と issue（#番号）を書く場所がある。"""
    body = need_section(pr_template(), "なぜ", where="pull_request_template.md", depth=2)
    missing = lacking(body, ["Dnnnn", "#番号"])
    assert not missing, f"「なぜ」の節に足りない語: {missing}"


TABLE_HEAD = re.compile(r"^\|\s*AC\s*\|\s*確かめたテスト\s*\|\s*結果\s*\|\s*$")
TABLE_RULE = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")


def test_D0055_AC_03_受け入れ基準の節にACとテストと結果の表がある():
    """D0055-AC-03: 「受け入れ基準と確かめたテスト」の節に、AC・確かめたテスト・結果の見出しの行と区切りの行と、Dnnnn-AC- の見本の行がある。"""
    body = need_section(pr_template(), "受け入れ基準と確かめたテスト", where="pull_request_template.md", depth=2)
    lines = [ln.strip() for ln in body.splitlines()]
    assert any(TABLE_HEAD.match(ln) for ln in lines), "| AC | 確かめたテスト | 結果 | の見出しの行が無い"
    assert any(TABLE_RULE.match(ln) for ln in lines), "表の区切りの行が無い"
    assert any(ln.startswith("|") and "Dnnnn-AC-" in ln for ln in lines), "Dnnnn-AC- の見本の行が無い"


# ---- AC-04：図（任意）と Mermaid の見本 ---------------------------------------


def test_D0055_AC_04_図の節は任意で_mermaidの見本が1つコメントの中にある():
    """D0055-AC-04: 「図（任意）」の節に「任意」とあり、mermaid の見本がちょうど1つ、丸ごと1つのコメントの中にある。見本に細い矢印が無く、ファイル全体でコメントの印が交互に出てくる。"""
    md = pr_template()
    body = need_section(md, "図（任意）", where="pull_request_template.md", depth=2)
    assert "任意" in body, "「図（任意）」の節の本文に「任意」が無い"
    assert len(mermaid_blocks(md)) == 1, f"ファイル全体の mermaid の見本の数: {len(mermaid_blocks(md))}"
    blocks = mermaid_blocks(body)
    assert len(blocks) == 1, f"「図（任意）」の節の mermaid の見本の数: {len(blocks)}"
    start, end = blocks[0]
    assert "-->" not in body[start:end], "見本の中に細い矢印（コメントの閉じと同じ文字）がある"
    assert inside_comment(body, start, end), "見本が丸ごと1つのコメントの中に無い"
    assert comment_mark_problems(md) == []


SAMPLE_FIG = "## 図（任意）\n図は任意。\n\n<!--\n```mermaid\nflowchart LR\n  A[要件定義] {arrow} B[設計]\n```\n-->\n"


def test_D0055_AC_04_見本_細い矢印でコメントが閉じる図を見つける_守る():
    """D0055-AC-04: 細い矢印を入れた見本ではコメントの中と判定せず、太い矢印なら中と判定する。コメントの外の図も中としない。（今のまま通る。守る）"""
    thin = SAMPLE_FIG.format(arrow="-->")
    thick = SAMPLE_FIG.format(arrow="==>")
    (s, e), = mermaid_blocks(thin)
    assert not inside_comment(thin, s, e)
    (s, e), = mermaid_blocks(thick)
    assert inside_comment(thick, s, e)
    bare = "## 図（任意）\n\n```mermaid\nflowchart LR\n  A ==> B\n```\n"
    (s, e), = mermaid_blocks(bare)
    assert not inside_comment(bare, s, e)
    closed_before = "<!-- 説明 -->\n\n```mermaid\nflowchart LR\n  A ==> B\n```\n"
    (s, e), = mermaid_blocks(closed_before)
    assert not inside_comment(closed_before, s, e)


def test_D0055_AC_04_見本_コメントの印の閉じ忘れと入れ子と余った閉じを見つける_守る():
    """D0055-AC-04: 印の検査は、交互の見本を通し、閉じ忘れ・入れ子・始まりの無い閉じをそれぞれ問題として返す。（今のまま通る。守る）"""
    assert comment_mark_problems(SAMPLE_FIG.format(arrow="==>")) == []
    assert comment_mark_problems("<!-- a\n## 見出し\n")
    assert comment_mark_problems("<!-- a <!-- b --> -->")
    assert comment_mark_problems("本文 --> 本文")
    assert comment_mark_problems(SAMPLE_FIG.format(arrow="-->")), "細い矢印で余った閉じを見つける"


# ---- AC-05：issue forms の形とラベル -------------------------------------------


def test_D0055_AC_05_不具合と機能の要望のformが1つずつある():
    """D0055-AC-05: bug.yml と feature.yml があり、小さな読み手で読め、name がそれぞれ「不具合」「機能の要望」。"""
    assert load_form("bug").get("name") == "不具合"
    assert load_form("feature").get("name") == "機能の要望"


@pytest.mark.parametrize("name", ["bug", "feature"])
def test_D0055_AC_05_formの欄はtypeとidの決まりを守る(name):
    """D0055-AC-05: name・description・body があり、欄は type を持ち、markdown 以外は id を持ち markdown は持たない。id は重ならず、英数字・-・_ だけ。"""
    assert form_problems(load_form(name)) == []


def test_D0055_AC_05_formのラベルは既定のbugとenhancementだけ():
    """D0055-AC-05: 不具合の form は bug だけ、機能の要望の form は enhancement だけを付ける（GitHub の既定のラベル）。"""
    assert load_form("bug").get("labels") == ["bug"]
    assert load_form("feature").get("labels") == ["enhancement"]


GOOD_FORM = {
    "name": "不具合",
    "description": "説明",
    "labels": ["bug"],
    "body": [
        {"type": "markdown", "attributes": {"value": "注意"}},
        {"type": "textarea", "id": "what-happened", "attributes": {"label": "起きたこと"}},
        {"type": "input", "id": "version_1", "attributes": {"label": "版"}},
    ],
}


def with_body(*items) -> dict:
    return {**GOOD_FORM, "body": [*GOOD_FORM["body"], *items]}


def test_D0055_AC_05_見本_idの重なりとmarkdownのidを見つける_守る():
    """D0055-AC-05: 形の検査は、正しい見本を通し、id の重なり・markdown の id・id の無い入力の欄・使えない字の id・type の無い欄・name の無い form をそれぞれ問題として返す。（今のまま通る。守る）"""
    assert form_problems(GOOD_FORM) == []
    cases = {
        "id が重なっている": with_body({"type": "textarea", "id": "what-happened"}),
        "markdown の欄に id がある": with_body({"type": "markdown", "id": "note", "attributes": {"value": "x"}}),
        "に id が無い": with_body({"type": "textarea", "attributes": {"label": "x"}}),
        "以外の字がある": with_body({"type": "input", "id": "版"}),
        "type が無い": with_body({"id": "plain"}),
        "name が無い": {k: v for k, v in GOOD_FORM.items() if k != "name"},
        "body が無い": {k: v for k, v in GOOD_FORM.items() if k != "body"},
    }
    for expect, form in cases.items():
        problems = form_problems(form)
        assert any(expect in p for p in problems), f"{expect} を見つけない: {problems}"
    assert form_problems(["一覧"]) != []


# ---- AC-06：必須の欄 -----------------------------------------------------------


def test_D0055_AC_06_不具合のformは起きたことと再現の手順が必須():
    """D0055-AC-06: 不具合の form に起きたこと・期待したこと・再現の手順の欄があり、起きたことと再現の手順は required が true。"""
    form = load_form("bug")
    happened = field(form, "what-happened", "bug.yml")
    field(form, "expected", "bug.yml")
    steps = field(form, "steps", "bug.yml")
    assert is_required(happened), "起きたこと（what-happened）が必須になっていない"
    assert is_required(steps), "再現の手順（steps）が必須になっていない"


def test_D0055_AC_06_機能の要望のformは困っていることとしてほしいことが必須():
    """D0055-AC-06: 機能の要望の form に困っていること・してほしいことの欄があり、どちらも required が true。"""
    form = load_form("feature")
    assert is_required(field(form, "problem", "feature.yml")), "困っていること（problem）が必須になっていない"
    assert is_required(field(form, "proposal", "feature.yml")), "してほしいこと（proposal）が必須になっていない"


# ---- AC-07：触る側 -------------------------------------------------------------


@pytest.mark.parametrize("name", ["bug", "feature"])
def test_D0055_AC_07_触る側の選択に5つの側がある(name):
    """D0055-AC-07: area の欄が dropdown で、選べるものに本体・ジェネレーター・プラグイン・拡張・文書が入っている。"""
    item = field(load_form(name), "area", f"{name}.yml")
    assert item.get("type") == "dropdown", f"area の欄の type: {item.get('type')!r}"
    options = as_dict(item.get("attributes")).get("options")
    assert isinstance(options, list) and options, f"area の欄に選べるもの（attributes.options）が無い: {options!r}"
    missing = [w for w in AREAS if not any(w in str(o) for o in options)]
    assert not missing, f"選べるものに無い側: {missing}"


# ---- AC-08：config.yml ---------------------------------------------------------


def test_D0055_AC_08_config_ymlは白紙のissueを許す():
    """D0055-AC-08: config.yml があり、blank_issues_enabled が true。"""
    config = load_yaml(ISSUE_CONFIG)
    assert isinstance(config, dict) and config.get("blank_issues_enabled") == "true", f"config.yml: {config!r}"


# ---- AC-09：秘密とパスの注意 -----------------------------------------------------


def test_D0055_AC_09_PRのテンプレートに秘密とパスの注意がある():
    """D0055-AC-09: PR のテンプレートに「秘密」と「パス」を両方含む行がある。"""
    lines = [ln for ln in pr_template().splitlines() if "秘密" in ln and "パス" in ln]
    assert lines, "「秘密」と「パス」を両方含む行が無い"


def notice_texts(form: dict) -> list[str]:
    """markdown の欄の value と、どの欄の description も集める。"""
    out: list[str] = []
    for item in form.get("body") or []:
        if not isinstance(item, dict):
            continue
        attrs = as_dict(item.get("attributes"))
        if item.get("type") == "markdown":
            out.append(str(attrs.get("value", "")))
        out.append(str(attrs.get("description", "")))
    return out


@pytest.mark.parametrize("name", ["bug", "feature"])
def test_D0055_AC_09_formに秘密とパスの注意がある(name):
    """D0055-AC-09: markdown の欄の value か、どれかの欄の description に、「秘密」と「パス」を両方含む文がある。"""
    texts = [t for t in notice_texts(load_form(name)) if "秘密" in t and "パス" in t]
    assert texts, f"{name}.yml に「秘密」と「パス」を両方含む注意が無い"


# ---- AC-11・12：workflow.md と specs.md の決まり ---------------------------------


def pr_issue_section() -> str:
    return need_section(read_doc(WORKFLOW_MD), "7. PR と issue", where="workflow.md", depth=2)


def test_D0055_AC_11_workflow_mdにPRとissueの節があり決まりの語がある():
    """D0055-AC-11: workflow.md の「7. PR と issue」の節に、タイトル・テンプレートの置き場所・mermaid・任意・秘密の語がある。"""
    words = ["タイトルはコミットの1行目と同じ形", ".github/pull_request_template.md", ".github/ISSUE_TEMPLATE/", "mermaid", "任意", "秘密"]
    missing = lacking(pr_issue_section(), words)
    assert not missing, f"「7. PR と issue」に足りない語: {missing}"


def test_D0055_AC_12_Mermaidの決まりに図を勧める場面がある():
    """D0055-AC-12: 同じ節に、図を勧める場面（変更の流れ・依存の向き・状態の移り変わり）と、決定の記録でも勧めることと、コメントの中の太い矢印がある。"""
    missing = lacking(pr_issue_section(), ["変更の流れ", "依存の向き", "状態の移り変わり", "決定の記録", "==>"])
    assert not missing, f"「7. PR と issue」に足りない語: {missing}"


def test_D0055_AC_12_specs_mdの決定の記録の節に図は任意とある():
    """D0055-AC-12: specs.md の「決定の記録」の節に、Mermaid の図と「任意」がある。"""
    body = need_section(read_doc(SPECS_MD), "決定の記録", where="specs.md", depth=2)
    assert "mermaid" in body.lower(), "specs.md の「決定の記録」の節に Mermaid が無い"
    assert "任意" in body, "specs.md の「決定の記録」の節に「任意」が無い"


# ---- AC-13・14・15：置き場所の表・CLAUDE.md・SKILL.md ----------------------------


def test_D0055_AC_13_designの置き場所の表にテンプレートの行がある():
    """D0055-AC-13: design.md の表の1行に、.github/pull_request_template.md と .github/ISSUE_TEMPLATE/ の両方がある。"""
    rows = [
        ln
        for ln in read_doc(DESIGN_MD).splitlines()
        if ln.lstrip().startswith("|") and ".github/pull_request_template.md" in ln and ".github/ISSUE_TEMPLATE/" in ln
    ]
    assert rows, "design.md の表に PR と issue のテンプレートの行が無い"


def test_D0055_AC_14_CLAUDE_mdにPRとissueの決まりへの案内がある():
    """D0055-AC-14: CLAUDE.md の「7. PR と issue」を含む行が workflow.md を指す。"""
    line = line_with(read_doc(CLAUDE_MD), "7. PR と issue", "CLAUDE.md")
    assert "workflow.md" in line, f"その行に workflow.md が無い: {line}"


def finish_section() -> str:
    return need_section(read_doc(SKILL_MD), "決定の記録と仕上げ", where="SKILL.md", depth=3)


def test_D0055_AC_15_仕上げにPRの本文の案を見せる手順がある():
    """D0055-AC-15: SKILL.md の「決定の記録と仕上げ」に、PR の本文の案をテンプレートに沿って見せ、Mermaid の案も入れる手順がある。"""
    missing = lacking(finish_section(), ["PR の本文の案", ".github/pull_request_template.md", "Mermaid"])
    assert not missing, f"「決定の記録と仕上げ」に足りない語: {missing}"


def test_D0055_AC_15_仕上げにpushは人に言われてからの文が残る_守る():
    """D0055-AC-15: 同じ節に、push は人に言われるまでしない、の文が残る。（今のまま通る。守る）"""
    missing = lacking(finish_section(), ["push", "人に言われるまで"])
    assert not missing, f"「決定の記録と仕上げ」に足りない語: {missing}"
