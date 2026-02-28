class BudgetExhausted(Exception):
    """Raised when the dollar budget is exceeded."""
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
