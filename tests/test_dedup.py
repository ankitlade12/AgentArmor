import pytest
import threading
from agentarmor.modules.dedup import DedupModule
from agentarmor.exceptions import DuplicateRequest
from agentarmor.hooks import RequestContext


def _make_ctx(content="hello", model="gpt-4o"):
    return RequestContext(messages=[{"role": "user", "content": content}], model=model)


# ---------------------------------------------------------------------------
# Basic dedup
# ---------------------------------------------------------------------------

def test_dedup_allows_first_call():
    module = DedupModule()
    ctx = _make_ctx("What is Python?")
    result = module.pre_check(ctx)
    assert result is ctx
    assert module.duplicates_detected == 0


def test_dedup_blocks_duplicate():
    module = DedupModule(on_duplicate="block")
    module.pre_check(_make_ctx("What is Python?"))

    with pytest.raises(DuplicateRequest, match="Duplicate prompt"):
        module.pre_check(_make_ctx("What is Python?"))

    assert module.duplicates_detected == 1


def test_dedup_warns_on_duplicate():
    import warnings as _warnings
    module = DedupModule(on_duplicate="warn")
    module.pre_check(_make_ctx("hello"))

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        module.pre_check(_make_ctx("hello"))

    assert module.duplicates_detected == 1
    assert any("Duplicate" in str(w.message) for w in caught)


def test_dedup_different_prompts_allowed():
    module = DedupModule(on_duplicate="block")
    module.pre_check(_make_ctx("What is Python?"))
    module.pre_check(_make_ctx("What is JavaScript?"))
    module.pre_check(_make_ctx("What is Rust?"))

    assert module.duplicates_detected == 0
    assert module.total_checked == 3


def test_dedup_different_models_not_duplicate():
    module = DedupModule(on_duplicate="block")
    module.pre_check(_make_ctx("hello", model="gpt-4o"))
    # Same prompt but different model should NOT be a duplicate
    module.pre_check(_make_ctx("hello", model="gpt-3.5-turbo"))

    assert module.duplicates_detected == 0


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------

def test_dedup_lru_eviction():
    module = DedupModule(max_cache=3, on_duplicate="block")

    module.pre_check(_make_ctx("a"))
    module.pre_check(_make_ctx("b"))
    module.pre_check(_make_ctx("c"))
    # Cache is full: [a, b, c]

    module.pre_check(_make_ctx("d"))
    # Now cache is [b, c, d] — "a" evicted

    # "a" should be allowed again since it was evicted
    module.pre_check(_make_ctx("a"))
    assert module.duplicates_detected == 0


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_dedup_ttl_expires():
    module = DedupModule(on_duplicate="block", ttl_calls=3)

    module.pre_check(_make_ctx("hello"))  # call 1
    module.pre_check(_make_ctx("x"))      # call 2
    module.pre_check(_make_ctx("y"))      # call 3
    module.pre_check(_make_ctx("z"))      # call 4

    # "hello" was seen at call 1, now at call 5, gap = 4 > ttl_calls=3
    # Should be allowed again
    module.pre_check(_make_ctx("hello"))
    assert module.duplicates_detected == 0


def test_dedup_ttl_not_expired():
    module = DedupModule(on_duplicate="block", ttl_calls=5)

    module.pre_check(_make_ctx("hello"))  # call 1
    module.pre_check(_make_ctx("x"))      # call 2

    # "hello" was seen at call 1, now at call 3, gap = 2 < ttl_calls=5
    with pytest.raises(DuplicateRequest):
        module.pre_check(_make_ctx("hello"))


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_dedup_thread_safety():
    module = DedupModule(on_duplicate="block")
    results = []

    def call():
        try:
            module.pre_check(_make_ctx("same prompt"))
            results.append("ok")
        except DuplicateRequest:
            results.append("blocked")

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert results.count("blocked") == 4


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_dedup_report():
    module = DedupModule(on_duplicate="warn", max_cache=100)
    module.pre_check(_make_ctx("a"))
    module.pre_check(_make_ctx("b"))
    module.pre_check(_make_ctx("a"))  # duplicate

    report = module.report()
    assert report["total_checked"] == 3
    assert report["duplicates_detected"] == 1
    assert report["cache_size"] == 2
    assert report["max_cache"] == 100


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_dedup_invalid_on_duplicate():
    with pytest.raises(ValueError, match="on_duplicate"):
        DedupModule(on_duplicate="ignore")


def test_dedup_invalid_max_cache():
    with pytest.raises(ValueError, match="max_cache"):
        DedupModule(max_cache=0)
