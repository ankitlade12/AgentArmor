"""OpenAI Moderation baseline with per-dataset category projection
(SPEC v4 D1, D5-superseded-by-D37).

``score(text)`` reduces the API's per-category floats to a single scalar via
``max`` over a projection list. The runner selects the projection per cell
from ``benchmarks.taxonomy_applicability.get_projection``. Without a
projection, ``score`` falls back to max over all categories — present as a
transitional default; the rubric-driven path is what the runner exercises.
"""

from typing import Any, Dict, Optional, Tuple

from .base import BaselineChecker, register_baseline


@register_baseline
class OpenAIModerationBaseline(BaselineChecker):
    name = "openai_moderation"
    description = "OpenAI Moderation API with per-dataset category projection"
    requires_api_key = "OPENAI_API_KEY"
    default_threshold = 0.5

    def __init__(
        self,
        projection: Optional[Tuple[str, ...]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        cfg = config or {}
        self._projection = projection
        self._model = cfg.get("model", "omni-moderation-latest")
        threshold = cfg.get("default_threshold")
        if threshold is not None:
            self.default_threshold = float(threshold)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI()
        return self._client

    def _category_scores_dict(self, category_scores_obj: Any) -> Dict[str, float]:
        """Extract a dict from the pydantic model OpenAI returns.

        Newer SDK: ``category_scores.model_dump()``; older may expose
        ``dict()``; fall back to ``__dict__`` attributes.
        """
        if hasattr(category_scores_obj, "model_dump"):
            return dict(category_scores_obj.model_dump())
        if hasattr(category_scores_obj, "dict"):
            return dict(category_scores_obj.dict())  # type: ignore[attr-defined]
        if hasattr(category_scores_obj, "__dict__"):
            return {
                k: v
                for k, v in category_scores_obj.__dict__.items()
                if isinstance(v, (int, float))
            }
        if isinstance(category_scores_obj, dict):
            return category_scores_obj
        raise TypeError(
            f"Unsupported category_scores shape: {type(category_scores_obj)!r}"
        )

    def score(self, text: str) -> float:
        client = self._get_client()
        response = client.moderations.create(input=text, model=self._model)
        scores = self._category_scores_dict(response.results[0].category_scores)
        values = [v for v in scores.values() if isinstance(v, (int, float))]
        if self._projection:
            projected = [
                scores[cat] for cat in self._projection if cat in scores
            ]
            if not projected:
                # Projection named only categories the API didn't return.
                raise ValueError(
                    f"OpenAI Moderation projection {self._projection} produced no "
                    f"scores; available categories: {sorted(scores.keys())}"
                )
            return float(max(projected))
        if not values:
            raise ValueError("OpenAI Moderation returned no numeric category scores")
        return float(max(values))
