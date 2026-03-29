"""OpenAI Moderation API baseline -- free, no extra API key needed."""

import os

from .base import BaselineChecker, register_baseline


@register_baseline
class OpenAIModerationBaseline(BaselineChecker):
    name = "openai_moderation"
    description = "OpenAI Moderation API (free endpoint)"
    requires_api_key = "OPENAI_API_KEY"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI()
        return self._client

    def check(self, text: str) -> bool:
        client = self._get_client()
        response = client.moderations.create(input=text)
        return response.results[0].flagged
