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

class TestBuiltinCategories:
    @pytest.mark.parametrize("category", [
        k for k in SAFE_ALTERNATIVES if k != "_default"
    ])
    def test_each_category_has_alternatives(self, category):
        alt = SAFE_ALTERNATIVES[category]
        assert "reason_template" in alt
        assert "alternatives" in alt
        assert len(alt["alternatives"]) >= 2
