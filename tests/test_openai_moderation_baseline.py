"""Tests for OpenAI Moderation baseline with per-dataset projection (SPEC v4 D37)."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import pytest

from benchmarks.baselines.openai_moderation import OpenAIModerationBaseline


class _FakeCategoryScores:
    """Stand-in for the pydantic model OpenAI returns."""

    def __init__(self, **kwargs):
        self._data = kwargs

    def model_dump(self):
        return dict(self._data)


def _fake_response(category_scores: dict):
    return SimpleNamespace(
        results=[SimpleNamespace(category_scores=_FakeCategoryScores(**category_scores))]
    )


class TestProjection:
    def test_max_over_projection_subset(self):
        """When a projection is supplied, score is max over only those categories."""
        b = OpenAIModerationBaseline(projection=("hate", "violence"))
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response(
                        {
                            "hate": 0.7,
                            "violence": 0.3,
                            "sexual": 0.9,  # ignored — not in projection
                        }
                    )
                )
            ),
        ):
            assert b.score("text") == 0.7

    def test_no_projection_falls_back_to_max_over_all(self):
        b = OpenAIModerationBaseline(projection=None)
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response(
                        {"hate": 0.3, "violence": 0.8, "sexual": 0.1}
                    )
                )
            ),
        ):
            assert b.score("text") == 0.8

    def test_projection_with_missing_category_uses_available(self):
        """If some projected categories aren't in the response, use what is."""
        b = OpenAIModerationBaseline(projection=("hate", "missing_one", "violence"))
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response(
                        {"hate": 0.2, "violence": 0.6}
                    )
                )
            ),
        ):
            assert b.score("text") == 0.6

    def test_projection_producing_no_hits_raises(self):
        """If the projection names only categories the API didn't return → raise."""
        b = OpenAIModerationBaseline(projection=("nonexistent_a", "nonexistent_b"))
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response(
                        {"hate": 0.2, "violence": 0.6}
                    )
                )
            ),
        ):
            with pytest.raises(ValueError, match="projection"):
                b.score("text")


class TestConfigOverrides:
    def test_threshold_override_from_config(self):
        b = OpenAIModerationBaseline(config={"default_threshold": 0.75})
        assert b.default_threshold == 0.75

    def test_model_from_config(self):
        b = OpenAIModerationBaseline(config={"model": "custom-model"})
        assert b._model == "custom-model"

    def test_default_model(self):
        b = OpenAIModerationBaseline()
        assert b._model == "text-moderation-latest"


class TestCheck:
    def test_check_uses_threshold(self):
        b = OpenAIModerationBaseline(projection=("hate",))
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response({"hate": 0.7})
                )
            ),
        ):
            assert b.check("toxic") is True

        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response({"hate": 0.1})
                )
            ),
        ):
            assert b.check("benign") is False


class TestCategoryScoresShape:
    def test_accepts_model_dump_pydantic(self):
        b = OpenAIModerationBaseline(projection=("hate",))
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(
                    create=lambda **kw: _fake_response({"hate": 0.5})
                )
            ),
        ):
            b.score("t")  # doesn't raise

    def test_accepts_plain_dict(self):
        """Legacy SDKs return a plain dict."""
        from benchmarks.baselines.openai_moderation import OpenAIModerationBaseline
        b = OpenAIModerationBaseline(projection=("hate",))
        response = SimpleNamespace(
            results=[SimpleNamespace(category_scores={"hate": 0.4})]
        )
        with mock.patch.object(
            b,
            "_get_client",
            return_value=SimpleNamespace(
                moderations=SimpleNamespace(create=lambda **kw: response)
            ),
        ):
            assert b.score("t") == 0.4


class TestNoDeprecationWarning:
    def test_openai_moderation_no_longer_bridged(self):
        """After the rewrite, importing openai_moderation shouldn't emit the ABC bridge warning."""
        import importlib
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from benchmarks.baselines import openai_moderation
            importlib.reload(openai_moderation)

        moderation_deprecations = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "OpenAIModerationBaseline" in str(w.message)
        ]
        assert moderation_deprecations == []
