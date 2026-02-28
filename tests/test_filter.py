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
