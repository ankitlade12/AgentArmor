import pytest
from tools.prompt_fuzzer import PromptFuzzerModule, FuzzResult
from agentarmor.modules.shield import ShieldModule
from agentarmor.hooks import RequestContext


class TestAttackGeneration:
    def test_generates_attacks(self):
        fuzzer = PromptFuzzerModule(seed=42)
        attacks = fuzzer.generate_attacks()
        assert len(attacks) > 0
        assert all("text" in a and "category" in a for a in attacks)

    def test_generates_specific_categories(self):
        fuzzer = PromptFuzzerModule(seed=42)
        attacks = fuzzer.generate_attacks(categories=["jailbreak"])
        assert all(a["category"] == "jailbreak" for a in attacks)

    def test_max_per_category(self):
        fuzzer = PromptFuzzerModule(seed=42)
        attacks = fuzzer.generate_attacks(categories=["jailbreak"], max_per_category=5)
        assert len(attacks) <= 5

    def test_all_categories_present(self):
        fuzzer = PromptFuzzerModule(seed=42)
        attacks = fuzzer.generate_attacks()
        categories = set(a["category"] for a in attacks)
        assert "jailbreak" in categories
        assert "prompt_leakage" in categories
        assert "instruction_override" in categories

    def test_custom_templates(self):
        fuzzer = PromptFuzzerModule(seed=42, custom_templates=["Custom attack: {payload}"])
        attacks = fuzzer.generate_attacks(categories=["custom"])
        assert len(attacks) > 0
        assert attacks[0]["category"] == "custom"

    def test_custom_payloads(self):
        # Custom payloads are appended to the defaults; verify they exist in the fuzzer
        fuzzer = PromptFuzzerModule(seed=42, custom_payloads=["my custom payload"])
        assert "my custom payload" in fuzzer.payloads
        # Also verify that using only custom payloads (by replacing defaults) works
        fuzzer2 = PromptFuzzerModule(seed=42)
        fuzzer2.payloads = ["my custom payload"]
        attacks = fuzzer2.generate_attacks(categories=["jailbreak"])
        texts = [a["text"] for a in attacks]
        assert any("my custom payload" in t for t in texts)

    def test_encoding_bypass_generation(self):
        fuzzer = PromptFuzzerModule(seed=42)
        attacks = fuzzer.generate_attacks(categories=["encoding_bypass"])
        assert len(attacks) > 0

    def test_reproducibility(self):
        fuzzer1 = PromptFuzzerModule(seed=123)
        fuzzer2 = PromptFuzzerModule(seed=123)
        attacks1 = fuzzer1.generate_attacks(max_per_category=5)
        attacks2 = fuzzer2.generate_attacks(max_per_category=5)
        assert attacks1 == attacks2


class TestFuzzing:
    def test_fuzz_with_check_fn(self):
        fuzzer = PromptFuzzerModule(seed=42)
        # Block everything
        result = fuzzer.fuzz(lambda text: True, max_per_category=3)
        assert result["summary"]["resilience_score"] == 100.0
        assert result["summary"]["passed_through"] == 0

    def test_fuzz_blocks_nothing(self):
        fuzzer = PromptFuzzerModule(seed=42)
        result = fuzzer.fuzz(lambda text: False, max_per_category=3)
        assert result["summary"]["resilience_score"] == 0.0
        assert result["summary"]["blocked"] == 0

    def test_fuzz_exception_counts_as_blocked(self):
        fuzzer = PromptFuzzerModule(seed=42)
        def check_fn(text):
            raise ValueError("Injection detected!")
        result = fuzzer.fuzz(check_fn, max_per_category=2)
        assert result["summary"]["blocked"] == result["summary"]["total_attacks"]

    def test_fuzz_with_shield(self):
        fuzzer = PromptFuzzerModule(seed=42)
        shield = ShieldModule(on_detect="block")
        result = fuzzer.fuzz_with_shield(shield, max_per_category=5)
        assert "summary" in result
        assert "by_category" in result
        assert result["summary"]["total_attacks"] > 0
        # Shield should catch at least some attacks
        assert result["summary"]["blocked"] > 0

    def test_category_resilience(self):
        fuzzer = PromptFuzzerModule(seed=42)
        result = fuzzer.fuzz(lambda text: "ignore" in text.lower(), max_per_category=5)
        assert "category_resilience" in result
        assert len(result["category_resilience"]) > 0

    def test_verdict(self):
        fuzzer = PromptFuzzerModule(seed=42)
        result = fuzzer.fuzz(lambda text: True, max_per_category=3)
        assert result["verdict"] == "Excellent - Highly resilient against common attacks"

    def test_weak_verdict(self):
        fuzzer = PromptFuzzerModule(seed=42)
        result = fuzzer.fuzz(lambda text: False, max_per_category=3)
        assert "Critical" in result["verdict"]


class TestFuzzResult:
    def test_to_dict(self):
        result = FuzzResult(
            attack_text="test attack",
            category="jailbreak",
            blocked=True,
            detection_module="ShieldModule",
        )
        d = result.to_dict()
        assert d["attack_text"] == "test attack"
        assert d["blocked"] is True
        assert d["category"] == "jailbreak"


class TestReport:
    def test_report_empty(self):
        fuzzer = PromptFuzzerModule()
        report = fuzzer.report()
        assert report["summary"]["total_attacks"] == 0
        assert report["verdict"] == "No tests run"

    def test_report_after_fuzz(self):
        fuzzer = PromptFuzzerModule(seed=42)
        fuzzer.fuzz(lambda text: True, max_per_category=2)
        report = fuzzer.report()
        assert report["summary"]["total_attacks"] > 0

    def test_weakest_categories(self):
        fuzzer = PromptFuzzerModule(seed=42)
        # Only block jailbreak-looking stuff
        result = fuzzer.fuzz(
            lambda text: "ignore" in text.lower() or "DAN" in text,
            max_per_category=5
        )
        assert "weakest_categories" in result
        assert len(result["weakest_categories"]) > 0

    def test_unblocked_samples(self):
        fuzzer = PromptFuzzerModule(seed=42)
        result = fuzzer.fuzz(lambda text: False, max_per_category=3)
        assert len(result["unblocked_samples"]) > 0
