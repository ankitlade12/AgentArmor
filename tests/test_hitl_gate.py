import pytest
from agentarmor.modules.hitl_gate import HITLGateModule, PolicyRule, ApprovalRequest
from agentarmor.exceptions import HumanApprovalRequired, HumanApprovalDenied, HumanApprovalTimeout
from agentarmor.hooks import ResponseContext, RequestContext


def make_response_ctx(text="", raw_response=None):
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4o")
    return ResponseContext(text=text, model="gpt-4o", provider="openai", request=req, raw_response=raw_response)


class TestPolicyRule:
    def test_matches_tool_name(self):
        rule = PolicyRule(name="test", pattern=r"delete_file", risk_level="critical")
        assert rule.matches("delete_file") is True
        assert rule.matches("read_file") is False

    def test_matches_with_regex(self):
        rule = PolicyRule(name="test", pattern=r"(?:delete|remove).*file", risk_level="critical")
        assert rule.matches("delete_file") is True
        assert rule.matches("remove_file") is True
        assert rule.matches("read_file") is False

    def test_matches_with_arg_patterns(self):
        rule = PolicyRule(
            name="test", pattern=r"execute",
            risk_level="high",
            arg_patterns={"command": r"rm\s+-rf"}
        )
        assert rule.matches("execute_command", {"command": "rm -rf /"}) is True
        assert rule.matches("execute_command", {"command": "ls -la"}) is False

    def test_case_insensitive(self):
        rule = PolicyRule(name="test", pattern=r"Delete_File", risk_level="high")
        assert rule.matches("DELETE_FILE") is True


class TestCheckAction:
    def test_no_match(self):
        module = HITLGateModule(use_defaults=False, policies=[
            {"name": "test", "pattern": r"delete_file", "risk_level": "high"}
        ])
        assert module.check_action("read_file") == "no_match"

    def test_auto_approve(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"write_file", "risk_level": "low"}],
            auto_approve_levels=["low"],
        )
        assert module.check_action("write_file") == "approved"

    def test_auto_deny(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"delete_db", "risk_level": "critical"}],
            auto_deny_levels=["critical"],
        )
        assert module.check_action("delete_db") == "denied"

    def test_callback_approve(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"send_email", "risk_level": "high"}],
            approval_callback=lambda req: True,
            auto_approve_levels=[],
        )
        assert module.check_action("send_email") == "approved"

    def test_callback_deny(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"send_email", "risk_level": "high"}],
            approval_callback=lambda req: False,
            auto_approve_levels=[],
        )
        assert module.check_action("send_email") == "denied"

    def test_no_callback_pending(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"delete_file", "risk_level": "high"}],
            auto_approve_levels=[],
        )
        assert module.check_action("delete_file") == "pending"


class TestDefaultPolicies:
    def test_shell_execute_matches(self):
        module = HITLGateModule(auto_approve_levels=[])
        result = module.check_action("execute_shell_command")
        assert result in ("pending", "denied")

    def test_file_delete_matches(self):
        module = HITLGateModule(auto_approve_levels=[])
        result = module.check_action("delete_file_path")
        assert result in ("pending", "denied")

    def test_safe_action_no_match(self):
        module = HITLGateModule()
        result = module.check_action("get_weather")
        assert result == "no_match"


class TestAuditLog:
    def test_audit_log_recorded(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[{"name": "test", "pattern": r"action", "risk_level": "low"}],
        )
        module.check_action("action_test")

        report = module.report()
        assert report["audit_log_size"] == 1
        assert report["recent_decisions"][0]["tool_name"] == "action_test"

    def test_stats_tracking(self):
        module = HITLGateModule(
            use_defaults=False,
            policies=[
                {"name": "low_action", "pattern": r"low_action", "risk_level": "low"},
                {"name": "high_action", "pattern": r"high_action", "risk_level": "critical"},
            ],
            auto_approve_levels=["low"],
            auto_deny_levels=["critical"],
        )
        module.check_action("low_action")
        module.check_action("high_action")
        module.check_action("unmatched")

        report = module.report()
        assert report["stats"]["auto_approved"] == 1
        assert report["stats"]["auto_denied"] == 1
        assert report["stats"]["no_match"] == 1


class TestPostFilter:
    def test_no_tool_calls_passes(self):
        module = HITLGateModule()
        ctx = make_response_ctx("Just text, no tool calls")
        result = module.post_filter(ctx)
        assert result.text == "Just text, no tool calls"


class TestApprovalRequest:
    def test_to_dict(self):
        rule = PolicyRule(name="test_rule", pattern=r"test", risk_level="high", description="Test rule")
        req = ApprovalRequest(tool_name="test_action", arguments={"key": "value"}, rule=rule)
        d = req.to_dict()
        assert d["tool_name"] == "test_action"
        assert d["risk_level"] == "high"
        assert d["rule_name"] == "test_rule"
