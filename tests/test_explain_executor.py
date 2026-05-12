"""Tests for agentarmor._run_in_executor (S-13 + S-31)."""

import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import pytest

from agentarmor._run_in_executor import run_in_executor
from agentarmor.trace import ExplainModeWarning, _active_trace, _TraceBuilder


def _read_active_trace_id():
    builder = _active_trace.get()
    return builder.context_id if builder is not None else None


def test_run_in_executor_propagates_context_to_thread():
    builder = _TraceBuilder()
    token = _active_trace.set(builder)
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = run_in_executor(ex, _read_active_trace_id)
            result = future.result(timeout=5)
        assert result == builder.context_id
    finally:
        _active_trace.reset(token)
        builder.close("after_response")


def test_run_in_executor_no_context_returns_none():
    """No active trace in caller -> worker also sees None."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = run_in_executor(ex, _read_active_trace_id)
        result = future.result(timeout=5)
    assert result is None


def _identity(x):
    return x


def test_run_in_executor_rejects_process_pool_with_warning():
    try:
        executor = ProcessPoolExecutor(max_workers=1)
    except (NotImplementedError, PermissionError) as exc:
        pytest.skip(f"ProcessPoolExecutor unavailable in this environment: {exc}")

    with executor as ex:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            future = run_in_executor(ex, _identity, 42)
            result = future.result(timeout=15)
        assert result == 42
        explain_warnings = [w for w in caught if issubclass(w.category, ExplainModeWarning)]
        assert len(explain_warnings) == 1
        assert "ProcessPoolExecutor" in str(explain_warnings[0].message)


def test_run_in_executor_threadpool_no_warning():
    with ThreadPoolExecutor(max_workers=1) as ex:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            future = run_in_executor(ex, _identity, 1)
            future.result(timeout=5)
        explain_warnings = [w for w in caught if issubclass(w.category, ExplainModeWarning)]
        assert len(explain_warnings) == 0
