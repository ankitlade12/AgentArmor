"""Deterministic controls must work through AsyncOpenAI, not just sync.

The async path was only tested for hook-firing; the actual controls (budget,
redaction, rate limit, tool firewall) were never exercised async. These close
that coverage gap — and would fail loudly if a control were silently sync-only.
"""
import pytest
from unittest.mock import MagicMock

import agentarmor
from agentarmor.exceptions import RateLimitExceeded, ToolCallBlocked

openai = pytest.importorskip("openai")


def _chat_response(content="hello", usage=(100, 50)):
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message.content = content
    r.choices[0].message.tool_calls = None
    if usage:
        u = MagicMock()
        u.prompt_tokens, u.completion_tokens = usage
        r.usage = u
    else:
        r.usage = None
    return r


class _Fn:
    def __init__(self, name):
        self.name = name


class _ToolCall:
    def __init__(self, name):
        self.function = _Fn(name)
        self.type = "function"


def _patch_async(response):
    cls = openai.resources.chat.completions.AsyncCompletions
    original = cls.create

    async def mock_create(*args, **kwargs):
        return response

    cls.create = MagicMock(side_effect=mock_create)
    return cls, original


async def _call():
    client = openai.AsyncOpenAI(api_key="mock")
    return await client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
    )


@pytest.mark.asyncio
async def test_budget_is_tracked_on_async_calls():
    cls, original = _patch_async(_chat_response())
    try:
        core = agentarmor.init(budget="$5")
        await _call()
        assert core.modules["budget"].spent > 0
    finally:
        agentarmor.teardown()
        cls.create = original


@pytest.mark.asyncio
async def test_redaction_applies_to_async_responses():
    cls, original = _patch_async(_chat_response("reach me at user@example.com"))
    try:
        agentarmor.init(filter=["pii"])
        resp = await _call()
        assert "user@example.com" not in resp.choices[0].message.content
    finally:
        agentarmor.teardown()
        cls.create = original


@pytest.mark.asyncio
async def test_rate_limit_blocks_async_calls():
    cls, original = _patch_async(_chat_response())
    try:
        agentarmor.init(rate_limit="1/min")
        await _call()
        with pytest.raises(RateLimitExceeded):
            await _call()
    finally:
        agentarmor.teardown()
        cls.create = original


@pytest.mark.asyncio
async def test_tool_firewall_blocks_unauthorized_tool_on_async():
    resp = _chat_response()
    resp.choices[0].message.tool_calls = [_ToolCall("delete_file")]
    cls, original = _patch_async(resp)
    try:
        agentarmor.init(tool_firewall={"allow": ["search"], "on_violation": "block"})
        with pytest.raises(ToolCallBlocked):
            await _call()
    finally:
        agentarmor.teardown()
        cls.create = original
