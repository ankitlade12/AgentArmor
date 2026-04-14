"""Tests for the Runtime Taint Tracking module."""
import pytest
from unittest.mock import MagicMock

import agentarmor
from agentarmor.modules.taint_tracker import (
    TaintTrackerModule, TaintViolation, TaintedData,
    TAINT_USER_INPUT, TAINT_PII, TAINT_RAG, TAINT_TOOL_OUTPUT,
)
from agentarmor.hooks import RequestContext, ResponseContext


def _make_req_ctx(messages=None):
    return RequestContext(
        messages=messages or [{"role": "user", "content": "hello"}],
        model="gpt-4o",
    )


def _make_res_ctx(raw_response=None, provider="openai"):
    req = _make_req_ctx()
    return ResponseContext(
        text="response", model="gpt-4o", provider=provider,
        request=req, raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# TaintedData
# ---------------------------------------------------------------------------

class TestTaintedData:
    def test_creation(self):
        td = TaintedData("hello", {"user_input"}, "user")
        assert td.text == "hello"
        assert "user_input" in td.labels
        assert td.source == "user"

    def test_repr(self):
        td = TaintedData("x", {"pii"}, "system")
        assert "pii" in repr(td)


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------

class TestPIIDetection:
    def test_detects_email(self):
        assert TaintTrackerModule._contains_pii("Contact me at john@example.com")

    def test_detects_ssn(self):
        assert TaintTrackerModule._contains_pii("SSN: 123-45-6789")

    def test_detects_phone(self):
        assert TaintTrackerModule._contains_pii("Call me at (555) 123-4567")

    def test_detects_credit_card(self):
        assert TaintTrackerModule._contains_pii("Card: 4111-1111-1111-1111")

    def test_detects_api_key(self):
        assert TaintTrackerModule._contains_pii("key: sk-abcdefghijklmnopqrstuv")

    def test_clean_text(self):
        assert not TaintTrackerModule._contains_pii("Just a normal message")


# ---------------------------------------------------------------------------
# Pre-check (message labeling)
# ---------------------------------------------------------------------------

class TestPreCheck:
    def test_labels_user_input(self):
        mod = TaintTrackerModule()
        ctx = _make_req_ctx([{"role": "user", "content": "what is 2+2?"}])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 1
        assert TAINT_USER_INPUT in mod._tainted_strings[0].labels

    def test_labels_pii(self):
        mod = TaintTrackerModule(auto_detect_pii=True)
        ctx = _make_req_ctx([{"role": "user", "content": "email me at bob@test.com"}])
        mod.pre_check(ctx)
        assert TAINT_PII in mod._tainted_strings[0].labels

    def test_labels_rag(self):
        mod = TaintTrackerModule(track_rag=True)
        ctx = _make_req_ctx([
            {"role": "system", "content": "Context: The capital of France is Paris."},
        ])
        mod.pre_check(ctx)
        assert TAINT_RAG in mod._tainted_strings[0].labels

    def test_no_rag_when_disabled(self):
        mod = TaintTrackerModule(track_rag=False)
        ctx = _make_req_ctx([
            {"role": "system", "content": "You are a helpful assistant."},
        ])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 0

    def test_accumulates_taint_across_requests(self):
        mod = TaintTrackerModule()
        ctx1 = _make_req_ctx([{"role": "user", "content": "first question here"}])
        mod.pre_check(ctx1)
        assert len(mod._tainted_strings) == 1

        ctx2 = _make_req_ctx([{"role": "user", "content": "second question here"}])
        mod.pre_check(ctx2)
        assert len(mod._tainted_strings) == 2

    def test_reset_clears_taint(self):
        mod = TaintTrackerModule()
        ctx = _make_req_ctx([{"role": "user", "content": "first question here"}])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 1
        mod.reset()
        assert len(mod._tainted_strings) == 0

    def test_plain_system_prompt_not_labeled_rag(self):
        mod = TaintTrackerModule(track_rag=True)
        ctx = _make_req_ctx([
            {"role": "system", "content": "You are a helpful assistant."},
        ])
        mod.pre_check(ctx)
        # Plain system prompt should NOT be labeled as RAG
        assert len(mod._tainted_strings) == 0

    def test_rag_context_message_labeled(self):
        mod = TaintTrackerModule(track_rag=True)
        ctx = _make_req_ctx([
            {"role": "system", "content": "Context: The capital of France is Paris."},
        ])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 1
        assert TAINT_RAG in mod._tainted_strings[0].labels

    def test_context_role_always_labeled_rag(self):
        mod = TaintTrackerModule(track_rag=True)
        ctx = _make_req_ctx([
            {"role": "context", "content": "Retrieved document about quantum physics."},
        ])
        mod.pre_check(ctx)
        assert TAINT_RAG in mod._tainted_strings[0].labels

    def test_tool_result_auto_labeled(self):
        mod = TaintTrackerModule()
        ctx = _make_req_ctx([
            {"role": "tool", "content": "Search result: Paris is the capital."},
        ])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 1
        assert TAINT_TOOL_OUTPUT in mod._tainted_strings[0].labels


# ---------------------------------------------------------------------------
# Sink policy enforcement
# ---------------------------------------------------------------------------

class _FnMock:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _TCMock:
    def __init__(self, name, arguments):
        self.function = _FnMock(name, arguments)


class _MsgMock:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = None


class _ChoiceMock:
    def __init__(self, msg):
        self.message = msg


class _OpenAIResp:
    def __init__(self, tool_calls):
        self.choices = [_ChoiceMock(_MsgMock(tool_calls))]


class TestSinkPolicies:
    def test_blocks_pii_in_tool_args(self):
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["pii"]},
            on_violation="block",
        )
        # Simulate user sending PII
        ctx = _make_req_ctx([{"role": "user", "content": "My SSN is 123-45-6789"}])
        mod.pre_check(ctx)

        # Simulate model calling send_email with the PII
        tc = _TCMock("send_email", '{"body": "Your SSN is 123-45-6789"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        with pytest.raises(TaintViolation, match="pii"):
            mod.post_filter(res_ctx)

    def test_allows_clean_tool_args(self):
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["pii"]},
            on_violation="block",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "Hello world"}])
        mod.pre_check(ctx)

        tc = _TCMock("send_email", '{"body": "generic greeting"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        # Should not raise
        result = mod.post_filter(res_ctx)
        assert result is res_ctx

    def test_wildcard_policy(self):
        mod = TaintTrackerModule(
            sink_policies={"*": ["pii"]},
            on_violation="block",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "card: 4111-1111-1111-1111"}])
        mod.pre_check(ctx)

        tc = _TCMock("any_tool", '{"data": "card: 4111-1111-1111-1111"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        with pytest.raises(TaintViolation):
            mod.post_filter(res_ctx)

    def test_warn_mode_does_not_raise(self):
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["pii"]},
            on_violation="warn",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "SSN: 123-45-6789"}])
        mod.pre_check(ctx)

        tc = _TCMock("send_email", '{"body": "SSN: 123-45-6789"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        result = mod.post_filter(res_ctx)
        assert result is res_ctx
        assert mod.stats["taint_violations"] == 1

    def test_user_input_blocked_from_external_tool(self):
        mod = TaintTrackerModule(
            sink_policies={"web_search": ["user_input"]},
            on_violation="block",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "my secret query"}])
        mod.pre_check(ctx)

        tc = _TCMock("web_search", '{"query": "my secret query"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        with pytest.raises(TaintViolation, match="user_input"):
            mod.post_filter(res_ctx)


# ---------------------------------------------------------------------------
# Manual taint registration
# ---------------------------------------------------------------------------

class TestManualTaint:
    def test_register_taint(self):
        mod = TaintTrackerModule(
            sink_policies={"store_data": ["tool_output"]},
            on_violation="block",
        )
        mod.register_taint("sensitive tool result", {"tool_output"}, source="tool_x")

        violations = mod.check_text("store_data", "the sensitive tool result was")
        assert "tool_output" in violations


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_structure(self):
        mod = TaintTrackerModule(sink_policies={"t": ["pii"]})
        r = mod.report()
        assert "stats" in r
        assert "violations" in r
        assert "sink_policies" in r
        assert "active_tainted_items" in r

    def test_stats_tracked(self):
        mod = TaintTrackerModule()
        ctx = _make_req_ctx([{"role": "user", "content": "email: a@b.com"}])
        mod.pre_check(ctx)
        assert mod.stats["requests_scanned"] == 1
        assert mod.stats["pii_detected"] == 1


# ---------------------------------------------------------------------------
# Init integration
# ---------------------------------------------------------------------------

class TestInitIntegration:
    def teardown_method(self):
        agentarmor.teardown()

    def test_taint_tracker_in_modules(self):
        core = agentarmor.init(
            taint_tracker={"sink_policies": {"*": ["pii"]}},
        )
        assert "taint_tracker" in core.modules

    def test_taint_tracker_bool(self):
        core = agentarmor.init(taint_tracker=True)
        assert "taint_tracker" in core.modules


# ---------------------------------------------------------------------------
# Review-added: bounded state, min-length filter, Responses API coverage
# ---------------------------------------------------------------------------

class TestBoundedState:
    def test_taint_state_caps_at_max_tainted_items(self):
        """Long-running sessions must not leak memory."""
        mod = TaintTrackerModule(max_tainted_items=5)
        for i in range(20):
            ctx = _make_req_ctx([
                {"role": "user", "content": f"unique user message number {i}"},
            ])
            mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 5
        # FIFO — oldest are evicted, newest kept.
        kept = [td.text for td in mod._tainted_strings]
        assert "unique user message number 19" in kept
        assert "unique user message number 0" not in kept


class TestMinTaintLength:
    def test_short_user_input_is_not_tracked(self):
        """Substring-match on 2-char content would false-positive everywhere."""
        mod = TaintTrackerModule()
        ctx = _make_req_ctx([{"role": "user", "content": "hi"}])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 0

    def test_short_register_taint_is_dropped(self):
        mod = TaintTrackerModule()
        mod.register_taint("ok", {"tool_output"}, source="tool")
        assert len(mod._tainted_strings) == 0

    def test_min_taint_length_configurable(self):
        """Users can opt back into tracking short strings."""
        mod = TaintTrackerModule(min_taint_length=0)
        ctx = _make_req_ctx([{"role": "user", "content": "hi"}])
        mod.pre_check(ctx)
        assert len(mod._tainted_strings) == 1

    def test_short_string_does_not_false_positive_against_tool_arg(self):
        """The original FP scenario: short tainted 'hi' would match any
        tool arg containing 'hi' as a substring. min_taint_length stops
        this at the source."""
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["user_input"]},
            on_violation="block",
        )
        # User types "hi" — should not be tracked at all.
        ctx = _make_req_ctx([{"role": "user", "content": "hi"}])
        mod.pre_check(ctx)

        # Model calls send_email with body containing "hi" substring.
        # Without min_taint_length, this would trigger a violation.
        tc = _TCMock("send_email", '{"body": "this is a normal message"}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        # Must not raise.
        result = mod.post_filter(res_ctx)
        assert result is res_ctx


class TestResponsesAPICoverage:
    """Taint tracker must extract tool calls from the OpenAI Responses API
    surface, not just Chat Completions."""

    def _make_responses_function_call(self, name, arguments_json):
        item = MagicMock()
        item.type = "function_call"
        item.name = name
        item.arguments = arguments_json
        return item

    def _make_responses_raw(self, items):
        raw = MagicMock()
        raw.output = items
        # No choices attribute to ensure we're hitting the Responses path only
        del raw.choices
        return raw

    def test_extracts_function_call_from_responses_output(self):
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["pii"]},
            on_violation="block",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "My SSN is 123-45-6789"}])
        mod.pre_check(ctx)

        fc = self._make_responses_function_call(
            "send_email", '{"body": "Your SSN is 123-45-6789"}'
        )
        raw = self._make_responses_raw([fc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        with pytest.raises(TaintViolation, match="pii"):
            mod.post_filter(res_ctx)

    def test_responses_api_clean_args_pass(self):
        mod = TaintTrackerModule(
            sink_policies={"send_email": ["pii"]},
            on_violation="block",
        )
        ctx = _make_req_ctx([{"role": "user", "content": "send a friendly greeting"}])
        mod.pre_check(ctx)

        fc = self._make_responses_function_call(
            "send_email", '{"body": "hello there"}'
        )
        raw = self._make_responses_raw([fc])
        res_ctx = _make_res_ctx(raw_response=raw, provider="openai")

        # Must not raise.
        assert mod.post_filter(res_ctx) is res_ctx
