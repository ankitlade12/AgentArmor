"""Perspective API baseline (SPEC v4 D1, D34).

Exposes ``score(text) -> float`` returning the TOXICITY summary float directly;
``check()`` is the default thresholded view. Endpoint and attribute are read
from config when provided, class defaults otherwise.
"""

import json
import os
import urllib.request
from typing import Any, Dict, Optional

from .base import BaselineChecker, register_baseline

_DEFAULT_ENDPOINT = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
_DEFAULT_ATTRIBUTE = "TOXICITY"


@register_baseline
class PerspectiveBaseline(BaselineChecker):
    name = "perspective"
    description = "Perspective API (Google Jigsaw toxicity scorer)"
    requires_api_key = "PERSPECTIVE_API_KEY"
    default_threshold = 0.5

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._endpoint = cfg.get("endpoint", _DEFAULT_ENDPOINT)
        self._attribute = cfg.get("attribute", _DEFAULT_ATTRIBUTE)
        threshold = cfg.get("default_threshold")
        if threshold is not None:
            self.default_threshold = float(threshold)

    def score(self, text: str) -> float:
        api_key = os.environ.get(self.requires_api_key, "")
        url = f"{self._endpoint}?key={api_key}"
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {self._attribute: {}},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
        return float(
            result["attributeScores"][self._attribute]["summaryScore"]["value"]
        )
