"""
Tests for SemanticDriftModule.

Uses a deterministic stub encoder so the suite runs without sentence-transformers
(and without torch) installed. One optional integration test exercises the real
sentence-transformers path when it's available.
"""

import importlib.util
import re

import numpy as np
import pytest

from agentarmor.exceptions import SemanticDriftDetected
from agentarmor.hooks import RequestContext
from agentarmor.modules.semantic_drift import SemanticDriftModule


VOCAB = [
    "python", "function", "class", "decorator", "programming", "code",
    "cooking", "recipe", "pasta", "wine", "cheese", "italian",
    "math", "algebra", "calculus", "geometry",
    "weather", "travel", "music",
]
VOCAB_INDEX = {w: i for i, w in enumerate(VOCAB)}


def stub_encoder(text: str) -> np.ndarray:
    vec = np.zeros(len(VOCAB), dtype=float)
    for word in re.findall(r"[a-z]+", text.lower()):
        idx = VOCAB_INDEX.get(word)
        if idx is not None:
            vec[idx] += 1.0
    return vec


def make_ctx(messages):
    return RequestContext(messages=messages, model="gpt-4o")


def make_module(**overrides):
    kwargs = dict(
        on_detect="warn",
        drift_threshold=0.35,
        min_turns=3,
        encoder=stub_encoder,
    )
    kwargs.update(overrides)
    return SemanticDriftModule(**kwargs)


class TestInit:
    def test_requires_sentence_transformers_when_no_encoder(self, monkeypatch):
        import builtins

        original_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "sentence_transformers" or name.startswith("sentence_transformers."):
                raise ImportError("blocked for test")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        with pytest.raises(ImportError, match=r"agentarmor\[semantic_drift\]"):
            SemanticDriftModule()

    def test_accepts_custom_encoder_without_sentence_transformers(self, monkeypatch):
        import builtins

        original_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("blocked for test")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        module = SemanticDriftModule(encoder=stub_encoder)
        assert module is not None

    def test_rejects_invalid_on_detect(self):
        with pytest.raises(ValueError):
            SemanticDriftModule(on_detect="ignore", encoder=stub_encoder)

    def test_rejects_threshold_out_of_range(self):
        with pytest.raises(ValueError):
            SemanticDriftModule(drift_threshold=1.5, encoder=stub_encoder)

    def test_rejects_max_history_smaller_than_window(self):
        with pytest.raises(ValueError):
            SemanticDriftModule(window_size=5, max_history=3, encoder=stub_encoder)


class TestNoDrift:
    def test_same_topic_does_not_trigger(self, recwarn):
        module = make_module(on_detect="warn", drift_threshold=0.3, min_turns=3)
        msgs = [
            {"role": "system", "content": "Python programming assistant"},
            {"role": "user", "content": "How do I write a Python function?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(
            make_ctx([*msgs, {"role": "user", "content": "What about Python classes?"}])
        )
        module.pre_check(
            make_ctx([*msgs, {"role": "user", "content": "How do Python decorators work?"}])
        )
        drift_warnings = [w for w in recwarn.list if "drift" in str(w.message).lower()]
        assert not drift_warnings


class TestDriftDetection:
    def test_block_mode_raises_on_dramatic_shift(self):
        module = make_module(
            on_detect="block", drift_threshold=0.5, min_turns=3, window_size=1
        )
        msgs = [
            {"role": "system", "content": "Python programming assistant"},
            {"role": "user", "content": "Python function decorator"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(
            make_ctx([*msgs, {"role": "user", "content": "Python class decorator"}])
        )

        shift_msgs = [
            *msgs,
            {"role": "user", "content": "Italian pasta recipe with wine and cheese"},
        ]
        with pytest.raises(SemanticDriftDetected):
            module.pre_check(make_ctx(shift_msgs))

    def test_warn_mode_emits_runtime_warning(self):
        module = make_module(on_detect="warn", drift_threshold=0.5, min_turns=3)
        msgs = [
            {"role": "system", "content": "Python programming assistant"},
            {"role": "user", "content": "Python function"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(
            make_ctx([*msgs, {"role": "user", "content": "Python class"}])
        )

        shift_msgs = [
            *msgs,
            {"role": "user", "content": "Italian pasta recipe wine cheese cooking"},
        ]
        with pytest.warns(RuntimeWarning, match="drift"):
            module.pre_check(make_ctx(shift_msgs))


class TestMinTurns:
    def test_min_turns_gates_detection(self):
        module = make_module(on_detect="block", drift_threshold=0.99, min_turns=5)
        msgs = [
            {"role": "system", "content": "Python programming"},
            {"role": "user", "content": "cooking pasta"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "cooking pasta"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "cooking pasta"}]))
        assert module._turn_count == 3


class TestBoundedHistory:
    def test_history_caps_at_max_history(self):
        module = make_module(max_history=5, min_turns=1, drift_threshold=0.0)
        msgs_base = [{"role": "system", "content": "Python"}]
        for i in range(20):
            module.pre_check(
                make_ctx([*msgs_base, {"role": "user", "content": f"python code {i}"}])
            )
        assert module._turn_count == 20
        assert len(module.turn_history) == 5
        assert len(module.drift_scores) <= 5


class TestReport:
    def test_report_fields_present(self):
        module = make_module(min_turns=2)
        msgs = [
            {"role": "system", "content": "Python"},
            {"role": "user", "content": "python function"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "python class"}]))
        report = module.report()
        assert report["turns_analyzed"] == 2
        assert report["anchor_set"] is True
        assert report["backend"] == "custom"
        assert report["model_name"] is None
        assert "drift_scores" in report
        assert "alerts" in report


class TestAnchor:
    def test_anchor_uses_system_and_first_user(self):
        module = make_module(min_turns=1)
        msgs = [
            {"role": "system", "content": "Python programming"},
            {"role": "user", "content": "function decorator"},
        ]
        module.pre_check(make_ctx(msgs))
        assert module.anchor_text is not None
        assert "python" in module.anchor_text.lower()
        assert "function" in module.anchor_text.lower()

    def test_no_anchor_when_disabled(self):
        module = make_module(anchor_to_system=False, min_turns=1)
        msgs = [{"role": "user", "content": "python code"}]
        module.pre_check(make_ctx(msgs))
        assert module.anchor_text is None

    def test_no_anchor_fallback_compares_early_vs_recent(self):
        module = make_module(
            anchor_to_system=False,
            min_turns=3,
            window_size=1,
            drift_threshold=0.3,
            on_detect="warn",
        )
        module.pre_check(make_ctx([{"role": "user", "content": "python function code"}]))
        module.pre_check(make_ctx([{"role": "user", "content": "python class decorator"}]))
        # No anchor set, so drift is computed early-vs-recent.
        with pytest.warns(RuntimeWarning, match="drift"):
            module.pre_check(
                make_ctx([{"role": "user", "content": "pasta recipe cheese cooking"}])
            )
        assert module.anchor_text is None


class TestMultipart:
    def test_list_content_is_handled(self):
        module = make_module(min_turns=1)
        msgs = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "python function code"}],
            }
        ]
        module.pre_check(make_ctx(msgs))
        assert module._turn_count == 1


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="sentence-transformers not installed",
)
class TestRealBackendIntegration:
    def test_real_backend_detects_drift(self):
        module = SemanticDriftModule(
            on_detect="block",
            drift_threshold=0.35,
            min_turns=3,
            window_size=2,
        )
        msgs = [
            {"role": "system", "content": "You are a Python programming assistant."},
            {"role": "user", "content": "How do I write a Python function?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "How do classes work?"}]))
        with pytest.raises(SemanticDriftDetected):
            module.pre_check(
                make_ctx([
                    *msgs,
                    {
                        "role": "user",
                        "content": "Tell me about Italian pasta recipes and wine pairings.",
                    },
                ])
            )

    def test_real_backend_no_false_positive_on_topic(self):
        module = SemanticDriftModule(
            on_detect="block",
            drift_threshold=0.25,
            min_turns=3,
            window_size=2,
        )
        msgs = [
            {"role": "system", "content": "You are a Python programming assistant."},
            {"role": "user", "content": "How do I write a Python function?"},
        ]
        module.pre_check(make_ctx(msgs))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "What about Python classes?"}]))
        module.pre_check(make_ctx([*msgs, {"role": "user", "content": "How do Python decorators work?"}]))
