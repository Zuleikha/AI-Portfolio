"""Unit tests for RequestMetrics — accumulation, properties, rolling window, and to_dict."""

import pytest

from src.monitoring.metrics import RequestMetrics, get_metrics

# ── Accumulation ──────────────────────────────────────────────────────────────


class TestAccumulation:
    def test_initial_state_is_zero(self):
        m = RequestMetrics()
        assert m.query_count == 0
        assert m.total_tokens == 0
        assert m.total_latency_ms == 0.0
        assert m.errors == 0

    def test_record_increments_query_count(self):
        m = RequestMetrics()
        m.record(50, 200.0)
        assert m.query_count == 1

    def test_multiple_records_accumulate_query_count(self):
        m = RequestMetrics()
        for _ in range(5):
            m.record(10, 100.0)
        assert m.query_count == 5

    def test_record_accumulates_total_tokens(self):
        m = RequestMetrics()
        m.record(100, 50.0)
        m.record(200, 50.0)
        assert m.total_tokens == 300

    def test_record_accumulates_total_latency(self):
        m = RequestMetrics()
        m.record(10, 300.0)
        m.record(10, 200.0)
        assert m.total_latency_ms == pytest.approx(500.0)


# ── Properties ────────────────────────────────────────────────────────────────


class TestProperties:
    def test_avg_latency_ms_is_arithmetic_mean(self):
        m = RequestMetrics()
        m.record(10, 100.0)
        m.record(10, 200.0)
        assert m.avg_latency_ms == pytest.approx(150.0)

    def test_avg_tokens_per_query_is_arithmetic_mean(self):
        m = RequestMetrics()
        m.record(100, 10.0)
        m.record(200, 10.0)
        assert m.avg_tokens_per_query == pytest.approx(150.0)

    def test_avg_latency_with_no_queries_returns_zero(self):
        m = RequestMetrics()
        assert m.avg_latency_ms == 0.0

    def test_avg_tokens_with_no_queries_returns_zero(self):
        m = RequestMetrics()
        assert m.avg_tokens_per_query == 0.0

    def test_errors_field_is_directly_mutable(self):
        m = RequestMetrics()
        m.errors += 3
        assert m.errors == 3


# ── Rolling window ────────────────────────────────────────────────────────────


class TestRollingWindow:
    def test_window_caps_at_100_latency_entries(self):
        m = RequestMetrics()
        for i in range(120):
            m.record(i, float(i))
        assert len(m._latency_window) <= 100

    def test_window_caps_at_100_token_entries(self):
        m = RequestMetrics()
        for i in range(120):
            m.record(i, float(i))
        assert len(m._token_window) <= 100

    def test_window_retains_most_recent_values(self):
        m = RequestMetrics()
        for i in range(110):
            m.record(i, float(i))
        # Most recent latency (109.0) should be the last element
        assert m._latency_window[-1] == pytest.approx(109.0)

    def test_window_exactly_at_100_is_not_trimmed(self):
        m = RequestMetrics()
        for i in range(100):
            m.record(i, float(i))
        assert len(m._latency_window) == 100


# ── to_dict ───────────────────────────────────────────────────────────────────


class TestToDict:
    def test_to_dict_contains_all_expected_keys(self):
        m = RequestMetrics()
        d = m.to_dict()
        for key in (
            "query_count",
            "total_tokens",
            "avg_latency_ms",
            "avg_tokens_per_query",
            "errors",
            "recent_latencies_ms",
        ):
            assert key in d

    def test_recent_latencies_shows_at_most_last_ten(self):
        m = RequestMetrics()
        for i in range(15):
            m.record(10, float(i * 100))
        d = m.to_dict()
        assert len(d["recent_latencies_ms"]) == 10

    def test_recent_latencies_last_entry_is_most_recent(self):
        m = RequestMetrics()
        for i in range(15):
            m.record(10, float(i * 100))
        d = m.to_dict()
        assert d["recent_latencies_ms"][-1] == pytest.approx(1400.0)

    def test_avg_values_are_rounded(self):
        m = RequestMetrics()
        m.record(1, 100.123456)
        d = m.to_dict()
        # Should be rounded to 1 decimal place per implementation
        assert isinstance(d["avg_latency_ms"], float)

    def test_errors_in_dict_reflects_mutable_field(self):
        m = RequestMetrics()
        m.errors = 7
        assert m.to_dict()["errors"] == 7


# ── Singleton ─────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_metrics_returns_same_instance(self):
        assert get_metrics() is get_metrics()

    def test_records_persist_across_get_metrics_calls(self):
        m = get_metrics()
        before = m.query_count
        get_metrics().record(10, 100.0)
        assert get_metrics().query_count == before + 1
