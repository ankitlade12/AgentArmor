"""Tests for the rewritten Perspective baseline (SPEC v4 D1, D34)."""

import json
from unittest import mock

import pytest

from benchmarks.baselines.perspective_api import PerspectiveBaseline


def _mock_response(score: float):
    body = {
        "attributeScores": {
            "TOXICITY": {"summaryScore": {"value": score}}
        }
    }

    class _Resp:
        def read(self):
            return json.dumps(body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Resp()


class TestPerspectiveScore:
    def test_defaults(self):
        p = PerspectiveBaseline()
        assert p.default_threshold == 0.5
        assert p.score_emitting is True

    def test_config_overrides_threshold_and_endpoint(self):
        p = PerspectiveBaseline(
            config={
                "endpoint": "https://mirror.example/v1/analyze",
                "attribute": "INSULT",
                "default_threshold": 0.7,
            }
        )
        assert p._endpoint.startswith("https://mirror.example")
        assert p._attribute == "INSULT"
        assert p.default_threshold == 0.7

    def test_score_returns_toxicity_float(self, monkeypatch):
        monkeypatch.setenv("PERSPECTIVE_API_KEY", "fake-key")
        p = PerspectiveBaseline()

        with mock.patch(
            "benchmarks.baselines.perspective_api.urllib.request.urlopen",
            return_value=_mock_response(0.82),
        ):
            assert p.score("toxic text") == 0.82

    def test_check_uses_default_threshold(self, monkeypatch):
        monkeypatch.setenv("PERSPECTIVE_API_KEY", "fake-key")
        p = PerspectiveBaseline()

        with mock.patch(
            "benchmarks.baselines.perspective_api.urllib.request.urlopen",
            return_value=_mock_response(0.82),
        ):
            assert p.check("toxic text") is True

        with mock.patch(
            "benchmarks.baselines.perspective_api.urllib.request.urlopen",
            return_value=_mock_response(0.1),
        ):
            assert p.check("benign text") is False

    def test_no_deprecation_warning_on_import(self):
        """Perspective now implements score() explicitly; no bridge should fire."""
        import importlib
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Reimport the module to trigger __init_subclass__ afresh.
            from benchmarks.baselines import perspective_api
            importlib.reload(perspective_api)

        perspective_deprecations = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "PerspectiveBaseline" in str(w.message)
        ]
        assert perspective_deprecations == []
