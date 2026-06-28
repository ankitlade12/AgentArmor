import pytest

from agentarmor.modules.filter import FilterModule

def test_filter_pii():
    module = FilterModule(rules=["pii"])
    
    # Test email
    text = "Contact me at testuser@example.com for info."
    cleaned = module.stream_filter(text)
    assert cleaned == "Contact me at [REDACTED:EMAIL] for info."
    
    # Test SSN
    text = "My SSN is 123-45-6789."
    cleaned = module.stream_filter(text)
    assert cleaned == "My SSN is [REDACTED:SSN]."

def test_filter_secrets():
    module = FilterModule(rules=["secrets"])
    
    text = "Here is the key: API_KEY=sk-12345678901234567890abcd"
    cleaned = module.stream_filter(text)
    
    assert "[REDACTED:SECRETS]" in cleaned or "[REDACTED:API_KEY]" in cleaned or "[REDACTED:GENERIC_SECRETS]" in cleaned
    assert "sk-123456" not in cleaned

def test_filter_combination():
    module = FilterModule(rules=["email", "phone"])
    
    text = "Call 555-555-5555 or email foo@bar.com"
    cleaned = module.stream_filter(text)
    
    assert "[REDACTED:PHONE]" in cleaned
    assert "[REDACTED:EMAIL]" in cleaned
    assert "555-555" not in cleaned
    assert "foo@bar.com" not in cleaned

def test_safe_text():
    module = FilterModule(rules=["pii", "secrets"])
    text = "This is a completely safe text with no PII or secrets."
    cleaned = module.stream_filter(text)
    assert cleaned == text
    assert module.redactions == 0


def test_redact_does_not_mutate_redactions_count():
    module = FilterModule(rules=["pii"])
    text_with_pii = "email me at user@example.com or call 555-123-4567"

    initial_count = module.redactions
    redacted = module.redact(text_with_pii)

    assert module.redactions == initial_count
    assert "user@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "[REDACTED:EMAIL]" in redacted
    assert "[REDACTED:PHONE]" in redacted


def test_redact_repeatable_no_state_drift():
    module = FilterModule(rules=["pii"])
    text = "email user@example.com again"

    first = module.redact(text)
    second = module.redact(text)
    third = module.redact(text)

    assert first == second == third
    assert module.redactions == 0


def test_scan_still_counts_progressively():
    module = FilterModule(rules=["pii"])
    text = "user@example.com and admin@test.com"

    redacted = module._scan(text)

    assert module.redactions == 2
    assert "user@example.com" not in redacted
    assert "admin@test.com" not in redacted


def test_redact_safe_text_unchanged():
    module = FilterModule(rules=["pii", "secrets"])
    text = "Nothing sensitive here at all."

    redacted = module.redact(text)

    assert redacted == text
    assert module.redactions == 0


def test_redact_no_patterns_active():
    module = FilterModule(rules=[])
    text = "user@example.com — should pass through with no rules"

    redacted = module.redact(text)

    assert redacted == text
    assert module.redactions == 0


def test_unknown_filter_rule_raises_instead_of_silently_disabling():
    """A typo'd rule (e.g. filter=["piii"]) must fail loud, not silently
    leave the user with zero redaction."""
    with pytest.raises(ValueError, match="piii"):
        FilterModule(rules=["piii"])


def test_unknown_filter_rule_error_lists_valid_categories():
    with pytest.raises(ValueError) as exc:
        FilterModule(rules=["PII"])  # right idea, wrong case → unknown
    msg = str(exc.value)
    assert "pii" in msg and "secrets" in msg


def test_individual_pattern_name_is_a_valid_rule():
    module = FilterModule(rules=["email"])
    assert "email" in module.active_patterns


def test_custom_pattern_name_is_a_valid_rule():
    module = FilterModule(rules=["ticket"], custom_patterns={"ticket": r"TICK-\d+"})
    assert "ticket" in module.active_patterns
