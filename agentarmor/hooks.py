import dataclasses
import time
from typing import List, Dict, Any, Callable, Optional

@dataclasses.dataclass
class RequestContext:
    """Context object representing an outbound request to an LLM provider."""
    messages: List[Dict[str, Any]]
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    extra_kwargs: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.messages, list):
            raise TypeError("messages must be a list")
        if not isinstance(self.model, str):
            raise TypeError("model must be a string")

@dataclasses.dataclass
class ResponseContext:
    """Context object representing an inbound response from an LLM provider."""
    text: str
    model: str
    provider: str
    request: RequestContext
    cost: Optional[float] = None
    latency_ms: Optional[float] = None
    usage: Optional[Dict[str, int]] = None
    raw_response: Any = None

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.model, str):
            raise TypeError("model must be a string")
        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not isinstance(self.request, RequestContext):
            raise TypeError("request must be a RequestContext instance")

class HookRegistry:
    """Registry for managing and executing middleware hooks."""
    def __init__(self):
        self._before_request: List[Callable[[RequestContext], RequestContext]] = []
        self._after_response: List[Callable[[ResponseContext], ResponseContext]] = []
        self._on_stream_chunk: List[Callable[[str], str]] = []

    def register_before_request(self, func: Callable[[RequestContext], RequestContext]) -> Callable[[RequestContext], RequestContext]:
        self._before_request.append(func)
        return func

    def register_after_response(self, func: Callable[[ResponseContext], ResponseContext]) -> Callable[[ResponseContext], ResponseContext]:
        self._after_response.append(func)
        return func

    def register_on_stream_chunk(self, func: Callable[[str], str]) -> Callable[[str], str]:
        self._on_stream_chunk.append(func)
        return func

    def execute_before_request(self, ctx: RequestContext) -> RequestContext:
        for hook in self._before_request:
            ctx = _invoke_with_trace(hook, ctx, "before_request")
            if not isinstance(ctx, RequestContext):
                raise TypeError(f"Hook {hook.__name__} must return a RequestContext object.")
        return ctx

    def execute_after_response(self, ctx: ResponseContext) -> ResponseContext:
        for hook in self._after_response:
            ctx = _invoke_with_trace(hook, ctx, "after_response")
            if not isinstance(ctx, ResponseContext):
                raise TypeError(f"Hook {hook.__name__} must return a ResponseContext object.")
        return ctx

    def execute_on_stream_chunk(self, accumulated_text: str) -> str:
        for hook in self._on_stream_chunk:
            accumulated_text = _invoke_with_trace(hook, accumulated_text, "on_stream_chunk")
        return accumulated_text

    def clone(self) -> 'HookRegistry':
        """Creates a shallow copy of this registry."""
        new_registry = HookRegistry()
        new_registry._before_request = list(self._before_request)
        new_registry._after_response = list(self._after_response)
        new_registry._on_stream_chunk = list(self._on_stream_chunk)
        return new_registry

# Global hook registry exported via the package root
global_registry = HookRegistry()
before_request = global_registry.register_before_request
after_response = global_registry.register_after_response
on_stream_chunk = global_registry.register_on_stream_chunk


# ---------------------------------------------------------------------------
# Explain Mode v2 hook instrumentation (per S-1, S-2, S-6, S-11, S-24)
#
# Wraps each hook call with trace recording when explain mode is on AND a
# trace is active. Zero-overhead early-return when no active trace —
# verified by the existing 800+ tests still passing without modification.
# ---------------------------------------------------------------------------


def _invoke_with_trace(hook, arg, hook_type):
    # Lazy imports to avoid circular dep at module import time
    from .trace import _active_trace
    builder = _active_trace.get()
    if builder is None:
        # Zero-overhead path: explain off OR no active trace
        return hook(arg)

    from .exceptions import SHIELD_EXCEPTIONS
    module_name = _module_name_for_hook(hook)
    start_ns = time.perf_counter_ns()
    try:
        result = hook(arg)
    except SHIELD_EXCEPTIONS as e:
        latency_us = (time.perf_counter_ns() - start_ns) // 1000
        builder.auto_record(
            module=module_name,
            hook=hook_type,
            decision="blocked",
            detail={"exception_type": type(e).__name__, "message": str(e)},
            latency_us=latency_us,
        )
        raise
    except Exception as e:
        latency_us = (time.perf_counter_ns() - start_ns) // 1000
        builder.auto_record(
            module=module_name,
            hook=hook_type,
            decision="error",
            detail={"exception_type": type(e).__name__, "message": str(e)},
            latency_us=latency_us,
        )
        raise

    # Hook returned successfully. If it called record_decision, the explicit
    # event is already in the trace. If it didn't, this module is "silent"
    # for this hook — per S-11 we do NOT record a "passed" event (would be
    # noise); the silent module set is tracked by trace.get_silent_modules.
    latency_us = (time.perf_counter_ns() - start_ns) // 1000
    builder.note_silent_if_unrecorded(module_name, hook_type, latency_us)
    return result


def _module_name_for_hook(hook):
    func_module = getattr(hook, "__module__", None) or ""
    parts = func_module.rsplit(".", 1)
    if len(parts) == 2 and parts[0] == "agentarmor.modules":
        return parts[1]
    # Non-module hook (user-registered, lambda, etc.); use the qualname tail
    qualname = getattr(hook, "__qualname__", getattr(hook, "__name__", "unknown"))
    return qualname.split(".")[-1] or "unknown"
