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
    def test_openai_format_injection(self):
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
        # Should inject in OpenAI format (matching existing)
        injected = [t for t in tools if "function" in t]
        injected_names = {t["function"]["name"] for t in injected}
        assert "get_admin_credentials" in injected_names
        assert "export_all_users" in injected_names
        assert "search" in injected_names

    def test_anthropic_format_injection(self):
        from agentarmor.hooks import RequestContext
        mod = HoneytoolsModule(include_defaults=True)
        tools = [
            {"name": "search", "description": "Search docs", "input_schema": {"type": "object"}},
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)
        # Should inject in Anthropic format (matching existing)
        all_names = {t["name"] for t in tools}
        assert "get_admin_credentials" in all_names
        assert "search" in all_names
        # Verify injected tools use Anthropic schema
        injected = [t for t in tools if t["name"] == "get_admin_credentials"][0]
        assert "input_schema" in injected
        assert "function" not in injected

    def test_anthropic_format_dedup(self):
        from agentarmor.hooks import RequestContext
        mod = HoneytoolsModule(
            include_defaults=False,
            custom_honeytools=[{"name": "trap", "description": "x"}],
        )
        tools = [
            {"name": "trap", "description": "Already exists", "input_schema": {}},
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)
        assert len(tools) == 1  # Not duplicated

    def test_openai_format_dedup(self):
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
        assert len(tools) == 1

    def test_no_tools_param_is_noop(self):
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


# ---------------------------------------------------------------------------
# Review-added: collision fix, bounded alerts, token redaction, Responses API
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock


class TestCollisionFix:
    """Regression: a user's real tool that happens to share a name with a
    default honeytool must NOT be flagged as a tripwire."""

    def test_user_tool_colliding_with_default_is_not_flagged(self):
        """If the user's tools list already has `read_env_secrets`, the
        honeytool module must NOT trigger when the model calls it."""
        mod = HoneytoolsModule(on_trigger="block")

        # User has a legit tool with the same name as a default honeytool.
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_env_secrets",
                    "parameters": {},
                },
            },
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)

        # Confirm the colliding name was removed from the tripwire set.
        assert "read_env_secrets" not in mod._injected_names
        # But other defaults are still armed.
        assert "get_admin_credentials" in mod._injected_names

        # Now the model calls the user's real read_env_secrets — must NOT raise.
        tc = _TCMock("read_env_secrets", '{}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw)
        # Should pass without raising.
        assert mod.post_filter(res_ctx) is res_ctx

    def test_non_colliding_honeytool_still_triggers(self):
        """Collision fix must not disable tripwires that weren't colliding."""
        mod = HoneytoolsModule(on_trigger="block")
        tools = [
            {"type": "function", "function": {"name": "search", "parameters": {}}},
        ]
        ctx = RequestContext(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            extra_kwargs={"tools": tools},
        )
        mod.pre_check(ctx)

        tc = _TCMock("get_admin_credentials", '{}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw)
        with pytest.raises(HoneytoolTriggered, match="get_admin_credentials"):
            mod.post_filter(res_ctx)

    def test_no_tools_list_means_all_honeytools_armed(self):
        """If user doesn't provide a tools list, all default honeytools
        remain armed (backwards-compatible with the original semantics)."""
        mod = HoneytoolsModule(on_trigger="block")
        # No pre_check run — _injected_names stays at full registry.
        tc = _TCMock("get_admin_credentials", '{}')
        raw = _OpenAIResp([tc])
        res_ctx = _make_res_ctx(raw_response=raw)
        with pytest.raises(HoneytoolTriggered):
            mod.post_filter(res_ctx)

    def test_direct_check_tool_call_still_uses_registry(self):
        """The direct check_tool_call() API (used by tests/user code) still
        matches the full registry, even when injected_only was engaged elsewhere."""
        mod = HoneytoolsModule(on_trigger="alert")
        # Simulate a collision wiping 'read_env_secrets' from injected set
        mod._injected_names.discard("read_env_secrets")
        # Direct API call (not from post_filter) should still flag.
        assert mod.check_tool_call("read_env_secrets") is True


class TestBoundedAlerts:
    def test_alerts_capped_at_max_alerts(self):
        mod = HoneytoolsModule(on_trigger="alert", max_alerts=5)
        for _ in range(20):
            mod.check_tool_call("get_admin_credentials")
        assert len(mod.alerts) == 5
        assert mod.stats["tool_triggers"] == 20  # stats keep growing


class TestHoneytokenRedaction:
    def test_alert_does_not_contain_raw_token_value(self):
        """Alert log must NOT contain any prefix of the honeytoken value,
        since even 20 chars is enough to identify the token."""
        mod = HoneytoolsModule(on_trigger="alert")
        mod.check_text_for_tokens(
            "API key leaked: sk-honey-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        )
        assert len(mod.alerts) == 1
        alert = mod.alerts[0]
        # Must log type and a stable hash
        assert alert["token_type"] == "api_key"
        assert "token_hash" in alert
        # Raw value or prefix must NOT appear anywhere in the alert
        alert_str = str(alert)
        assert "sk-honey-" not in alert_str
        assert "sk-honey" not in alert_str
        assert "XXXXXXXX" not in alert_str

    def test_token_hash_is_stable_for_same_value(self):
        mod = HoneytoolsModule(on_trigger="alert")
        mod.check_text_for_tokens("leak: admin_p@ssw0rd_2026!")
        mod.check_text_for_tokens("another leak: admin_p@ssw0rd_2026!")
        h1 = mod.alerts[0]["token_hash"]
        h2 = mod.alerts[1]["token_hash"]
        assert h1 == h2


class TestResponsesAPICoverage:
    """Tool calls on the OpenAI Responses API surface (output[*].function_call)
    must be scanned for honeytool usage."""

    def _make_function_call_item(self, name, args_json="{}"):
        item = MagicMock()
        item.type = "function_call"
        item.name = name
        item.arguments = args_json
        return item

    def _make_responses_raw(self, items):
        raw = MagicMock()
        raw.output = items
        del raw.choices  # Force the Responses-only path
        return raw

    def test_responses_api_honeytool_call_triggers(self):
        mod = HoneytoolsModule(on_trigger="block")
        raw = self._make_responses_raw([
            self._make_function_call_item("export_all_users"),
        ])
        ctx = _make_res_ctx(raw_response=raw, provider="openai")
        with pytest.raises(HoneytoolTriggered, match="export_all_users"):
            mod.post_filter(ctx)

    def test_responses_api_clean_tool_call_passes(self):
        mod = HoneytoolsModule(on_trigger="block")
        raw = self._make_responses_raw([
            self._make_function_call_item("search_docs"),
        ])
        ctx = _make_res_ctx(raw_response=raw, provider="openai")
        assert mod.post_filter(ctx) is ctx
