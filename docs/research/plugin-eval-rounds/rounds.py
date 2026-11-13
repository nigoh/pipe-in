"""プラグインの eval のラウンドの結果（claude plugin eval の JSON）を、ケースごとの表と前の回との差にまとめる（D0096）。

使い方：
    python docs/research/plugin-eval-rounds/rounds.py [<名前>=]<結果の JSON> [[<名前>=]<結果の JSON> ...]

- 結果の JSON は `claude plugin eval --json <ファイル>` の出力か、`--output-dir` の先の aggregate-result.json（中身は同じ）。回の順に並べる。
- <名前> は英数字で始まる 16 字までの英数字・.・-（例 1a・1b・2・final-runs3）。最初の = の前がこの形のときだけ名前として読み、
  そうでなければ全体をパスとして読む。名前が無ければ、並びの番号（1・2…）。
- 出力は標準出力の Markdown だけ。ファイルは書かない。LLM・子プロセス・ネットワークは使わない。標準ライブラリだけ。
- 回の数は、ケースごとの arms.with の長さ（実際に流れた回の数）から数える。cases[].runsPerCase は読まない。
- partial が真の回と、skippedPaidGraders が真の回を含むケースは、前の回との差を「比べられない」と出す（公式の文書の、比べられない回を
  傾向から外す決まり）。途中で止まった回は、次の回の差の基準にしない。
- 読むのは表に要る鍵だけ。パス・モデルの返事・道具の出力が入りうる鍵（suite.root・cases[].dir・promptMarkdown・tracePath・
  explanation・evidence・judgeVotes・error の中身など）は、読みも出しもしない。名前・版・モデル名は決まった形の文字だけを通す。
- 知らない形・欠け・壊れた JSON・ケースが 0 件のときは、表を出さずに、標準エラーへ理由の 1 行を出して終了コード 1 で止まる。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ARG_NAME = re.compile(r"[0-9A-Za-z][0-9A-Za-z.-]{0,15}")
CLAUDE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,31}")
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
CASE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
GRADER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
DEFAULT = "既定"
NONE_MARK = "—"
NOT_COMPARABLE = "比べられない"


class RoundError(Exception):
    """結果の JSON が読めない・知らない形。文は場所だけを示し、値やパスは入れない。"""


class CaseRow:
    """1 つのケースの、表に要る値。"""

    def __init__(self, name: str, score: float, runs: int, passed_runs: int, error_runs: int,
                 failed: dict[str, int], skipped: bool = False) -> None:
        self.name = name
        self.score = score
        self.runs = runs  # with の腕で流れた回の数（頭の行の「回の数」と、表の分母に使う）
        self.passed_runs = passed_runs
        self.error_runs = error_runs
        self.failed = failed  # 落ちた採点の名前 → 落ちた回の数
        self.skipped = skipped  # with の回のどれかで、費用の上限で審査の採点が飛ばされた（skippedPaidGraders が真）


class Round:
    """1 回の結果のうち、表に要る値だけ。"""

    def __init__(self, *, claude: str, model: str | None, judge: str | None, threshold: float | None, passed: int,
                 total: int, overall: float, cost: float, duration: float, partial: bool, cases: list[CaseRow]) -> None:
        self.claude = claude
        self.model = model
        self.judge = judge
        self.threshold = threshold
        self.passed = passed
        self.total = total
        self.overall = overall
        self.cost = cost
        self.duration = duration
        self.partial = partial
        self.cases = {c.name: c for c in cases}


# ---- 形の確かめ -------------------------------------------------------------------------------------------


def _is_dict(v: object) -> bool:
    return isinstance(v, dict)


def _is_bool(v: object) -> bool:
    return isinstance(v, bool)


def _is_int(v: object, low: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= low


def _is_num(v: object, low: float = 0.0, high: float | None = None) -> bool:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        return False
    return v >= low and (high is None or v <= high)


def _is_name(pattern: re.Pattern[str], v: object) -> bool:
    return isinstance(v, str) and pattern.fullmatch(v) is not None


def _take(obj: object, key: str, where: str, ok) -> object:
    """obj[key] を読み、ok(値) が偽なら止める。"""
    if not isinstance(obj, dict) or key not in obj or not ok(obj[key]):
        raise RoundError(f"{where} が無いか、形が違う")
    return obj[key]


def _model(suite: object, key: str) -> object:
    return _take(suite, key, f"suite.{key}", lambda v: v is None or _is_name(MODEL_NAME, v))


def _case(raw: object, i: int) -> CaseRow:
    at = f"cases[{i}]"
    name = _take(raw, "name", f"{at}.name", lambda v: _is_name(CASE_NAME, v))
    aggregates = _take(raw, "aggregates", f"{at}.aggregates", _is_dict)
    score = _take(aggregates, "score", f"{at}.aggregates.score", lambda v: _is_num(v, 0.0, 1.0))
    arms = _take(raw, "arms", f"{at}.arms", _is_dict)
    runs = _take(arms, "with", f"{at}.arms.with", lambda v: isinstance(v, list) and len(v) > 0)
    passed_runs = error_runs = 0
    skipped = False
    failed: dict[str, int] = {}
    for j, run in enumerate(runs):
        rat = f"{at}.arms.with[{j}]"
        passed_runs += bool(_take(run, "passed", f"{rat}.passed", _is_bool))
        # 鍵が無ければ偽。あれば真偽でなければ止まる（_take が run を対応表と確かめたあと）
        if "skippedPaidGraders" in run:
            skipped = bool(_take(run, "skippedPaidGraders", f"{rat}.skippedPaidGraders", _is_bool)) or skipped
        error = _take(run, "error", f"{rat}.error", lambda v: v is None or isinstance(v, str))
        error_runs += bool(error)  # 中身は読まず、数えるだけ
        graders = _take(run, "graders", f"{rat}.graders", lambda v: isinstance(v, list))
        for k, grader in enumerate(graders):
            gat = f"{rat}.graders[{k}]"
            gname = _take(grader, "name", f"{gat}.name", lambda v: _is_name(GRADER_NAME, v))
            gpassed = _take(grader, "passed", f"{gat}.passed", _is_bool)
            # scored が無ければ、点に数える採点として読む（_take が grader を対応表と確かめたあと）
            scored = _take(grader, "scored", f"{gat}.scored", _is_bool) if "scored" in grader else True
            if scored and not gpassed:
                failed[gname] = failed.get(gname, 0) + 1
    return CaseRow(name, float(score), len(runs), passed_runs, error_runs, failed, skipped)


def parse_round(text: str) -> Round:
    """JSON の文字を読み、使う鍵だけを確かめて Round を返す。読めなければ RoundError（0 点の Round は返さない）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RoundError(f"JSON として読めない（{e.lineno} 行目）") from None
    if not isinstance(data, dict):
        raise RoundError("一番上が対応表でない（知らない形）")
    version = data.get("schemaVersion")
    if not (isinstance(version, int) and not isinstance(version, bool) and version == 1):
        raise RoundError("schemaVersion が 1 でない（知らない形）")
    claude = _take(data, "claudeVersion", "claudeVersion", lambda v: _is_name(CLAUDE_VERSION, v))
    cost = _take(data, "costUsd", "costUsd", _is_num)
    duration = _take(data, "durationSeconds", "durationSeconds", _is_num)
    partial = _take(data, "partial", "partial", _is_bool)
    suite = _take(data, "suite", "suite", _is_dict)
    model, judge = _model(suite, "modelOverride"), _model(suite, "judgeModel")
    threshold = _take(suite, "threshold", "suite.threshold", lambda v: v is None or _is_num(v, 0.0, 1.0))
    aggregates = _take(data, "aggregates", "aggregates", _is_dict)
    total = _take(aggregates, "casesTotal", "aggregates.casesTotal", lambda v: _is_int(v, 0))
    passed = _take(aggregates, "casesPassed", "aggregates.casesPassed", lambda v: _is_int(v, 0))
    overall = _take(aggregates, "overallScore", "aggregates.overallScore", lambda v: _is_num(v, 0.0, 1.0))
    raw_cases = _take(data, "cases", "cases", lambda v: isinstance(v, list))
    if not raw_cases:
        raise RoundError("ケースが 0 件")
    cases: list[CaseRow] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_cases):
        row = _case(raw, i)
        if row.name in seen:
            raise RoundError(f"cases[{i}].name が前のケースと重なっている")
        seen.add(row.name)
        cases.append(row)
    return Round(
        claude=claude, model=model, judge=judge, threshold=threshold, passed=passed, total=total,
        overall=float(overall), cost=float(cost), duration=float(duration), partial=partial, cases=cases,
    )


# ---- 表を作る ----------------------------------------------------------------------------------------------


def _two(x: float) -> str:
    return f"{x:.2f}"


def _diff(now: float, before: float) -> str:
    """表に出す 2 桁の値どうしの差。丸めて 0 なら符号なしの 0.00。"""
    d = float(_two(now)) - float(_two(before))
    text = f"{d:+.2f}"
    return "0.00" if text in ("+0.00", "-0.00") else text


def _failed(case: CaseRow) -> str:
    if not case.failed:
        return NONE_MARK
    names = sorted(case.failed)
    if case.runs >= 2:
        return "・".join(f"{n}（{case.failed[n]}/{case.runs}）" for n in names)
    return "・".join(names)


def _or_default(v: str | None) -> str:
    return DEFAULT if v is None else v


def _runs_text(rnd: Round) -> str:
    """頭の行の「回の数」。ケースの with の長さが全部同じならその数、違えば「最小〜最大」（途中で止まった回などを隠さない）。"""
    counts = {c.runs for c in rnd.cases.values()}
    low, high = min(counts), max(counts)
    return str(low) if low == high else f"{low}〜{high}"


def _diff_cell(cname: str, case: CaseRow, rnd: Round, first: bool, base: tuple[str, Round] | None) -> str:
    """1 つのケースの「前の回との差」の欄。上から順に、最初に当たったもの（D0096 の設計 18.3.2）。

    base は差の基準（前の回のうち、途中で止まっていない一番近い回の名前と Round）。first は前に回が無いこと。
    """
    if first:
        return NONE_MARK
    if rnd.partial or base is None:
        # この回が途中で止まった・前の回がどれも途中で止まった
        return NOT_COMPARABLE
    before = base[1].cases.get(cname)
    if before is None:
        return "新しい"
    if case.skipped or before.skipped:
        # 審査の採点が費用の上限で飛ばされた回を含むケースは、点の意味が違うので比べない
        return NOT_COMPARABLE
    return _diff(case.score, before.score)


def _notes(rnd: Round, first: bool, base: tuple[str, Round] | None, between: list[str]) -> list[str]:
    """表の下の注意の行（D0096 の設計 18.3.3 の順）。入るのは回とケースの名前・版・モデル名だけ。

    between は、基準のあとの途中で止まった回の名前（引数の順）。
    """
    notes: list[str] = []
    if rnd.partial:
        notes.append("注意：この回は途中で止まった（partial）。前の回との差は比べず、次の回の差の基準にもしない")
    elif base is not None and between:
        notes.append(f"注意：差は回 {base[0]} と比べた（途中で止まった回 {'・'.join(between)} は基準にしない）")
    elif base is None and not first:
        notes.append("注意：前に途中で止まっていない回が無いので、差は比べられない")
    if base is not None:
        # 「前の回」は基準の回のこと（基準が直前の回でないときは、上の「差は回 … と比べた」の行で分かる）
        prev = base[1]
        gone = sorted(set(prev.cases) - set(rnd.cases))
        if gone:
            notes.append("前の回にあってこの回に無いケース：" + "・".join(gone))
        for label, before, now in (
            ("Claude Code の版", prev.claude, rnd.claude),
            ("モデル", _or_default(prev.model), _or_default(rnd.model)),
            ("審査役", _or_default(prev.judge), _or_default(rnd.judge)),
        ):
            if before != now:
                notes.append(f"注意：{label}が前の回と違う（{before} → {now}）。差は比べられないことがある")
    skipped = sorted(n for n, c in rnd.cases.items() if c.skipped)
    if skipped:
        notes.append(f"注意：審査の採点が費用の上限で飛ばされた回を含むケース：{'・'.join(skipped)}（このケースの点は、前後の回と比べられない）")
    return notes


def _block(name: str, rnd: Round, *, first: bool, base: tuple[str, Round] | None, between: list[str]) -> list[str]:
    threshold = DEFAULT if rnd.threshold is None else format(rnd.threshold, "g")
    lines = [
        f"## 回 {name}",
        "",
        f"- Claude Code {rnd.claude}・モデル {_or_default(rnd.model)}・審査役 {_or_default(rnd.judge)}・回の数 {_runs_text(rnd)}・合格の線 {threshold}",
        f"- 合格 {rnd.passed}/{rnd.total}・全体の点 {_two(rnd.overall)}・費用 ${_two(rnd.cost)}・時間 {round(rnd.duration)} 秒・"
        f"途中で止まった {'はい' if rnd.partial else 'いいえ'}",
        "",
        "| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cname in sorted(rnd.cases):
        c = rnd.cases[cname]
        diff = _diff_cell(cname, c, rnd, first, base)
        lines.append(f"| {cname} | {_two(c.score)} | {c.passed_runs}/{c.runs} | {_failed(c)} | {c.error_runs} | {diff} |")
    for note in _notes(rnd, first, base, between):
        lines += ["", note]
    return lines


def render(rounds: list[tuple[str, Round]]) -> str:
    """名前と Round の並び（回の順）から Markdown を作る。純粋な関数。

    差の基準は、前の回のうち途中で止まっていない一番近い回。途中で止まった回は基準にせず、基準のあとの並びに足す。
    """
    blocks: list[str] = []
    base: tuple[str, Round] | None = None
    between: list[str] = []
    for i, (name, rnd) in enumerate(rounds):
        blocks.append("\n".join(_block(name, rnd, first=i == 0, base=base, between=between)))
        if rnd.partial:
            between = [*between, name]
        else:
            base, between = (name, rnd), []
    return "\n\n".join(blocks)


# ---- 入口 -------------------------------------------------------------------------------------------------


def _split(arg: str, index: int) -> tuple[str, str]:
    """「名前=パス」なら (名前, パス)、そうでなければ (並びの番号, 全体)。"""
    head, sep, tail = arg.partition("=")
    if sep and ARG_NAME.fullmatch(head):
        return head, tail
    return str(index), arg


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rounds.py",
        description="claude plugin eval の結果の JSON を回の順に読み、ケースごとの点と前の回との差を Markdown の表で出す（読むだけ）。",
    )
    parser.add_argument("results", nargs="+", metavar="RESULT", help="[名前=]結果の JSON（--json の出力か aggregate-result.json）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    loaded: list[tuple[str, Round]] = []
    for i, arg in enumerate(args.results, 1):
        name, path = _split(arg, i)
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            reason = f"読めない（{type(e).__name__}）"
        else:
            try:
                loaded.append((name, parse_round(text)))
                continue
            except RoundError as e:
                reason = str(e)
        print(f"rounds.py: {i} 番目の結果（{name}）: {reason}", file=sys.stderr)
        return 1
    print(render(loaded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
