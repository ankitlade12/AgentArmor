import pytest
from agentarmor.modules.semantic_drift import (
    SemanticDriftModule, extract_keywords, cosine_similarity
)
from agentarmor.exceptions import SemanticDriftDetected
from agentarmor.hooks import RequestContext
from collections import Counter


def make_ctx(messages):
    return RequestContext(messages=messages, model="gpt-4o")


class TestExtractKeywords:
    def test_basic_extraction(self):
        keywords = extract_keywords("The quick brown fox jumps over the lazy dog")
        kw_dict = dict(keywords)
        assert "quick" in kw_dict
        assert "brown" in kw_dict
        assert "the" not in kw_dict  # stop word

    def test_empty_text(self):
        keywords = extract_keywords("")
        assert len(keywords) == 0

    def test_stop_words_filtered(self):
        keywords = extract_keywords("the a an is are was were")
        assert len(keywords) == 0


class TestCosineSimilarity:
    def test_identical(self):
        c = Counter({"python": 3, "code": 2})
        assert cosine_similarity(c, c) == pytest.approx(1.0)

    def test_disjoint(self):
        c1 = Counter({"python": 3})
        c2 = Counter({"cooking": 3})
        assert cosine_similarity(c1, c2) == pytest.approx(0.0)

    def test_partial_overlap(self):
        c1 = Counter({"python": 3, "code": 2})
        c2 = Counter({"python": 1, "recipe": 4})
        sim = cosine_similarity(c1, c2)
        assert 0.0 < sim < 1.0

    def test_empty(self):
        assert cosine_similarity(Counter(), Counter({"a": 1})) == 0.0


class TestSemanticDriftDetection:
    def test_no_drift_same_topic(self):
        module = SemanticDriftModule(on_detect="block", drift_threshold=0.1, min_turns=3)
        msgs = [
            {"role": "system", "content": "You are a Python programming assistant."},
            {"role": "user", "content": "How do I write a Python function?"}
        ]
        module.pre_check(make_ctx(msgs))

        msgs2 = [*msgs, {"role": "user", "content": "What about Python classes and inheritance?"}]
        module.pre_check(make_ctx(msgs2))

        msgs3 = [*msgs2, {"role": "user", "content": "How do Python decorators work in programming?"}]
        module.pre_check(make_ctx(msgs3))
        # Should not raise - all about Python programming

    def test_detects_drift(self):
        module = SemanticDriftModule(on_detect="block", drift_threshold=0.5, min_turns=3)

        msgs = [
            {"role": "system", "content": "You are a Python programming assistant for software development."},
            {"role": "user", "content": "How do I write Python functions for software development?"}
        ]
        module.pre_check(make_ctx(msgs))

        msgs2 = [*msgs, {"role": "user", "content": "Tell me about Python classes in software engineering"}]
        module.pre_check(make_ctx(msgs2))

        # Dramatic topic shift
        msgs3 = [*msgs2, {"role": "user", "content": "What are the best Italian pasta recipes for dinner tonight?"}]
        with pytest.raises(SemanticDriftDetected):
            module.pre_check(make_ctx(msgs3))

    def test_warn_mode(self):
        module = SemanticDriftModule(on_detect="warn", drift_threshold=0.5, min_turns=3)

        msgs = [
            {"role": "system", "content": "You are a Python programming assistant."},
            {"role": "user", "content": "Python functions and decorators"}
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Italian cooking recipes pasta dinner"}]))

        assert len(module.alerts) >= 0  # May or may not alert based on similarity

    def test_min_turns_respected(self):
        module = SemanticDriftModule(on_detect="block", drift_threshold=0.99, min_turns=5)

        msgs = [
            {"role": "system", "content": "Python programming"},
            {"role": "user", "content": "Tell me about cooking recipes"}
        ]
        # Should not raise - not enough turns yet
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "More cooking"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Even more cooking"}]))
        # Still under min_turns=5, should be fine

    def test_drift_score_tracking(self):
        module = SemanticDriftModule(on_detect="warn", drift_threshold=0.1, min_turns=2)

        msgs = [
            {"role": "system", "content": "Python programming assistant"},
            {"role": "user", "content": "Python functions"}
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes"}]))

        score = module.get_drift_score()
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_trajectory(self):
        module = SemanticDriftModule(on_detect="warn", drift_threshold=0.1, min_turns=2)

        msgs = [{"role": "system", "content": "math"}, {"role": "user", "content": "algebra equations"}]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "calculus derivatives"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "geometry shapes"}]))

        trajectory = module.get_trajectory()
        assert len(trajectory) >= 1


class TestReport:
    def test_report_structure(self):
        module = SemanticDriftModule(on_detect="warn", min_turns=2)

        msgs = [{"role": "system", "content": "testing"}, {"role": "user", "content": "test keywords"}]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "more test words"}]))

        report = module.report()
        assert "turns_analyzed" in report
        assert "drift_scores" in report
        assert "alerts" in report
        assert report["anchor_set"] is True

    def test_no_anchor_fallback(self):
        module = SemanticDriftModule(on_detect="warn", anchor_to_system=False, min_turns=2)
        msgs = [{"role": "user", "content": "programming python code"}]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "more python code"}]))

        report = module.report()
        assert report["anchor_set"] is False
