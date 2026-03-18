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
