"""
Canary Token Injection — injects invisible canary tokens into system
prompts and detects prompt leakage when they appear in the output.
"""

import uuid
import warnings
from typing import Optional

from ..exceptions import CanaryLeakDetected
from ..hooks import RequestContext, ResponseContext


class CanaryModule:
    """Pre-request hook that injects canary tokens, post-response hook that detects leaks.

    The canary token is injected as a neutral-looking metadata field that LLMs
    do not interpret as HTML or special syntax. It uses a random UUID-based string
    embedded inside a structured tag that is opaque to the model.

    Note: pre_check modifies ctx.messages in place. If you reuse the same messages
    list across multiple calls, canary tokens will accumulate. Use a fresh list per call.
    """

    def __init__(self, on_leak: str = "warn", canary_word: Optional[str] = None):
        if on_leak not in ("warn", "block"):
            raise ValueError(
                f"on_leak must be 'warn' or 'block', got {on_leak!r}."
            )
        # Use an opaque, non-HTML format — not a comment syntax the model knows about.
        # Example: [_sys:a3f9c1e2b7d4]
        self.canary = canary_word or f"[_sys:{uuid.uuid4().hex[:12]}]"
        self.on_leak = on_leak
        self.injections = 0
        self.leaks = 0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Injects canary token into the system message."""
        canary_tag = f"\n{self.canary}"

        # Find existing system message
        for msg in ctx.messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    msg["content"] = content + canary_tag
                self.injections += 1
                return ctx

        # No system message — prepend one with the canary
        ctx.messages.insert(0, {"role": "system", "content": canary_tag.lstrip()})
        self.injections += 1
        return ctx

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Checks if the canary token leaked into the LLM output."""
        if self.canary in ctx.text:
            self.leaks += 1
            if self.on_leak == "block":
                raise CanaryLeakDetected(
                    "Canary token detected in LLM output — system prompt has been leaked."
                )
            else:
                warnings.warn(
                    "[AgentArmor] Canary token detected in output. "
                    "Possible system prompt leak.",
                    stacklevel=2,
                )
        return ctx

    def report(self) -> dict:
        return {
            "canary": f"{self.canary[:8]}…",
            "injections": self.injections,
            "leaks": self.leaks,
        }
