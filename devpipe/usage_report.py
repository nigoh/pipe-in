"""まとめ（99_summary.md）のうち、トークン・モデル別・環境・利用枠の節を組み立てる。

入力は state.json の runs と同じ形（段の実行には seq と metrics がある）。数字が1つもなければ何も出さない。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .metrics import summarize_runs

RATE_WINDOW_LABELS = {"five_hour": "5時間枠", "seven_day": "7日枠"}
COST_BASIS_NOTES = {
    "list": "定価（list）での見積もり。サブスクリプションでログインしている場合、請求額とは一致しない（利用枠の使用率のほうが実際の負担に近い）",
}


def usage_sections(history: list[dict[str, Any]], stage_labels: dict[str, str]) -> list[str]:
    runs = [h for h in history if "seq" in h]
    metrics = [h.get("metrics") or {} for h in runs]
    total = summarize_runs(metrics)
    if not any(total["tokens"][k] for k in ("input", "cache_write", "cache_read", "output")) and not total["by_model"]:
        return []

    lines = ["", "## トークンの内訳", ""]
    lines += [
        "| # | 段 | 回 | 入力 | キャッシュ書き込み | キャッシュ読み込み | 出力 | うち thinking | キャッシュ再利用率 | API 待ち |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for h, m in zip(runs, metrics):
        t = m.get("tokens") or {}
        lines.append(
            f"| {h['seq']} | {stage_labels.get(h.get('stage', ''), h.get('stage', ''))} | {h.get('attempt') or ''} | "
            + _token_cells(t)
            + f" | {_rate(t.get('cache_reuse_rate'))} | {_sec(m.get('duration_api_ms'))} |"
        )
    t = total["tokens"]
    lines.append(
        "| | **合計** | | " + _token_cells(t, bold=True)
        + f" | **{_rate(t['cache_reuse_rate'])}** | **{_sec(total['duration_api_ms'])}** |"
    )
    if t["web_search"] or t["web_fetch"]:
        lines += ["", f"- Web 検索 {t['web_search']} 回・Web 取得 {t['web_fetch']} 回"]

    if total["by_model"]:
        lines += ["", "## モデル別", ""]
        lines += [
            "| モデル | 入力 | キャッシュ書き込み | キャッシュ読み込み | 出力 | うち thinking | 費用 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for name, mu in sorted(total["by_model"].items(), key=lambda kv: -kv[1]["cost_usd"]):
            lines.append(f"| {name} | " + _token_cells(mu["tokens"]) + f" | ${mu['cost_usd']:.3f} |")

    lines += ["", "## 環境", ""]
    lines.append(f"- 段の既定のモデル: {_join(total['models'])}")
    lines.append(f"- Claude Code: {_join(_distinct(metrics, 'claude_code_version'))}")
    lines.append(f"- 認証の出どころ（apiKeySource）: {_join(_distinct(metrics, 'api_key_source'))}")
    lines.append(f"- 許可のモード: {_join(_distinct(metrics, 'permission_mode'))}")
    bases = _distinct(metrics, "cost_basis")
    if bases:
        lines.append(f"- 費用の根拠: {'、'.join(COST_BASIS_NOTES.get(b, b) for b in bases)}")
    reasons = [
        f"{h['seq']}: {m.get('terminal_reason')}"
        for h, m in zip(runs, metrics)
        if m.get("terminal_reason") not in (None, "completed")
    ]
    if reasons:
        lines.append(f"- 途中で止まった段（terminal_reason）: {'、'.join(reasons)}")

    rates = total["rate_limits"]
    if rates:
        lines += ["", "## 利用枠", ""]
        lines += ["| 枠 | 使用率（開始 → 終了） | 戻る時刻 |", "|---|---|---|"]
        for name, w in rates.items():
            span = f"{_pct(w.get('first'))} → {_pct(w.get('last'))}"
            if w.get("reset_seen"):
                span += f"（途中で枠が戻りました。最大 {_pct(w.get('peak'))}）"
            lines.append(f"| {RATE_WINDOW_LABELS.get(name, name)} | {span} | {_time(w.get('resets_at'))} |")
        overage = _distinct(metrics, "overage_status")
        if overage:
            lines += ["", f"- 枠を超えたときの超過利用: {_join(overage)}"]
    return lines


def _token_cells(t: dict[str, Any], *, bold: bool = False) -> str:
    keys = ("input", "cache_write", "cache_read", "output", "thinking")
    cells = [f"{int(t.get(k) or 0):,}" for k in keys]
    return " | ".join(f"**{c}**" if bold else c for c in cells)


def _distinct(metrics: list[dict[str, Any]], key: str) -> list[str]:
    out: list[str] = []
    for m in metrics:
        v = m.get(key)
        if v and v not in out:
            out.append(v)
    return out


def _join(values: list[str]) -> str:
    return "、".join(values) if values else "（記録なし）"


def _rate(v: Any) -> str:
    return f"{float(v) * 100:.1f}%" if isinstance(v, (int, float)) else "—"


def _pct(v: Any) -> str:
    return f"{float(v) * 100:.0f}%" if isinstance(v, (int, float)) else "—"


def _sec(ms: Any) -> str:
    return f"{int(ms) / 1000:.0f}s" if isinstance(ms, int) and ms else "—"


def _time(ts: Any) -> str:
    if not isinstance(ts, int):
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
