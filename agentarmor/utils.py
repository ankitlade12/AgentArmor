"""Shared utility functions for AgentArmor modules."""

from typing import List


def estimate_tokens(messages: List[dict]) -> int:
    """
    Estimates the token count of a message list using a chars-per-token heuristic.

    Handles both plain string content and multimodal content blocks
    (list of dicts with a ``text`` key, as used by OpenAI vision and Anthropic APIs).

    Uses the widely-accepted ~4 characters per token approximation.
    Returns at least 1 to avoid division-by-zero in callers.
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total_chars += len(part["text"])
    return max(1, total_chars // 4)
