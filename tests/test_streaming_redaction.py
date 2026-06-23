"""Streaming redaction must not emit a secret's prefix before the pattern
completes across chunk boundaries (#85).

Current code emits the safe-looking suffix immediately, so `user@exa` is streamed
to the caller before chunk 3 reveals it's an email — and can't be recalled.
"""
import pytest
from unittest.mock import MagicMock

import agentarmor

openai = pytest.importorskip("openai")


def _chunk(content):
    c = MagicMock()
    c.choices = [MagicMock()]
    c.choices[0].delta.content = content
    c.usage = None
    return c


def _run_stream(deltas, rules=("pii",)):
    """Stream the given deltas through AgentArmor; return the caller-visible
    concatenation of the (possibly-redacted) deltas."""
    client = openai.OpenAI(api_key="mock")
    Completions = openai.resources.chat.completions.Completions
    original = Completions.create

    def gen():
        for d in deltas:
            yield _chunk(d)

    Completions.create = MagicMock(return_value=gen())
    try:
        agentarmor.init(filter=list(rules))
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        out = ""
        for ch in res:
            piece = ch.choices[0].delta.content
            if piece:
                out += piece
        return out
    finally:
        agentarmor.teardown()
        Completions.create = original


def test_secret_split_across_chunks_is_redacted_not_leaked():
    out = _run_stream(["my email is ", "user@exa", "mple.com ok"])
    assert out == "my email is [REDACTED:EMAIL] ok"
    assert "user@exa" not in out


def test_clean_text_streams_through_unchanged():
    assert _run_stream(["Hello ", "world!"]) == "Hello world!"


def test_long_clean_stream_is_not_dropped_or_reordered():
    deltas = ["a" * 30, "b" * 30, "c" * 30]
    assert _run_stream(deltas) == "a" * 30 + "b" * 30 + "c" * 30


@pytest.mark.asyncio
async def test_secret_split_across_chunks_is_redacted_async():
    aclient = openai.AsyncOpenAI(api_key="mock")
    AsyncCompletions = openai.resources.chat.completions.AsyncCompletions
    original = AsyncCompletions.create

    async def agen():
        for d in ["my email is ", "user@exa", "mple.com ok"]:
            yield _chunk(d)

    async def mock_create(*args, **kwargs):
        return agen()

    AsyncCompletions.create = MagicMock(side_effect=mock_create)
    try:
        agentarmor.init(filter=["pii"])
        res = await aclient.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        out = ""
        async for ch in res:
            piece = ch.choices[0].delta.content
            if piece:
                out += piece
        assert out == "my email is [REDACTED:EMAIL] ok"
        assert "user@exa" not in out
    finally:
        agentarmor.teardown()
        AsyncCompletions.create = original
