"""Unit tests for agentarmor.trace standalone components.

These cover what's testable without the HookRegistry instrumentation
or core.py wiring (which land in later commits). Lifecycle and integration
tests live in tests/test_explain_lifecycle.py (commit 8).
"""

import datetime
import decimal
import json
import warnings
from types import MappingProxyType

import pytest

from agentarmor import trace as trace_module
from agentarmor.trace import (
    ExplainModeWarning,
    Trace,
    TraceEvent,
    TraceJSONEncoder,
    _freeze,
    _normalize_detail,
    _serialize_safe,
    _TraceBuilder,
    clear_last_trace,
    find_trace,
    last_trace,
    last_trace_status,
    record_decision,
)


# ---------------------------------------------------------------------------
# _serialize_safe — type coercion (S-4) + cycle/depth guard (S-8)
# ---------------------------------------------------------------------------


def test_serialize_safe_passes_primitives_through():
    assert _serialize_safe("hello") == "hello"
    assert _serialize_safe(42) == 42
    assert _serialize_safe(3.14) == 3.14
    assert _serialize_safe(True) is True
    assert _serialize_safe(None) is None


def test_serialize_safe_coerces_tuple_to_list():
    assert _serialize_safe((1, 2, 3)) == [1, 2, 3]


def test_serialize_safe_coerces_datetime_to_isoformat():
    dt = datetime.datetime(2026, 4, 14, 10, 30, 0)
    assert _serialize_safe(dt) == "2026-04-14T10:30:00"
    d = datetime.date(2026, 4, 14)
    assert _serialize_safe(d) == "2026-04-14"


def test_serialize_safe_coerces_decimal_to_str():
    assert _serialize_safe(decimal.Decimal("0.92")) == "0.92"


def test_serialize_safe_coerces_set_to_sorted_list():
    assert _serialize_safe({3, 1, 2}) == [1, 2, 3]


def test_serialize_safe_coerces_bytes_to_utf8():
    assert _serialize_safe(b"hello") == "hello"
    assert _serialize_safe(b"\xff\xfe") == "\ufffd\ufffd"


def test_serialize_safe_coerces_unknown_via_repr():
    obj = object()
    out = _serialize_safe(obj)
    assert isinstance(out, str)
    assert "object" in out


def test_serialize_safe_handles_dict_with_non_string_keys():
    out = _serialize_safe({1: "a", 2: "b"})
    assert out == {"1": "a", "2": "b"}


def test_serialize_safe_recurses_dict():
    out = _serialize_safe({"x": (1, 2, 3), "y": {"z": decimal.Decimal("0.5")}})
    assert out == {"x": [1, 2, 3], "y": {"z": "0.5"}}


def test_serialize_safe_handles_self_referential_dict():
    d = {"x": 1}
    d["self"] = d
    out = _serialize_safe(d)
    assert out["x"] == 1
    assert "cycle" in out["self"]


def test_serialize_safe_caps_recursion_depth():
    # Build a 50-deep nested dict
    deep = current = {}
    for i in range(50):
        current["next"] = {}
        current = current["next"]
    out = _serialize_safe(deep)
    # Walk down the result and confirm we hit the depth-cap marker
    cur = out
    for _ in range(40):
        if isinstance(cur, dict) and "next" in cur:
            cur = cur["next"]
        else:
            break
    assert isinstance(cur, str) and "max-depth" in cur


# ---------------------------------------------------------------------------
# _normalize_detail
# ---------------------------------------------------------------------------


def test_normalize_detail_none_returns_none():
    out, coerced = _normalize_detail(None)
    assert out is None
    assert coerced == []


def test_normalize_detail_non_dict_wraps_value():
    out, coerced = _normalize_detail("just a string")
    assert out == {"_value": "just a string"}
    assert coerced  # non-empty


def test_normalize_detail_tracks_coerced_keys():
    out, coerced = _normalize_detail({"a": 1, "b": (2, 3), "c": "ok"})
    assert out["a"] == 1
    assert out["b"] == [2, 3]
    assert out["c"] == "ok"
    assert "b" in coerced


# ---------------------------------------------------------------------------
# _freeze (S-3) — true immutability
# ---------------------------------------------------------------------------


def test_freeze_dict_returns_mappingproxy():
    out = _freeze({"a": 1, "b": [2, 3]})
    assert isinstance(out, MappingProxyType)
    with pytest.raises(TypeError):
        out["a"] = 99


def test_freeze_list_returns_tuple():
    out = _freeze([1, 2, 3])
    assert isinstance(out, tuple)
    with pytest.raises(AttributeError):
        out.append(4)


def test_freeze_nested_dict_inner_also_frozen():
    out = _freeze({"outer": {"inner": "value"}})
    assert isinstance(out, MappingProxyType)
    assert isinstance(out["outer"], MappingProxyType)
    with pytest.raises(TypeError):
        out["outer"]["inner"] = "spoofed"


def test_freeze_idempotent_on_mappingproxy():
    p = MappingProxyType({"a": 1})
    out = _freeze(p)
    assert out is p


# ---------------------------------------------------------------------------
# Trace + TraceEvent dataclass shape
# ---------------------------------------------------------------------------


def test_trace_event_is_frozen():
    e = TraceEvent(
        schema_version=1, timestamp_ns=0, module="x", hook="before_request",
        decision="passed", detail=None, latency_us=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError) if False else pytest.raises(Exception):
        e.module = "spoof"


def test_trace_event_kw_only_required():
    # Positional construction should fail (kw_only=True)
    with pytest.raises(TypeError):
        TraceEvent(1, 0, "x", "before_request", "passed", None, 0)


def test_trace_construction_from_builder():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"k": "v"}, latency_us=42,
    )
    snap = b.snapshot()
    assert isinstance(snap, Trace)
    assert snap.schema_version == 1
    assert len(snap.events) == 1
    assert snap.events[0].module == "shield"
    assert snap.events[0].decision == "passed"


# ---------------------------------------------------------------------------
# Snapshot is actually frozen (regression for round-1 F5)
# ---------------------------------------------------------------------------


def test_snapshot_events_are_immutable_tuple():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"k": "v"}, latency_us=0,
    )
    snap = b.snapshot()
    assert isinstance(snap.events, tuple)
    with pytest.raises(AttributeError):
        snap.events.append(99)


def test_snapshot_event_detail_is_mappingproxy():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"matched": "x"}, latency_us=0,
    )
    snap = b.snapshot()
    detail = snap.events[0].detail
    assert isinstance(detail, MappingProxyType)
    with pytest.raises(TypeError):
        detail["matched"] = "spoof"


def test_snapshot_preserves_types_via_deepcopy():
    """JSON round-trip would lose tuples/datetimes; deepcopy + freeze does not."""
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"groups": [1, 2, 3]},  # list (already JSON-primitive)
        latency_us=0,
    )
    snap = b.snapshot()
    # The list should freeze to a tuple
    assert isinstance(snap.events[0].detail["groups"], tuple)


# ---------------------------------------------------------------------------
# TraceJSONEncoder (S-30)
# ---------------------------------------------------------------------------


def test_json_encoder_handles_mappingproxy():
    p = MappingProxyType({"a": 1, "b": "x"})
    out = json.dumps(p, cls=TraceJSONEncoder)
    assert json.loads(out) == {"a": 1, "b": "x"}


def test_json_encoder_handles_trace_dataclass():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"k": "v"}, latency_us=0,
    )
    snap = b.snapshot()
    out = json.dumps(snap, cls=TraceJSONEncoder)
    parsed = json.loads(out)
    assert parsed["schema_version"] == 1
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["module"] == "shield"


def test_bare_json_dumps_fails_without_encoder():
    """Documented stdlib pattern — bare json.dumps fails on mappingproxy."""
    p = MappingProxyType({"a": 1})
    with pytest.raises(TypeError):
        json.dumps(p)


# ---------------------------------------------------------------------------
# Trace.to_dict() + Trace.to_otel_attributes() (S-18, S-32)
# ---------------------------------------------------------------------------


def test_trace_to_dict_unfreezes():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"k": "v"}, latency_us=0,
    )
    snap = b.snapshot()
    d = snap.to_dict()
    assert isinstance(d, dict)
    # Inner detail should be a plain dict, not a mappingproxy
    assert isinstance(d["events"][0]["detail"], dict)
    assert not isinstance(d["events"][0]["detail"], MappingProxyType)


def test_trace_to_otel_attributes_shape():
    b = _TraceBuilder()
    for i in range(3):
        b.auto_record(
            module=f"shield_{i}", hook="before_request", decision="passed",
            detail={"k": i}, latency_us=10 * i,
        )
    snap = b.close("after_response")
    attrs = snap.to_otel_attributes()
    assert "explain.closed_reason" in attrs
    assert attrs["explain.closed_reason"] == "after_response"
    assert "explain.event.0.module" in attrs
    assert attrs["explain.event.0.module"] == "shield_0"
    assert "explain.event.2.latency_us" in attrs
    assert "explain.trace_json" in attrs


def test_trace_to_otel_caps_events_at_20():
    b = _TraceBuilder()
    for i in range(30):
        b.auto_record(
            module=f"shield_{i}", hook="before_request", decision="passed",
            detail=None, latency_us=0,
        )
    attrs = b.snapshot().to_otel_attributes()
    # event.0 through event.19 only
    assert "explain.event.0.module" in attrs
    assert "explain.event.19.module" in attrs
    assert "explain.event.20.module" not in attrs


# ---------------------------------------------------------------------------
# record_decision — no-op when no active trace (S-6, S-14)
# ---------------------------------------------------------------------------


def test_record_decision_no_op_when_no_active_trace():
    """No exception when called outside any hook context, explain off."""
    # Without explain enabled and no active trace, this should silently no-op
    record_decision("passed", {"x": 1})
    assert last_trace() is None


def test_record_decision_warns_once_when_explain_on_no_trace(monkeypatch):
    """When explain is enabled but no trace is active, warn once."""
    monkeypatch.setattr(trace_module._config, "enabled", True)
    # Reset the once-flag
    monkeypatch.setattr(trace_module, "_background_warning_emitted", False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        record_decision("passed", {"x": 1})
        # Second call should NOT warn again
        record_decision("passed", {"x": 2})
    explain_warnings = [w for w in caught if issubclass(w.category, ExplainModeWarning)]
    assert len(explain_warnings) == 1


# ---------------------------------------------------------------------------
# find_trace (S-16, S-28) — walks __cause__ only, not __context__
# ---------------------------------------------------------------------------


def test_find_trace_returns_none_for_exception_without_trace():
    e = ValueError("plain")
    assert find_trace(e) is None


def test_find_trace_returns_attached_trace():
    b = _TraceBuilder()
    snap = b.close("after_response")
    e = RuntimeError("test")
    e.trace = snap
    assert find_trace(e) is snap


def test_find_trace_walks_cause_chain():
    b = _TraceBuilder()
    snap = b.close("after_response")
    inner = RuntimeError("inner")
    inner.trace = snap
    outer = RuntimeError("outer")
    outer.__cause__ = inner
    assert find_trace(outer) is snap


def test_find_trace_does_not_walk_context_chain():
    """Per S-28: walk __cause__ only, not __context__."""
    b = _TraceBuilder()
    snap = b.close("after_response")
    unrelated = RuntimeError("totally unrelated")
    unrelated.trace = snap
    new_exc = RuntimeError("new")
    new_exc.__context__ = unrelated  # implicit chaining
    new_exc.__cause__ = None  # explicit none — no `from` clause
    assert find_trace(new_exc) is None  # __context__ not walked


def test_find_trace_handles_cause_cycle():
    """Don't infinite-loop on a pathological __cause__ cycle."""
    a = RuntimeError("a")
    b = RuntimeError("b")
    a.__cause__ = b
    b.__cause__ = a
    # Should not hang; returns None because no .trace attribute
    assert find_trace(a) is None


# ---------------------------------------------------------------------------
# clear_last_trace (S-29)
# ---------------------------------------------------------------------------


def test_clear_last_trace_when_no_state_is_idempotent():
    clear_last_trace()
    assert last_trace() is None


def test_clear_last_trace_clears_completed_slot():
    b = _TraceBuilder()
    snap = b.close("after_response")
    trace_module._last_completed_trace.set(snap)
    assert last_trace() is snap
    clear_last_trace()
    assert last_trace() is None


# ---------------------------------------------------------------------------
# last_trace_status (S-17)
# ---------------------------------------------------------------------------


def test_last_trace_status_when_disabled():
    status = last_trace_status()
    assert "explain_enabled" in status
    assert "active_trace_open" in status
    assert "last_close_reason" in status


def test_last_trace_status_with_completed_trace():
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail=None, latency_us=0,
    )
    snap = b.close("after_response")
    trace_module._last_completed_trace.set(snap)
    status = last_trace_status()
    assert status["last_close_reason"] == "after_response"
    assert status["events_recorded"] == 1
    # Cleanup so we don't pollute other tests
    clear_last_trace()


# ---------------------------------------------------------------------------
# Detail size cap (S-7)
# ---------------------------------------------------------------------------


def test_detail_over_size_cap_truncated():
    b = _TraceBuilder()
    huge = {"x": "A" * 100_000}  # exceeds 64KB default
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail=huge, latency_us=0,
    )
    event = b.events[0]
    assert event.detail["_truncated"] is True
    assert event.detail["original_size_bytes"] > 65536
    assert "preview" in event.detail


# ---------------------------------------------------------------------------
# PII redaction by default (DoD-5)
# ---------------------------------------------------------------------------


def test_redaction_applies_to_string_detail_values(monkeypatch):
    monkeypatch.setattr(trace_module._config, "enabled", True)
    monkeypatch.setattr(trace_module._config, "redact", True)
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"user_text": "my SSN is 123-45-6789"},
        latency_us=0,
    )
    assert "123-45-6789" not in b.events[0].detail["user_text"]
    assert "[REDACTED:SSN]" in b.events[0].detail["user_text"]


def test_redaction_off_passes_pii_through(monkeypatch):
    monkeypatch.setattr(trace_module._config, "enabled", True)
    monkeypatch.setattr(trace_module._config, "redact", False)
    b = _TraceBuilder()
    b.auto_record(
        module="shield", hook="before_request", decision="passed",
        detail={"user_text": "my SSN is 123-45-6789"},
        latency_us=0,
    )
    assert "123-45-6789" in b.events[0].detail["user_text"]


# Need to import dataclasses for the FrozenInstanceError check above
import dataclasses  # noqa: E402
