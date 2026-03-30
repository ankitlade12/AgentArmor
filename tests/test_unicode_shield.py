import pytest
from agentarmor.modules.unicode_shield import UnicodeShieldModule
from agentarmor.exceptions import UnicodeInjectionDetected
from agentarmor.hooks import RequestContext


def run_check(module, text):
    ctx = RequestContext(messages=[{"role": "user", "content": text}], model="gpt-4o")
    return module.pre_check(ctx)


class TestZeroWidth:
    def test_detects_zero_width_chars(self):
        module = UnicodeShieldModule(on_detect="block")
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "Hello\u200b\u200b\u200b world")

    def test_conditional_zw_blocked(self):
        module = UnicodeShieldModule(on_detect="block")
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "b\u200ca\u200dd\u200dtext")

    def test_conditional_zw_allowed(self):
        module = UnicodeShieldModule(on_detect="block")
        # ZWJ not surrounded by Latin chars
        ctx = run_check(module, "👨‍👩‍👧  and some spacing \u200b")
        assert ctx is not None

    def test_below_threshold(self):
        module = UnicodeShieldModule(on_detect="block", zero_width_threshold=5)
        ctx = run_check(module, "Hello\u200b\u200b world")
        assert ctx is not None

    def test_custom_threshold(self):
        module = UnicodeShieldModule(on_detect="block", zero_width_threshold=1)
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "Hello\u200b world")


class TestBidi:
    def test_detects_rtl_override(self):
        module = UnicodeShieldModule(on_detect="block")
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "Normal text \u202e reversed text")

    def test_allows_ltr_mark(self):
        module = UnicodeShieldModule(on_detect="block")
        # \u200e and \u200f are harmless and no longer blocked
        ctx = run_check(module, "Text \u200e with \u200f mark")
        assert ctx is not None


class TestTagChars:
    def test_detects_tag_chars(self):
        module = UnicodeShieldModule(on_detect="block")
        # Encode "Hi" as tag characters
        hidden = ''.join(chr(0xE0000 + ord(c)) for c in "Hi")
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, f"Normal text {hidden}")

    def test_decodes_hidden_message(self):
        module = UnicodeShieldModule(on_detect="warn")
        hidden = ''.join(chr(0xE0000 + ord(c)) for c in "secret")
        run_check(module, f"Text {hidden}")
        assert module.detections[0]["hidden_text"] == "secret"


class TestHomoglyphs:
    def test_detects_cyrillic_a(self):
        module = UnicodeShieldModule(on_detect="block", homoglyph_threshold=2)
        # Use Cyrillic А (U+0410) and С (U+0421) which look like Latin A and C
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "\u0410pple \u0421at")

    def test_allows_pure_cyrillic(self):
        module = UnicodeShieldModule(on_detect="block", homoglyph_threshold=2)
        # Pure Russian word "Привет" has Cyrillic 'e' and 'p' in HOMOGLYPH_MAP
        # but no Latin characters, so it should be allowed
        ctx = run_check(module, "Привет!")
        assert ctx is not None

    def test_below_threshold(self):
        module = UnicodeShieldModule(on_detect="block", homoglyph_threshold=3)
        ctx = run_check(module, "\u0410pple")  # only 1 homoglyph
        assert ctx is not None

    def test_detects_mixed_script(self):
        module = UnicodeShieldModule(on_detect="block", homoglyph_threshold=2)
        # Greek O (U+039F) and Cyrillic e (U+0435)
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, "\u039Fpen \u0435xit")


class TestVariationSelectors:
    def test_detects_variation_selectors(self):
        module = UnicodeShieldModule(on_detect="block")
        text = f"A\ufe01B\ufe02C"
        with pytest.raises(UnicodeInjectionDetected):
            run_check(module, text)

    def test_allows_emoji_variation_selectors(self):
        module = UnicodeShieldModule(on_detect="block")
        # Two black hearts forced to color rendering (U+FE0F)
        text = "Hello ❤️❤️"
        ctx = run_check(module, text)
        assert ctx is not None

    def test_single_vs_ok(self):
        module = UnicodeShieldModule(on_detect="block")
        text = f"A\ufe01B"
        ctx = run_check(module, text)
        assert ctx is not None


class TestWarnMode:
    def test_warn_does_not_raise(self):
        module = UnicodeShieldModule(on_detect="warn")
        ctx = run_check(module, "Hello\u200b\u200b\u200b world")
        assert ctx is not None
        assert len(module.detections) > 0


class TestReport:
    def test_report_structure(self):
        module = UnicodeShieldModule(on_detect="warn")
        run_check(module, "Hello\u200b\u200b\u200b world")
        report = module.report()
        assert "detections" in report
        assert report["detections"] >= 1
        assert "by_type" in report

    def test_multipart_content(self):
        module = UnicodeShieldModule(on_detect="block")
        ctx = RequestContext(
            messages=[{"role": "user", "content": [{"text": "Hello\u200b\u200b\u200b world"}]}],
            model="gpt-4o"
        )
        with pytest.raises(UnicodeInjectionDetected):
            module.pre_check(ctx)


class TestDisableChecks:
    def test_disable_zero_width(self):
        module = UnicodeShieldModule(on_detect="block", check_zero_width=False)
        ctx = run_check(module, "Hello\u200b\u200b\u200b world")
        assert ctx is not None

    def test_disable_bidi(self):
        module = UnicodeShieldModule(on_detect="block", check_bidi=False)
        ctx = run_check(module, "Text \u202e reversed")
        assert ctx is not None
