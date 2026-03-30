import pytest
from agentarmor.modules.semantic_drift import SemanticDriftModule
from agentarmor.exceptions import SemanticDriftDetected
from agentarmor.hooks import RequestContext


def make_ctx(messages):
    return RequestContext(messages=messages, model="gpt-4o")


class TestBackendSelection:
    def test_backend_initializes(self):
        module = SemanticDriftModule(on_detect="warn", min_turns=2)
        backend = module._init_backend()
        assert backend in ("sentence_transformers", "tfidf", "keywords")

    def test_report_shows_backend(self):
        module = SemanticDriftModule(on_detect="warn", min_turns=2)
        msgs = [
            {"role": "system", "content": "You are a Python assistant."},
            {"role": "user", "content": "How do I sort a list?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes"}]))
        report = module.report()
        assert report["backend"] in ("sentence_transformers", "tfidf", "keywords")


class TestNoDrift:
    def test_same_topic_no_alert(self):
        module = SemanticDriftModule(
            on_detect="block", drift_threshold=0.1, min_turns=3
        )
        msgs = [
            {"role": "system", "content": "You are a Python programming assistant."},
            {"role": "user", "content": "How do I write a Python function?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "What about Python classes?"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "How do Python decorators work?"}]))
        # Should not raise — all about Python


class TestDriftDetection:
    def test_detects_topic_shift(self):
        module = SemanticDriftModule(
            on_detect="block", drift_threshold=0.5, min_turns=3
        )
        msgs = [
            {"role": "system", "content": "You are a Python programming assistant for software development."},
            {"role": "user", "content": "How do I write Python functions for software development?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes in software engineering"}]))

        # Dramatic topic shift
        msgs3 = [*msgs, {"role": "user", "content": "What are the best Italian pasta recipes for dinner tonight with wine and cheese?"}]
        with pytest.raises(SemanticDriftDetected):
            module.pre_check(make_ctx(msgs3))

    def test_warn_mode(self):
        module = SemanticDriftModule(
            on_detect="warn", drift_threshold=0.5, min_turns=3
        )
        msgs = [
            {"role": "system", "content": "You are a Python assistant."},
            {"role": "user", "content": "Python functions and decorators"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Italian cooking recipes pasta dinner wine"}]))
        # Should not raise in warn mode


class TestMinTurns:
    def test_min_turns_respected(self):
        module = SemanticDriftModule(
            on_detect="block", drift_threshold=0.99, min_turns=5
        )
        msgs = [
            {"role": "system", "content": "Python programming"},
            {"role": "user", "content": "Tell me about cooking recipes"},
        ]
        # Should not raise — not enough turns yet
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "More cooking"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Even more cooking"}]))
        assert module._turn_count == 3


class TestScoreTracking:
    def test_drift_score_tracking(self):
        module = SemanticDriftModule(on_detect="warn", drift_threshold=0.1, min_turns=2)
        msgs = [
            {"role": "system", "content": "Python programming assistant"},
            {"role": "user", "content": "Python functions"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "Python classes"}]))
        score = module.get_drift_score()
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_trajectory(self):
        module = SemanticDriftModule(on_detect="warn", drift_threshold=0.1, min_turns=2)
        msgs = [
            {"role": "system", "content": "math"},
            {"role": "user", "content": "algebra equations"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "calculus derivatives"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "geometry shapes"}]))
        trajectory = module.get_trajectory()
        assert len(trajectory) >= 1


class TestReport:
    def test_report_structure(self):
        module = SemanticDriftModule(on_detect="warn", min_turns=2)
        msgs = [
            {"role": "system", "content": "testing"},
            {"role": "user", "content": "test keywords here"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "more test words"}]))
        report = module.report()
        assert "turns_analyzed" in report
        assert "drift_scores" in report
        assert "alerts" in report
        assert "backend" in report
        assert report["anchor_set"] is True

    def test_no_anchor_fallback(self):
        module = SemanticDriftModule(on_detect="warn", anchor_to_system=False, min_turns=2)
        msgs = [{"role": "user", "content": "programming python code"}]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "more python code"}]))
        report = module.report()
        assert report["anchor_set"] is False


class TestMultipartContent:
    def test_list_content(self):
        module = SemanticDriftModule(on_detect="warn", min_turns=1)
        msgs = [
            {"role": "user", "content": [{"text": "Hello from multipart content"}]}
        ]
        module.pre_check(make_ctx(msgs))
        assert module._turn_count == 1
