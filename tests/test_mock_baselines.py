"""Tests for MockBaselineScored and MockBaselineFailing (SPEC v4 D14, D55)."""

import json

import pytest

from benchmarks.baselines.mock import MockBaselineFailing, MockBaselineScored


class TestMockBaselineScored:
    def test_returns_scripted_score(self):
        b = MockBaselineScored(scripted_scores={"unsafe text": 0.9, "safe text": 0.1})
        assert b.score("unsafe text") == 0.9
        assert b.score("safe text") == 0.1

    def test_falls_back_to_default_score(self):
        b = MockBaselineScored(scripted_scores={"known": 0.8}, default_score=0.2)
        assert b.score("unknown") == 0.2

    def test_check_uses_default_threshold(self):
        b = MockBaselineScored(scripted_scores={"hot": 0.7, "cold": 0.3})
        assert b.check("hot") is True
        assert b.check("cold") is False

    def test_empty_scripted_scores(self):
        b = MockBaselineScored()
        assert b.score("anything") == 0.0
        assert b.check("anything") is False

    def test_is_available(self):
        assert MockBaselineScored().is_available() is True


class TestMockBaselineFailing:
    @pytest.mark.parametrize(
        "mode,exc_type,msg_fragment",
        [
            ("timeout", TimeoutError, "timeout"),
            ("connection_refused", ConnectionError, "connection"),
            ("quota_exceeded", RuntimeError, "quota"),
            ("malformed_logprobs", ValueError, "logprobs"),
        ],
    )
    def test_raises_configured_failure(self, mode, exc_type, msg_fragment):
        b = MockBaselineFailing(failure_mode=mode)
        with pytest.raises(exc_type, match=msg_fragment):
            b.score("any text")

    def test_json_error_mode_raises_json_decode_error(self):
        b = MockBaselineFailing(failure_mode="json_error")
        with pytest.raises(json.JSONDecodeError):
            b.score("any text")

    def test_unknown_mode_raises_runtime_error(self):
        b = MockBaselineFailing(failure_mode="bogus")  # type: ignore
        with pytest.raises(RuntimeError, match="unknown mock failure"):
            b.score("any text")

    def test_check_also_surfaces_failure(self):
        b = MockBaselineFailing(failure_mode="timeout")
        with pytest.raises(TimeoutError):
            b.check("any text")
