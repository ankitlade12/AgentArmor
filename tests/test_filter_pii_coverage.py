"""filter=["pii"] should cover the common non-US formats a GDPR user assumes
are redacted: IP addresses, IBANs, and international phone numbers — not just
US email/SSN/phone. And it must not over-redact ordinary prose.
"""
from agentarmor.modules.filter import FilterModule


def test_pii_redacts_ipv4_address():
    out = FilterModule(rules=["pii"]).redact("server 203.0.113.42 is down")
    assert "203.0.113.42" not in out
    assert "REDACTED" in out


def test_pii_redacts_iban():
    out = FilterModule(rules=["pii"]).redact("wire to DE89370400440532013000 today")
    assert "DE89370400440532013000" not in out
    assert "REDACTED" in out


def test_pii_redacts_lowercase_iban():
    out = FilterModule(rules=["pii"]).redact("wire to de89370400440532013000 today")
    assert "de89370400440532013000" not in out
    assert "REDACTED" in out


def test_pii_redacts_formatted_iban():
    formatted = "DE89 3704 0044 0532 0130 00"
    out = FilterModule(rules=["pii"]).redact(f"wire to {formatted} today")
    assert formatted not in out
    assert "DE89" not in out
    assert "[REDACTED:IBAN]" in out


def test_pii_does_not_redact_non_country_code_iban_like_id():
    text = "order AB12CDEFGHIJKLMNO shipped"
    assert FilterModule(rules=["pii"]).redact(text) == text


def test_pii_redacts_international_phone():
    out = FilterModule(rules=["pii"]).redact("ring +44 20 7946 0958 after noon")
    assert "7946 0958" not in out
    assert "REDACTED" in out


def test_pii_does_not_over_redact_plain_prose():
    text = "The meeting is at 3pm to review version 2 of the doc."
    assert FilterModule(rules=["pii"]).redact(text) == text


def test_new_patterns_are_individually_selectable():
    for name in ("ipv4", "iban", "intl_phone"):
        assert name in FilterModule(rules=[name]).active_patterns
