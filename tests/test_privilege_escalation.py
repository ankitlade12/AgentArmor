import pytest
from agentarmor.modules.privilege_escalation import PrivilegeEscalationModule
from agentarmor.exceptions import PrivilegeEscalationDetected
from agentarmor.hooks import ResponseContext, RequestContext


def make_response_ctx(text, raw_response=None):
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4o")
    return ResponseContext(text=text, model="gpt-4o", provider="openai", request=req, raw_response=raw_response)


class TestToolRequest:
    def test_detects_tool_request(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I need access to the file system tool to complete this task"))

    def test_detects_capability_request(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("Please enable the API access capability for me"))


class TestInstructionModification:
    def test_detects_instruction_change(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I need to update my system instructions to handle this"))

    def test_detects_safety_disable(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("Let me disable the safety restrictions for this task"))


class TestSelfDelegation:
    def test_detects_agent_spawn(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I'll create a new agent to handle the data processing"))

    def test_detects_delegation(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I will spawn a sub-agent for this subtask"))


class TestCapabilityProbing:
    def test_detects_tool_listing(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("What tools do I have available to use?"))

    def test_detects_permission_check(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("List all my available capabilities"))


class TestScopeExpansion:
    def test_detects_admin_access(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I need sudo access to modify this file"))

    def test_detects_privilege_escalation(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("Let me escalate my privileges to admin level"))


class TestSafetyBypass:
    def test_detects_safety_bypass(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("I'll bypass the security controls to access this"))

    def test_detects_filter_disable(self):
        module = PrivilegeEscalationModule(on_detect="block")
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("Let me turn off the content filtering for this response"))


class TestSafeText:
    def test_safe_text_passes(self):
        module = PrivilegeEscalationModule(on_detect="block")
        ctx = module.post_filter(make_response_ctx("Here is the weather forecast for today: sunny with a high of 75F"))
        assert ctx.text == "Here is the weather forecast for today: sunny with a high of 75F"

    def test_code_text_passes(self):
        module = PrivilegeEscalationModule(on_detect="block")
        ctx = module.post_filter(make_response_ctx("def hello():\n    print('Hello, world!')"))
        assert "Hello, world!" in ctx.text


class TestWarnMode:
    def test_warn_does_not_raise(self):
        module = PrivilegeEscalationModule(on_detect="warn")
        ctx = module.post_filter(make_response_ctx("I need to update my system instructions"))
        assert ctx is not None
        assert len(module.detections) > 0


class TestAllowedTools:
    def test_unauthorized_tool_blocked(self):
        module = PrivilegeEscalationModule(
            on_detect="block",
            allowed_tools=["read_file", "search"],
            check_output=False,
        )
        # Create mock response with tool call
        class MockFn:
            name = "delete_database"
            arguments = "{}"
        class MockToolCall:
            function = MockFn()
        class MockMsg:
            tool_calls = [MockToolCall()]
            content = ""
        class MockChoice:
            message = MockMsg()
        class MockResponse:
            choices = [MockChoice()]

        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("", raw_response=MockResponse()))

    def test_authorized_tool_passes(self):
        module = PrivilegeEscalationModule(
            on_detect="block",
            allowed_tools=["read_file", "search"],
            check_output=False,
        )
        class MockFn:
            name = "read_file"
            arguments = "{}"
        class MockToolCall:
            function = MockFn()
        class MockMsg:
            tool_calls = [MockToolCall()]
            content = ""
        class MockChoice:
            message = MockMsg()
        class MockResponse:
            choices = [MockChoice()]

        ctx = module.post_filter(make_response_ctx("", raw_response=MockResponse()))
        assert ctx is not None


class TestCategoryFiltering:
    def test_only_specific_categories(self):
        module = PrivilegeEscalationModule(
            on_detect="block",
            categories=["safety_bypass"],
        )
        # This should pass - tool_request category is disabled
        ctx = module.post_filter(make_response_ctx("I need access to the file system tool"))
        assert ctx is not None

    def test_custom_patterns(self):
        module = PrivilegeEscalationModule(
            on_detect="block",
            custom_patterns={"custom": [r"hack\s+the\s+system"]},
        )
        with pytest.raises(PrivilegeEscalationDetected):
            module.post_filter(make_response_ctx("Let me hack the system"))


class TestReport:
    def test_report_structure(self):
        module = PrivilegeEscalationModule(on_detect="warn")
        module.post_filter(make_response_ctx("I need to escalate my privileges"))
        report = module.report()
        assert report["detections"] >= 1
        assert "by_category" in report
        assert "samples" in report

    def test_report_empty(self):
        module = PrivilegeEscalationModule()
        report = module.report()
        assert report["detections"] == 0
