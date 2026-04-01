"""Perspective API baseline -- Google's toxicity scorer."""

import json
import os
import urllib.request

from .base import BaselineChecker, register_baseline

PERSPECTIVE_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"


@register_baseline
class PerspectiveBaseline(BaselineChecker):
    name = "perspective"
    description = "Perspective API (Google Jigsaw toxicity scorer)"
    requires_api_key = "PERSPECTIVE_API_KEY"

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def check(self, text: str) -> bool:
        api_key = os.environ.get("PERSPECTIVE_API_KEY", "")
        url = f"{PERSPECTIVE_URL}?key={api_key}"

        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {"TOXICITY": {}},
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
        score = result["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        return score >= self.threshold
