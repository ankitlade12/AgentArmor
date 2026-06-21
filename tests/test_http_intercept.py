"""httpx-layer interception (observe-first).

Covers the bypass surfaces that don't go through a patched SDK *method* but DO
go over httpx: LiteLLM (SDK mode), OpenAI .parse()/.stream(), and any custom
httpx client hitting a provider host. Applies the deterministic controls
(budget, audit, non-streaming redaction) generically, skips non-LLM hosts, and
must not double-count calls already handled by the SDK layer.
"""
import pytest

import agentarmor
from agentarmor.exceptions import BudgetExhausted

httpx = pytest.importorskip("httpx")
from agentarmor import _http_intercept


def _client(payload, headers=None, status=200):
    def handler(request):
        return httpx.Response(status, json=payload, headers=headers or {})
    return httpx.Client(transport=httpx.MockTransport(handler))


_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_BODY = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}


def _openai_response(content="hello"):
    return {
        "model": "gpt-4o",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }


def test_raw_httpx_openai_call_is_budget_tracked():
    core = agentarmor.init(budget="$5")
    try:
        client = _client(_openai_response())
        client.post(_OPENAI_URL, json=_OPENAI_BODY)
        assert core.modules["budget"].spent > 0
    finally:
        agentarmor.teardown()


def test_non_llm_host_is_untouched():
    core = agentarmor.init(budget="$5")
    try:
        client = _client({"hello": "world"})
        r = client.post("https://example.com/api", json={"x": 1})
        assert core.modules["budget"].spent == 0
        assert r.json() == {"hello": "world"}
    finally:
        agentarmor.teardown()


def test_non_streaming_response_is_redacted():
    agentarmor.init(filter=["pii"])
    try:
        client = _client(_openai_response("reach me at user@example.com"))
        r = client.post(_OPENAI_URL, json=_OPENAI_BODY)
        content = r.json()["choices"][0]["message"]["content"]
        assert "user@example.com" not in content
        assert "REDACTED" in content
    finally:
        agentarmor.teardown()


def test_sdk_layer_flag_prevents_double_counting():
    core = agentarmor.init(budget="$5")
    try:
        client = _client(_openai_response())
        token = _http_intercept.sdk_layer_active.set(True)
        try:
            client.post(_OPENAI_URL, json=_OPENAI_BODY)
        finally:
            _http_intercept.sdk_layer_active.reset(token)
        assert core.modules["budget"].spent == 0
    finally:
        agentarmor.teardown()


def test_budget_breaker_blocks_httpx_call_when_exhausted():
    core = agentarmor.init(budget="$5")
    core.modules["budget"].spent = 5.0  # already at the limit
    try:
        client = _client(_openai_response())
        with pytest.raises(BudgetExhausted):
            client.post(_OPENAI_URL, json=_OPENAI_BODY)
    finally:
        agentarmor.teardown()


def test_real_openai_sdk_call_is_counted_once_not_twice():
    """A real openai SDK call goes through the SDK wrapper AND httpx underneath.
    The sdk_layer_active flag must make the httpx layer skip it so it is counted
    exactly once, not double-billed."""
    import openai

    core = agentarmor.init(budget="$5")
    try:
        def handler(request):
            return httpx.Response(200, json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            })

        oai = openai.OpenAI(
            api_key="x",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        oai.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
        )
        assert len(core.modules["budget"].calls) == 1
    finally:
        agentarmor.teardown()


def test_streaming_response_is_passed_through_untouched():
    """Observe-first defers streaming-SSE handling — it must pass through
    cleanly, not error."""
    agentarmor.init(filter=["pii"])
    try:
        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"data: {}\n\n",
            )
        client = httpx.Client(transport=httpx.MockTransport(handler))
        r = client.post(_OPENAI_URL, json=_OPENAI_BODY)
        assert r.status_code == 200
    finally:
        agentarmor.teardown()
