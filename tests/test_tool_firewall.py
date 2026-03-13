import pytest
from agentarmor.modules.tool_firewall import ToolFirewallModule
from agentarmor.exceptions import ToolCallBlocked
from agentarmor.hooks import RequestContext, ResponseContext


# ---------------------------------------------------------------------------
# Mock helpers — OpenAI format
# ---------------------------------------------------------------------------

class MockFunction:
    def __init__(self, name):
        self.name = name

class MockToolCall:
    def __init__(self, name):
        self.function = MockFunction(name)
        self.id = "call_123"
        self.type = "function"

class MockMessage:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls
        self.content = "I'll help with that."

class MockChoice:
    def __init__(self, message):
        self.message = message

class MockOpenAIResponse:
    def __init__(self, tool_calls=None):
        self.choices = [MockChoice(MockMessage(tool_calls))]


# ---------------------------------------------------------------------------
# Mock helpers — Anthropic format
# ---------------------------------------------------------------------------

class MockAnthropicToolBlock:
    def __init__(self, name):
        self.type = "tool_use"
        self.name = name
        self.id = "tool_123"
        self.input = {}

class MockAnthropicTextBlock:
    def __init__(self, text="Hello"):
        self.type = "text"
        self.text = text

class MockAnthropicResponse:
    def __init__(self, content):
        self.content = content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(raw_response):
    req = RequestContext(messages=[], model="gpt-4o")
    return ResponseContext(
        text="test",
        model="gpt-4o",
        provider="openai",
        request=req,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Tests — Allowlist
# ---------------------------------------------------------------------------

def test_allowlist_permits_listed_tools():
    module = ToolFirewallModule(allow=["search", "calculator"])
    raw = MockOpenAIResponse([MockToolCall("search")])
    ctx = _make_ctx(raw)
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.violations == 0


def test_allowlist_blocks_unlisted_tools():
    module = ToolFirewallModule(allow=["search", "calculator"])
    raw = MockOpenAIResponse([MockToolCall("execute_code")])
    ctx = _make_ctx(raw)

    with pytest.raises(ToolCallBlocked, match="execute_code"):
        module.post_filter(ctx)

    assert module.violations == 1
    assert "execute_code" in module.blocked_tools


# ---------------------------------------------------------------------------
# Tests — Blocklist
# ---------------------------------------------------------------------------

def test_blocklist_blocks_listed_tools():
    module = ToolFirewallModule(block=["delete_database", "send_email"])
    raw = MockOpenAIResponse([MockToolCall("delete_database")])
    ctx = _make_ctx(raw)

    with pytest.raises(ToolCallBlocked):
        module.post_filter(ctx)

    assert module.violations == 1


def test_blocklist_permits_unlisted_tools():
    module = ToolFirewallModule(block=["delete_database"])
    raw = MockOpenAIResponse([MockToolCall("search")])
    ctx = _make_ctx(raw)

    result = module.post_filter(ctx)
    assert result is ctx
    assert module.violations == 0


# ---------------------------------------------------------------------------
# Tests — Strip mode
# ---------------------------------------------------------------------------

def test_strip_mode_removes_tool_calls():
    module = ToolFirewallModule(allow=["search"], on_violation="strip")
    raw = MockOpenAIResponse([MockToolCall("search"), MockToolCall("execute_code")])
    ctx = _make_ctx(raw)

    module.post_filter(ctx)
    assert module.violations == 1

    # The violating tool call should be stripped
    remaining = raw.choices[0].message.tool_calls
    assert len(remaining) == 1
    assert remaining[0].function.name == "search"


# ---------------------------------------------------------------------------
# Tests — Validation
# ---------------------------------------------------------------------------

def test_both_allow_and_block_raises_valueerror():
    with pytest.raises(ValueError, match="Cannot specify both"):
        ToolFirewallModule(allow=["a"], block=["b"])


# ---------------------------------------------------------------------------
# Tests — Anthropic format
# ---------------------------------------------------------------------------

def test_anthropic_tool_use_format():
    module = ToolFirewallModule(block=["dangerous_tool"])
    raw = MockAnthropicResponse([
        MockAnthropicTextBlock("Here's the result"),
        MockAnthropicToolBlock("dangerous_tool"),
    ])
    ctx = _make_ctx(raw)
    ctx.provider = "anthropic"

    with pytest.raises(ToolCallBlocked):
        module.post_filter(ctx)


def test_anthropic_strip_mode():
    module = ToolFirewallModule(block=["dangerous_tool"], on_violation="strip")
    raw = MockAnthropicResponse([
        MockAnthropicTextBlock("Hello"),
        MockAnthropicToolBlock("safe_tool"),
        MockAnthropicToolBlock("dangerous_tool"),
    ])
    ctx = _make_ctx(raw)
    ctx.provider = "anthropic"

    module.post_filter(ctx)
    assert module.violations == 1
    assert len(raw.content) == 2
    assert raw.content[0].type == "text"
    assert raw.content[1].name == "safe_tool"


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------

def test_no_tool_calls_passes_through():
    module = ToolFirewallModule(allow=["search"])
    raw = MockOpenAIResponse(tool_calls=None)
    ctx = _make_ctx(raw)

    result = module.post_filter(ctx)
    assert result is ctx
    assert module.violations == 0


def test_no_raw_response_passes_through():
    module = ToolFirewallModule(allow=["search"])
    ctx = _make_ctx(raw_response=None)

    result = module.post_filter(ctx)
    assert result is ctx
    assert module.violations == 0


# ---------------------------------------------------------------------------
# Tests — Report
# ---------------------------------------------------------------------------

def test_report():
    module = ToolFirewallModule(block=["bad_tool"])
    raw = MockOpenAIResponse([MockToolCall("bad_tool")])
    ctx = _make_ctx(raw)

    with pytest.raises(ToolCallBlocked):
        module.post_filter(ctx)

    report = module.report()
    assert report["violations"] == 1
    assert "bad_tool" in report["blocked_tools"]
