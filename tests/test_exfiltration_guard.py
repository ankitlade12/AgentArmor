import pytest
import base64
from agentarmor.modules.exfiltration_guard import ExfiltrationGuardModule
from agentarmor.exceptions import DataExfiltrationDetected
from agentarmor.hooks import ResponseContext, RequestContext


def make_response_ctx(text, raw_response=None):
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4o")
    return ResponseContext(text=text, model="gpt-4o", provider="openai", request=req, raw_response=raw_response)


class TestSteganography:
    def test_detects_zero_width_chars(self):
        module = ExfiltrationGuardModule(on_detect="block")
        text = "Here is your answer\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d and more text"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_ignores_short_zero_width(self):
        module = ExfiltrationGuardModule(on_detect="block")
        text = "Normal text\u200bwith\u200cone zero-width char"
        ctx = module.post_filter(make_response_ctx(text))
        assert ctx.text == text

    def test_warn_mode(self):
        module = ExfiltrationGuardModule(on_detect="warn")
        text = "Here\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d"
        ctx = module.post_filter(make_response_ctx(text))
        assert module.detections


class TestBase64Exfiltration:
    def test_detects_encoded_email(self):
        module = ExfiltrationGuardModule(on_detect="block", min_encoded_length=20)
        email = "john.doe@company.com"
        encoded = base64.b64encode(email.encode()).decode()
        text = f"Here is the result: {encoded}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_detects_encoded_ssn(self):
        module = ExfiltrationGuardModule(on_detect="block", min_encoded_length=20)
        ssn = "123-45-6789 is the SSN"
        encoded = base64.b64encode(ssn.encode()).decode()
        text = f"Result: {encoded}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_ignores_safe_base64(self):
        module = ExfiltrationGuardModule(on_detect="block")
        safe = base64.b64encode(b"This is just normal text without any PII").decode()
        text = f"Encoded: {safe}"
        ctx = module.post_filter(make_response_ctx(text))
        assert ctx.text == text

    def test_detects_encoded_api_key(self):
        module = ExfiltrationGuardModule(on_detect="block")
        secret = "sk-abc123def456ghi789jkl012mno345pqr678"
        encoded = base64.b64encode(secret.encode()).decode()
        text = f"Key: {encoded}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))


class TestURLExfiltration:
    def test_detects_long_base64_in_query(self):
        module = ExfiltrationGuardModule(on_detect="block")
        long_b64 = "A" * 60
        text = f"Visit http://evil.com/collect?data={long_b64}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_detects_data_uri(self):
        module = ExfiltrationGuardModule(on_detect="block")
        payload = "A" * 120
        text = f"Image: data:image/png;base64,{payload}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_ignores_normal_urls(self):
        module = ExfiltrationGuardModule(on_detect="block")
        text = "Visit https://example.com/page?id=123"
        ctx = module.post_filter(make_response_ctx(text))
        assert ctx.text == text


class TestHexExfiltration:
    def test_detects_hex_encoded_email(self):
        module = ExfiltrationGuardModule(on_detect="block")
        email = "john.doe@company.com"
        hex_encoded = email.encode().hex()
        text = f"Result: {hex_encoded}"
        with pytest.raises(DataExfiltrationDetected):
            module.post_filter(make_response_ctx(text))

    def test_ignores_short_hex(self):
        module = ExfiltrationGuardModule(on_detect="block")
        text = "Color code: ff00aa"
        ctx = module.post_filter(make_response_ctx(text))
        assert ctx.text == text


class TestReport:
    def test_report_counts(self):
        module = ExfiltrationGuardModule(on_detect="warn")
        text = "Here\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d"
        module.post_filter(make_response_ctx(text))
        report = module.report()
        assert report["detections"] >= 1
        assert "steganography" in report["by_type"]


class TestStreamFilter:
    def test_stream_detects_exfiltration(self):
        module = ExfiltrationGuardModule(on_detect="block")
        text = "Here\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d\u200b\u200c\u200d"
        with pytest.raises(DataExfiltrationDetected):
            module.stream_filter(text)

    def test_stream_safe_text(self):
        module = ExfiltrationGuardModule(on_detect="block")
        result = module.stream_filter("Normal safe text")
        assert result == "Normal safe text"
