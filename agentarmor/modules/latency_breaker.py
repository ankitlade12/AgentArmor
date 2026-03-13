"""
Latency Circuit Breaker — monitors API response times and trips a circuit
breaker when latency consistently exceeds a threshold.
"""

import threading
from collections import deque
from typing import Optional

from ..exceptions import LatencyThresholdExceeded
from ..hooks import ResponseContext


class LatencyBreakerModule:
    """Post-response hook that monitors latency and trips after consecutive breaches."""

    def __init__(
        self,
        threshold_ms: float = 5000.0,
        consecutive_limit: int = 3,
        on_breach: str = "warn",
        window_size: int = 20,
    ):
        """
        Args:
            threshold_ms: Latency threshold in milliseconds.
            consecutive_limit: Number of consecutive breaches before the circuit trips.
            on_breach: Action when circuit trips — 'warn' or 'block'.
            window_size: Number of recent latencies to keep for reporting.
        """
        if threshold_ms <= 0:
            raise ValueError("threshold_ms must be positive.")
        if consecutive_limit < 1:
            raise ValueError("consecutive_limit must be at least 1.")
        if on_breach not in ("warn", "block"):
            raise ValueError(f"on_breach must be 'warn' or 'block', got {on_breach!r}.")

        self.threshold_ms = threshold_ms
        self.consecutive_limit = consecutive_limit
        self.on_breach = on_breach
        self.window_size = window_size

        self._lock = threading.Lock()
        self._consecutive_breaches = 0
        self._recent_latencies: deque = deque(maxlen=window_size)
        self.total_breaches = 0
        self.total_trips = 0
        self.total_calls = 0
        self.tripped = False

    def post_check(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook that checks latency against the threshold."""
        latency = ctx.latency_ms or 0.0
        self.total_calls += 1

        with self._lock:
            self._recent_latencies.append(latency)

            if latency > self.threshold_ms:
                self._consecutive_breaches += 1
                self.total_breaches += 1

                if self._consecutive_breaches >= self.consecutive_limit:
                    self.tripped = True
                    self.total_trips += 1

                    if self.on_breach == "block":
                        raise LatencyThresholdExceeded(
                            f"Latency circuit breaker tripped: "
                            f"{self._consecutive_breaches} consecutive calls exceeded "
                            f"{self.threshold_ms}ms threshold "
                            f"(last: {latency:.0f}ms)."
                        )
                    else:
                        print(
                            f"[AgentArmor] WARNING: Latency circuit breaker tripped — "
                            f"{self._consecutive_breaches} consecutive calls exceeded "
                            f"{self.threshold_ms}ms (last: {latency:.0f}ms)."
                        )
            else:
                # Reset consecutive counter on a fast response
                self._consecutive_breaches = 0
                self.tripped = False

        return ctx

    @property
    def avg_latency_ms(self) -> Optional[float]:
        """Returns the average latency of recent calls, or None if no calls yet."""
        with self._lock:
            if not self._recent_latencies:
                return None
            return sum(self._recent_latencies) / len(self._recent_latencies)

    @property
    def p95_latency_ms(self) -> Optional[float]:
        """Returns the 95th percentile latency of recent calls."""
        with self._lock:
            if not self._recent_latencies:
                return None
            sorted_latencies = sorted(self._recent_latencies)
            idx = int(len(sorted_latencies) * 0.95)
            return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def report(self) -> dict:
        avg = self.avg_latency_ms
        p95 = self.p95_latency_ms
        return {
            "threshold_ms": self.threshold_ms,
            "consecutive_limit": self.consecutive_limit,
            "total_calls": self.total_calls,
            "total_breaches": self.total_breaches,
            "total_trips": self.total_trips,
            "tripped": self.tripped,
            "avg_latency_ms": round(avg, 1) if avg else None,
            "p95_latency_ms": round(p95, 1) if p95 else None,
        }
