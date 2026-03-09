import time
import threading
import pytest
from agentarmor.modules.rate_limiter import RateLimiterModule
from agentarmor.exceptions import RateLimitExceeded
from agentarmor.hooks import RequestContext


def make_ctx():
    return RequestContext(messages=[{"role": "user", "content": "hello"}], model="gpt-4o")


def test_rate_limiter_allows_within_limit():
    module = RateLimiterModule(limit=3, window_seconds=60)

    for _ in range(3):
        module.pre_check(make_ctx())

    assert module.calls_in_window == 3
    assert module.total_blocked == 0


def test_rate_limiter_blocks_over_limit():
    module = RateLimiterModule(limit=2, window_seconds=60)

    module.pre_check(make_ctx())
    module.pre_check(make_ctx())

    with pytest.raises(RateLimitExceeded):
        module.pre_check(make_ctx())

    assert module.total_blocked == 1


def test_rate_limiter_window_expiry():
    module = RateLimiterModule(limit=2, window_seconds=0.2)

    module.pre_check(make_ctx())
    module.pre_check(make_ctx())

    with pytest.raises(RateLimitExceeded):
        module.pre_check(make_ctx())

    time.sleep(0.3)

    module.pre_check(make_ctx())
    assert module.calls_in_window == 1


def test_rate_limiter_report():
    module = RateLimiterModule(limit=5, window_seconds=30)
    module.pre_check(make_ctx())
    module.pre_check(make_ctx())

    report = module.report()
    assert report["limit"] == 5
    assert report["window_seconds"] == 30
    assert report["calls_in_window"] == 2
    assert report["total_blocked"] == 0


def test_rate_limiter_single_call_limit():
    module = RateLimiterModule(limit=1, window_seconds=60)

    module.pre_check(make_ctx())

    with pytest.raises(RateLimitExceeded):
        module.pre_check(make_ctx())

    assert module.total_blocked == 1


def test_rate_limiter_zero_limit_raises():
    """limit=0 should raise immediately at construction — not silently block everything."""
    with pytest.raises(ValueError, match="positive integer"):
        RateLimiterModule(limit=0, window_seconds=60)


def test_rate_limiter_negative_limit_raises():
    with pytest.raises(ValueError):
        RateLimiterModule(limit=-5, window_seconds=60)


def test_rate_limiter_thread_safety():
    """Concurrent threads must not both slip past a limit=1 window."""
    module = RateLimiterModule(limit=1, window_seconds=60)
    results = []

    def call():
        try:
            module.pre_check(make_ctx())
            results.append("ok")
        except RateLimitExceeded:
            results.append("blocked")

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert results.count("blocked") == 4
