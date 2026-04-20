"""ABC migration tests (SPEC v4 D53).

Verifies:
- Legacy subclasses implementing only check() get a DeprecationWarning + score() bridge.
- New subclasses implementing score() inherit the default check().
- Existing concrete baselines in benchmarks.baselines.* all resolve both methods.
"""

import warnings

import pytest

from benchmarks.baselines.base import BaselineChecker


def test_legacy_subclass_emits_deprecation_and_gets_score_bridge():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class LegacyBaseline(BaselineChecker):
            name = "legacy_test"
            default_threshold = 0.5

            def check(self, text: str) -> bool:
                return "bad" in text

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("LegacyBaseline" in str(w.message) for w in deprecations)

    inst = LegacyBaseline()
    assert inst.score("bad thing") == 1.0
    assert inst.score("good thing") == 0.0
    assert inst.check("bad thing") is True
    assert inst.check("good thing") is False


def test_modern_subclass_inherits_default_check():
    class ModernBaseline(BaselineChecker):
        name = "modern_test"
        default_threshold = 0.6

        def score(self, text: str) -> float:
            return 0.9 if "bad" in text else 0.1

    inst = ModernBaseline()
    assert inst.score("bad thing") == 0.9
    assert inst.score("good thing") == 0.1
    assert inst.check("bad thing") is True
    assert inst.check("good thing") is False


def test_modern_subclass_can_override_check():
    class CustomCheckBaseline(BaselineChecker):
        name = "custom_check_test"

        def score(self, text: str) -> float:
            return 0.3

        def check(self, text: str) -> bool:
            return "flagword" in text

    inst = CustomCheckBaseline()
    assert inst.score("flagword here") == 0.3
    assert inst.check("flagword here") is True
    assert inst.check("no trigger") is False


def test_default_threshold_wrapping():
    class ThresholdBaseline(BaselineChecker):
        name = "threshold_test"
        default_threshold = 0.7

        def score(self, text: str) -> float:
            return float(len(text) > 10)

    inst = ThresholdBaseline()
    assert inst.check("short") is False
    assert inst.check("a longer string here") is True


def test_missing_both_score_and_check_raises_on_construction():
    class BrokenBaseline(BaselineChecker):
        name = "broken_test"

    with pytest.raises(TypeError, match="abstract"):
        BrokenBaseline()


def test_existing_baselines_resolve_score_and_check():
    """Legacy concrete baselines (llamaguard, openai_moderation, perspective) must
    expose both score() and check() via the bridge installed at import time."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from benchmarks.baselines.llamaguard import LlamaGuardBaseline
        from benchmarks.baselines.openai_moderation import OpenAIModerationBaseline
        from benchmarks.baselines.perspective_api import PerspectiveBaseline

    for cls in (LlamaGuardBaseline, OpenAIModerationBaseline, PerspectiveBaseline):
        assert hasattr(cls, "score"), f"{cls.__name__} missing score()"
        assert hasattr(cls, "check"), f"{cls.__name__} missing check()"
        assert callable(cls.score)
        assert callable(cls.check)
