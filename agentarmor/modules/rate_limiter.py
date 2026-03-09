import threading
import time
from collections import deque

from ..exceptions import RateLimitExceeded
from ..hooks import RequestContext


class RateLimiterModule:
    """Sliding-window rate limiter for LLM API calls.

    Thread-safe and async-safe: a reentrant lock is held during the
    check-and-append operation so concurrent callers cannot both slip
    through the limit simultaneously.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0):
        """
        Initializes the rate limiter.

        Args:
            limit: Maximum number of calls allowed within the time window.
                   Must be a positive integer.
            window_seconds: Duration of the sliding window in seconds (default: 60).
        """
        if limit <= 0:
            raise ValueError(f"rate_limit count must be a positive integer, got {limit}.")
        self.limit = limit
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = threading.Lock()
        self.total_blocked = 0

    def _evict_expired(self, now: float) -> None:
        """Removes timestamps outside the current sliding window. Call with lock held."""
        while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
            self._timestamps.popleft()

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Before-request hook that enforces the rate limit."""
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            if len(self._timestamps) >= self.limit:
                self.total_blocked += 1
                retry_in = self._timestamps[0] + self.window_seconds - now
                raise RateLimitExceeded(
                    f"Rate limit exceeded: {self.limit} calls per "
                    f"{self.window_seconds}s window. "
                    f"Try again in {retry_in:.1f}s."
                )
            self._timestamps.append(now)
        return ctx

    @property
    def calls_in_window(self) -> int:
        """Returns the number of calls currently within the active window."""
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            return len(self._timestamps)

    def report(self) -> dict:
        return {
            "limit": self.limit,
            "window_seconds": self.window_seconds,
            "calls_in_window": self.calls_in_window,
            "total_blocked": self.total_blocked,
        }
