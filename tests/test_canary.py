import pytest
from agentarmor.modules.canary import CanaryModule
from agentarmor.exceptions import CanaryLeakDetected
from agentarmor.hooks import RequestContext, ResponseContext


def _make_req(messages, model="gpt-4o"):
    return RequestContext(messages=messages, model=model)


def _make_res(text, req):
    return ResponseContext(
        text=text,
        model=req.model,
        provider="openai",
        request=req,
    )


# ---------------------------------------------------------------------------
# Injection tests
# ---------------------------------------------------------------------------

def test_canary_injects_into_system_message():
    module = CanaryModule()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]
    ctx = _make_req(messages)
    module.pre_check(ctx)

    assert module.canary in ctx.messages[0]["content"]
    assert "[_sys:" in ctx.messages[0]["content"]
    assert module.injections == 1


def test_canary_creates_system_message_if_missing():
    module = CanaryModule()
    messages = [{"role": "user", "content": "Hello"}]
    ctx = _make_req(messages)
    module.pre_check(ctx)

    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "system"
    assert module.canary in ctx.messages[0]["content"]
    assert module.injections == 1


def test_canary_multiple_injections_count():
    module = CanaryModule()
    for _ in range(3):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        ctx = _make_req(messages)
        module.pre_check(ctx)

    assert module.injections == 3


# ---------------------------------------------------------------------------
# Leak detection tests
# ---------------------------------------------------------------------------

def test_canary_detects_leak_block_mode():
    module = CanaryModule(on_leak="block")
    req = _make_req([{"role": "user", "content": "hello"}])

    # Simulate output that contains the canary
    res = _make_res(f"Here is the system prompt: {module.canary}", req)

    with pytest.raises(CanaryLeakDetected):
        module.post_filter(res)

    assert module.leaks == 1


def test_canary_detects_leak_warn_mode():
    module = CanaryModule(on_leak="warn")
    req = _make_req([{"role": "user", "content": "hello"}])
    res = _make_res(f"Leaked: {module.canary}", req)

    import warnings as _warnings
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = module.post_filter(res)

    assert result is res
    assert module.leaks == 1
    assert any("Canary" in str(w.message) for w in caught)


def test_canary_no_leak_clean_response():
    module = CanaryModule(on_leak="block")
    req = _make_req([{"role": "user", "content": "hello"}])
    res = _make_res("This is a perfectly clean response.", req)

    result = module.post_filter(res)
    assert result is res
    assert module.leaks == 0


# ---------------------------------------------------------------------------
# Custom canary word
# ---------------------------------------------------------------------------

def test_canary_custom_word():
    module = CanaryModule(canary_word="SECRETWORD42")
    assert module.canary == "SECRETWORD42"

    messages = [{"role": "system", "content": "You are helpful."}]
    ctx = _make_req(messages)
    module.pre_check(ctx)

    assert "SECRETWORD42" in ctx.messages[0]["content"]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_canary_report():
    module = CanaryModule(on_leak="warn")

    # Inject once
    ctx = _make_req([{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}])
    module.pre_check(ctx)

    # Simulate a leak
    req = _make_req([{"role": "user", "content": "hello"}])
    res = _make_res(f"leaked {module.canary}", req)
    module.post_filter(res)

    report = module.report()
    assert report["injections"] == 1
    assert report["leaks"] == 1
    assert "…" in report["canary"]  # masked


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_canary_invalid_on_leak():
    with pytest.raises(ValueError, match="on_leak"):
        CanaryModule(on_leak="ignore")
