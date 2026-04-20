import contextvars
from typing import Optional
from typing import Any

__version__ = "1.5.0"

from .core import ArmorCore
from .hooks import before_request, after_response, on_stream_chunk, RequestContext, ResponseContext
from .config import load_config
from .exceptions import (
    ContextOverflow, LatencyThresholdExceeded, CanaryLeakDetected,
    ToolCallBlocked, DuplicateRequest, MLInjectionDetected,
    AgentDepthExceeded, AgentLimitExceeded, AgentBudgetExhausted,
    MCPViolation, InsecureCodeDetected, HallucinationDetected, ReasoningViolation, ToxicContentDetected,
    UnicodeInjectionDetected,
    HumanApprovalRequired, HumanApprovalDenied, HumanApprovalTimeout,
    DataExfiltrationDetected,
    PrivilegeEscalationDetected,
    SemanticDriftDetected,
    ConfigurationError,
    SHIELD_EXCEPTIONS,
)
from .modules.cost_tags import set_tag, clear_tag, get_tag
from .modules.taint_tracker import TaintViolation
from .modules.honeytools import HoneytoolTriggered
from .modules.safe_plan import SafePlanEngine, SafePlanSuggestion
from .modules.echo_chamber import EchoChamberDetected
from .demo import demo_attacks, DemoReport
from .trace import (
    Trace,
    TraceEvent,
    TraceJSONEncoder,
    ExplainModeWarning,
    record_decision,
    last_trace,
    last_trace_status,
    find_trace,
    clear_last_trace,
)
from ._run_in_executor import run_in_executor
from . import trace as _trace_module
from . import _audit, _watchdog

# Thread-safe and async-safe context variable for the active Engine/Core instance
_active_core: contextvars.ContextVar[Optional[ArmorCore]] = contextvars.ContextVar(
    "_agentarmor_core", default=None
)
_active_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_agentarmor_agent", default=None
)

_explain_startup_warned = False


def init(budget=None, shield=False, filter=None, record=False, rate_limit=None, context_guard=False, latency_breaker=None, canary=None, tool_firewall=None, cost_tags=None, dedup=None, cascade=None, ml_shield=None, agent_graph=None, mcp_firewall=None, code_shield=None, grounding=None, cot_auditor=None, toxicity=None, compliance=None, hitl_gate=None, exfiltration_guard=None, privilege_escalation=None, unicode_shield=None, semantic_drift=None, taint_tracker=None, honeytools=None, echo_chamber=None, explain=False, explain_redact=True, explain_max_detail_bytes=65536, explain_max_active_traces=10000, explain_max_trace_age_seconds=300, strict=False, **kwargs) -> ArmorCore:
    """
    Initializes AgentArmor for the current execution context.
    Returns the active ArmorCore instance.

    Args:
        strict: When True, unknown kwargs raise ConfigurationError with a
            "did you mean ...?" suggestion. Default False emits a UserWarning
            and continues (preserves backwards compatibility). Use strict=True
            in production code to catch typos like ``unicode_sheild=True`` that
            would otherwise be silently ignored.
        explain: Enable Explain Mode v2. When True, agentarmor.last_trace()
            returns a structured Trace of which shields ran and what each
            decided. Off by default; near-zero overhead when off.
        explain_redact: When True (default), trace event detail is PII-redacted
            via the configured filter pipeline before storage. Set False ONLY
            for local debugging — never in production telemetry.
        explain_max_detail_bytes: Per-event detail size cap (default 64KB).
            Over-cap values are replaced with a truncation marker.
        explain_max_active_traces: Process-wide ceiling on concurrently-open
            traces (default 10000). On overflow, oldest is force-closed and
            ExplainModeWarning is emitted.
        explain_max_trace_age_seconds: Watchdog timeout (default 300). Streams
            held longer than this get force-closed with closed_reason='timeout'.
    """
    from ._strict import validate_kwargs
    validate_kwargs(kwargs.keys(), strict=strict)

    core = ArmorCore(
        budget=budget,
        shield=shield,
        filter=filter or [],
        record=record,
        rate_limit=rate_limit,
        context_guard=context_guard,
        latency_breaker=latency_breaker,
        canary=canary,
        tool_firewall=tool_firewall,
        cost_tags=cost_tags,
        dedup=dedup,
        cascade=cascade,
        ml_shield=ml_shield,
        agent_graph=agent_graph,
        mcp_firewall=mcp_firewall,
        code_shield=code_shield,
        grounding=grounding,
        cot_auditor=cot_auditor,
        toxicity=toxicity,
        compliance=compliance,
        unicode_shield=unicode_shield,
        hitl_gate=hitl_gate,
        exfiltration_guard=exfiltration_guard,
        privilege_escalation=privilege_escalation,
        semantic_drift=semantic_drift,
        taint_tracker=taint_tracker,
        honeytools=honeytools,
        echo_chamber=echo_chamber,
        explain=explain,
        explain_redact=explain_redact,
        explain_max_detail_bytes=explain_max_detail_bytes,
        explain_max_active_traces=explain_max_active_traces,
        explain_max_trace_age_seconds=explain_max_trace_age_seconds,
        **kwargs
    )
    core.patch()
    _active_core.set(core)
    _apply_explain_config(
        core=core,
        enabled=explain,
        redact=explain_redact,
        max_detail_bytes=explain_max_detail_bytes,
        max_active_traces=explain_max_active_traces,
        max_trace_age_seconds=explain_max_trace_age_seconds,
        filter_rules=filter or [],
    )
    return core


def _apply_explain_config(*, core, enabled, redact, max_detail_bytes,
                          max_active_traces, max_trace_age_seconds, filter_rules):
    """Apply explain settings to module-level state + start watchdog + warn once."""
    cfg = _trace_module._config
    cfg.enabled = bool(enabled)
    cfg.redact = bool(redact)
    cfg.max_detail_bytes = int(max_detail_bytes)
    cfg.max_active_traces = int(max_active_traces)
    cfg.max_trace_age_seconds = int(max_trace_age_seconds)
    cfg.user_redactor = None

    # Wire user PII filter as single source of truth (S-5)
    if "pii" in filter_rules and "filter" in core.modules:
        cfg.user_redactor = core.modules["filter"].redact

    if not enabled:
        return

    # Start watchdog (idempotent) per S-12
    _watchdog.start_watchdog(_trace_module.get_active_traces, max_trace_age_seconds)

    # One-time startup warning listing silent modules per S-11
    global _explain_startup_warned
    if not _explain_startup_warned:
        silent = _audit.get_uninstrumented_modules(core.registry)
        if silent:
            import warnings
            warnings.warn(
                (
                    f"explain mode enabled; these {len(silent)} modules do not call "
                    f"record_decision and will not surface detail in traces "
                    f"(they will run silently and appear only in Trace.silent_modules): "
                    f"{', '.join(silent)}. "
                    "(silence with: warnings.filterwarnings('ignore', "
                    "category=agentarmor.ExplainModeWarning))"
                ),
                ExplainModeWarning,
                stacklevel=3,
            )
        _explain_startup_warned = True

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

def spawn_agent(agent_id: str, parent_id: Optional[str] = None,
                budget_limit: Optional[float] = None,
                policies: Optional[dict] = None):
    """Register a sub-agent in the current ArmorCore's agent graph."""
    core = get_core()
    if core and "agent_graph" in core.modules:
        node = core.modules["agent_graph"].spawn_agent(
            agent_id, parent_id, budget_limit, policies=policies,
        )
        _active_agent.set(agent_id)
        return node
    return None

def end_agent(agent_id: str):
    """End a sub-agent and roll up its stats."""
    core = get_core()
    if core and "agent_graph" in core.modules:
        graph = core.modules["agent_graph"]
        node = graph.get_agent(agent_id)
        graph.end_agent(agent_id)
        if node and node.parent:
            _active_agent.set(node.parent.agent_id)
        else:
            _active_agent.set(None)

def teardown() -> None:
    """Unpatches SDKs and clears the current context's AgentArmor instance."""
    core = get_core()
    if core:
        core.unpatch()
        _active_core.set(None)

def compliance_report(framework=None) -> Optional[dict]:
    """Generate a compliance report from all active modules."""
    core = get_core()
    if core and "compliance" in core.modules:
        return core.modules["compliance"].generate_report(
            module_reports=core.report(),
            framework=framework
        )
    return None

def validate_mcp_server(server_name: str, server_uri=None) -> bool:
    """Convenience function to validate an MCP server against the active firewall."""
    core = get_core()
    if core and "mcp_firewall" in core.modules:
        return core.modules["mcp_firewall"].validate_server(server_name, server_uri)
    return True

def validate_mcp_tool(tool_name: str, arguments: dict, server_name=None) -> bool:
    """Convenience function to validate an MCP tool call against the active firewall."""
    core = get_core()
    if core and "mcp_firewall" in core.modules:
        return core.modules["mcp_firewall"].validate_tool_call(tool_name, arguments, server_name)
    return True

def authenticate_mcp_server(server_name: str, auth_token: str) -> bool:
    """Pre-authenticate an MCP server for the active session.

    Call this at server registration/connection time. Once authenticated,
    the server is allowed to make tool calls through the MCP firewall.
    Returns True if auth succeeds, False if token doesn't match.
    """
    core = get_core()
    if core and "mcp_firewall" in core.modules:
        return core.modules["mcp_firewall"].validate_server_auth(server_name, auth_token)
    return True

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
    "spawn_agent",
    "end_agent",
    "before_request",
    "after_response",
    "on_stream_chunk",
    "RequestContext",
    "ResponseContext",
    "ArmorCore",
    "load_config",
    "ContextOverflow",
    "LatencyThresholdExceeded",
    "CanaryLeakDetected",
    "ToolCallBlocked",
    "set_tag",
    "clear_tag",
    "get_tag",
    "DuplicateRequest",
    "MLInjectionDetected",
    "AgentDepthExceeded",
    "AgentLimitExceeded",
    "AgentBudgetExhausted",
    "MCPViolation",
    "validate_mcp_server",
    "validate_mcp_tool",
    "authenticate_mcp_server",
    "InsecureCodeDetected",
    "HallucinationDetected",
    "ReasoningViolation",
    "ToxicContentDetected",
    "UnicodeInjectionDetected",
    "HumanApprovalRequired",
    "HumanApprovalDenied",
    "HumanApprovalTimeout",
    "DataExfiltrationDetected",
    "PrivilegeEscalationDetected",
    "SemanticDriftDetected",
    "TaintViolation",
    "HoneytoolTriggered",
    "SafePlanEngine",
    "SafePlanSuggestion",
    "EchoChamberDetected",
    "ConfigurationError",
    "compliance_report",
    "demo_attacks",
    # Explain mode v2 public surface
    "Trace",
    "TraceEvent",
    "TraceJSONEncoder",
    "ExplainModeWarning",
    "record_decision",
    "last_trace",
    "last_trace_status",
    "find_trace",
    "clear_last_trace",
    "run_in_executor",
    "SHIELD_EXCEPTIONS",
    "DemoReport",
]
