"""Tests for pricing table lookups and runtime override API."""

import pytest

from agentarmor import pricing
from agentarmor.pricing import DEFAULT, PRICING, get_cost, register_pricing


@pytest.fixture(autouse=True)
def _reset_custom_pricing():
    """Ensure every test starts and ends with an empty override table."""
    original = dict(pricing._custom_pricing)
    pricing._custom_pricing.clear()
    yield
    pricing._custom_pricing.clear()
    pricing._custom_pricing.update(original)


class TestBuiltinLookup:
    def test_exact_match_returns_built_in_entry(self):
        assert get_cost("gpt-4o") == PRICING["gpt-4o"]

    def test_case_insensitive_match(self):
        assert get_cost("GPT-4O") == PRICING["gpt-4o"]
        assert get_cost("Gpt-4o") == PRICING["gpt-4o"]

    def test_substring_match_picks_known_model(self):
        # Provider-prefixed aliases like "openai/gpt-4o" should resolve.
        assert get_cost("openai/gpt-4o") == PRICING["gpt-4o"]

    def test_unknown_model_returns_default(self):
        assert get_cost("nonexistent-model-xyz") == DEFAULT

    def test_new_frontier_models_present(self):
        # These were added in the 1.3.0 release; regression-guard them.
        for model in [
            "o3", "o4-mini",
            "claude-opus-4-6", "claude-sonnet-4-6",
            "gemini-2.5-pro", "gemini-2.5-flash",
        ]:
            cost = get_cost(model)
            assert cost is not DEFAULT, f"{model} should have a built-in price"
            assert cost["input"] > 0
            assert cost["output"] > 0


class TestRegisterPricing:
    def test_register_adds_new_model(self):
        register_pricing("my-custom-model", 0.001, 0.002)
        assert get_cost("my-custom-model") == {"input": 0.001, "output": 0.002}

    def test_register_overrides_built_in(self):
        original = get_cost("gpt-4o")
        register_pricing("gpt-4o", 0.0, 0.0)
        assert get_cost("gpt-4o") == {"input": 0.0, "output": 0.0}
        assert original != {"input": 0.0, "output": 0.0}

    def test_register_is_case_insensitive_on_lookup(self):
        register_pricing("CustomModel", 0.01, 0.02)
        assert get_cost("custommodel") == {"input": 0.01, "output": 0.02}
        assert get_cost("CUSTOMMODEL") == {"input": 0.01, "output": 0.02}

    def test_custom_takes_precedence_over_builtin(self):
        # Register a broad override that would substring-match gpt-4o variants.
        register_pricing("gpt-4o", 99.99, 99.99)
        assert get_cost("gpt-4o-mini")["input"] == 99.99

    def test_unknown_still_returns_default_after_unrelated_registration(self):
        register_pricing("something-else", 1.0, 2.0)
        assert get_cost("nonexistent-model-xyz") == DEFAULT
