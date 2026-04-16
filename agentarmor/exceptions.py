class BudgetExhausted(Exception):
    """Raised when the dollar budget is exceeded."""
    pass

class RateLimitExceeded(Exception):
    """Raised when the call rate exceeds the configured limit."""
    pass

class InjectionDetected(Exception):
    """Raised when a prompt injection attack is detected."""
    pass

class FilterViolation(Exception):
    """Raised when output contains banned content (block mode)."""
    pass

class HookError(Exception):
    """Raised when a user-defined hook raises an unhandled exception."""
    pass

class PatchError(Exception):
    """Raised when SDK patching fails (e.g., incompatible SDK version)."""
    pass

class ContextOverflow(Exception):
    """Raised when the message payload is likely to exceed the model's context window."""
    pass

class LatencyThresholdExceeded(Exception):
    """Raised when the latency circuit breaker trips due to consecutive slow responses."""
    pass

class CanaryLeakDetected(Exception):
    """Raised when a canary token is detected in the LLM's output, indicating prompt leakage."""
    pass

class ToolCallBlocked(Exception):
    """Raised when an LLM attempts to call a tool that is not authorized."""
    pass

class DuplicateRequest(Exception):
    """Raised when a duplicate prompt is detected and blocked to save API spend."""
    pass

class MLInjectionDetected(Exception):
    """Raised when the ML classifier detects a likely prompt injection."""
    pass

class AgentDepthExceeded(Exception):
    """Raised when agent spawn depth exceeds the configured maximum."""
    pass

class AgentLimitExceeded(Exception):
    """Raised when total number of agents exceeds the configured maximum."""
    pass

class AgentBudgetExhausted(Exception):
    """Raised when a sub-agent's allocated budget is exhausted."""
    pass

class MCPViolation(Exception):
    """Raised when an MCP tool call violates security policies."""
    pass

class InsecureCodeDetected(Exception):
    """Raised when LLM output contains potentially dangerous code patterns."""
    pass

class HallucinationDetected(Exception):
    """Raised when response grounding score falls below threshold."""
    pass

class ReasoningViolation(Exception):
    """Raised when chain-of-thought auditing detects misaligned reasoning."""
    pass

class ToxicContentDetected(Exception):
    """Raised when toxic or harmful content is detected in LLM output."""
    pass

class UnicodeInjectionDetected(Exception):
    """Raised when invisible unicode-based prompt injection is detected."""
    pass

class HumanApprovalRequired(Exception):
    """Raised when an action requires human approval before proceeding."""
    pass

class HumanApprovalDenied(Exception):
    """Raised when a human denies an action requested by the agent."""
    pass

class HumanApprovalTimeout(Exception):
    """Raised when human approval request times out."""
    pass

class DataExfiltrationDetected(Exception):
    """Raised when data exfiltration attempt is detected in LLM output."""
    pass

class PrivilegeEscalationDetected(Exception):
    """Raised when an LLM agent attempts to escalate its privileges."""
    pass

class SemanticDriftDetected(Exception):
    """Raised when conversation semantic drift exceeds the configured threshold."""
    pass


class ConfigurationError(ValueError):
    """Raised when init() is called with invalid configuration under strict mode.

    Subclasses ValueError so existing except-ValueError handlers still catch it.
    """
    pass


# Registry of "shield blocked" exceptions used by Explain Mode v2 to classify
# hook outcomes. A hook raising one of these records decision="blocked" in the
# trace; any other Exception records decision="error".
#
# HookError and PatchError are intentionally excluded — they represent
# infrastructure errors, not shield decisions. ConfigurationError is excluded
# because it fires at init() time, never inside a hook execution.
#
# If you add a new shield exception class above, add it to this tuple. The
# explain-mode audit script (scripts/audit_hook_modules.py) verifies the
# tuple stays in sync with declared classes.
SHIELD_EXCEPTIONS = (
    BudgetExhausted,
    RateLimitExceeded,
    InjectionDetected,
    FilterViolation,
    ContextOverflow,
    LatencyThresholdExceeded,
    CanaryLeakDetected,
    ToolCallBlocked,
    DuplicateRequest,
    MLInjectionDetected,
    AgentDepthExceeded,
    AgentLimitExceeded,
    AgentBudgetExhausted,
    MCPViolation,
    InsecureCodeDetected,
    HallucinationDetected,
    ReasoningViolation,
    ToxicContentDetected,
    UnicodeInjectionDetected,
    HumanApprovalRequired,
    HumanApprovalDenied,
    HumanApprovalTimeout,
    DataExfiltrationDetected,
    PrivilegeEscalationDetected,
    SemanticDriftDetected,
)
