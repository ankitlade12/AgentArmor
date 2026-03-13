"""
Semantic Dedup (Replay Shield) — content-aware duplicate detection that
prevents wasted API spend on identical or repeated prompts.
"""

import hashlib
import json
import threading
import warnings
from collections import OrderedDict
from typing import Optional

from ..exceptions import DuplicateRequest
from ..hooks import RequestContext


class DedupModule:
    """Pre-request hook that detects duplicate prompts and blocks or warns."""

    def __init__(
        self,
        max_cache: int = 256,
        on_duplicate: str = "block",
        ttl_calls: Optional[int] = None,
    ):
        """
        Args:
            max_cache: Maximum number of prompt hashes to remember (LRU eviction).
            on_duplicate: Action on duplicate — 'block' (raise DuplicateRequest)
                          or 'warn' (print warning but allow).
            ttl_calls: If set, a prompt hash is only considered a duplicate if
                       it was seen within the last N *calls* (not seconds).
                       None means no expiry.
        """
        if on_duplicate not in ("block", "warn"):
            raise ValueError(
                f"on_duplicate must be 'block' or 'warn', got {on_duplicate!r}."
            )
        if max_cache < 1:
            raise ValueError("max_cache must be at least 1.")

        self.max_cache = max_cache
        self.on_duplicate = on_duplicate
        self.ttl_calls = ttl_calls

        self._cache: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()
        self._call_counter = 0
        self.duplicates_detected = 0
        self.total_checked = 0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Before-request hook that checks for duplicate prompts."""
        prompt_hash = self._hash_messages(ctx.messages, ctx.model)
        self.total_checked += 1

        with self._lock:
            self._call_counter += 1

            if prompt_hash in self._cache:
                seen_at = self._cache[prompt_hash]

                # Check TTL if configured
                if self.ttl_calls and (self._call_counter - seen_at) > self.ttl_calls:
                    # Expired — treat as new
                    self._cache[prompt_hash] = self._call_counter
                    self._cache.move_to_end(prompt_hash)
                    return ctx

                self.duplicates_detected += 1

                if self.on_duplicate == "block":
                    raise DuplicateRequest(
                        f"Duplicate prompt detected (hash: {prompt_hash[:12]}…). "
                        f"Call blocked to save API spend."
                    )
                else:
                    warnings.warn(
                        f"[AgentArmor] Duplicate prompt detected "
                        f"(hash: {prompt_hash[:12]}…).",
                        stacklevel=2,
                    )

            # Record this prompt
            self._cache[prompt_hash] = self._call_counter
            self._cache.move_to_end(prompt_hash)

            # Evict oldest if over capacity
            while len(self._cache) > self.max_cache:
                self._cache.popitem(last=False)

        return ctx

    @staticmethod
    def _hash_messages(messages: list, model: str) -> str:
        """Creates a deterministic hash of the message payload + model."""
        payload = json.dumps(
            {"model": model, "messages": messages},
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def report(self) -> dict:
        return {
            "total_checked": self.total_checked,
            "duplicates_detected": self.duplicates_detected,
            "cache_size": len(self._cache),
            "max_cache": self.max_cache,
        }
