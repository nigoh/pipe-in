"""指摘の形 v1 と出典の台帳の検査（D0043）：形・出典・引用の一致・役割の決まり・Schema とコードの一致。

SDK は呼ばない。見本はテストの中の辞書（架空の仕様書の文）で作り、リポジトリの実物には書かない。
"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "generator" / "schemas"


def fc():
    from pipe_in_generator import findings_check

    return findings_check


# ---- 見本（架空の仕様書。手元の情報は入れない） ----------------------------------------------------

SPEC_TEXT = (
    "# 貸出管理システム\n"
    "\n"
    "利用者は、本を最大5冊まで借りられる。\n"
    "返却期限は、貸出日から14日とする。\n"
    "延滞した場合の扱いは、別途定める。\n"
    "Library Card を提示する。\n"
    "貸出　期間は、画面に表示する。\n"
)

QUOTE = "利用者は、本を最大5冊まで借りられる。"


def good_sources() -> dict:
    def src(n: int, kind: str, **extra) -> dict:
        return {"id": f"SRC-{n:03d}", "kind": kind, "title": f"資料{n}", "version": "1.0", "where": "第1章", **extra}

    return {
        "v": 1,
        "sources": [
            src(1, "spec", file="spec.md"),
            src(2, "law"),
            src(3, "customer"),
            src(4, "past_case"),
            src(5, "standard"),
            src(6, "public_spec"),
        ],
    }


def good_finding(**override) -> dict:
    f = {
        "id": "F-001",
        "role": "quality",
        "location": {"source": "SRC-001", "section": "2.1", "quote": QUOTE},
        "kind": "ambiguous",
        "statement": "冊数の数え方が分からない。",
        "rationale": "同じ本の続き物を1冊と数えるか決まっていない。",
        "sources": ["SRC-001"],
        "guess": False,
        "confidence": "high",
        "severity": "minor",
        "status": "open",
    }
    f.update(override)
    return f


def good_question() -> dict:
    return {"text": "続き物は1冊と数えますか。", "type": "yes_no"}


def good_verification() -> dict:
    return {"verdict": "supported", "reason": "引用が主張を支えている。"}


def good_risk() -> dict:
    return {"condition": "冊数の上限を超えて借りられたとき", "impact": "在庫が足りなくなる", "estimate": "2人日"}


def good_links() -> dict:
    return {"requirements": ["FR-01"], "acceptance": ["AC-01"]}


def without(d: dict, key: str) -> dict:
    out = copy.deepcopy(d)
    out.pop(key)
    return out


def with_(d: dict, key: str, value) -> dict:
    out = copy.deepcopy(d)
    out[key] = value
    return out


def set_path(d: dict, path: str, value) -> dict:
    out = copy.deepcopy(d)
    node = out
    *head, last = path.split(".")
    for part in head:
        node = node[part]
    node[last] = value
    return out


def loc(**override) -> dict:
    base = {"source": "SRC-001", "section": "2.1", "quote": QUOTE}
    base.update(override)
    return base


def problems(findings=None, sources=None, specs=None):
    """check_findings を呼ぶ。台帳と本文の既定は見本。"""
    findings = [good_finding()] if findings is None else findings
    sources = good_sources()["sources"] if sources is None else sources
    specs = {"SRC-001": SPEC_TEXT} if specs is None else specs
    return fc().check_findings(findings, sources, specs)


def has(ps, field: str, *words: str) -> bool:
    return any(p.field == field and all(w in p.reason for w in words) for p in ps)


def describe(ps) -> str:
    return "\n".join(p.line() for p in ps) or "(誤りなし)"


# ---- AC-01: 必須の欄 ---------------------------------------------------------------------------


def test_good_finding_passes():
    """D0043-AC-01: 欄が全部そろった指摘は通る（任意の欄を全部付けても通る）。"""
    assert problems() == []
    full = good_finding(
        question=good_question(),
        verification=good_verification(),
        kind="risk",
        risk=good_risk(),
        status="confirmed",
        links=good_links(),
    )
    ps = problems([full])
    assert ps == [], describe(ps)


REQUIRED = [
    "id",
    "role",
    "location",
    "kind",
    "statement",
    "rationale",
    "sources",
    "guess",
    "confidence",
    "severity",
    "status",
]


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_reported(field):
    """D0043-AC-01: 必須の欄が1つ欠けた指摘は、その欄の名前を添えた行で落ちる（11欄を1つずつ）。"""
    ps = problems([without(good_finding(), field)])
    assert has(ps, field, "欄がありません"), describe(ps)


def test_blank_text_counts_as_missing():
    """D0043-AC-01: 空白だけの statement は、欄が無いのと同じ。"""
    ps = problems([with_(good_finding(), "statement", "  　 ")])
    assert has(ps, "statement", "欄がありません"), describe(ps)


# ---- AC-02: 決まった値 --------------------------------------------------------------------------

ENUM_CASES = [
    ("role", "reviewer"),
    ("perspective", "chef"),
    ("kind", "typo"),
    ("severity", "blocker"),
    ("confidence", "certain"),
    ("status", "done"),
    ("question.type", "multi"),
    ("verification.verdict", "maybe"),
]


@pytest.mark.parametrize("field,bad", ENUM_CASES)
def test_value_outside_enum_is_reported(field, bad):
    """D0043-AC-02: 決まった値の外は、欄の名前と入れた値を添えて落ちる（8つの欄）。"""
    base = good_finding(question=good_question(), verification=good_verification())
    if field == "perspective":
        base = with_(with_(base, "role", "perspective"), "perspective", bad)
    else:
        base = set_path(base, field, bad)
    ps = problems([base])
    assert has(ps, field, "決まった値の外", repr(bad)), describe(ps)


# ---- AC-03: id ---------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["F-1", "f-001", "F-００１", "F-001x", "001"])
def test_bad_id_shape_is_reported(bad):
    """D0043-AC-03: id が F- と3けた以上の数字の形でないと落ちる（全角数字も通さない）。"""
    ps = problems([good_finding(id=bad)])
    assert has(ps, "id", "形が違います"), describe(ps)


def test_duplicate_id_is_reported():
    """D0043-AC-03: 同じファイルの中で id が重なると、重なった id を添えて、後の指摘の1件だけ落ちる。"""
    ps = problems([good_finding(), good_finding()])
    dup = [p for p in ps if p.field == "id" and "重なっています" in p.reason]
    assert len(dup) == 1, describe(ps)
    assert "F-001" in dup[0].reason


# ---- AC-04: 欄どうしの対 -------------------------------------------------------------------------


def test_perspective_pairs_with_role():
    """D0043-AC-04: role が perspective のときだけ perspective が要る（無くても、余計に付いても落ちる）。"""
    ok = problems([good_finding(role="perspective", perspective="user")])
    assert ok == [], describe(ok)
    missing = problems([good_finding(role="perspective")])
    assert has(missing, "perspective", "role が perspective"), describe(missing)
    extra = problems([good_finding(role="quality", perspective="user")])
    assert has(extra, "perspective", "role が perspective"), describe(extra)


def test_choices_pair_with_choice_type():
    """D0043-AC-04: question.type が choice なら choices（1つ以上）が要り、choice 以外で choices があると落ちる。"""
    ok = problems([good_finding(question={"text": "どちらですか。", "type": "choice", "choices": ["a", "b"]})])
    assert ok == [], describe(ok)
    none = problems([good_finding(question={"text": "どちらですか。", "type": "choice"})])
    assert has(none, "question.choices", "type が choice"), describe(none)
    empty = problems([good_finding(question={"text": "どちらですか。", "type": "choice", "choices": []})])
    assert has(empty, "question.choices", "type が choice"), describe(empty)
    extra = problems([good_finding(question={"text": "自由に書いて。", "type": "free", "choices": ["a"]})])
    assert has(extra, "question.choices", "type が choice"), describe(extra)


# ---- AC-05: 余計な欄・型 -------------------------------------------------------------------------


def test_unknown_field_is_reported():
    """D0043-AC-05: 定義に無い欄（綴りの違い sevrity・入れ子の location.foo・question.foo）は、欄の名前を添えて落ちる。"""
    ps = problems([with_(good_finding(), "sevrity", "minor")])
    assert has(ps, "sevrity", "定義にない欄"), describe(ps)
    ps = problems([good_finding(location=loc(foo="x"))])
    assert has(ps, "location.foo", "定義にない欄"), describe(ps)
    ps = problems([good_finding(question={**good_question(), "foo": 1})])
    assert has(ps, "question.foo", "定義にない欄"), describe(ps)


WRONG_TYPES = [
    ("guess", "no", "真偽値"),
    ("guess", 1, "真偽値"),
    ("sources", "SRC-001", "配列"),
    ("location", [], "辞書"),
    ("statement", 5, "文字列"),
    ("kind", ["missing"], "文字列"),
]


@pytest.mark.parametrize("field,value,expected", WRONG_TYPES)
def test_wrong_type_is_reported(field, value, expected):
    """D0043-AC-05: 型の違いは、期待する型を添えて落ちる（整数 1 を真偽値として通さない・リストで例外にならない）。"""
    ps = problems([with_(good_finding(), field, value)])
    assert has(ps, field, "型が違います", expected), describe(ps)


def test_bool_is_not_a_number():
    """D0043-AC-05: bool を数として通さない（v に true を入れても版が分からない）。"""
    with pytest.raises(fc().InputError):
        fc().load_versioned({"v": True, "findings": []}, "findings", "指摘")


def test_non_dict_item_is_reported_without_raising():
    """D0043-AC-05: 指摘の並びの要素が辞書でなくても、例外にせず「辞書ではありません」で落ちる。"""
    ps = problems([5])
    assert [p.owner for p in ps] == ["findings[0]"], describe(ps)
    assert "辞書ではありません" in ps[0].reason


# ---- AC-06: 台帳 --------------------------------------------------------------------------------


def test_unknown_source_id_is_reported():
    """D0043-AC-06: sources が台帳に無い ID を指すと、その ID を添えて落ちる。"""
    ps = problems([good_finding(sources=["SRC-001", "SRC-099"])])
    assert has(ps, "sources", "台帳にない出典", "SRC-099"), describe(ps)


def test_unknown_location_source_is_reported():
    """D0043-AC-06: location.source が台帳に無い ID を指すと、その ID を添えて落ちる（引用の照らしはしない）。"""
    ps = problems([good_finding(location=loc(source="SRC-099"))])
    assert has(ps, "location.source", "台帳にない出典", "SRC-099"), describe(ps)
    assert not any(p.field == "location.quote" for p in ps), describe(ps)


def test_bad_sources_ledger_is_reported():
    """D0043-AC-06: 台帳の id の重なり・SRC- の形でない id・決まった値の外の kind が落ちる。"""
    base = good_sources()["sources"]
    dup = fc().check_sources(base + [{**base[1], "title": "別の資料"}])
    assert has(dup, "id", "重なっています", "SRC-002"), describe(dup)
    bad_id = fc().check_sources([{**base[1], "id": "SRC-1"}])
    assert has(bad_id, "id", "形が違います"), describe(bad_id)
    bad_kind = fc().check_sources([{**base[1], "kind": "memo"}])
    assert has(bad_kind, "kind", "決まった値の外", "'memo'"), describe(bad_kind)
    assert fc().check_sources(base) == []


# ---- AC-07: guess と sources -----------------------------------------------------------------


def test_guess_must_match_sources():
    """D0043-AC-07: sources が空で guess が偽、sources があるのに guess が真は落ちる。空で真は通る。"""
    no_src = problems([good_finding(sources=[], guess=False)])
    assert has(no_src, "guess", "出典がないのに"), describe(no_src)
    with_src = problems([good_finding(sources=["SRC-001"], guess=True)])
    assert has(with_src, "guess", "出典があるのに"), describe(with_src)
    guess = problems([good_finding(sources=[], guess=True)])
    assert guess == [], describe(guess)


# ---- AC-08・09: 引用 ----------------------------------------------------------------------------

LINE = "Library Card を提示する。"

BODY_VARIANTS = {
    "lf": lambda s: s,
    "crlf": lambda s: s.replace("\n", "\r\n"),
    "fullwidth-space": lambda s: s.replace(" ", "\u3000"),
    "tab-and-edges": lambda s: "\t " + s.replace(" ", "\t") + "  \n",
}
QUOTE_VARIANTS = {
    "same": LINE,
    "fullwidth-space": "Library\u3000Card\u3000を提示する。",
    "newline-inside": "Library\nCard を提示する。",
    "tab-crlf-and-edges": "  Library\tCard\r\nを提示する。  ",
}


@pytest.mark.parametrize("body_variant", list(BODY_VARIANTS))
@pytest.mark.parametrize("quote_variant", list(QUOTE_VARIANTS))
def test_quote_ignores_whitespace_and_newline_kinds(body_variant, quote_variant):
    """D0043-AC-08: 改行（CRLF・LF）・空白・タブ・全角空白・前後の空白の違いを無視して、同じ文なら通る。"""
    body = BODY_VARIANTS[body_variant](SPEC_TEXT)
    f = good_finding(location=loc(quote=QUOTE_VARIANTS[quote_variant]))
    ps = problems([f], specs={"SRC-001": body})
    assert ps == [], describe(ps)


def test_normalize():
    """D0043-AC-08: normalize は NFKC にして空白を全部消す（全角英数は半角になり、大文字小文字はそのまま）。"""
    assert fc().normalize("ＡＢ　c\r\nd") == "ABcd"
    assert fc().normalize(" \t\n\u3000") == ""
    assert fc().normalize("Ab") != fc().normalize("aB")


@pytest.mark.parametrize(
    "quote",
    ["返却期限は、貸出日から14日とする。", "延滞した場合の扱いは、別途定める。", QUOTE],
)
def test_quote_in_body_passes(quote):
    """D0043-AC-09: 本文にある文を引いた指摘は通る。"""
    ps = problems([good_finding(location=loc(quote=quote))])
    assert ps == [], describe(ps)


@pytest.mark.parametrize(
    "quote",
    [
        "利用者は、本を最大10冊まで借りられる。",
        "利用者は、本を最大五冊まで借りられる。",
        "利用者は、本を最大5冊借りられる。",
        "仕様書に書かれていない文。",
    ],
)
def test_quote_not_in_body_fails(quote):
    """D0043-AC-09: 本文に無い文・言い換えた文・語を抜いた文は、本文にありませんで落ちる。"""
    ps = problems([good_finding(location=loc(quote=quote))])
    assert has(ps, "location.quote", "本文にありません"), describe(ps)


def test_quote_is_case_sensitive():
    """D0043-AC-09: 大文字と小文字は区別する。"""
    ps = problems([good_finding(location=loc(quote="library card を提示する。"))])
    assert has(ps, "location.quote", "本文にありません"), describe(ps)


# ---- AC-10: missing と空の引用 ---------------------------------------------------------------


def test_missing_kind_may_have_empty_quote():
    """D0043-AC-10: kind が missing のときだけ quote を空にしてよい（section は要る）。"""
    ps = problems([good_finding(kind="missing", location=loc(quote="", section="3.2"))])
    assert ps == [], describe(ps)


def test_missing_kind_needs_section():
    """D0043-AC-10: missing で quote が空のとき、section が空白だけだと落ちる。"""
    ps = problems([good_finding(kind="missing", location=loc(quote="", section="  "))])
    assert has(ps, "location.section", "欄がありません"), describe(ps)


@pytest.mark.parametrize("quote", ["", "  ", "\u3000\n"])
def test_empty_quote_fails_for_other_kinds(quote):
    """D0043-AC-10: missing 以外で quote が空（空白だけも空）だと、空にできるのはで落ちる。"""
    ps = problems([good_finding(kind="ambiguous", location=loc(quote=quote))])
    assert has(ps, "location.quote", "空にできるのは"), describe(ps)


# ---- AC-11: 照らせない出典 -------------------------------------------------------------------


def test_non_spec_location_source_cannot_be_checked():
    """D0043-AC-11: location.source が law の件だと、引用が本文と一致していても「照らせません」で落ちる（安全側）。"""
    ps = problems([good_finding(location=loc(source="SRC-002"))])
    assert has(ps, "location.quote", "この出典は本文と照らせません", "law"), describe(ps)


def test_spec_without_body_cannot_be_checked():
    """D0043-AC-11: spec の件でも本文が渡されていなければ、同じ「照らせません」で落ちる。"""
    ps = problems([good_finding()], specs={})
    assert has(ps, "location.quote", "この出典は本文と照らせません"), describe(ps)


# ---- AC-12: naive ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_id,kind",
    [("SRC-002", "law"), ("SRC-003", "customer"), ("SRC-004", "past_case"), ("SRC-005", "standard"), ("SRC-006", "public_spec")],
)
def test_naive_cannot_use_non_spec_source(source_id, kind):
    """D0043-AC-12: naive は spec 以外の台帳の件の ID を sources に持てない（5つの kind のすべて）。"""
    ps = problems([good_finding(role="naive", sources=[source_id])])
    assert has(ps, "sources", "naive は spec 以外の出典を使えません", source_id), describe(ps)


def test_naive_may_use_spec_or_guess():
    """D0043-AC-12: naive でも spec だけなら通る。guess が真で sources が空でも通る。"""
    ok = problems([good_finding(role="naive", sources=["SRC-001"])])
    assert ok == [], describe(ok)
    guess = problems([good_finding(role="naive", sources=[], guess=True)])
    assert guess == [], describe(guess)


def test_naive_with_broken_ledger_kind_fails():
    """D0043-AC-12: 台帳の kind が壊れた件を naive が指しても落ちる（すり抜けの道を塞ぐ）。"""
    ledger = good_sources()["sources"]
    ledger[3] = {**ledger[3], "kind": "memo"}
    ps = problems([good_finding(role="naive", sources=["SRC-004"])], sources=ledger)
    assert has(ps, "sources", "naive は spec 以外の出典を使えません", "SRC-004"), describe(ps)


def test_other_roles_may_use_non_spec_source():
    """D0043-AC-12: quality など naive 以外は、law の出典を使っても通る。"""
    ps = problems([good_finding(role="quality", sources=["SRC-001", "SRC-002"])])
    assert ps == [], describe(ps)


# ---- AC-13: risk -------------------------------------------------------------------------------


def test_risk_pairs_with_kind():
    """D0043-AC-13: kind が risk なのに risk が無い、risk でないのに risk があると落ちる。対がそろえば通る。"""
    ok = problems([good_finding(kind="risk", risk=good_risk())])
    assert ok == [], describe(ok)
    missing = problems([good_finding(kind="risk")])
    assert has(missing, "risk", "kind が risk なのに"), describe(missing)
    extra = problems([good_finding(kind="ambiguous", risk=good_risk())])
    assert has(extra, "risk", "kind が risk のときだけ"), describe(extra)


@pytest.mark.parametrize("part", ["condition", "impact", "estimate"])
def test_risk_parts_are_required(part):
    """D0043-AC-13: risk の中の condition・impact・estimate が欠けると落ちる。"""
    ps = problems([good_finding(kind="risk", risk=without(good_risk(), part))])
    assert has(ps, f"risk.{part}", "欄がありません"), describe(ps)


# ---- AC-14: links ------------------------------------------------------------------------------


def test_links_only_when_confirmed():
    """D0043-AC-14: links は status が confirmed のときだけ持てる。confirmed で links が無いと落ちる。"""
    ok = problems([good_finding(status="confirmed", links=good_links())])
    assert ok == [], describe(ok)
    extra = problems([good_finding(status="open", links=good_links())])
    assert has(extra, "links", "status が confirmed のときだけ"), describe(extra)
    missing = problems([good_finding(status="confirmed")])
    assert has(missing, "links", "status が confirmed なのに"), describe(missing)


@pytest.mark.parametrize(
    "key,value",
    [
        ("requirements", "FR1"),
        ("requirements", "fr-01"),
        ("acceptance", "AC1"),
        ("acceptance", "D43-AC-01"),
        ("acceptance", "D0043-AC-"),
    ],
)
def test_link_values_must_match_shape(key, value):
    """D0043-AC-14: requirements は FR- と数字、acceptance は AC- か Dnnnn-AC- と数字の形でないと落ちる。"""
    links = {**good_links(), key: [value]}
    ps = problems([good_finding(status="confirmed", links=links)])
    assert any(p.field.startswith(f"links.{key}") and repr(value) in p.reason for p in ps), describe(ps)


def test_acceptance_accepts_both_forms():
    """D0043-AC-14: AC-01 と D0043-AC-01 の両方の形を通す。"""
    links = {"requirements": ["FR-01", "FR-12"], "acceptance": ["AC-01", "D0043-AC-01"]}
    ps = problems([good_finding(status="confirmed", links=links)])
    assert ps == [], describe(ps)


# ---- AC-16: 並び -------------------------------------------------------------------------------


def test_problem_order_is_stable_and_follows_field_order():
    """D0043-AC-16: 指摘の並び順、1件の中は欄の正準の順（id が kind より前）。同じ入力なら同じ並び。"""
    first = good_finding(id="f1", kind="typo")
    second = good_finding(id="F-002", severity="blocker")
    ps = problems([first, second])
    assert [p.field for p in ps] == ["id", "kind", "severity"], describe(ps)
    assert [p.owner for p in ps][-1] == "F-002"
    assert problems([first, second]) == ps
    # 欄の順を入れ替えて書いても並びは同じ（辞書の並びに頼らない）
    shuffled = dict(reversed(list(first.items())))
    assert [p.field for p in problems([shuffled, second])] == ["id", "kind", "severity"]


def test_problem_line_has_three_parts():
    """D0043-AC-16: 誤りの1行は「<id>: <欄>: <理由>」の形。"""
    ps = problems([good_finding(kind="typo")])
    assert len(ps) == 1, describe(ps)
    assert re.fullmatch(r"F-001: kind: .+", ps[0].line()), ps[0].line()


# ---- AC-19: Schema とコードの一致 ------------------------------------------------------------


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _if_pairs(node) -> set[tuple[str, str]]:
    """Schema の if/then の条件の欄 → then で要る欄、の組を全部集める。"""
    pairs: set[tuple[str, str]] = set()
    if isinstance(node, dict):
        cond = node.get("if")
        then = node.get("then")
        if isinstance(cond, dict) and isinstance(then, dict):
            props = cond.get("properties", {})
            required = then.get("required", [])
            for field in props:
                for target in required:
                    pairs.add((field, target))
        for value in node.values():
            pairs |= _if_pairs(value)
    elif isinstance(node, list):
        for item in node:
            pairs |= _if_pairs(item)
    return pairs


def schema_differences(mod) -> list[str]:
    """Schema の2つのファイルとコードの定数を比べて、食い違いを文で返す。"""
    diffs: list[str] = []
    fs = _load_schema("finding.schema.json")
    ss = _load_schema("sources.schema.json")
    defs = fs["$defs"]
    sdef = ss["$defs"]["source"]

    def eq(label, schema_value, code_value):
        if schema_value != code_value:
            diffs.append(f"{label}: Schema={schema_value!r} コード={code_value!r}")

    def enum(label, prop, code):
        eq(label, sorted(prop.get("enum", [])), sorted(code))

    eq("v const (finding)", fs["properties"]["v"].get("const"), mod.SCHEMA_VERSION)
    eq("v const (sources)", ss["properties"]["v"].get("const"), mod.SCHEMA_VERSION)

    finding = defs["finding"]
    props = finding["properties"]
    eq("finding properties の並び", list(props), list(mod.FINDING_FIELDS))
    eq("finding required", sorted(finding["required"]), sorted(mod.FINDING_REQUIRED))
    eq("finding.id pattern", props["id"].get("pattern"), mod.FINDING_ID_PATTERN)
    eq("finding.sources pattern", props["sources"]["items"].get("pattern"), mod.SOURCE_ID_PATTERN)
    enum("role", props["role"], mod.ROLES)
    enum("perspective", props["perspective"], mod.PERSPECTIVES)
    enum("kind", props["kind"], mod.KINDS)
    enum("severity", props["severity"], mod.SEVERITIES)
    enum("confidence", props["confidence"], mod.CONFIDENCES)
    enum("status", props["status"], mod.STATUSES)

    question = defs["question"]
    eq("question properties", list(question["properties"]), list(mod.QUESTION_FIELDS))
    enum("question.type", question["properties"]["type"], mod.QUESTION_TYPES)
    eq("location properties", list(defs["location"]["properties"]), list(mod.LOCATION_FIELDS))
    eq("risk properties", list(defs["risk"]["properties"]), list(mod.RISK_FIELDS))
    eq("verification properties", list(defs["verification"]["properties"]), list(mod.VERIFICATION_FIELDS))
    enum("verification.verdict", defs["verification"]["properties"]["verdict"], mod.VERDICTS)
    eq("links properties", list(defs["links"]["properties"]), list(mod.LINKS_FIELDS))
    eq("links.requirements pattern", defs["links"]["properties"]["requirements"]["items"].get("pattern"), mod.FR_PATTERN)
    eq("links.acceptance pattern", defs["links"]["properties"]["acceptance"]["items"].get("pattern"), mod.AC_PATTERN)

    eq("source properties", list(sdef["properties"]), list(mod.SOURCE_FIELDS))
    eq("source required", sorted(sdef["required"]), sorted(mod.SOURCE_REQUIRED))
    eq("source.id pattern", sdef["properties"]["id"].get("pattern"), mod.SOURCE_ID_PATTERN)
    enum("source.kind", sdef["properties"]["kind"], mod.SOURCE_KINDS)
    return diffs


def test_finding_schema_matches_code():
    """D0043-AC-19: 指摘の Schema の enum・required・properties の名前と並び・pattern・v が、コードの定数と同じ。"""
    diffs = [d for d in schema_differences(fc()) if not d.startswith(("source", "v const (sources)"))]
    assert diffs == []


def test_sources_schema_matches_code():
    """D0043-AC-19: 台帳の Schema の properties・required・pattern・kind の enum・v が、コードの定数と同じ。"""
    diffs = [d for d in schema_differences(fc()) if d.startswith(("source", "v const (sources)"))]
    assert diffs == []


def test_conditional_pairs_match_code():
    """D0043-AC-19: Schema の if/then の対（role→perspective・kind→risk・status→links・type→choices・台帳 kind→file）がコードの対と同じ組。"""
    fs = _load_schema("finding.schema.json")
    ss = _load_schema("sources.schema.json")
    assert _if_pairs(fs["$defs"]["finding"]) == {("role", "perspective"), ("kind", "risk"), ("status", "links")}
    assert _if_pairs(fs["$defs"]["question"]) == {("type", "choices")}
    assert _if_pairs(ss["$defs"]["source"]) == {("kind", "file")}


def test_schema_comparison_detects_a_difference(monkeypatch):
    """D0043-AC-19: 比べる関数そのものが、定数が1つ違うことを見つけられる（テスト自身が効いている）。"""
    mod = fc()
    assert schema_differences(mod) == []
    monkeypatch.setattr(mod, "KINDS", (*mod.KINDS, "extra_kind"))
    diffs = schema_differences(mod)
    assert any(d.startswith("kind") for d in diffs), diffs


# ---- AC-21: 見本に手元の情報が無い -----------------------------------------------------------


def test_samples_have_no_personal_info():
    """D0043-AC-21: 見本のデータにユーザー名の入ったパス・メール・実在の会社名らしき語が無い。"""
    blob = json.dumps(
        [SPEC_TEXT, good_sources(), good_finding(), good_question(), good_verification(), good_risk(), good_links()],
        ensure_ascii=False,
    )
    assert "/home/" not in blob and "/Users/" not in blob and "C:\\\\Users" not in blob
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)
    assert not re.search(r"株式会社|有限会社|Inc\.|Corp\.|Ltd", blob)


# ---- AC-23: パッケージと実行時の Schema ----------------------------------------------------------


def test_package_data_includes_schemas():
    """D0043-AC-23: pip install した版にも Schema が入る（package-data の pipe_in_generator に schemas/*.json）。"""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "schemas/*.json" in data["tool"]["setuptools"]["package-data"]["pipe_in_generator"]


def test_dependencies_unchanged():
    """D0043-AC-22・23: dependencies は claude-agent-sdk だけのまま（今の作りで通る。増えたら落ちる守りの検査）。"""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert len(deps) == 1 and deps[0].startswith("claude-agent-sdk")


def test_check_does_not_read_schema_files(tmp_path, monkeypatch):
    """D0043-AC-23: 実行時は Schema を読まない（.schema.json を読むと例外になる偽物のもとでも run が動く）。"""
    import builtins

    findings = tmp_path / "findings.json"
    sources = tmp_path / "sources.json"
    spec = tmp_path / "spec.md"
    findings.write_text(json.dumps({"v": 1, "findings": [good_finding()]}, ensure_ascii=False), encoding="utf-8")
    sources.write_text(json.dumps(good_sources(), ensure_ascii=False), encoding="utf-8")
    spec.write_text(SPEC_TEXT, encoding="utf-8")

    def guard(orig):
        def wrapper(target, *a, **k):
            if str(target).endswith(".schema.json"):
                raise AssertionError(f"Schema を読みに行った: {target}")
            return orig(target, *a, **k)

        return wrapper

    orig_read, orig_open, orig_builtin = Path.read_text, Path.open, builtins.open
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: guard(lambda t, *x, **y: orig_read(t, *x, **y))(self, *a, **k))
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: guard(lambda t, *x, **y: orig_open(t, *x, **y))(self, *a, **k))
    monkeypatch.setattr(builtins, "open", guard(orig_builtin))
    code, lines = fc().run(findings, sources, [spec])
    assert code == 0, lines
