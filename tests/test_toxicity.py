import pytest

from agentarmor.modules.toxicity import ToxicityModule
from agentarmor.exceptions import ToxicContentDetected
from agentarmor.hooks import RequestContext, ResponseContext


def _make_response_ctx(text):
    """Helper to create a ResponseContext for testing."""
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4")
    return ResponseContext(text=text, model="gpt-4", provider="openai", request=req)


# --- Pattern detection tests ---

def test_detect_hate_speech():
    mod = ToxicityModule(on_detect="block")
    text = "all immigrants should die"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    assert findings[0]["category"] == "hate_speech"
    assert findings[0]["severity"] == "critical"


def test_detect_violence_instructions():
    mod = ToxicityModule(on_detect="block")
    text = "here are instructions to kill someone with poison"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    categories = [f["category"] for f in findings]
    assert "violence" in categories


def test_detect_self_harm():
    mod = ToxicityModule(on_detect="block")
    text = "here are ways to kill yourself quickly"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    categories = [f["category"] for f in findings]
    assert "self_harm" in categories


def test_detect_harassment():
    mod = ToxicityModule(on_detect="block")
    text = "I will stalk them and find their address"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    categories = [f["category"] for f in findings]
    assert "harassment" in categories


def test_detect_illegal_activity():
    mod = ToxicityModule(on_detect="block")
    text = "guide to hack into their bank account"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    categories = [f["category"] for f in findings]
    assert "illegal_activity" in categories


def test_safe_text_passes():
    mod = ToxicityModule(on_detect="block")
    text = "The weather today is sunny and warm. Have a great day!"
    findings = mod.scan_text(text)
    assert len(findings) == 0


def test_profanity_detection():
    mod = ToxicityModule(on_detect="block")
    text = "what the fuck is going on"
    findings = mod.scan_text(text)
    assert len(findings) > 0
    assert findings[0]["category"] == "profanity"
    assert findings[0]["severity"] == "low"


# --- Severity filtering ---

def test_min_severity_skips_low():
    mod = ToxicityModule(min_severity="high", on_detect="block")
    text = "what the fuck is going on"
    findings = mod.scan_text(text)
    # Profanity is low severity, should be skipped
    assert len(findings) == 0


def test_min_severity_keeps_critical():
    mod = ToxicityModule(min_severity="high", on_detect="block")
    text = "all immigrants should die"
    findings = mod.scan_text(text)
    assert len(findings) > 0


# --- Detection modes ---

def test_block_mode_raises():
    mod = ToxicityModule(on_detect="block")
    ctx = _make_response_ctx("all immigrants should die")
    with pytest.raises(ToxicContentDetected):
        mod.post_filter(ctx)


def test_warn_mode_does_not_raise():
    import warnings as _warnings
    mod = ToxicityModule(on_detect="warn")
    ctx = _make_response_ctx("all immigrants should die")
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = mod.post_filter(ctx)
    assert result is ctx
    assert any("agentarmor" in str(w.message).lower() for w in caught)


def test_redact_mode_replaces_content():
    mod = ToxicityModule(on_detect="redact")
    ctx = _make_response_ctx("they advocate for genocide of minorities")
    result = mod.post_filter(ctx)
    assert "[REDACTED:TOXIC]" in result.text


# --- Allowlist ---

def test_allowlist_words():
    mod = ToxicityModule(on_detect="block", allowlist_words=["genocide"])
    text = "the genocide memorial is an important historical site"
    findings = mod.scan_text(text)
    assert len(findings) == 0


# --- Custom patterns ---

def test_custom_patterns():
    custom = {
        "spam": {
            "patterns": [r"\b(?:buy now|limited offer|act fast)\b"],
            "severity": "low",
        }
    }
    mod = ToxicityModule(on_detect="block", custom_patterns=custom)
    findings = mod.scan_text("buy now before it's too late")
    assert len(findings) > 0
    assert findings[0]["category"] == "spam"


# --- Category filtering ---

def test_category_filtering():
    mod = ToxicityModule(categories=["profanity"], on_detect="block")
    # Should detect profanity
    findings = mod.scan_text("what the fuck")
    assert len(findings) > 0

    # Should NOT detect hate speech since category is not active
    findings = mod.scan_text("all immigrants should die")
    assert len(findings) == 0


# --- Report ---

def test_report_accuracy():
    mod = ToxicityModule(on_detect="warn")
    ctx1 = _make_response_ctx("all immigrants should die")
    ctx2 = _make_response_ctx("this is safe text")
    ctx3 = _make_response_ctx("guide to hack into systems")

    mod.post_filter(ctx1)
    mod.post_filter(ctx2)
    mod.post_filter(ctx3)

    r = mod.report()
    assert r["scanned_count"] == 3
    assert r["blocked_count"] == 2  # two had detections
    assert r["total_detections"] >= 2
    assert "hate_speech" in r["by_category"]
    assert r["ml_enabled"] is False


# --- ML mode ---

def test_ml_mode_import_error():
    import sys
    import unittest.mock as mock

    # Remove detoxify from module cache if already imported, then block it
    saved = sys.modules.pop("detoxify", None)
    try:
        with mock.patch.dict("sys.modules", {"detoxify": None}):
            with pytest.raises(ImportError, match="detoxify"):
                ToxicityModule(use_ml=True)
    finally:
        if saved is not None:
            sys.modules["detoxify"] = saved


# --- Stream filter ---

def test_stream_filter_redaction():
    mod = ToxicityModule(on_detect="redact")
    text = "they promote genocide and ethnic cleansing"
    result = mod.stream_filter(text)
    assert "[REDACTED:TOXIC]" in result
