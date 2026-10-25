"""仕様書レビューの指摘（指摘の形 v1）と出典の台帳を、LLM を呼ばずに検査する（D0043）。

findings-check は、指摘のファイル・台帳・仕様書の本文を読み、形・出典・引用の一致・役割ごとの決まりを確かめる。
標準ライブラリだけで動く（pipe_in.* も SDK も読み込まない）。

決まりはこのファイルの定数が持つ。generator/schemas/ の JSON Schema は、エディタや他の言語の道具に渡す契約で、
実行時には読まない（食い違わないことはテストが守る）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# ---- 決まり（Schema と同じ内容。テストが食い違いを見張る） ------------------------------------------

ROLES = ("quality", "gap", "perspective", "naive")
PERSPECTIVES = ("user", "tester", "designer", "operations", "security", "legal")
KINDS = ("missing", "ambiguous", "inconsistent", "unverifiable", "excess", "risk")
SEVERITIES = ("critical", "major", "minor")
CONFIDENCES = ("high", "medium", "low")
STATUSES = ("open", "confirmed", "rejected")
QUESTION_TYPES = ("yes_no", "choice", "free")
VERDICTS = ("supported", "rejected", "needs_human")
SOURCE_KINDS = ("spec", "customer", "law", "standard", "public_spec", "past_case")

# 判定は re.fullmatch。\d は全角数字も通すので [0-9] を使う
FINDING_ID_PATTERN = "^F-[0-9]{3,}$"
SOURCE_ID_PATTERN = "^SRC-[0-9]{3,}$"
FR_PATTERN = "^FR-[0-9]+$"
AC_PATTERN = "^(AC-[0-9]+|D[0-9]{4}-AC-[0-9]+)$"

# 欄の並びが、誤りを出す順（正準の順）
FINDING_FIELDS = (
    "id",
    "role",
    "perspective",
    "location",
    "kind",
    "statement",
    "rationale",
    "sources",
    "guess",
    "confidence",
    "severity",
    "question",
    "risk",
    "verification",
    "status",
    "links",
)
FINDING_REQUIRED = (
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
)
LOCATION_FIELDS = ("source", "section", "quote")
QUESTION_FIELDS = ("text", "type", "choices")
RISK_FIELDS = ("condition", "impact", "estimate")
VERIFICATION_FIELDS = ("verdict", "reason")
LINKS_FIELDS = ("requirements", "acceptance")
SOURCE_FIELDS = ("id", "kind", "title", "version", "where", "file")
SOURCE_REQUIRED = ("id", "kind", "title", "version", "where")


@dataclass(frozen=True)
class Problem:
    owner: str  # 指摘の id（無いときは "findings[3]"）か、台帳の id（無いときは "sources[1]"）
    field: str  # 欄の名前。入れ子は "location.quote"・"links.acceptance[0]"
    reason: str  # 日本語の1行。入れた値は repr で添える

    def line(self) -> str:
        return f"{self.owner}: {self.field}: {self.reason}"


class InputError(Exception):
    """入力を受け取れない（終了コード 2）。"""


# ---- 読み込み -------------------------------------------------------------------------------------


def normalize(text: str) -> str:
    """NFKC にして、空白（改行・タブ・全角空白を含む）を全部消す。大文字小文字はそのまま。"""
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except OSError as e:
        raise InputError(f"{path} を読めません（{e.strerror or e}）") from e
    except UnicodeDecodeError as e:
        raise InputError(f"{path} は UTF-8 ではありません") from e


def load_json(path: Path) -> Any:
    text = _read_text(path)
    try:
        return json.loads(text)
    except ValueError as e:
        raise InputError(f"{path} は JSON ではありません（{e}）") from e


def load_versioned(doc: Any, key: str, label: str) -> list:
    if not isinstance(doc, dict):
        raise InputError(f"{label}のファイルの一番上が辞書ではありません")
    v = doc.get("v")
    if "v" not in doc or type(v) is not int or v != SCHEMA_VERSION:
        shown = repr(v) if "v" in doc else "なし"
        raise InputError(f"{label}のファイルの版が分かりません（v: {shown}。対応するのは {SCHEMA_VERSION} だけです）")
    items = doc.get(key)
    if not isinstance(items, list):
        raise InputError(f"{label}のファイルの {key} が配列ではありません")
    return items


def _file_name(path: str) -> str:
    return re.split(r"[/\\]", str(path))[-1]


def _owner(item: Any, index: int, label: str) -> str:
    if isinstance(item, dict):
        v = item.get("id")
        if isinstance(v, str) and v.strip():
            return v
    return f"{label}[{index}]"


def _match_specs(sources: list, names: list[str]) -> dict[str, int]:
    """台帳の spec の件の id → 結ぶ --spec の位置。結べないときは InputError。"""
    matched: dict[str, int] = {}
    for i, entry in enumerate(sources):
        if not isinstance(entry, dict) or entry.get("kind") != "spec":
            continue
        owner = _owner(entry, i, "sources")
        file = entry.get("file")
        if not isinstance(file, str) or not file.strip():
            raise InputError(f"台帳 {owner}: spec の件に file（仕様書のファイル名）がありません")
        if "/" in file or "\\" in file:
            raise InputError(f"台帳 {owner}: file はファイル名だけにしてください（{file!r}）")
        if not names:
            raise InputError(f"台帳 {owner}: spec の件があるのに --spec がありません（{file!r} を指定してください）")
        hits = [j for j, name in enumerate(names) if name == file]
        if not hits:
            raise InputError(f"台帳 {owner}: file {file!r} と同じ名前の --spec がありません")
        if len(hits) > 1:
            raise InputError(f"台帳 {owner}: file {file!r} と同じ名前の --spec が {len(hits)} つあります")
        matched.setdefault(owner, hits[0])
    return matched


def resolve_specs(sources: list, spec_files: list[tuple[str, str]]) -> dict[str, str]:
    """台帳の spec の件の id → 本文。--spec のファイル名（パスの最後）と台帳の file を結ぶ。"""
    matched = _match_specs(sources, [_file_name(p) for p, _ in spec_files])
    return {owner: spec_files[j][1] for owner, j in matched.items()}


# ---- 欄の検査の部品 ------------------------------------------------------------------------------


class _Sink:
    """1件分の誤りを集める。"""

    def __init__(self, owner: str):
        self.owner = owner
        self.items: list[Problem] = []

    def add(self, field: str, reason: str) -> None:
        self.items.append(Problem(self.owner, field, reason))

    def text(self, d: dict, key: str, path: str) -> str | None:
        """必須の文字列の欄。無い・空白だけ・型違いは誤りにして None。"""
        if key not in d:
            self.add(path, "欄がありません")
            return None
        v = d[key]
        if not isinstance(v, str):
            self.add(path, "型が違います（文字列にしてください）")
            return None
        if not v.strip():
            self.add(path, "欄がありません（空白だけです）")
            return None
        return v

    def enum(self, value: str, choices: tuple[str, ...], path: str) -> None:
        if value not in choices:
            self.add(path, f"決まった値の外です: {value!r}（{'・'.join(choices)}）")

    def shape(self, value: str, pattern: str, path: str, what: str) -> bool:
        if re.fullmatch(pattern, value) is None:
            self.add(path, f"形が違います: {value!r}（{what}）")
            return False
        return True

    def unknown(self, d: dict, known: tuple[str, ...], prefix: str) -> None:
        for key in d:
            if key not in known:
                self.add(f"{prefix}{key}", "定義にない欄です")

    def dict_of(self, d: dict, key: str, path: str) -> dict | None:
        """入れ子の辞書の欄。型違いは誤りにして None。"""
        v = d[key]
        if not isinstance(v, dict):
            self.add(path, "型が違います（辞書にしてください）")
            return None
        return v

    def str_list(self, v: Any, path: str, pattern: str | None, what: str) -> list[str] | None:
        if not isinstance(v, list):
            self.add(path, "型が違います（配列にしてください）")
            return None
        out: list[str] = []
        for i, item in enumerate(v):
            if not isinstance(item, str):
                self.add(f"{path}[{i}]", "型が違います（文字列にしてください）")
            elif pattern is not None and not self.shape(item, pattern, f"{path}[{i}]", what):
                pass
            else:
                out.append(item)
        return out


def _pair(sink: _Sink, d: dict, cond_key: str, cond_value: str, target: str, path: str | None = None) -> None:
    """「cond_key が cond_value のときだけ target を持つ」の対。cond が文字列でなければ見ない。"""
    cond = d.get(cond_key)
    if not isinstance(cond, str):
        return
    path = path or target
    leaf = target.split(".")[-1]
    if cond == cond_value and target.split(".")[-1] not in d:
        sink.add(path, f"{cond_key} が {cond_value} なのに {leaf} がありません")
    elif cond != cond_value and leaf in d:
        sink.add(path, f"{leaf} は {cond_key} が {cond_value} のときだけ持てます（{cond_key}: {cond!r}）")


def _check_question(sink: _Sink, q: dict) -> None:
    sink.unknown(q, QUESTION_FIELDS, "question.")
    sink.text(q, "text", "question.text")
    t = sink.text(q, "type", "question.type")
    if t is not None:
        sink.enum(t, QUESTION_TYPES, "question.type")
    if isinstance(q.get("type"), str):
        _pair(sink, q, "type", "choice", "choices", "question.choices")
    if "choices" in q:
        choices = q["choices"]
        if not isinstance(choices, list):
            sink.add("question.choices", "型が違います（配列にしてください）")
        elif not choices:
            if q.get("type") == "choice":
                sink.add("question.choices", "type が choice なのに choices が空です（1つ以上要ります）")
        else:
            for i, c in enumerate(choices):
                if not isinstance(c, str) or not c.strip():
                    sink.add(f"question.choices[{i}]", "型が違います（空でない文字列にしてください）")


def _check_risk(sink: _Sink, r: dict) -> None:
    sink.unknown(r, RISK_FIELDS, "risk.")
    for key in RISK_FIELDS:
        sink.text(r, key, f"risk.{key}")


def _check_verification(sink: _Sink, v: dict) -> None:
    sink.unknown(v, VERIFICATION_FIELDS, "verification.")
    verdict = sink.text(v, "verdict", "verification.verdict")
    if verdict is not None:
        sink.enum(verdict, VERDICTS, "verification.verdict")
    sink.text(v, "reason", "verification.reason")


def _check_links(sink: _Sink, links: dict) -> None:
    sink.unknown(links, LINKS_FIELDS, "links.")
    for key, pattern, what in (
        ("requirements", FR_PATTERN, "FR- と数字"),
        ("acceptance", AC_PATTERN, "AC-数字 か Dnnnn-AC-数字"),
    ):
        if key not in links:
            sink.add(f"links.{key}", "欄がありません")
        else:
            sink.str_list(links[key], f"links.{key}", pattern, what)


# ---- 指摘の検査 ----------------------------------------------------------------------------------


def _ledger_index(sources: list) -> dict[str, dict]:
    """台帳の id → 件。壊れた件は読める分だけ。同じ id は先の件を使う。"""
    index: dict[str, dict] = {}
    for entry in sources:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            index.setdefault(entry["id"], entry)
    return index


def _check_citation(
    sink: _Sink, f: dict, loc: dict, ledger: dict[str, dict], specs: dict[str, str], bodies: dict[str, str]
) -> None:
    source = sink.text(loc, "source", "location.source")
    sink.text(loc, "section", "location.section")
    if "quote" not in loc:
        sink.add("location.quote", "欄がありません")
        return
    quote = loc["quote"]
    if not isinstance(quote, str):
        sink.add("location.quote", "型が違います（文字列にしてください）")
        return
    if source is None:
        return
    if source not in ledger:
        sink.add("location.source", f"台帳にない出典です: {source!r}")
        return
    wanted = normalize(quote)
    if wanted == "":
        if f.get("kind") != "missing":
            sink.add("location.quote", "引用が空です。空にできるのは kind が missing のときだけです")
        return
    kind = ledger[source].get("kind")
    if kind != "spec":
        sink.add("location.quote", f"この出典は本文と照らせません（kind: {kind!r}）")
        return
    if source not in specs:
        sink.add("location.quote", f"この出典は本文と照らせません（kind: {kind!r}。本文が渡されていません）")
        return
    if source not in bodies:
        bodies[source] = normalize(specs[source])
    if wanted not in bodies[source]:
        sink.add("location.quote", f"引用が本文にありません: {quote!r}")


def _check_one(f: dict, sink: _Sink, ledger: dict[str, dict], specs: dict[str, str], bodies: dict[str, str]) -> None:
    sink.unknown(f, FINDING_FIELDS, "")

    fid = sink.text(f, "id", "id")
    if fid is not None:
        sink.shape(fid, FINDING_ID_PATTERN, "id", "F- と3けた以上の数字")

    role = sink.text(f, "role", "role")
    if role is not None:
        sink.enum(role, ROLES, "role")
    if "perspective" in f:
        p = f["perspective"]
        if not isinstance(p, str):
            sink.add("perspective", "型が違います（文字列にしてください）")
        else:
            sink.enum(p, PERSPECTIVES, "perspective")
    _pair(sink, f, "role", "perspective", "perspective")

    if "location" not in f:
        sink.add("location", "欄がありません")
    else:
        loc = sink.dict_of(f, "location", "location")
        if loc is not None:
            sink.unknown(loc, LOCATION_FIELDS, "location.")
            _check_citation(sink, f, loc, ledger, specs, bodies)

    kind = sink.text(f, "kind", "kind")
    if kind is not None:
        sink.enum(kind, KINDS, "kind")
    sink.text(f, "statement", "statement")
    sink.text(f, "rationale", "rationale")

    ids: list[str] | None = None
    if "sources" not in f:
        sink.add("sources", "欄がありません")
    else:
        ids = sink.str_list(f["sources"], "sources", SOURCE_ID_PATTERN, "SRC- と3けた以上の数字")
        for sid in ids or []:
            if sid not in ledger:
                sink.add("sources", f"台帳にない出典です: {sid!r}")
    guess = f.get("guess")
    if "guess" not in f:
        sink.add("guess", "欄がありません")
    elif not isinstance(guess, bool):
        sink.add("guess", "型が違います（真偽値にしてください）")
    elif isinstance(f.get("sources"), list):
        if not f["sources"] and not guess:
            sink.add("guess", "出典がないのに guess が偽です（出典が無い指摘は guess を真にしてください）")
        elif f["sources"] and guess:
            sink.add("guess", "出典があるのに guess が真です")

    conf = sink.text(f, "confidence", "confidence")
    if conf is not None:
        sink.enum(conf, CONFIDENCES, "confidence")
    sev = sink.text(f, "severity", "severity")
    if sev is not None:
        sink.enum(sev, SEVERITIES, "severity")
    status = sink.text(f, "status", "status")
    if status is not None:
        sink.enum(status, STATUSES, "status")

    for key, check in (("question", _check_question), ("verification", _check_verification)):
        if key in f:
            sub = sink.dict_of(f, key, key)
            if sub is not None:
                check(sink, sub)
    if "risk" in f:
        r = sink.dict_of(f, "risk", "risk")
        if r is not None:
            _check_risk(sink, r)
    _pair(sink, f, "kind", "risk", "risk")
    if "links" in f:
        links = sink.dict_of(f, "links", "links")
        if links is not None:
            _check_links(sink, links)
    _pair(sink, f, "status", "confirmed", "links")

    # 役割の決まり（上の欄の検査とは独立に出す）
    if f.get("role") == "naive":
        for sid in ids or []:
            entry = ledger.get(sid)
            if entry is not None and entry.get("kind") != "spec":
                sink.add("sources", f"naive は spec 以外の出典を使えません: {sid!r}（kind: {entry.get('kind')!r}）")


def _field_rank(field: str, order: tuple[str, ...]) -> int:
    head = re.split(r"[.\[]", field, maxsplit=1)[0]
    return order.index(head) if head in order else len(order)


def check_sources(sources: list) -> list[Problem]:
    out: list[Problem] = []
    seen: set[str] = set()
    for i, entry in enumerate(sources):
        owner = _owner(entry, i, "sources")
        if not isinstance(entry, dict):
            out.append(Problem(owner, "(出典)", "辞書ではありません"))
            continue
        sink = _Sink(owner)
        sink.unknown(entry, SOURCE_FIELDS, "")
        sid = sink.text(entry, "id", "id")
        if sid is not None:
            sink.shape(sid, SOURCE_ID_PATTERN, "id", "SRC- と3けた以上の数字")
            if sid in seen:
                sink.add("id", f"重なっています: {sid!r}")
            seen.add(sid)
        kind = sink.text(entry, "kind", "kind")
        if kind is not None:
            sink.enum(kind, SOURCE_KINDS, "kind")
        for key in ("title", "version", "where"):
            sink.text(entry, key, key)
        if "file" in entry:
            if kind != "spec":
                sink.add("file", "定義にない欄です（file を持てるのは kind が spec の件だけです）")
            elif not isinstance(entry["file"], str):
                sink.add("file", "型が違います（文字列にしてください）")
        elif kind == "spec":
            sink.add("file", "欄がありません（spec の件は file が要ります）")
        out.extend(sorted(sink.items, key=lambda p: _field_rank(p.field, SOURCE_FIELDS)))
    return out


def check_findings(findings: list, sources: list, specs: dict[str, str]) -> list[Problem]:
    ledger = _ledger_index(sources)
    bodies: dict[str, str] = {}
    out: list[Problem] = []
    seen_ids: set[str] = set()
    for i, f in enumerate(findings):
        owner = _owner(f, i, "findings")
        if not isinstance(f, dict):
            out.append(Problem(owner, "(指摘)", "辞書ではありません"))
            continue
        sink = _Sink(owner)
        _check_one(f, sink, ledger, specs, bodies)
        fid = f.get("id")
        if isinstance(fid, str) and fid.strip():
            if fid in seen_ids:
                sink.add("id", f"重なっています: {fid!r}")
            seen_ids.add(fid)
        # 欄の正準の順に並べる（同じ欄の中は出た順。sorted は安定）
        out.extend(sorted(sink.items, key=lambda p: _field_rank(p.field, FINDING_FIELDS)))
    return out


def check_documents(findings_doc: Any, sources_doc: Any, specs: dict[str, str]) -> list[Problem]:
    findings = load_versioned(findings_doc, "findings", "指摘")
    sources = load_versioned(sources_doc, "sources", "台帳")
    return [*check_sources(sources), *check_findings(findings, sources, specs)]


# ---- 実行 ----------------------------------------------------------------------------------------


def run(findings_path: Path, sources_path: Path, spec_paths: list[Path]) -> tuple[int, list[str]]:
    findings_doc = load_json(findings_path)
    sources_doc = load_json(sources_path)
    findings = load_versioned(findings_doc, "findings", "指摘")
    sources = load_versioned(sources_doc, "sources", "台帳")
    names = [_file_name(str(p)) for p in spec_paths]
    matched = _match_specs(sources, names)
    # 結ばれた --spec だけを開く（使われないものは開かない）
    texts = {j: _read_text(spec_paths[j]) for j in sorted(set(matched.values()))}
    specs = {owner: texts[j] for owner, j in matched.items()}
    problems = check_documents(findings_doc, sources_doc, specs)
    if not problems:
        return 0, [f"誤りなし（指摘 {len(findings)} 件・出典 {len(sources)} 件）"]
    return 1, [*(p.line() for p in problems), f"誤り {len(problems)} 件"]


def _utf8(stream: Any) -> None:
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="pipe-in-gen findings-check",
        description="指摘のファイル（指摘の形 v1）を、形・出典・引用の一致・役割の決まりで検査します（LLM を呼びません）。",
    )
    ap.add_argument("findings", type=Path, help="指摘のファイル（{\"v\": 1, \"findings\": [...]}）")
    ap.add_argument("--sources", type=Path, required=True, help="出典の台帳（{\"v\": 1, \"sources\": [...]}）")
    ap.add_argument(
        "--spec",
        type=Path,
        action="append",
        default=[],
        help="仕様書の本文。台帳の spec の件の file と同じ名前のものと結ぶ（何度でも書ける）",
    )
    args = ap.parse_args(argv)
    _utf8(sys.stdout)
    _utf8(sys.stderr)
    try:
        code, lines = run(args.findings, args.sources, args.spec)
    except InputError as e:
        sys.stderr.write(f"findings-check: 入力を受け取れません: {e}\n")
        return 2
    sys.stdout.write("".join(line + "\n" for line in lines))
    return code
