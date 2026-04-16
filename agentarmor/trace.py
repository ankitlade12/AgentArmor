"""Explain Mode v2 — trace recording, snapshots, public API.

Off by default. When enabled via init(explain=True), the HookRegistry
instruments each hook call with a TraceEvent capturing module, decision,
detail, and latency. The trace is per-request via contextvars.

Public surface (also re-exported from agentarmor.__init__):
- Trace, TraceEvent          dataclasses
- ExplainModeWarning         warning class
- TraceJSONEncoder           json.JSONEncoder for serialization
- record_decision()          called by hook bodies for richer detail
- last_trace()               returns most recent completed trace
- last_trace_status()        diagnostic accessor
- find_trace(e)              walk exception __cause__ chain for .trace
- clear_last_trace()         memory management

Schema version is 1 in v1.4.0. Additive field changes do not bump the version
(consumers default missing fields to None). Breaking changes bump to 2.
"""

import copy
import dataclasses
import datetime
import decimal
import json
import threading
import time
import uuid
import warnings
import weakref
from contextvars import ContextVar
from types import MappingProxyType
from typing import Any, Literal, Optional

from ._redactor import default_redact

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

Decision = Literal["passed", "modified", "blocked", "error", "not_recorded"]
HookType = Literal["before_request", "after_response", "on_stream_chunk"]


class ExplainModeWarning(UserWarning):
    """Warning emitted by Explain Mode for non-fatal anomalies.

    Examples: second record_decision() call in a hook (first wins, dropped),
    non-JSON-serializable detail values (coerced via repr), background
    record_decision() after parent trace closed (dropped), active-trace ceiling
    reached (oldest evicted), uninstrumented modules detected at startup.

    To silence:
        import warnings
        import agentarmor
        warnings.filterwarnings("ignore", category=agentarmor.ExplainModeWarning)

    Note: must be set AFTER any warnings.simplefilter() reset.
    """


@dataclasses.dataclass(frozen=True, kw_only=True)
class TraceEvent:
    schema_version: int
    timestamp_ns: int
    module: str
    hook: HookType
    decision: Decision
    detail: Any  # dict (frozen via MappingProxyType in snapshot) or None
    latency_us: int


@dataclasses.dataclass(frozen=True, kw_only=True)
class Trace:
    schema_version: int
    started_at_ns: int
    ended_at_ns: Optional[int]
    events: tuple
    blocked_by: Optional[str]
    closed_reason: Optional[str]
    context_id: str
    silent_modules: tuple = ()

    def to_dict(self) -> dict:
        """Generic serialization. Use this with json.dumps + TraceJSONEncoder."""
        return _to_dict(self)

    def to_otel_attributes(self) -> dict:
        """Flat-dict shape for OTel span attributes (S-32).

        Returns ~64 attributes typical, well under the 128-attr backend cap:
        - 4 trace-level
        - per-event roll-up capped at 20 events (3 attrs each)
        - full trace as JSON blob in single 'explain.trace_json' attribute
        """
        attrs: dict = {
            "explain.closed_reason": self.closed_reason or "open",
            "explain.blocked_by": self.blocked_by or "",
            "explain.duration_us": (
                (self.ended_at_ns - self.started_at_ns) // 1000
                if self.ended_at_ns
                else 0
            ),
            "explain.context_id": self.context_id,
        }
        for i, ev in enumerate(self.events[:20]):
            attrs[f"explain.event.{i}.module"] = ev.module
            attrs[f"explain.event.{i}.decision"] = ev.decision
            attrs[f"explain.event.{i}.latency_us"] = ev.latency_us

        # JSON blob for full fidelity, size-capped
        try:
            blob = json.dumps(self.to_dict(), cls=TraceJSONEncoder)
        except (TypeError, ValueError):
            blob = "<serialization failed>"
        if len(blob.encode("utf-8")) > 8192:
            blob = blob[:8192] + "...[truncated]"
        attrs["explain.trace_json"] = blob
        return attrs


class TraceJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles Trace, TraceEvent, MappingProxyType, tuples.

    Use as: json.dumps(trace, cls=agentarmor.TraceJSONEncoder)
    Bare json.dumps(trace) fails by design (consistent with stdlib pattern
    for datetime / Decimal / etc.).
    """

    def default(self, obj):
        if isinstance(obj, MappingProxyType):
            return dict(obj)
        if isinstance(obj, Trace):
            return _to_dict(obj)
        if isinstance(obj, TraceEvent):
            return {
                "schema_version": obj.schema_version,
                "timestamp_ns": obj.timestamp_ns,
                "module": obj.module,
                "hook": obj.hook,
                "decision": obj.decision,
                "detail": _unfreeze(obj.detail),
                "latency_us": obj.latency_us,
            }
        return super().default(obj)


# ---------------------------------------------------------------------------
# Internal: detail serialization with coercion + cycle/depth guard
# ---------------------------------------------------------------------------

_MAX_DEPTH = 32
_REPR_LIMIT = 256


def _serialize_safe(value: Any, *, depth: int = 0, seen: Optional[set] = None) -> Any:
    """Coerce value to JSON-primitive types per S-4 + S-8 (cycle/depth guard).

    - tuple -> list
    - set / frozenset -> sorted list
    - datetime / date -> isoformat str
    - Decimal -> str
    - bytes -> utf-8 str (replace errors), truncated to 256 chars
    - dict -> dict with string keys (recursive)
    - other -> repr() truncated, with warning emitted via caller
    """
    if seen is None:
        seen = set()
    if depth > _MAX_DEPTH:
        return f"<max-depth-exceeded depth={depth}>"

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        decoded = bytes(value).decode("utf-8", errors="replace")
        return decoded[:_REPR_LIMIT]
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        try:
            return sorted(_serialize_safe(v, depth=depth + 1, seen=seen) for v in value)
        except TypeError:
            return [_serialize_safe(v, depth=depth + 1, seen=seen) for v in value]

    obj_id = id(value)
    if isinstance(value, (dict, list, tuple)):
        if obj_id in seen:
            return f"<cycle to id={obj_id}>"
        seen = seen | {obj_id}

    if isinstance(value, dict):
        return {
            str(k): _serialize_safe(v, depth=depth + 1, seen=seen)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_safe(v, depth=depth + 1, seen=seen) for v in value]

    return repr(value)[:_REPR_LIMIT]


def _normalize_detail(detail: Any) -> tuple:
    """Returns (normalized_dict, warnings_list).

    Always returns a dict (or None if input was None). Tracks coercions so
    caller can emit one ExplainModeWarning summarizing what was coerced.
    """
    if detail is None:
        return None, []
    if not isinstance(detail, dict):
        return {"_value": _serialize_safe(detail)}, [
            f"detail was {type(detail).__name__}; coerced to {{'_value': ...}}"
        ]
    coerced_keys = []
    out = {}
    for k, v in detail.items():
        normalized = _serialize_safe(v)
        if not isinstance(v, (str, int, float, bool, type(None))):
            coerced_keys.append(str(k))
        out[str(k)] = normalized
    return out, coerced_keys


# ---------------------------------------------------------------------------
# Internal: snapshot freezing (S-3)
# ---------------------------------------------------------------------------


def _freeze(obj: Any) -> Any:
    if isinstance(obj, MappingProxyType):
        return obj
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    if isinstance(obj, tuple):
        return tuple(_freeze(v) for v in obj)
    return obj


def _to_dict(trace: "Trace") -> dict:
    """Trace -> plain dict (unwraps MappingProxyType + tuples for JSON)."""
    return {
        "schema_version": trace.schema_version,
        "started_at_ns": trace.started_at_ns,
        "ended_at_ns": trace.ended_at_ns,
        "blocked_by": trace.blocked_by,
        "closed_reason": trace.closed_reason,
        "context_id": trace.context_id,
        "silent_modules": list(trace.silent_modules),
        "events": [
            {
                "schema_version": e.schema_version,
                "timestamp_ns": e.timestamp_ns,
                "module": e.module,
                "hook": e.hook,
                "decision": e.decision,
                "detail": _unfreeze(e.detail),
                "latency_us": e.latency_us,
            }
            for e in trace.events
        ],
    }


def _unfreeze(obj: Any) -> Any:
    if isinstance(obj, MappingProxyType):
        return {k: _unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_unfreeze(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unfreeze(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _ExplainConfig:
    enabled: bool = False
    redact: bool = True
    max_detail_bytes: int = 65536
    max_active_traces: int = 10000
    max_trace_age_seconds: int = 300
    user_redactor: Optional[Any] = None  # set by init() if filter=["pii"] is active


_config = _ExplainConfig()
_active_trace: ContextVar[Optional["_TraceBuilder"]] = ContextVar(
    "agentarmor_active_trace", default=None
)
_last_completed_trace: ContextVar[Optional[Trace]] = ContextVar(
    "agentarmor_last_completed_trace", default=None
)
_background_warning_emitted = False

# Process-wide registry of in-flight TraceBuilders used by the watchdog
# (S-27) to iterate stale traces. WeakSet so closed/dropped builders are GC'd
# without explicit unregister.
_active_traces_registry: "weakref.WeakSet" = weakref.WeakSet()
_registry_lock = threading.Lock()


def get_active_traces() -> tuple:
    """Snapshot of currently-open _TraceBuilder instances. Used by the watchdog."""
    with _registry_lock:
        return tuple(_active_traces_registry)


# ---------------------------------------------------------------------------
# Internal: TraceBuilder (mutable accumulator)
# ---------------------------------------------------------------------------


class _TraceBuilder:
    """Mutable in-flight trace. Snapshot via .snapshot() returns a frozen Trace."""

    def __init__(self):
        self.schema_version = 1
        self.started_at_ns = time.time_ns()
        self.ended_at_ns: Optional[int] = None
        self.events: list = []
        self.blocked_by: Optional[str] = None
        self.closed_reason: Optional[str] = None
        self.context_id = uuid.uuid4().hex
        self.silent_modules: tuple = ()
        # Track which modules have explicitly recorded so we know which
        # auto-events to suppress (per S-11 — silent modules don't appear)
        self._explicit_decisions: dict = {}  # module -> Decision
        self._auto_blocked_override_pending: Optional[tuple] = None
        # Register for the watchdog to find (S-27)
        with _registry_lock:
            _active_traces_registry.add(self)

    def record_explicit(self, module: str, decision: Decision, detail: Any) -> None:
        """Called by user-facing record_decision()."""
        if module in self._explicit_decisions:
            warnings.warn(
                (
                    f"record_decision() called multiple times in module '{module}'; "
                    f"first wins, dropping decision='{decision}'. "
                    "(silence with: warnings.filterwarnings('ignore', "
                    "category=agentarmor.ExplainModeWarning))"
                ),
                ExplainModeWarning,
                stacklevel=3,
            )
            return
        self._explicit_decisions[module] = decision
        normalized, coerced_keys = _normalize_detail(detail)
        if coerced_keys:
            warnings.warn(
                f"detail values coerced via repr/coercion in module '{module}': {coerced_keys}",
                ExplainModeWarning,
                stacklevel=3,
            )
        normalized = self._apply_redaction(normalized)
        normalized = self._apply_size_cap(normalized)
        self._append_event(
            module=module, hook="before_request", decision=decision, detail=normalized,
            latency_us=0,
        )

    def auto_record(
        self,
        *,
        module: str,
        hook: HookType,
        decision: Decision,
        detail: Any,
        latency_us: int,
    ) -> None:
        """Called by HookRegistry instrumentation for blocked / error / passed."""
        # If the hook explicitly recorded, the explicit record takes precedence
        # for "passed"/"modified"/"not_recorded". But auto-blocked/error always
        # wins (S-6 + S-7 resolution).
        if decision in ("blocked", "error"):
            prior = self._explicit_decisions.get(module)
            if prior and prior not in ("blocked", "error"):
                warnings.warn(
                    (
                        f"hook in module '{module}' raised after explicit record_decision('{prior}'); "
                        f"auto-detected decision='{decision}' overrides."
                    ),
                    ExplainModeWarning,
                    stacklevel=3,
                )
            self._explicit_decisions[module] = decision
            if decision == "blocked" and self.blocked_by is None:
                self.blocked_by = module
        else:
            if module in self._explicit_decisions:
                # Hook explicitly recorded; suppress auto-default
                return

        normalized, _ = _normalize_detail(detail)
        normalized = self._apply_redaction(normalized)
        normalized = self._apply_size_cap(normalized)
        self._append_event(
            module=module, hook=hook, decision=decision, detail=normalized,
            latency_us=latency_us,
        )

    def _append_event(
        self,
        *,
        module: str,
        hook: HookType,
        decision: Decision,
        detail: Any,
        latency_us: int,
    ) -> None:
        self.events.append(
            TraceEvent(
                schema_version=1,
                timestamp_ns=time.time_ns(),
                module=module,
                hook=hook,
                decision=decision,
                detail=detail,
                latency_us=latency_us,
            )
        )

    def _apply_redaction(self, detail: Any) -> Any:
        if not _config.redact or detail is None:
            return detail
        return _redact_recursive(detail)

    def _apply_size_cap(self, detail: Any) -> Any:
        if detail is None:
            return detail
        try:
            serialized = json.dumps(detail, cls=TraceJSONEncoder)
        except (TypeError, ValueError, RecursionError):
            return {"_serialization_failed": True}
        size = len(serialized.encode("utf-8"))
        if size > _config.max_detail_bytes:
            return {
                "_truncated": True,
                "original_size_bytes": size,
                "preview": serialized[:1024],
            }
        return detail

    def close(self, reason: str) -> Trace:
        if self.ended_at_ns is None:
            self.ended_at_ns = time.time_ns()
            self.closed_reason = reason
            with _registry_lock:
                _active_traces_registry.discard(self)
        return self.snapshot()

    def snapshot(self) -> Trace:
        events = tuple(
            TraceEvent(
                schema_version=e.schema_version,
                timestamp_ns=e.timestamp_ns,
                module=e.module,
                hook=e.hook,
                decision=e.decision,
                detail=_freeze(copy.deepcopy(e.detail)),
                latency_us=e.latency_us,
            )
            for e in self.events
        )
        return Trace(
            schema_version=self.schema_version,
            started_at_ns=self.started_at_ns,
            ended_at_ns=self.ended_at_ns,
            events=events,
            blocked_by=self.blocked_by,
            closed_reason=self.closed_reason,
            context_id=self.context_id,
            silent_modules=tuple(self.silent_modules),
        )


def _redact_recursive(value: Any) -> Any:
    """Walk the detail dict, redacting all string values."""
    if isinstance(value, str):
        if _config.user_redactor is not None:
            return _config.user_redactor(value)
        return default_redact(value)
    if isinstance(value, dict):
        return {k: _redact_recursive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_recursive(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_decision(decision: Decision, detail: Optional[dict] = None) -> None:
    """Record this hook's decision into the active trace.

    No-op when explain mode is off OR when called outside an active hook
    context. First-wins among explicit calls (S-7); subsequent calls in the
    same hook emit ExplainModeWarning and are dropped.

    Auto-detected decisions (blocked from raised SHIELD_EXCEPTIONS, error from
    other exceptions) always override an explicit non-block per S-6.

    Args:
        decision: one of "passed", "modified", "blocked", "error", "not_recorded"
        detail: optional dict with JSON-primitive values; non-conforming values
                are coerced (tuple->list, datetime->iso str, Decimal->str, etc.)
                with a single warning summarizing coerced keys.
    """
    builder = _active_trace.get()
    if builder is None:
        if _config.enabled:
            global _background_warning_emitted
            if not _background_warning_emitted:
                warnings.warn(
                    (
                        "record_decision() called outside an active trace context "
                        "(possibly from a background task after parent trace closed); "
                        "call discarded."
                    ),
                    ExplainModeWarning,
                    stacklevel=2,
                )
                _background_warning_emitted = True
        return

    # Derive caller module from the call frame
    import sys
    frame = sys._getframe(1)
    module_path = frame.f_globals.get("__name__", "unknown")
    module = module_path.rsplit(".", 1)[-1]
    builder.record_explicit(module, decision, detail)


def last_trace() -> Optional[Trace]:
    """Return the most recent completed Trace from the current context, or None."""
    return _last_completed_trace.get()


def last_trace_status() -> dict:
    """Diagnostic accessor — turns 'trace is None' debug from 5 min to 5 sec."""
    builder = _active_trace.get()
    last = _last_completed_trace.get()
    return {
        "explain_enabled": _config.enabled,
        "active_trace_open": builder is not None,
        "last_close_reason": last.closed_reason if last else None,
        "context_id": (builder.context_id if builder else (last.context_id if last else None)),
        "events_recorded": len(builder.events) if builder else (len(last.events) if last else 0),
    }


def find_trace(e: BaseException) -> Optional[Trace]:
    """Walk e.__cause__ chain looking for a .trace attribute.

    Use this when a framework (FastAPI, Celery, Sentry) wraps your exception
    and bare e.trace is no longer accessible. Document for users:
        try: ...
        except Exception as e:
            t = agentarmor.find_trace(e) or agentarmor.last_trace()

    Walks __cause__ only (not __context__) to avoid picking up unrelated traces
    from shared finally blocks per S-28.
    """
    seen = set()
    cur = e
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        t = getattr(cur, "trace", None)
        if isinstance(t, Trace):
            return t
        cur = cur.__cause__
    return None


def clear_last_trace() -> None:
    """Force-close any open trace + clear last-completed slot.

    Subsequent last_trace() returns None. last_trace_status() reports
    last_close_reason='cleared'.
    """
    builder = _active_trace.get()
    if builder is not None:
        cleared = builder.close("cleared")
        _last_completed_trace.set(cleared)
        _active_trace.set(None)
    else:
        _last_completed_trace.set(None)
