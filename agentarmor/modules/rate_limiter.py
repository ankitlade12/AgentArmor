import time
from collections import deque
from ..exceptions import RateLimitExceeded
from ..hooks import RequestContext


class RateLimiterModule:
    """Sliding-window rate limiter for LLM API calls."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        """
        Initializes the rate limiter.

        Args:
            limit: Maximum number of calls allowed within the time window.
            window_seconds: Duration of the sliding window in seconds (default: 60).
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self.total_blocked = 0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Before-request hook that enforces the rate limit."""
        now = time.monotonic()

        # Evict expired timestamps outside the sliding window
        while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.limit:
            self.total_blocked += 1
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.limit} calls per {self.window_seconds}s window. "
                f"Try again in {self._timestamps[0] + self.window_seconds - now:.1f}s."
            )

        self._timestamps.append(now)
        return ctx

    @property
    def calls_in_window(self) -> int:
        """Returns the number of calls currently within the active window."""
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
            self._timestamps.popleft()
        return len(self._timestamps)

    def report(self) -> dict:
        return {
            "limit": self.limit,
            "window_seconds": self.window_seconds,
            "calls_in_window": self.calls_in_window,
            "total_blocked": self.total_blocked,
        }
