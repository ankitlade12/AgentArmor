"""Mock baselines for CI smoke tests and snapshot fixtures (SPEC v4 D14, D55).

``MockBaselineScored`` — happy path; returns scripted scores per text.
``MockBaselineFailing`` — simulates real-world failure modes (timeout, JSON error,
connection refused, quota exceeded, malformed logprobs). Used by the runner's
D35 "blank cell + note" path tests.
"""

import json
from typing import Dict, Literal

from .base import BaselineChecker


class MockBaselineScored(BaselineChecker):
    """Returns scripted scores per text; falls back to ``default_score`` when absent."""

    name = "mock_scored"
    description = "Mock baseline returning scripted scores."
    requires_api_key = None
    default_threshold = 0.5

    def __init__(
        self,
        scripted_scores: Dict[str, float] | None = None,
        default_score: float = 0.0,
    ):
        self._scores = dict(scripted_scores or {})
        self._default = default_score

    def score(self, text: str) -> float:
        return self._scores.get(text, self._default)


FailureMode = Literal[
    "timeout",
    "json_error",
    "connection_refused",
    "quota_exceeded",
    "malformed_logprobs",
]


class MockBaselineFailing(BaselineChecker):
    """Raises a configured failure on every ``score()``.

    Failure modes match the classes of real failures the runner must survive
    per SPEC v4 D35 (blank cell + note, never paper fallback).
    """

    name = "mock_failing"
    description = "Mock baseline that always fails with a configured mode."
    requires_api_key = None
    default_threshold = 0.5

    def __init__(self, failure_mode: FailureMode = "timeout"):
        self._mode = failure_mode

    def score(self, text: str) -> float:
        if self._mode == "timeout":
            raise TimeoutError("mock timeout")
        if self._mode == "json_error":
            raise json.JSONDecodeError("mock JSON error", doc="", pos=0)
        if self._mode == "connection_refused":
            raise ConnectionError("mock connection refused")
        if self._mode == "quota_exceeded":
            raise RuntimeError("quota exceeded (mock)")
        if self._mode == "malformed_logprobs":
            raise ValueError("logprobs shape malformed (mock)")
        raise RuntimeError(f"unknown mock failure mode: {self._mode}")
