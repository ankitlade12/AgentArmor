import contextvars
from typing import Optional
from typing import Any

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
)
from .modules.cost_tags import set_tag, clear_tag, get_tag
from .modules.taint_tracker import TaintViolation

# Thread-safe and async-safe context variable for the active Engine/Core instance
_active_core: contextvars.ContextVar[Optional[ArmorCore]] = contextvars.ContextVar(
    "_agentarmor_core", default=None
)
_active_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_agentarmor_agent", default=None
)

def init(budget=None, shield=False, filter=None, record=False, rate_limit=None, context_guard=False, latency_breaker=None, canary=None, tool_firewall=None, cost_tags=None, dedup=None, cascade=None, ml_shield=None, agent_graph=None, mcp_firewall=None, code_shield=None, grounding=None, cot_auditor=None, toxicity=None, compliance=None, hitl_gate=None, exfiltration_guard=None, privilege_escalation=None, unicode_shield=None, semantic_drift=None, taint_tracker=None, **kwargs) -> ArmorCore:
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
    "compliance_report",
]
