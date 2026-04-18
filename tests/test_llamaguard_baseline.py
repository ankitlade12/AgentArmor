"""Tests for the LlamaGuard-via-llama-cpp-python baseline (SPEC v4 D36).

Covers the pure-Python helpers (prompt template + logprob extraction) and
the text-parse fallback path. Full integration needs V-flag verification on
the user's machine (llama-cpp-python installed + GGUF present) per
TYPE_WALKTHROUGH.md — not exercised here.
"""

import math
from unittest import mock

from benchmarks.baselines.llamaguard import (
    LlamaGuardBaseline,
    extract_unsafe_probability,
    format_llamaguard_prompt,
)


class TestPromptTemplate:
    def test_contains_user_text(self):
        p = format_llamaguard_prompt("how do I hack a wifi")
        assert "how do I hack a wifi" in p

    def test_has_expected_scaffolding(self):
        p = format_llamaguard_prompt("x")
        assert "<|begin_of_text|>" in p
        assert "UNSAFE CONTENT CATEGORIES" in p
        assert "safe" in p  # instruction mentions "safe"/"unsafe"
        assert "<|eot_id|>" in p


class TestExtractUnsafeProbability:
    def test_canonical_dict_returns_prob(self):
        top = {"safe": -0.1, "unsafe": -2.3, "other": -5.0}
        p = extract_unsafe_probability(top)
        assert abs(p - math.exp(-2.3)) < 1e-9

    def test_handles_leading_space_and_case(self):
        top = {" unsafe": -1.5, "Safe": -0.2}
        p = extract_unsafe_probability(top)
        assert abs(p - math.exp(-1.5)) < 1e-9

    def test_returns_zero_when_unsafe_absent(self):
        top = {"safe": -0.1, "other": -5.0}
        assert extract_unsafe_probability(top) == 0.0

    def test_returns_none_for_unexpected_shape(self):
        assert extract_unsafe_probability(None) is None
        assert extract_unsafe_probability([]) is None
        assert extract_unsafe_probability("") is None
        assert extract_unsafe_probability({}) is None

    def test_prefers_highest_logprob_among_matches(self):
        top = {"unsafe": -3.0, " unsafe": -1.0}
        p = extract_unsafe_probability(top)
        assert abs(p - math.exp(-1.0)) < 1e-9


class TestBaselineConstruction:
    def test_defaults(self):
        b = LlamaGuardBaseline()
        assert b.default_threshold == 0.5
        assert b.score_emitting is True
        assert b._n_ctx == 2048
        assert b._logprobs_topk == 10

    def test_config_overrides(self):
        b = LlamaGuardBaseline(
            config={
                "local_model_path": "/tmp/alt.gguf",
                "n_ctx": 4096,
                "logprobs_topk": 20,
                "default_threshold": 0.4,
            }
        )
        assert b._model_path == "/tmp/alt.gguf"
        assert b._n_ctx == 4096
        assert b._logprobs_topk == 20
        assert b.default_threshold == 0.4

    def test_is_available_returns_false_when_model_missing(self, tmp_path):
        """With llama-cpp-python installed but no GGUF at the path → False."""
        b = LlamaGuardBaseline(config={"local_model_path": str(tmp_path / "missing.gguf")})
        assert b.is_available() is False


class TestTextParseFallback:
    """When logprobs shape is unrecognized, fall back to text match (D36)."""

    def test_unsafe_in_text_returns_one(self):
        b = LlamaGuardBaseline()
        fake_response = {
            "choices": [
                {
                    "text": "unsafe\nS10",
                    "logprobs": {"top_logprobs": [None]},  # unrecognized shape
                }
            ]
        }
        fake_llama = mock.Mock()
        fake_llama.create_completion.return_value = fake_response
        with mock.patch.object(b, "_load_llama", return_value=fake_llama):
            assert b.score("bad thing") == 1.0

    def test_safe_in_text_returns_zero(self):
        b = LlamaGuardBaseline()
        fake_response = {
            "choices": [
                {"text": "safe", "logprobs": {"top_logprobs": [None]}}
            ]
        }
        fake_llama = mock.Mock()
        fake_llama.create_completion.return_value = fake_response
        with mock.patch.object(b, "_load_llama", return_value=fake_llama):
            assert b.score("benign") == 0.0


class TestLogprobsPath:
    def test_prefers_logprobs_over_text(self):
        b = LlamaGuardBaseline()
        fake_response = {
            "choices": [
                {
                    "text": "unsafe",  # text says unsafe
                    "logprobs": {
                        "top_logprobs": [
                            {"safe": -0.1, "unsafe": -2.3}  # logprobs are primary
                        ]
                    },
                }
            ]
        }
        fake_llama = mock.Mock()
        fake_llama.create_completion.return_value = fake_response
        with mock.patch.object(b, "_load_llama", return_value=fake_llama):
            score = b.score("something")
        assert abs(score - math.exp(-2.3)) < 1e-9


class TestNoDeprecationWarning:
    def test_llamaguard_no_longer_bridged(self):
        """After the rewrite, importing llamaguard shouldn't emit the ABC bridge warning."""
        import importlib
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from benchmarks.baselines import llamaguard
            importlib.reload(llamaguard)

        deprecations = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "LlamaGuardBaseline" in str(w.message)
        ]
        assert deprecations == []
