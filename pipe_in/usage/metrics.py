"""段のメッセージから、費用・トークン・環境・利用枠を集める。

メッセージは SDK のオブジェクトを dict にしたもの（ログの1行と同じ形）で受け取る。
SDK の版で項目が増えたり欠けたりしても落ちないよう、知らない形は読み飛ばす。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Tokens:
    input: int = 0  # キャッシュを使わない入力
    cache_write: int = 0  # キャッシュへの書き込み
    cache_write_1h: int = 0
    cache_write_5m: int = 0
    cache_read: int = 0  # キャッシュからの読み込み
    output: int = 0
    thinking: int = 0  # 出力のうち考える過程の分
    web_search: int = 0
    web_fetch: int = 0

    @property
    def total_input(self) -> int:
        return self.input + self.cache_write + self.cache_read

    @property
    def cache_reuse_rate(self) -> float:
        """入力のうち、キャッシュから読めた割合。"""
        return self.cache_read / self.total_input if self.total_input else 0.0

    def add(self, other: Tokens) -> None:
        for k, v in asdict(other).items():
            setattr(self, k, getattr(self, k) + v)


@dataclass
class ModelUsage:
    tokens: Tokens = field(default_factory=Tokens)
    cost_usd: float = 0.0


@dataclass
class RateWindow:
    first: float | None = None  # 段の中で最初に見えた使用率（0〜1）
    last: float | None = None  # 最後に見えた使用率
    resets_at: int | None = None  # 枠が戻る時刻（UNIX 秒）
    peak: float | None = None  # 見えた使用率の最大
    reset_seen: bool = False  # 使用率が下がった＝途中で枠が戻った

    def observe(self, u: float | None) -> None:
        if u is None:
            return
        if self.first is None:
            self.first = u
        if self.last is not None and u < self.last:
            self.reset_seen = True
        self.last = u
        self.peak = u if self.peak is None else max(self.peak, u)


@dataclass
class StageMetrics:
    model: str | None = None
    claude_code_version: str | None = None
    api_key_source: str | None = None
    permission_mode: str | None = None
    cost_basis: str | None = None  # "list" なら定価ベースの見積もり
    tokens: Tokens = field(default_factory=Tokens)
    by_model: dict[str, ModelUsage] = field(default_factory=dict)
    duration_api_ms: int = 0
    stop_reason: str | None = None
    terminal_reason: str | None = None
    permission_denials: list[str] = field(default_factory=list)
    rate_limits: dict[str, RateWindow] = field(default_factory=dict)
    overage_status: str | None = None

    def feed(self, msg: dict[str, Any]) -> None:
        kind = msg.get("_type")
        if kind == "SystemMessage" and msg.get("subtype") == "init":
            self._init(_dict(msg.get("data")))
        elif kind == "RateLimitEvent":
            self._rate(_dict(msg.get("rate_limit_info")))
        elif kind == "ResultMessage":
            self._result(msg)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tokens"]["cache_reuse_rate"] = round(self.tokens.cache_reuse_rate, 4)
        return d

    # ---- 中身 -------------------------------------------------------------

    def _init(self, data: dict[str, Any]) -> None:
        self.model = _str(data.get("model")) or self.model
        self.claude_code_version = _str(data.get("claude_code_version")) or self.claude_code_version
        self.api_key_source = _str(data.get("apiKeySource")) or self.api_key_source
        self.permission_mode = _str(data.get("permissionMode")) or self.permission_mode

    def _rate(self, info: dict[str, Any]) -> None:
        self.overage_status = _str(info.get("overage_status")) or self.overage_status
        windows = _dict(_dict(info.get("raw")).get("unifiedWindows"))
        for name, w in windows.items():
            w = _dict(w)
            u = w.get("utilization")
            if not isinstance(u, (int, float)):
                continue
            rw = self.rate_limits.setdefault(name, RateWindow())
            rw.observe(float(u))
            if isinstance(w.get("resetsAt"), int):
                rw.resets_at = w["resetsAt"]

    def _result(self, msg: dict[str, Any]) -> None:
        self.duration_api_ms = _int(msg.get("duration_api_ms"))
        self.stop_reason = _str(msg.get("stop_reason"))
        self.terminal_reason = _str(msg.get("terminal_reason"))
        u = _dict(msg.get("usage"))
        cc = _dict(u.get("cache_creation"))
        stu = _dict(u.get("server_tool_use"))
        self.tokens = Tokens(
            input=_int(u.get("input_tokens")),
            cache_write=_int(u.get("cache_creation_input_tokens")),
            cache_write_1h=_int(cc.get("ephemeral_1h_input_tokens")),
            cache_write_5m=_int(cc.get("ephemeral_5m_input_tokens")),
            cache_read=_int(u.get("cache_read_input_tokens")),
            output=_int(u.get("output_tokens")),
            thinking=_int(_dict(u.get("output_tokens_details")).get("thinking_tokens")),
            web_search=_int(stu.get("web_search_requests")),
            web_fetch=_int(stu.get("web_fetch_requests")),
        )
        self.by_model = {}
        for name, mu in _dict(msg.get("model_usage")).items():
            mu = _dict(mu)
            self.by_model[name] = ModelUsage(
                tokens=Tokens(
                    input=_int(mu.get("inputTokens")),
                    cache_write=_int(mu.get("cacheCreationInputTokens")),
                    cache_read=_int(mu.get("cacheReadInputTokens")),
                    output=_int(mu.get("outputTokens")),
                    thinking=_int(mu.get("thinkingTokens")),
                    web_search=_int(mu.get("webSearchRequests")),
                ),
                cost_usd=float(mu.get("costUSD") or 0.0),
            )
            self.cost_basis = _str(mu.get("costBasis")) or self.cost_basis
        denials = msg.get("permission_denials")
        if isinstance(denials, list):
            self.permission_denials = [str(_dict(d).get("tool_name", "?")) for d in denials]


def summarize_runs(metrics: list[dict[str, Any] | None]) -> dict[str, Any]:
    """段ごとの metrics（to_dict の形）を、パイプライン全体の合計にまとめる。

    古い state.json の段（metrics なし）も受け付ける。
    """
    total = Tokens()
    by_model: dict[str, ModelUsage] = {}
    models: list[str] = []
    rates: dict[str, RateWindow] = {}
    api_ms = 0
    for m in metrics:
        m = _dict(m)
        if not m:
            continue
        total.add(_tokens(m.get("tokens")))
        api_ms += _int(m.get("duration_api_ms"))
        if m.get("model") and m["model"] not in models:
            models.append(m["model"])
        for name, mu in _dict(m.get("by_model")).items():
            agg = by_model.setdefault(name, ModelUsage())
            agg.tokens.add(_tokens(_dict(mu).get("tokens")))
            agg.cost_usd += float(_dict(mu).get("cost_usd") or 0.0)
        for name, w in _dict(m.get("rate_limits")).items():
            w = _dict(w)
            agg_w = rates.setdefault(name, RateWindow())
            # 段の中の最初・最大・最後を順に流すと、段をまたいで枠が戻ったことも拾える
            for key in ("first", "peak", "last"):
                if isinstance(w.get(key), (int, float)):
                    agg_w.observe(float(w[key]))
            agg_w.reset_seen = agg_w.reset_seen or bool(w.get("reset_seen"))
            if w.get("resets_at") is not None:
                agg_w.resets_at = w["resets_at"]
    tokens = asdict(total)
    tokens["cache_reuse_rate"] = round(total.cache_reuse_rate, 4)
    return {
        "tokens": tokens,
        "by_model": {
            k: {"tokens": asdict(v.tokens), "cost_usd": round(v.cost_usd, 6)} for k, v in by_model.items()
        },
        "models": models,
        "rate_limits": {k: asdict(v) for k, v in rates.items()},
        "duration_api_ms": api_ms,
    }


def _tokens(d: Any) -> Tokens:
    d = _dict(d)
    return Tokens(**{k: _int(d.get(k)) for k in Tokens.__dataclass_fields__})


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _int(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None
