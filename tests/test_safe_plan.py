"""Tests for the Counterfactual Safe-Plan Engine."""
import pytest

from agentarmor.modules.safe_plan import (
    SafePlanEngine, SafePlanSuggestion, SAFE_ALTERNATIVES,
)
from agentarmor.exceptions import (
    HumanApprovalDenied, ToolCallBlocked, DataExfiltrationDetected,
)


# ---------------------------------------------------------------------------
# SafePlanSuggestion
# ---------------------------------------------------------------------------

class TestSafePlanSuggestion:
    def test_to_dict(self):
        s = SafePlanSuggestion(
            tool_name="rm_file",
            reason="Blocked by policy",
            alternatives=["Use trash", "Request approval"],
            risk_level="high",
            policy_name="file_delete",
        )
        d = s.to_dict()
        assert d["tool_name"] == "rm_file"
        assert len(d["alternatives"]) == 2
        assert d["risk_level"] == "high"

    def test_to_message(self):
        s = SafePlanSuggestion(
            tool_name="curl",
            reason="Network request blocked",
            alternatives=["Use allowlisted endpoint"],
            risk_level="medium",
        )
        msg = s.to_message()
        assert "curl" in msg
        assert "Network request blocked" in msg
        assert "1." in msg


# ---------------------------------------------------------------------------
# SafePlanEngine.suggest
# ---------------------------------------------------------------------------

class TestSuggest:
    def test_categorized_tool(self):
        engine = SafePlanEngine(
            tool_categories={"rm_file": "file_delete"},
        )
        result = engine.suggest("rm_file", {"path": "/etc/passwd"})
        assert "file_delete" in result.reason or "Deleting" in result.reason
        assert len(result.alternatives) > 0

    def test_default_category_for_unknown_tool(self):
        engine = SafePlanEngine()
        result = engine.suggest("unknown_tool")
        assert result.tool_name == "unknown_tool"
        assert len(result.alternatives) > 0

    def test_format_vars_in_reason(self):
        engine = SafePlanEngine(
            tool_categories={"write_file": "file_write"},
        )
        result = engine.suggest("write_file", {"path": "/etc/config"})
        assert "/etc/config" in result.reason

    def test_risk_level_passed_through(self):
        engine = SafePlanEngine()
        result = engine.suggest("x", risk_level="critical")
        assert result.risk_level == "critical"

    def test_policy_name_passed_through(self):
        engine = SafePlanEngine()
        result = engine.suggest("x", policy_name="hitl_deny")
        assert result.policy_name == "hitl_deny"

    def test_custom_alternatives(self):
        engine = SafePlanEngine(
            custom_alternatives={
                "custom_cat": {
                    "reason_template": "Custom reason for {tool_name}",
                    "alternatives": ["Custom alt 1", "Custom alt 2"],
                }
            },
            tool_categories={"my_tool": "custom_cat"},
        )
        result = engine.suggest("my_tool")
        assert "Custom reason" in result.reason
        assert "Custom alt 1" in result.alternatives


# ---------------------------------------------------------------------------
# SafePlanEngine.suggest_for_exception
# ---------------------------------------------------------------------------

class TestSuggestForException:
    def test_from_hitl_denied(self):
        exc = HumanApprovalDenied("Action 'deploy' denied by admin")
        engine = SafePlanEngine()
        result = engine.suggest_for_exception(exc, tool_name="deploy")
        assert result.tool_name == "deploy"
        assert "denied" in result.reason
        assert result.policy_name == "HumanApprovalDenied"

    def test_from_tool_blocked(self):
        exc = ToolCallBlocked("Tool 'rm' is not in the allowlist")
        engine = SafePlanEngine()
        result = engine.suggest_for_exception(exc, tool_name="rm")
        assert result.tool_name == "rm"
        assert len(result.alternatives) > 0

    def test_from_exfiltration(self):
        exc = DataExfiltrationDetected("Base64-encoded PII detected")
        engine = SafePlanEngine()
        result = engine.suggest_for_exception(exc, tool_name="send_data")
        # Should get data_export category alternatives
        assert any("anonymized" in a.lower() or "masking" in a.lower()
                    for a in result.alternatives)

    def test_unknown_exception_type(self):
        exc = ValueError("something went wrong")
        engine = SafePlanEngine()
        result = engine.suggest_for_exception(exc)
        assert result.tool_name == "unknown"
        assert len(result.alternatives) > 0


# ---------------------------------------------------------------------------
# Coverage of all built-in categories
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Integration: SafePlanEngine inside HITLGateModule
# ---------------------------------------------------------------------------

class TestHITLIntegration:
    def test_denied_action_includes_safe_alternatives(self):
        from agentarmor.modules.hitl_gate import HITLGateModule
        from agentarmor.exceptions import HumanApprovalDenied
        from agentarmor.hooks import RequestContext, ResponseContext
        from unittest.mock import MagicMock

        gate = HITLGateModule(
            risk_map={"rm_file": "critical"},
            auto_deny_levels=["critical"],
            safe_plan={"tool_categories": {"rm_file": "file_delete"}},
        )

        # Build a response with a tool call
        fn = MagicMock()
        fn.name = "rm_file"
        fn.arguments = '{"path": "/etc/passwd"}'
        tc = MagicMock()
        tc.function = fn
        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.content = None
        choice = MagicMock()
        choice.message = msg
        raw = MagicMock()
        raw.choices = [choice]

        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(HumanApprovalDenied, match="Safe alternatives"):
            gate.post_filter(ctx)

    def test_hitl_without_safe_plan_still_works(self):
        from agentarmor.modules.hitl_gate import HITLGateModule
        from agentarmor.exceptions import HumanApprovalDenied
        from agentarmor.hooks import RequestContext, ResponseContext
        from unittest.mock import MagicMock

        gate = HITLGateModule(
            risk_map={"rm_file": "critical"},
            auto_deny_levels=["critical"],
        )

        fn = MagicMock()
        fn.name = "rm_file"
        fn.arguments = '{"path": "/tmp/x"}'
        tc = MagicMock()
        tc.function = fn
        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.content = None
        choice = MagicMock()
        choice.message = msg
        raw = MagicMock()
        raw.choices = [choice]

        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(HumanApprovalDenied) as exc_info:
            gate.post_filter(ctx)
        # Should NOT contain safe alternatives
        assert "Safe alternatives" not in str(exc_info.value)


class TestBuiltinCategories:
    @pytest.mark.parametrize("category", [
        k for k in SAFE_ALTERNATIVES if k != "_default"
    ])
    def test_each_category_has_alternatives(self, category):
        alt = SAFE_ALTERNATIVES[category]
        assert "reason_template" in alt
        assert "alternatives" in alt
        assert len(alt["alternatives"]) >= 2


# ---------------------------------------------------------------------------
# Integration: SafePlanEngine inside ToolFirewallModule
# ---------------------------------------------------------------------------

class TestToolFirewallIntegration:
    def test_blocked_tool_includes_structured_suggestions(self):
        from agentarmor.modules.tool_firewall import ToolFirewallModule
        from agentarmor.exceptions import ToolCallBlocked
        from agentarmor.hooks import RequestContext, ResponseContext
        from unittest.mock import MagicMock

        fw = ToolFirewallModule(
            block=["dangerous_tool"],
            on_violation="block",
            safe_plan={"tool_categories": {"dangerous_tool": "shell_exec"}},
        )

        # Build a response with a blocked tool call
        fn = MagicMock()
        fn.name = "dangerous_tool"
        tc = MagicMock()
        tc.function = fn
        msg_mock = MagicMock()
        msg_mock.tool_calls = [tc]
        msg_mock.content = None
        choice = MagicMock()
        choice.message = msg_mock
        raw = MagicMock()
        raw.choices = [choice]

        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(ToolCallBlocked) as exc_info:
            fw.post_filter(ctx)

        exc = exc_info.value
        # Exception must have structured suggestions attribute
        assert hasattr(exc, "suggestions")
        assert len(exc.suggestions) == 1
        assert exc.suggestions[0].tool_name == "dangerous_tool"
        assert len(exc.suggestions[0].alternatives) >= 2
        # Exception message must include the safe alternatives text
        assert "Safe alternatives" in str(exc)

    def test_blocked_tool_without_safe_plan_has_no_suggestions(self):
        from agentarmor.modules.tool_firewall import ToolFirewallModule
        from agentarmor.exceptions import ToolCallBlocked
        from agentarmor.hooks import RequestContext, ResponseContext
        from unittest.mock import MagicMock

        fw = ToolFirewallModule(block=["bad"], on_violation="block")

        fn = MagicMock()
        fn.name = "bad"
        tc = MagicMock()
        tc.function = fn
        msg_mock = MagicMock()
        msg_mock.tool_calls = [tc]
        msg_mock.content = None
        choice = MagicMock()
        choice.message = msg_mock
        raw = MagicMock()
        raw.choices = [choice]

        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(ToolCallBlocked) as exc_info:
            fw.post_filter(ctx)

        exc = exc_info.value
        assert not hasattr(exc, "suggestions")
        assert "Safe alternatives" not in str(exc)


# ---------------------------------------------------------------------------
# Review-added: parity for HumanApprovalRequired + lazy-import sanity
# ---------------------------------------------------------------------------

class TestHumanApprovalRequiredParity:
    """HumanApprovalRequired must expose .suggestion attribute, mirroring
    HumanApprovalDenied. Without this, app code can't programmatically
    extract suggestions for the 'pending approval' path."""

    def _build_response_with_tool_call(self, tool_name, args_json='{}'):
        from unittest.mock import MagicMock

        fn = MagicMock()
        fn.name = tool_name
        fn.arguments = args_json
        tc = MagicMock()
        tc.function = fn
        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.content = None
        choice = MagicMock()
        choice.message = msg
        raw = MagicMock()
        raw.choices = [choice]
        return raw

    def test_pending_action_exposes_structured_suggestion(self):
        from agentarmor.modules.hitl_gate import HITLGateModule
        from agentarmor.exceptions import HumanApprovalRequired
        from agentarmor.hooks import RequestContext, ResponseContext

        # No auto_deny, no callback → "pending" decision
        gate = HITLGateModule(
            risk_map={"deploy_to_prod": "high"},
            auto_deny_levels=[],  # don't auto-deny high
            safe_plan={"tool_categories": {"deploy_to_prod": "shell_exec"}},
        )

        raw = self._build_response_with_tool_call(
            "deploy_to_prod", '{"command": "kubectl apply"}'
        )
        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(HumanApprovalRequired) as exc_info:
            gate.post_filter(ctx)

        exc = exc_info.value
        # Parity with HumanApprovalDenied: structured .suggestion attribute.
        assert hasattr(exc, "suggestion"), (
            "HumanApprovalRequired must expose .suggestion for parity with HumanApprovalDenied"
        )
        assert exc.suggestion.tool_name == "deploy_to_prod"
        assert len(exc.suggestion.alternatives) >= 2
        # Message text still includes the safe alternatives.
        assert "Safe alternatives" in str(exc)

    def test_pending_action_without_safe_plan_has_no_suggestion(self):
        from agentarmor.modules.hitl_gate import HITLGateModule
        from agentarmor.exceptions import HumanApprovalRequired
        from agentarmor.hooks import RequestContext, ResponseContext

        gate = HITLGateModule(
            risk_map={"deploy_to_prod": "high"},
            auto_deny_levels=[],
        )

        raw = self._build_response_with_tool_call("deploy_to_prod")
        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="", model="gpt-4o", provider="openai",
            request=req, raw_response=raw,
        )

        with pytest.raises(HumanApprovalRequired) as exc_info:
            gate.post_filter(ctx)

        # No safe_plan configured → no .suggestion attribute, no alt text.
        assert not hasattr(exc_info.value, "suggestion")
        assert "Safe alternatives" not in str(exc_info.value)


class TestLazyImport:
    """hitl_gate must lazy-import safe_plan inside __init__ — matches
    tool_firewall pattern and prevents future circular-import risk."""

    def test_safe_plan_engine_not_bound_at_hitl_gate_module_level(self):
        """SafePlanEngine must not be visible in hitl_gate's namespace —
        that would mean it was eagerly imported at module load time."""
        from agentarmor.modules import hitl_gate
        assert not hasattr(hitl_gate, "SafePlanEngine"), (
            "hitl_gate has SafePlanEngine bound at module level, meaning it's "
            "eagerly imported. Move the import inside __init__ to match "
            "tool_firewall's pattern and avoid circular-import risk."
        )
