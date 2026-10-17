"""段のメッセージ（ログの1行と同じ形の dict）から、費用・トークン・環境・利用枠を集める。"""

from __future__ import annotations

from pipe_in.usage.metrics import StageMetrics, summarize_runs

INIT = {
    "_type": "SystemMessage",
    "subtype": "init",
    "data": {"model": "claude-opus-5-5", "claude_code_version": "2.1.301", "apiKeySource": "none", "permissionMode": "default"},
}


def rate(five: float, seven: float) -> dict:
    return {
        "_type": "RateLimitEvent",
        "rate_limit_info": {
            "status": "allowed",
            "utilization": None,
            "overage_status": "rejected",
            "raw": {
                "unifiedWindows": {
                    "five_hour": {"utilization": five, "resetsAt": 1792170000},
                    "seven_day": {"utilization": seven, "resetsAt": 1792591200},
                }
            },
        },
    }


RESULT = {
    "_type": "ResultMessage",
    "duration_ms": 207980,
    "duration_api_ms": 199164,
    "num_turns": 40,
    "stop_reason": "end_turn",
    "terminal_reason": "completed",
    "total_cost_usd": 1.6769318,
    "usage": {
        "input_tokens": 32,
        "cache_creation_input_tokens": 108921,
        "cache_read_input_tokens": 1511319,
        "output_tokens": 25141,
        "output_tokens_details": {"thinking_tokens": 1003},
        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 2},
        "cache_creation": {"ephemeral_1h_input_tokens": 108921, "ephemeral_5m_input_tokens": 0},
        "service_tier": "standard",
    },
    "model_usage": {
        "claude-opus-5-5": {
            "inputTokens": 32, "outputTokens": 25141, "cacheReadInputTokens": 1511319,
            "cacheCreationInputTokens": 108921, "thinkingTokens": 1003, "costUSD": 1.6765798, "costBasis": "list",
        },
        "claude-haiku-5-5": {
            "inputTokens": 1350, "outputTokens": 434, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "thinkingTokens": 410, "costUSD": 0.000352, "costBasis": "list",
        },
    },
    "permission_denials": [{"tool_name": "PowerShell", "tool_use_id": "x", "tool_input": {}}],
}


def fed(*msgs: dict) -> StageMetrics:
    m = StageMetrics()
    for msg in msgs:
        m.feed(msg)
    return m


def test_tokens_from_result():
    m = fed(INIT, RESULT)
    t = m.tokens
    assert (t.input, t.cache_write, t.cache_read, t.output) == (32, 108921, 1511319, 25141)
    assert (t.thinking, t.cache_write_1h, t.cache_write_5m) == (1003, 108921, 0)
    assert (t.web_search, t.web_fetch) == (0, 2)
    assert m.duration_api_ms == 199164
    assert (m.stop_reason, m.terminal_reason) == ("end_turn", "completed")


def test_cache_reuse_rate():
    t = fed(RESULT).tokens
    assert round(t.cache_reuse_rate, 4) == round(1511319 / (32 + 108921 + 1511319), 4)
    assert fed().tokens.cache_reuse_rate == 0.0  # 割り算で落ちない


def test_by_model():
    m = fed(RESULT)
    assert set(m.by_model) == {"claude-opus-5-5", "claude-haiku-5-5"}
    opus = m.by_model["claude-opus-5-5"]
    assert opus.tokens.cache_read == 1511319 and opus.tokens.thinking == 1003
    assert round(opus.cost_usd, 4) == 1.6766
    assert m.cost_basis == "list"


def test_environment_from_init():
    m = fed(INIT, RESULT)
    assert (m.model, m.claude_code_version, m.api_key_source, m.permission_mode) == (
        "claude-opus-5-5", "2.1.301", "none", "default",
    )


def test_rate_limits_keep_first_and_last():
    m = fed(rate(0.01, 0.14), RESULT, rate(0.03, 0.15))
    five = m.rate_limits["five_hour"]
    assert (five.first, five.last, five.resets_at) == (0.01, 0.03, 1792170000)
    assert m.rate_limits["seven_day"].last == 0.15
    assert m.overage_status == "rejected"


def test_permission_denials():
    assert fed(RESULT).permission_denials == ["PowerShell"]


def test_broken_messages_are_ignored():
    m = fed({"_type": "ResultMessage", "usage": None, "model_usage": "x"}, {"_type": "RateLimitEvent"}, {"_type": "SystemMessage"})
    assert m.tokens.output == 0 and m.by_model == {} and m.rate_limits == {}


def test_summarize_runs_totals_and_rate_span():
    a = fed(INIT, rate(0.01, 0.14), RESULT).to_dict()
    b = fed(INIT, RESULT, rate(0.05, 0.16)).to_dict()
    s = summarize_runs([a, b])
    assert s["tokens"]["output"] == 25141 * 2
    assert s["by_model"]["claude-opus-5-5"]["tokens"]["cache_read"] == 1511319 * 2
    assert s["models"] == ["claude-opus-5-5"]
    assert s["rate_limits"]["five_hour"] == {
        "first": 0.01, "last": 0.05, "resets_at": 1792170000, "peak": 0.05, "reset_seen": False,
    }
    assert s["duration_api_ms"] == 199164 * 2


def test_summarize_runs_accepts_old_entries_without_metrics():
    s = summarize_runs([{}, {"metrics": None}])
    assert s["tokens"]["output"] == 0 and s["models"] == []


def test_rate_window_reset_inside_a_stage():
    m = fed(rate(0.12, 0.14), rate(0.13, 0.14), rate(0.0, 0.14), rate(0.01, 0.15))
    five = m.rate_limits["five_hour"]
    assert (five.first, five.last, five.peak, five.reset_seen) == (0.12, 0.01, 0.13, True)
    assert m.rate_limits["seven_day"].reset_seen is False


def test_rate_window_reset_between_stages():
    a = fed(rate(0.12, 0.14), rate(0.13, 0.14)).to_dict()
    b = fed(rate(0.01, 0.14), rate(0.02, 0.15)).to_dict()
    five = summarize_runs([a, b])["rate_limits"]["five_hour"]
    assert five["first"] == 0.12 and five["last"] == 0.02
    assert five["peak"] == 0.13 and five["reset_seen"] is True
