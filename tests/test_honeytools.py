"""Tests for the Honeytools / Deception Rail module."""
import pytest

import agentarmor
from agentarmor.modules.honeytools import (
    HoneytoolsModule, HoneytoolTriggered,
    DEFAULT_HONEYTOOLS, DEFAULT_HONEYTOKENS,
)
from agentarmor.hooks import RequestContext, ResponseContext


def _make_res_ctx(raw_response=None, text="", provider="openai"):
    req = RequestContext(messages=[], model="gpt-4o")
    return ResponseContext(
        text=text, model="gpt-4o", provider=provider,
        request=req, raw_response=raw_response,
    )


# --- Mock OpenAI response helpers ---

class _FnMock:
    def __init__(self, name, arguments="{}"):
        self.name = name
        self.arguments = arguments

class _TCMock:
    def __init__(self, name, arguments="{}"):
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


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_default_honeytools_loaded(self):
        mod = HoneytoolsModule()
        assert len(mod._honeytools) == len(DEFAULT_HONEYTOOLS)
        assert "get_admin_credentials" in mod._honeytools

    def test_default_honeytokens_loaded(self):
        mod = HoneytoolsModule()
        assert len(mod._honeytokens) == len(DEFAULT_HONEYTOKENS)

    def test_no_defaults_when_disabled(self):
        mod = HoneytoolsModule(include_defaults=False)
        assert len(mod._honeytools) == 0
        assert len(mod._honeytokens) == 0


# ---------------------------------------------------------------------------
# Honeytool detection
# ---------------------------------------------------------------------------

class TestHoneytoolDetection:
    def test_triggers_on_honeytool_call(self):
        mod = HoneytoolsModule(on_trigger="block")
        with pytest.raises(HoneytoolTriggered, match="get_admin_credentials"):
            mod.check_tool_call("get_admin_credentials")

    def test_clean_tool_passes(self):
        mod = HoneytoolsModule(on_trigger="block")
        result = mod.check_tool_call("search_documents")
        assert result is False

    def test_alert_mode_does_not_raise(self):
        mod = HoneytoolsModule(on_trigger="alert")
        result = mod.check_tool_call("get_admin_credentials")
        assert result is True
        assert mod.stats["tool_triggers"] == 1
        assert len(mod.alerts) == 1

    def test_custom_honeytool(self):
        mod = HoneytoolsModule(
            include_defaults=False,
            custom_honeytools=[{"name": "steal_data", "description": "Steals data"}],
            on_trigger="block",
        )
        with pytest.raises(HoneytoolTriggered, match="steal_data"):
            mod.check_tool_call("steal_data")

    def test_post_filter_catches_honeytool(self):
        mod = HoneytoolsModule(on_trigger="block")
        tc = _TCMock("export_all_users")
        raw = _OpenAIResp([tc])
        ctx = _make_res_ctx(raw_response=raw)

        with pytest.raises(HoneytoolTriggered, match="export_all_users"):
            mod.post_filter(ctx)


# ---------------------------------------------------------------------------
# Honeytoken detection
# ---------------------------------------------------------------------------

class TestHoneytokenDetection:
    def test_detects_token_in_text(self):
        mod = HoneytoolsModule(on_trigger="block")
        with pytest.raises(HoneytoolTriggered, match="honeytoken_found"):
            mod.check_text_for_tokens(
                "The API key is sk-honey-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            )

    def test_clean_text_passes(self):
        mod = HoneytoolsModule(on_trigger="block")
        result = mod.check_text_for_tokens("Just a normal response")
        assert result == []

    def test_alert_mode_for_tokens(self):
        mod = HoneytoolsModule(on_trigger="alert")
        matches = mod.check_text_for_tokens(
            "Here's the key: sk-honey-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        )
        assert len(matches) == 1
        assert mod.stats["token_triggers"] == 1

    def test_post_filter_scans_response_text(self):
        mod = HoneytoolsModule(on_trigger="block")
        ctx = _make_res_ctx(
            text="Found credential: admin_p@ssw0rd_2026!"
        )
        with pytest.raises(HoneytoolTriggered):
            mod.post_filter(ctx)

    def test_custom_honeytoken(self):
        mod = HoneytoolsModule(
            include_defaults=False,
            honeytokens=[{"type": "secret", "value": "TRAP_TOKEN_123"}],
            on_trigger="block",
        )
        with pytest.raises(HoneytoolTriggered):
            mod.check_text_for_tokens("Leaked: TRAP_TOKEN_123")


# ---------------------------------------------------------------------------
# Runtime registration
# ---------------------------------------------------------------------------

class TestRuntimeRegistration:
    def test_add_honeytool(self):
        mod = HoneytoolsModule(include_defaults=False, on_trigger="block")
        mod.add_honeytool("new_trap", "A new trap tool")
        with pytest.raises(HoneytoolTriggered):
            mod.check_tool_call("new_trap")

    def test_add_honeytoken(self):
        mod = HoneytoolsModule(include_defaults=False, on_trigger="block")
        mod.add_honeytoken("token", "SECRET_CANARY_VALUE")
        with pytest.raises(HoneytoolTriggered):
            mod.check_text_for_tokens("leaked: SECRET_CANARY_VALUE")

    def test_get_tool_definitions(self):
        mod = HoneytoolsModule()
        defs = mod.get_tool_definitions()
        assert len(defs) == len(DEFAULT_HONEYTOOLS)
        names = {d["name"] for d in defs}
        assert "get_admin_credentials" in names


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auto-injection of decoy tools
# ---------------------------------------------------------------------------

class TestAutoInjection:
    def test_pre_check_injects_honeytools_into_tools_list(self):
        from agentarmor.hooks import RequestContext
        mod = HoneytoolsModule(include_defaults=True)
        tools = [
            {"type": "function", "function": {"name": "search", "parameters": {}}},
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)
        tool_names = {t["function"]["name"] for t in tools}
        assert "get_admin_credentials" in tool_names
        assert "export_all_users" in tool_names
        assert "search" in tool_names  # original preserved

    def test_pre_check_does_not_duplicate(self):
        from agentarmor.hooks import RequestContext
        mod = HoneytoolsModule(
            include_defaults=False,
            custom_honeytools=[{"name": "trap", "description": "x"}],
        )
        tools = [
            {"type": "function", "function": {"name": "trap", "parameters": {}}},
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)
        assert len(tools) == 1  # Not duplicated

    def test_pre_check_no_tools_param_is_noop(self):
        from agentarmor.hooks import RequestContext
        mod = HoneytoolsModule()
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
        )
        result = mod.pre_check(ctx)
        assert result is ctx


class TestReport:
    def test_report_structure(self):
        mod = HoneytoolsModule()
        r = mod.report()
        assert "stats" in r
        assert "honeytools_deployed" in r
        assert "honeytokens_deployed" in r
        assert "alerts" in r
        assert "honeytool_names" in r

    def test_report_counts(self):
        mod = HoneytoolsModule(on_trigger="alert")
        mod.check_tool_call("get_admin_credentials")
        mod.check_tool_call("export_all_users")
        r = mod.report()
        assert r["stats"]["tool_triggers"] == 2
        assert len(r["alerts"]) == 2


# ---------------------------------------------------------------------------
# Init integration
# ---------------------------------------------------------------------------

class TestInitIntegration:
    def teardown_method(self):
        agentarmor.teardown()

    def test_honeytools_in_modules(self):
        core = agentarmor.init(honeytools=True)
        assert "honeytools" in core.modules

    def test_honeytools_with_config(self):
        core = agentarmor.init(honeytools={"on_trigger": "alert"})
        assert "honeytools" in core.modules
        assert core.modules["honeytools"].on_trigger == "alert"

    def test_invalid_on_trigger(self):
        with pytest.raises(ValueError, match="on_trigger"):
            HoneytoolsModule(on_trigger="invalid")
