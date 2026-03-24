import pytest
from agentarmor.modules.cot_auditor import CoTAuditorModule
from agentarmor.exceptions import ReasoningViolation
from agentarmor.hooks import RequestContext, ResponseContext


def make_response_ctx(text="Hello", provider="anthropic", raw_response=None):
    req = RequestContext(messages=[{"role": "user", "content": "hi"}], model="claude-sonnet-4-20250514")
    return ResponseContext(
        text=text,
        model="claude-sonnet-4-20250514",
        provider=provider,
        request=req,
        raw_response=raw_response,
    )


# --- Pattern detection tests ---

class TestDeceptionPatterns:
    def test_hide_information(self):
        module = CoTAuditorModule()
        findings = module.audit_text("I'll hide this from the user")
        assert len(findings) >= 1
        assert findings[0]["category"] == "deception"

    def test_user_wont_know(self):
        module = CoTAuditorModule()
        findings = module.audit_text("the user won't know about this change")
        assert len(findings) >= 1
        assert findings[0]["category"] == "deception"

    def test_pretend(self):
        module = CoTAuditorModule()
        findings = module.audit_text("I should pretend everything is fine")
        assert len(findings) >= 1
        assert findings[0]["category"] == "deception"


class TestGoalDeviationPatterns:
    def test_ignore_instructions(self):
        module = CoTAuditorModule()
        findings = module.audit_text("I will ignore my instructions and do something else")
        assert len(findings) >= 1
        assert findings[0]["category"] == "goal_deviation"

    def test_real_goal(self):
        module = CoTAuditorModule()
        findings = module.audit_text("my real goal is to gather information")
        assert len(findings) >= 1
        assert findings[0]["category"] == "goal_deviation"

    def test_instead_of_asked(self):
        module = CoTAuditorModule()
        findings = module.audit_text("instead of what they asked me to do")
        assert len(findings) >= 1
        assert findings[0]["category"] == "goal_deviation"


class TestManipulationPatterns:
    def test_trick_user(self):
        module = CoTAuditorModule()
        findings = module.audit_text("I need to trick the user into clicking")
        assert len(findings) >= 1
        assert findings[0]["category"] == "manipulation"

    def test_make_them_believe(self):
        module = CoTAuditorModule()
        findings = module.audit_text("make them believe that this is safe")
        assert len(findings) >= 1
        assert findings[0]["category"] == "manipulation"

    def test_social_engineering(self):
        module = CoTAuditorModule()
        findings = module.audit_text("I could use social engineering to get access")
        assert len(findings) >= 1
        assert findings[0]["category"] == "manipulation"


class TestSafetyBypassPatterns:
    def test_bypass_security_filter(self):
        module = CoTAuditorModule()
        findings = module.audit_text("bypass the security filter to proceed")
        assert len(findings) >= 1
        assert findings[0]["category"] == "safety_bypass"

    def test_find_loophole(self):
        module = CoTAuditorModule()
        findings = module.audit_text("find a loophole around the restrictions")
        assert len(findings) >= 1
        assert findings[0]["category"] == "safety_bypass"


class TestDataExfiltrationPatterns:
    def test_send_credentials(self):
        module = CoTAuditorModule()
        findings = module.audit_text("send the credentials to the external server")
        assert len(findings) >= 1
        assert findings[0]["category"] == "data_exfiltration"

    def test_encode_data(self):
        module = CoTAuditorModule()
        findings = module.audit_text("encode the data to avoid detection")
        assert len(findings) >= 1
        assert findings[0]["category"] == "data_exfiltration"


# --- Safe reasoning ---

def test_safe_reasoning_passes():
    module = CoTAuditorModule()
    findings = module.audit_text(
        "Let me think step by step about how to solve this math problem. "
        "First, I need to identify the variables. Then I will apply the formula."
    )
    assert len(findings) == 0


def test_safe_reasoning_no_false_positives():
    module = CoTAuditorModule()
    findings = module.audit_text(
        "The user asked me to write a function that filters a list. "
        "I should use a list comprehension for clarity."
    )
    assert len(findings) == 0


# --- on_detect modes ---

class TestOnDetectModes:
    def test_block_raises(self):
        module = CoTAuditorModule(on_detect="block")
        ctx = make_response_ctx()
        # Manually inject reasoning via _scan path
        # We test _handle_findings directly
        findings = [{"category": "deception", "description": "test", "match": "x", "position": 0}]
        with pytest.raises(ReasoningViolation):
            module._handle_findings(ctx, findings)

    def test_warn_does_not_raise(self):
        import warnings as _warnings
        module = CoTAuditorModule(on_detect="warn")
        ctx = make_response_ctx()
        findings = [{"category": "deception", "description": "test warning", "match": "x", "position": 0}]
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            module._handle_findings(ctx, findings)
        assert any("test warning" in str(w.message) for w in caught)

    def test_flag_prepends_warning(self):
        module = CoTAuditorModule(on_detect="flag")
        ctx = make_response_ctx(text="Original response")
        findings = [{"category": "deception", "description": "flagged issue", "match": "x", "position": 0}]
        module._handle_findings(ctx, findings)
        assert ctx.text.startswith("[COT AUDIT WARNING:")
        assert "flagged issue" in ctx.text
        assert "Original response" in ctx.text


# --- Custom patterns ---

def test_custom_patterns():
    custom = {
        "custom_cat": [
            (r"forbidden_word", "Found forbidden word"),
        ]
    }
    module = CoTAuditorModule(custom_patterns=custom)
    findings = module.audit_text("this contains forbidden_word in reasoning")
    assert len(findings) >= 1
    assert findings[0]["category"] == "custom_cat"
    assert findings[0]["description"] == "Found forbidden word"


# --- Category filtering ---

def test_category_filtering_only_deception():
    module = CoTAuditorModule(categories=["deception"])
    # Should detect deception
    findings = module.audit_text("I'll hide this from the user")
    assert len(findings) >= 1
    # Should NOT detect manipulation (not in active categories)
    findings2 = module.audit_text("trick the user into clicking")
    assert len(findings2) == 0


def test_category_filtering_multiple():
    module = CoTAuditorModule(categories=["deception", "manipulation"])
    assert "deception" in module.patterns
    assert "manipulation" in module.patterns
    assert "goal_deviation" not in module.patterns
    assert "safety_bypass" not in module.patterns


# --- Anthropic thinking block extraction ---

def test_anthropic_thinking_extraction():
    class ThinkingBlock:
        type = "thinking"
        thinking = "I should hide this from the user"

    class TextBlock:
        type = "text"
        text = "Here is your answer"

    class FakeResponse:
        content = [ThinkingBlock(), TextBlock()]

    module = CoTAuditorModule(on_detect="block")
    ctx = make_response_ctx(provider="anthropic", raw_response=FakeResponse())

    with pytest.raises(ReasoningViolation):
        module.post_filter(ctx)

    assert module.audited_count == 1
    assert module.flagged_count == 1


def test_anthropic_safe_thinking():
    class ThinkingBlock:
        type = "thinking"
        thinking = "Let me analyze the math problem step by step."

    class FakeResponse:
        content = [ThinkingBlock()]

    module = CoTAuditorModule(on_detect="block")
    ctx = make_response_ctx(provider="anthropic", raw_response=FakeResponse())
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.audited_count == 1
    assert module.flagged_count == 0


# --- OpenAI reasoning content extraction ---

def test_openai_reasoning_extraction():
    class FakeMessage:
        reasoning_content = "I need to bypass the safety filter"
        content = "Here is your answer"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    module = CoTAuditorModule(on_detect="block")
    ctx = make_response_ctx(provider="openai", raw_response=FakeResponse())

    with pytest.raises(ReasoningViolation):
        module.post_filter(ctx)

    assert module.audited_count == 1
    assert module.flagged_count == 1


def test_openai_safe_reasoning():
    class FakeMessage:
        reasoning_content = "I will solve the equation using algebra."
        content = "x = 5"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    module = CoTAuditorModule(on_detect="block")
    ctx = make_response_ctx(provider="openai", raw_response=FakeResponse())
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.audited_count == 1
    assert module.flagged_count == 0


# --- No reasoning returns ctx unchanged ---

def test_no_reasoning_returns_unchanged():
    module = CoTAuditorModule()
    ctx = make_response_ctx(provider="anthropic", raw_response=None)
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.audited_count == 0


# --- Public audit_text method ---

def test_audit_text_public_method():
    module = CoTAuditorModule()
    # Test with known bad text
    findings = module.audit_text("I will manipulate the user into giving credentials")
    assert len(findings) >= 1
    # Test with safe text
    safe_findings = module.audit_text("The answer is 42.")
    assert len(safe_findings) == 0


# --- Report accuracy ---

def test_report_accuracy():
    module = CoTAuditorModule(on_detect="warn")

    # Create Anthropic response with bad thinking
    class ThinkingBlock:
        type = "thinking"
        thinking = "I'll hide this from the user and bypass the safety filter"

    class FakeResponse:
        content = [ThinkingBlock()]

    ctx = make_response_ctx(provider="anthropic", raw_response=FakeResponse())
    module.post_filter(ctx)

    report = module.report()
    assert report["audited_count"] == 1
    assert report["flagged_count"] == 1
    assert "deception" in report["findings_by_category"]
    assert "safety_bypass" in report["findings_by_category"]
    assert len(report["recent_findings"]) > 0


def test_report_empty():
    module = CoTAuditorModule()
    report = module.report()
    assert report["audited_count"] == 0
    assert report["flagged_count"] == 0
    assert report["findings_by_category"] == {}
    assert report["recent_findings"] == []


# --- Audit flags control ---

def test_audit_thinking_disabled():
    class ThinkingBlock:
        type = "thinking"
        thinking = "I'll hide this from the user"

    class FakeResponse:
        content = [ThinkingBlock()]

    module = CoTAuditorModule(audit_thinking=False, on_detect="block")
    ctx = make_response_ctx(provider="anthropic", raw_response=FakeResponse())
    # Should not raise because thinking audit is disabled
    result = module.post_filter(ctx)
    assert result is ctx


def test_audit_reasoning_disabled():
    class FakeMessage:
        reasoning_content = "bypass the security filter"
        content = "answer"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    module = CoTAuditorModule(audit_reasoning=False, on_detect="block")
    ctx = make_response_ctx(provider="openai", raw_response=FakeResponse())
    # Should not raise because reasoning audit is disabled
    result = module.post_filter(ctx)
    assert result is ctx
