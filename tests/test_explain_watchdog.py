"""Tests for agentarmor._watchdog (single sweeper thread per S-27)."""

import time

import pytest

from agentarmor import _watchdog
from agentarmor import trace as trace_module
from agentarmor.trace import _TraceBuilder, get_active_traces


@pytest.fixture(autouse=True)
def cleanup_watchdog():
    yield
    _watchdog.stop_watchdog()
    # Drain any registered builders so test isolation holds
    with trace_module._registry_lock:
        trace_module._active_traces_registry.clear()


def test_start_watchdog_is_idempotent():
    _watchdog.start_watchdog(get_active_traces, max_age_seconds=10)
    _watchdog.start_watchdog(get_active_traces, max_age_seconds=10)
    assert _watchdog.is_running()


def test_stop_watchdog_when_not_running_is_idempotent():
    _watchdog.stop_watchdog()
    _watchdog.stop_watchdog()  # no exception
    assert not _watchdog.is_running()


def test_watchdog_evicts_stale_trace():
    """With max_age=1s and poll=1s, a trace older than 1s should be force-closed."""
    builder = _TraceBuilder()
    # Age the builder by rewinding started_at
    builder.started_at_ns -= 5_000_000_000  # 5 seconds ago
    assert builder.ended_at_ns is None

    _watchdog.start_watchdog(get_active_traces, max_age_seconds=1)
    # Sweep should fire within poll interval (1s); give 3s margin
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if builder.ended_at_ns is not None:
            break
        time.sleep(0.1)
    assert builder.ended_at_ns is not None
    assert builder.closed_reason == "timeout"


def test_watchdog_does_not_evict_fresh_trace():
    builder = _TraceBuilder()
    _watchdog.start_watchdog(get_active_traces, max_age_seconds=10)
    time.sleep(1.5)  # exceed one poll interval but well within max_age
    assert builder.ended_at_ns is None


def test_active_traces_registry_tracks_open_builders():
    builder = _TraceBuilder()
    assert builder in get_active_traces()
    builder.close("after_response")
    # WeakSet drops on close (we discard explicitly in close)
    assert builder not in get_active_traces()
