"""Single daemon sweeper thread that force-closes stale traces.

Per S-27: poll every `max(1, max_trace_age_seconds / 10)` seconds; iterate the
active-trace registry; close traces whose age exceeds the configured limit.
Single thread regardless of trace count — no GIL/RLIMIT issues at scale.

Lazy-started at the first explain-enabled request via start_watchdog(); idempotent.
Tests can use stop_watchdog() to teardown cleanly.
"""

import threading
import time
from typing import Optional

_watchdog_thread: Optional[threading.Thread] = None
_watchdog_stop = threading.Event()
_watchdog_lock = threading.Lock()


def start_watchdog(get_active_traces, max_age_seconds: int) -> None:
    """Start the sweeper thread if not already running. Idempotent."""
    global _watchdog_thread
    with _watchdog_lock:
        if _watchdog_thread is not None and _watchdog_thread.is_alive():
            return
        _watchdog_stop.clear()
        poll_interval = max(1, max_age_seconds // 10)
        _watchdog_thread = threading.Thread(
            target=_sweep_loop,
            args=(get_active_traces, max_age_seconds, poll_interval),
            name="agentarmor-explain-watchdog",
            daemon=True,
        )
        _watchdog_thread.start()


def stop_watchdog(timeout: float = 1.0) -> None:
    """Signal the sweeper to stop and wait for it. Idempotent."""
    global _watchdog_thread
    with _watchdog_lock:
        if _watchdog_thread is None:
            return
        _watchdog_stop.set()
        _watchdog_thread.join(timeout=timeout)
        _watchdog_thread = None


def is_running() -> bool:
    return _watchdog_thread is not None and _watchdog_thread.is_alive()


def _sweep_loop(get_active_traces, max_age_seconds: int, poll_interval: int) -> None:
    max_age_ns = max_age_seconds * 1_000_000_000
    while not _watchdog_stop.is_set():
        try:
            now_ns = time.time_ns()
            for builder in list(get_active_traces()):
                if builder.ended_at_ns is not None:
                    continue
                if (now_ns - builder.started_at_ns) > max_age_ns:
                    try:
                        builder.close("timeout")
                    except Exception:
                        # Defensive: never let one builder's close error stop the sweep
                        pass
        except Exception:
            # Never crash the daemon thread
            pass
        if _watchdog_stop.wait(timeout=poll_interval):
            break
