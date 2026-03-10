import pytest
from agentarmor.modules.context_guard import ContextGuardModule
from agentarmor.exceptions import ContextOverflow
from agentarmor.hooks import RequestContext


def make_ctx(content: str, model: str = "gpt-4o"):
    return RequestContext(messages=[{"role": "user", "content": content}], model=model)


def test_context_guard_allows_small_message():
    module = ContextGuardModule()
    ctx = make_ctx("Hello, how are you?", model="gpt-4o")
    result = module.pre_check(ctx)
    assert result is ctx
    assert module.checks == 1


def test_context_guard_blocks_oversized_message():
    module = ContextGuardModule(safety_margin=0.95)
    # gpt-4 has 8192 token limit → effective = 7782 tokens → ~31128 chars
    huge_content = "x" * 40_000  # ~10,000 tokens, well over gpt-4's 8192 limit
    ctx = make_ctx(huge_content, model="gpt-4")

    with pytest.raises(ContextOverflow, match="Estimated"):
        module.pre_check(ctx)

    assert module.peak_tokens > 0


def test_context_guard_respects_model_limits():
    module = ContextGuardModule(safety_margin=0.95)
    # gpt-4o has a 128k limit — 10k tokens should be fine
    medium_content = "y" * 40_000  # ~10,000 tokens
    ctx = make_ctx(medium_content, model="gpt-4o")

    # Should NOT raise — 10k tokens is well within 128k window
    result = module.pre_check(ctx)
    assert result is ctx


def test_context_guard_unknown_model_uses_default():
    module = ContextGuardModule(safety_margin=0.95)
    # Unknown model falls back to DEFAULT_CONTEXT_LIMIT (8192)
    huge_content = "z" * 40_000  # ~10,000 tokens
    ctx = make_ctx(huge_content, model="some-unknown-model-v99")

    with pytest.raises(ContextOverflow):
        module.pre_check(ctx)


def test_context_guard_multipart_messages():
    module = ContextGuardModule(safety_margin=0.95)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me a story."},
        {"role": "assistant", "content": "Once upon a time..."},
        {"role": "user", "content": "Continue."},
    ]
    ctx = RequestContext(messages=messages, model="gpt-4o")
    result = module.pre_check(ctx)
    assert result is ctx
    assert module.peak_tokens > 0


def test_context_guard_report():
    module = ContextGuardModule(safety_margin=0.9)
    module.pre_check(make_ctx("test", model="gpt-4o"))
    module.pre_check(make_ctx("another test message", model="gpt-4o"))

    report = module.report()
    assert report["checks"] == 2
    assert report["peak_tokens"] > 0
    assert report["safety_margin"] == 0.9


def test_context_guard_custom_safety_margin():
    # With margin=0.5, effective limit for gpt-4 = 4096 tokens
    module = ContextGuardModule(safety_margin=0.5)
    # ~4500 tokens = 18000 chars → should exceed 4096
    content = "a" * 18_000
    ctx = make_ctx(content, model="gpt-4")

    with pytest.raises(ContextOverflow):
        module.pre_check(ctx)


def test_context_guard_invalid_safety_margin():
    with pytest.raises(ValueError):
        ContextGuardModule(safety_margin=0.0)

    with pytest.raises(ValueError):
        ContextGuardModule(safety_margin=1.5)
