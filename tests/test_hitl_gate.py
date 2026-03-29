import pytest
from agentarmor.modules.hitl_gate import HITLGateModule, PolicyRule, ApprovalRequest
from agentarmor.exceptions import HumanApprovalRequired, HumanApprovalDenied, HumanApprovalTimeout
from agentarmor.hooks import ResponseContext, RequestContext


def make_response_ctx(text="", raw_response=None):
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4o")
    return ResponseContext(text=text, model="gpt-4o", provider="openai", request=req, raw_response=raw_response)


class TestPolicyRule:
    def test_matches_tool_names(self):
        rule = PolicyRule(name="test", tool_names=["delete_file", "rm_file"], risk_level="critical")
        assert rule.matches("delete_file") is True
        assert rule.matches("rm_file") is True
        assert rule.matches("read_file") is False

    def test_matches_with_arg_patterns(self):
        rule = PolicyRule(
            name="test", tool_names=["execute_command"],
            risk_level="high",
            arg_patterns={"command": r"rm\s+-rf"}
        )
        assert rule.matches("execute_command", {"command": "rm -rf /"}) is True
        assert rule.matches("execute_command", {"command": "ls -la"}) is False

    def test_exact_match_enforced(self):
        rule = PolicyRule(name="test", tool_names=["delete_file"], risk_level="high")
        # Should NOT match substring or regex
        assert rule.matches("delete_file_2") is False
        assert rule.matches("my_delete_file") is False


class TestCheckAction:
    def test_unmapped_tool_uses_default(self):
        module = HITLGateModule(default_risk="high", auto_approve_levels=[])
        assert module.check_action("read_file") == "pending"

    def test_auto_approve(self):
        module = HITLGateModule(
            policies=[{"name": "test", "tool_names": ["write_file"], "risk_level": "low"}],
            auto_approve_levels=["low"],
        )
        assert module.check_action("write_file") == "approved"

    def test_auto_deny(self):
        module = HITLGateModule(
            policies=[{"name": "test", "tool_names": ["delete_db"], "risk_level": "critical"}],
            auto_deny_levels=["critical"],
        )
        assert module.check_action("delete_db") == "denied"

    def test_callback_approve(self):
        module = HITLGateModule(
            policies=[{"name": "test", "tool_names": ["send_email"], "risk_level": "high"}],
            approval_callback=lambda req: True,
            auto_approve_levels=[],
        )
        assert module.check_action("send_email") == "approved"

    def test_callback_deny(self):
        module = HITLGateModule(
            policies=[{"name": "test", "tool_names": ["send_email"], "risk_level": "high"}],
            approval_callback=lambda req: False,
            auto_approve_levels=[],
        )
        assert module.check_action("send_email") == "denied"

    def test_risk_map_initialization(self):
        module = HITLGateModule(
            risk_map={"drop_table": "critical", "get_status": "low"},
            auto_approve_levels=["low"],
            auto_deny_levels=["critical"]
        )
        assert module.check_action("drop_table") == "denied"
        assert module.check_action("get_status") == "approved"
        # Since default_risk is 'low', unmatched is auto-approved
        assert module.check_action("unknown_tool") == "approved"


class TestAuditLog:
    def test_audit_log_recorded(self):
        module = HITLGateModule(
            policies=[{"name": "test", "tool_names": ["action_test"], "risk_level": "low"}],
        )
        module.check_action("action_test")

        report = module.report()
        assert report["audit_log_size"] == 1
        assert report["recent_decisions"][0]["tool_name"] == "action_test"

    def test_stats_tracking(self):
        module = HITLGateModule(
            policies=[
                {"name": "low_action", "tool_names": ["low_action"], "risk_level": "low"},
                {"name": "high_action", "tool_names": ["high_action"], "risk_level": "critical"},
            ],
            auto_approve_levels=["low"],
            auto_deny_levels=["critical"],
        )
        module.check_action("low_action")
        module.check_action("high_action")
        module.check_action("unmatched")

        report = module.report()
        assert report["stats"]["auto_approved"] == 2  # low_action + unmatched (default=low)
        assert report["stats"]["auto_denied"] == 1    # high_action
        assert report["stats"]["unmapped"] == 1


class TestPostFilter:
    def test_no_tool_calls_passes(self):
        module = HITLGateModule()
        ctx = make_response_ctx("Just text, no tool calls")
        result = module.post_filter(ctx)
        assert result.text == "Just text, no tool calls"


class TestApprovalRequest:
    def test_to_dict(self):
        rule = PolicyRule(name="test_rule", tool_names=["test"], risk_level="high", description="Test rule")
        req = ApprovalRequest(tool_name="test_action", arguments={"key": "value"}, rule=rule)
        d = req.to_dict()
        assert d["tool_name"] == "test_action"
        assert d["risk_level"] == "high"
        assert d["rule_name"] == "test_rule"
