"""指摘の形 v1 のファイル2つか3つから、共通部分（同じ節への指摘）だけを残す（D0076）。

quorum は、同じ指示で別々に流した2体（か3体）の指摘のファイルを読み、
キー（location.source と location.section を正規化したもの）が合う指摘だけを書き出す。
標準ライブラリと findings_check（読み込みと正規化）だけで動く。SDK は呼ばない。
票の数や一致の数は指摘の欄に足さず、標準出力に出す。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .findings_check import InputError, load_json, load_versioned, normalize

Key = tuple[str, str]  # (正規化した location.source, 正規化した location.section)

DEFAULT_THRESHOLD = 0.8


def finding_key(f: Any, label: str) -> Key:
    if not isinstance(f, dict):
        raise InputError(f"{label}は辞書ではありません")
    loc = f.get("location")
    if not isinstance(loc, dict):
        raise InputError(f"{label}の location が辞書ではありません")
    source, section = loc.get("source"), loc.get("section")
    if not isinstance(source, str) or not isinstance(section, str):
        raise InputError(f"{label}の location.source と location.section は文字列にしてください")
    return normalize(source), normalize(section)


def load_findings(path: Path) -> list[dict]:
    items = load_versioned(load_json(path), "findings", "指摘")
    for i, f in enumerate(items):
        finding_key(f, f"{path} の {i + 1} 件目")
    return items


def _keys(findings: list[dict]) -> set[Key]:
    return {finding_key(f, "指摘") for f in findings}


def common(docs: list[list[dict]]) -> list[dict]:
    """2つ：1つ目のうち、キーが2つ目にもあるもの。3つ：キーが2つ以上のファイルにあるもの。

    残すのは、そのキーを持ついちばん前のファイルの指摘すべて（ファイルの順 → ファイルの中の順）。
    同じキーが1つのファイルに複数あっても、そのファイルは1票。
    """
    key_sets = [_keys(d) for d in docs]
    votes: dict[Key, int] = {}
    for ks in key_sets:
        for k in ks:
            votes[k] = votes.get(k, 0) + 1
    kept: list[dict] = []
    claimed: set[Key] = set()  # すでに前のファイルが持っていたキー
    for d, ks in zip(docs, key_sets):
        for f in d:
            k = finding_key(f, "指摘")
            if votes[k] >= 2 and k not in claimed:
                kept.append(f)
        claimed |= ks
    return kept


def jaccard(a: set[Key], b: set[Key]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def renumber(findings: list[dict]) -> list[dict]:
    out = copy.deepcopy(findings)
    for i, f in enumerate(out, 1):
        f["id"] = f"F-{i:03d}"
    return out


def run(paths: list[Path], out: Path, threshold: float, no_third: bool) -> tuple[int, list[str]]:
    if len(paths) not in (2, 3):
        raise InputError(f"指摘のファイルは2つか3つ渡してください（{len(paths)} 個です）")
    out_resolved = out.resolve()
    for p in paths:
        if p.resolve() == out_resolved:
            raise InputError(f"--out が入力のファイルと同じです: {out}")
    docs = [load_findings(p) for p in paths]
    kept = renumber(common(docs))

    counts = "・".join(f"{len(d)} 件" for d in docs)
    lines: list[str] = []
    code = 0
    if len(docs) == 2:
        score = jaccard(_keys(docs[0]), _keys(docs[1]))
        shown = f"{score:.2f}"
        lines.append(f"共通部分 {len(kept)} 件（各体 {counts}、節の一致 {shown}）")
        if score >= threshold:
            lines.append("3体目は要りません")
        elif no_third:
            lines.append(f"3体目は流さず、共通部分だけを書きました（節の一致 {shown}）")
        else:
            lines.append("3体目が要ります")
            code = 3
    else:
        lines.append(f"共通部分 {len(kept)} 件（各体 {counts}）")
        lines.append("使った体は3体")
        lines.append("3体目は要りません")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps({"v": 1, "findings": kept}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return code, lines


def _utf8(stream: Any) -> None:
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="pipe-in-gen quorum",
        description="同じ指示で流した2体（か3体）の指摘のファイルから、同じ節への指摘だけを残します（LLM を呼びません）。"
        "終了コード 0＝3体目は要らない、3＝3体目が要る、2＝入力を受け取れない。",
    )
    ap.add_argument("findings", type=Path, nargs="+", help="指摘のファイル（2つか3つ）")
    ap.add_argument("--out", type=Path, required=True, help="共通部分を書くファイル")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="節の一致がこれ未満なら3体目が要る（既定 0.8）")
    ap.add_argument("--no-third", action="store_true", help="3体目が要るときも終了コード 0 にする")
    args = ap.parse_args(argv)
    _utf8(sys.stdout)
    _utf8(sys.stderr)
    try:
        code, lines = run(args.findings, args.out, args.threshold, args.no_third)
    except InputError as e:
        sys.stderr.write(f"quorum: 入力を受け取れません: {e}\n")
        return 2
    sys.stdout.write("".join(line + "\n" for line in lines))
    return code
