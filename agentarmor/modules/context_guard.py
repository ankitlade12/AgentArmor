"""
Context Window Guard — prevents wasted API calls by checking if the
message payload is likely to exceed the model's context window limit.
"""

from ..exceptions import ContextOverflow
from ..hooks import RequestContext


# Maximum context window sizes (in tokens) per model
CONTEXT_LIMITS = {
    # OpenAI
    "gpt-4.5-preview":     128_000,
    "gpt-4.5":             128_000,
    "o3-mini":             128_000,
    "gpt-4o":              128_000,
    "gpt-4o-mini":         128_000,
    "gpt-4-turbo":         128_000,
    "gpt-4":                 8_192,
    "gpt-3.5-turbo":        16_385,
    # Anthropic
    "claude-4":            200_000,
    "claude-opus-4":       200_000,
    "claude-sonnet-4-5":   200_000,
    "claude-haiku-4-5":    200_000,
    # Google
    "gemini-2.0-pro":    1_000_000,
    "gemini-2.0-flash":  1_000_000,
    "gemini-1.5-pro":    2_000_000,
    "gemini-1.5-flash":  1_000_000,
}

DEFAULT_CONTEXT_LIMIT = 8_192  # Conservative fallback


class ContextGuardModule:
    """Pre-flight check that estimates token count and blocks requests
    that are likely to exceed the model's context window."""

    def __init__(self, safety_margin: float = 0.95):
        """
        Args:
            safety_margin: Fraction of the context window to allow (default 0.95).
                           Leaves headroom for the model's response tokens.
        """
        if not 0 < safety_margin <= 1.0:
            raise ValueError("safety_margin must be between 0 (exclusive) and 1.0 (inclusive).")
        self.safety_margin = safety_margin
        self.peak_tokens = 0
        self.checks = 0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Before-request hook that estimates token usage and blocks oversized requests."""
        estimated_tokens = self._estimate_tokens(ctx.messages)
        self.checks += 1
        self.peak_tokens = max(self.peak_tokens, estimated_tokens)

        limit = self._get_limit(ctx.model)
        effective_limit = int(limit * self.safety_margin)

        if estimated_tokens > effective_limit:
            raise ContextOverflow(
                f"Estimated {estimated_tokens:,} tokens exceeds {ctx.model}'s "
                f"context window ({limit:,} tokens × {self.safety_margin} safety margin = "
                f"{effective_limit:,} effective limit)."
            )

        return ctx

    def _estimate_tokens(self, messages: list) -> int:
        """Estimates token count from messages using chars/4 heuristic."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])
        # ~4 characters per token is a widely-used approximation
        return max(1, total_chars // 4)

    def _get_limit(self, model: str) -> int:
        """Looks up the context window limit for a model."""
        model_lower = model.lower()
        for key, limit in CONTEXT_LIMITS.items():
            if key in model_lower:
                return limit
        return DEFAULT_CONTEXT_LIMIT

    def report(self) -> dict:
        return {
            "checks": self.checks,
            "peak_tokens": self.peak_tokens,
            "safety_margin": self.safety_margin,
        }
