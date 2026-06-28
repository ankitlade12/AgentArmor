"""Regression: OpenAI only emits token usage on a streamed response when the
caller passes stream_options={"include_usage": True}. AgentArmor must inject it
automatically, otherwise the budget circuit breaker silently under-meters every
streamed call (input tokens ~0, output cost a char-count guess).
"""
import pytest
from unittest.mock import MagicMock

import agentarmor

openai = pytest.importorskip("openai")


def _one_chunk_stream():
    c = MagicMock()
    c.choices = [MagicMock()]
    c.choices[0].delta.content = "hi"
    c.usage = None
    yield c


def _call(stream=True, **extra):
    """Patch Completions.create with a mock, run one call, return its kwargs."""
    client = openai.OpenAI(api_key="mock")
    Completions = openai.resources.chat.completions.Completions
    original = Completions.create
    mock_create = MagicMock(return_value=_one_chunk_stream())
    Completions.create = mock_create
    try:
        agentarmor.init(budget="$5")
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            stream=stream,
            **extra,
        )
        if stream:
            list(res)  # drive the generator
        _, call_kwargs = mock_create.call_args
        return call_kwargs
    finally:
        agentarmor.teardown()
        Completions.create = original


def test_openai_streaming_injects_include_usage():
    kwargs = _call(stream=True)
    assert kwargs.get("stream_options") == {"include_usage": True}


def test_streaming_preserves_user_stream_options():
    kwargs = _call(stream=True, stream_options={"foo": "bar"})
    assert kwargs["stream_options"]["foo"] == "bar"
    assert kwargs["stream_options"]["include_usage"] is True


def test_non_streaming_call_is_not_given_stream_options():
    client = openai.OpenAI(api_key="mock")
    Completions = openai.resources.chat.completions.Completions
    original = Completions.create
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "ok"
    resp.usage = None
    mock_create = MagicMock(return_value=resp)
    Completions.create = mock_create
    try:
        agentarmor.init(budget="$5")
        client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
        )
        _, call_kwargs = mock_create.call_args
        assert "stream_options" not in call_kwargs
    finally:
        agentarmor.teardown()
        Completions.create = original
