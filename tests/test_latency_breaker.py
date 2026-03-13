import pytest
from agentarmor.modules.latency_breaker import LatencyBreakerModule
from agentarmor.exceptions import LatencyThresholdExceeded
from agentarmor.hooks import RequestContext, ResponseContext


def _make_res(latency_ms=100.0):
    req = RequestContext(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")
    return ResponseContext(
        text="response",
        model="gpt-4o",
        provider="openai",
        request=req,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Basic latency monitoring
# ---------------------------------------------------------------------------

def test_fast_responses_pass():
    module = LatencyBreakerModule(threshold_ms=1000)
    module.post_check(_make_res(latency_ms=200))
    module.post_check(_make_res(latency_ms=300))

    assert module.total_breaches == 0
    assert module.tripped is False


def test_single_slow_response_no_trip():
    module = LatencyBreakerModule(threshold_ms=1000, consecutive_limit=3)
    module.post_check(_make_res(latency_ms=1500))

    assert module.total_breaches == 1
    assert module.tripped is False  # Not enough consecutive breaches


def test_consecutive_breaches_trip_warn(capsys):
    module = LatencyBreakerModule(threshold_ms=1000, consecutive_limit=3, on_breach="warn")
    module.post_check(_make_res(latency_ms=1500))
    module.post_check(_make_res(latency_ms=2000))
    module.post_check(_make_res(latency_ms=1800))

    assert module.tripped is True
    assert module.total_trips == 1
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_consecutive_breaches_trip_block():
    module = LatencyBreakerModule(threshold_ms=1000, consecutive_limit=2, on_breach="block")
    module.post_check(_make_res(latency_ms=1500))

    with pytest.raises(LatencyThresholdExceeded, match="circuit breaker"):
        module.post_check(_make_res(latency_ms=2000))

    assert module.tripped is True
    assert module.total_trips == 1


# ---------------------------------------------------------------------------
# Reset on fast response
# ---------------------------------------------------------------------------

def test_fast_response_resets_consecutive():
    module = LatencyBreakerModule(threshold_ms=1000, consecutive_limit=3, on_breach="block")
    module.post_check(_make_res(latency_ms=1500))  # breach 1
    module.post_check(_make_res(latency_ms=1500))  # breach 2
    module.post_check(_make_res(latency_ms=200))   # fast! resets counter

    # Next slow one should be breach 1 again, not trip
    module.post_check(_make_res(latency_ms=1500))
    assert module.tripped is False
    assert module._consecutive_breaches == 1


# ---------------------------------------------------------------------------
# Consecutive limit = 1 (immediate trip)
# ---------------------------------------------------------------------------

def test_immediate_trip_with_limit_1():
    module = LatencyBreakerModule(threshold_ms=500, consecutive_limit=1, on_breach="block")

    with pytest.raises(LatencyThresholdExceeded):
        module.post_check(_make_res(latency_ms=600))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_avg_latency():
    module = LatencyBreakerModule(threshold_ms=5000)
    module.post_check(_make_res(latency_ms=100))
    module.post_check(_make_res(latency_ms=300))
    module.post_check(_make_res(latency_ms=200))

    assert module.avg_latency_ms == 200.0


def test_avg_latency_empty():
    module = LatencyBreakerModule(threshold_ms=5000)
    assert module.avg_latency_ms is None


def test_p95_latency():
    module = LatencyBreakerModule(threshold_ms=50000)
    for i in range(20):
        module.post_check(_make_res(latency_ms=float(i * 100)))

    p95 = module.p95_latency_ms
    assert p95 is not None
    assert p95 >= 1800  # 95th percentile of 0-1900


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_report():
    module = LatencyBreakerModule(threshold_ms=1000, consecutive_limit=2, on_breach="warn")
    module.post_check(_make_res(latency_ms=200))
    module.post_check(_make_res(latency_ms=1500))
    module.post_check(_make_res(latency_ms=1800))

    report = module.report()
    assert report["threshold_ms"] == 1000
    assert report["total_calls"] == 3
    assert report["total_breaches"] == 2
    assert report["total_trips"] == 1
    assert report["tripped"] is True
    assert report["avg_latency_ms"] is not None
    assert report["p95_latency_ms"] is not None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_invalid_threshold():
    with pytest.raises(ValueError, match="threshold_ms"):
        LatencyBreakerModule(threshold_ms=0)


def test_invalid_consecutive_limit():
    with pytest.raises(ValueError, match="consecutive_limit"):
        LatencyBreakerModule(consecutive_limit=0)


def test_invalid_on_breach():
    with pytest.raises(ValueError, match="on_breach"):
        LatencyBreakerModule(on_breach="ignore")
