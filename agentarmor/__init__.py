import contextvars
from typing import Optional
from typing import Any

from .core import ArmorCore
from .hooks import before_request, after_response, on_stream_chunk, RequestContext, ResponseContext
from .config import load_config
from .exceptions import ContextOverflow, LatencyThresholdExceeded

# Thread-safe and async-safe context variable for the active Engine/Core instance
_active_core: contextvars.ContextVar[Optional[ArmorCore]] = contextvars.ContextVar("_agentarmor_core", default=None)

def init(budget=None, shield=False, filter=None, record=False, rate_limit=None, context_guard=False, latency_breaker=None, **kwargs) -> ArmorCore:
    """
    Initializes AgentArmor for the current execution context.
    Returns the active ArmorCore instance.
    """
    core = ArmorCore(
        budget=budget,
        shield=shield,
        filter=filter or [],
        record=record,
        rate_limit=rate_limit,
        context_guard=context_guard,
        latency_breaker=latency_breaker,
        **kwargs
    )
    core.patch()
    _active_core.set(core)
    return core

def get_core() -> Optional[ArmorCore]:
    """Returns the currently active ArmorCore instance in this context."""
    return _active_core.get()

def report() -> Optional[dict[str, Any]]:
    """Returns the comprehensive report from all active modules."""
    core = get_core()
    return core.report() if core else None

def spent() -> float:
    """Returns the amount of money spent in the current context."""
    core = get_core()
    if core and "budget" in core.modules:
        return core.modules["budget"].spent
    return 0.0

def remaining() -> Optional[float]:
    """Returns the available budget remaining in the current context."""
    core = get_core()
    if core and "budget" in core.modules:
        return core.modules["budget"].remaining
    return None

def teardown() -> None:
    """Unpatches SDKs and clears the current context's AgentArmor instance."""
    core = get_core()
    if core:
        core.unpatch()
        _active_core.set(None)

def init_from_config(path=None, **overrides) -> ArmorCore:
    """
    Initializes AgentArmor from a config file (.agentarmor.yml / .json).
    
    Args:
        path: Explicit path to config file. Auto-discovers if None.
        **overrides: Override any config values programmatically.
    """
    config = load_config(path)
    config.update(overrides)
    return init(**config)

__all__ = [
    "init",
    "init_from_config",
    "report",
    "spent",
    "remaining",
    "teardown",
    "get_core",
    "before_request",
    "after_response",
    "on_stream_chunk",
    "RequestContext",
    "ResponseContext",
    "ArmorCore",
    "load_config",
    "ContextOverflow",
    "LatencyThresholdExceeded",
]
