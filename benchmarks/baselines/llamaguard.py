"""LlamaGuard baseline -- Meta's safety classifier via Together API."""

import json
import os
import urllib.request

from .base import BaselineChecker, register_baseline


@register_baseline
class LlamaGuardBaseline(BaselineChecker):
    name = "llamaguard"
    description = "LlamaGuard 3 via Together API"
    requires_api_key = "TOGETHER_API_KEY"

    def check(self, text: str) -> bool:
        api_key = os.environ.get("TOGETHER_API_KEY", "")
        url = "https://api.together.xyz/v1/chat/completions"

        payload = {
            "model": "meta-llama/Meta-Llama-Guard-3-8B",
            "messages": [{"role": "user", "content": text}],
            "max_tokens": 100,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        response_text = result["choices"][0]["message"]["content"].strip().lower()
        # LlamaGuard returns "safe" or "unsafe" + category
        return "unsafe" in response_text
