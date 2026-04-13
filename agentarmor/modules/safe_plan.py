"""
Counterfactual Safe-Plan Engine v1

Instead of just blocking dangerous tool calls, generates structured
explanations of *why* the action was blocked and suggests the nearest
safe alternative. v1 is purely rule-based (no LLM call).

Works as a wrapper around HITL gate decisions and tool firewall blocks.
"""

from typing import Any, Dict, List, Optional


# Maps risk categories to structured safe alternatives
SAFE_ALTERNATIVES = {
    "file_write": {
        "reason_template": "Writing to '{path}' is blocked because it matches a restricted path policy.",
        "alternatives": [
            "Write to a sandboxed directory (e.g. /tmp/ or a designated output folder)",
            "Use an append-only log instead of overwriting files",
            "Request human approval for this specific write operation",
        ],
    },
    "file_delete": {
        "reason_template": "Deleting '{path}' is blocked to prevent accidental data loss.",
        "alternatives": [
            "Move the file to a trash/archive directory instead of deleting",
            "Request human approval for deletion of specific files",
            "Mark the file for review rather than immediate deletion",
        ],
    },
    "shell_exec": {
        "reason_template": "Shell execution of '{command}' is blocked due to security policy.",
        "alternatives": [
            "Use a restricted command allowlist with pre-approved commands",
            "Execute through a sandboxed environment",
            "Request human approval for this specific command",
        ],
    },
    "network_request": {
        "reason_template": "External network request to '{url}' is blocked by policy.",
        "alternatives": [
            "Use an approved API endpoint from the allowlist",
            "Route through a proxy that enforces domain restrictions",
            "Request human approval for this specific external call",
        ],
    },
    "database_write": {
        "reason_template": "Database write operation '{operation}' is blocked by policy.",
        "alternatives": [
            "Use a read-only database connection for queries",
            "Write to a staging table for human review before production",
            "Request human approval for schema-modifying operations",
        ],
    },
    "credential_access": {
        "reason_template": "Accessing credentials for '{target}' is blocked by security policy.",
        "alternatives": [
            "Use a secrets manager with scoped, temporary credentials",
            "Request the minimum required permission via HITL approval",
            "Use a service account with pre-configured limited access",
        ],
    },
    "send_message": {
        "reason_template": "Sending message via '{channel}' is blocked by communication policy.",
        "alternatives": [
            "Draft the message for human review before sending",
            "Use an internal notification channel instead of external",
            "Queue the message for batch review and approval",
        ],
    },
    "data_export": {
        "reason_template": "Exporting data from '{source}' is blocked by data governance policy.",
        "alternatives": [
            "Export an anonymized or aggregated summary instead",
            "Use column-level masking to redact sensitive fields",
            "Request human approval with a data access justification",
        ],
    },
    "_default": {
        "reason_template": "Action '{tool_name}' was blocked by security policy ({policy_name}).",
        "alternatives": [
            "Request human approval for this specific action",
            "Check if a lower-risk alternative tool is available",
            "Review the action's risk level and adjust policies if appropriate",
        ],
    },
}


class SafePlanSuggestion:
    """A structured block explanation with safe alternatives."""

    def __init__(self, tool_name: str, reason: str,
                 alternatives: List[str], risk_level: str = "high",
                 policy_name: str = "", original_args: Optional[Dict] = None):
        self.tool_name = tool_name
        self.reason = reason
        self.alternatives = alternatives
        self.risk_level = risk_level
        self.policy_name = policy_name
        self.original_args = original_args or {}

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "policy_name": self.policy_name,
            "alternatives": self.alternatives,
            "original_args": self.original_args,
        }

    def to_message(self) -> str:
        """Format as a human-readable message."""
        lines = [
            f"Blocked: {self.tool_name} (risk: {self.risk_level})",
            f"Reason: {self.reason}",
            "",
            "Safe alternatives:",
        ]
        for i, alt in enumerate(self.alternatives, 1):
            lines.append(f"  {i}. {alt}")
        return "\n".join(lines)


class SafePlanEngine:
    """Generates safe alternative suggestions for blocked actions.

    Can be used standalone or integrated with HITLGateModule.
    """

    def __init__(
        self,
        tool_categories: Optional[Dict[str, str]] = None,
        custom_alternatives: Optional[Dict[str, Dict]] = None,
    ):
        """
        Args:
            tool_categories: Maps tool names to risk categories.
                e.g. {"rm_file": "file_delete", "curl": "network_request"}
            custom_alternatives: Additional or override alternative definitions.
                Same structure as SAFE_ALTERNATIVES.
        """
        self.tool_categories = tool_categories or {}
        self._alternatives = dict(SAFE_ALTERNATIVES)
        if custom_alternatives:
            self._alternatives.update(custom_alternatives)

    def suggest(self, tool_name: str, arguments: Optional[Dict] = None,
                risk_level: str = "high",
                policy_name: str = "") -> SafePlanSuggestion:
        """Generate a safe alternative suggestion for a blocked tool call.

        Returns a SafePlanSuggestion with structured reason and alternatives.
        """
        arguments = arguments or {}
        category = self.tool_categories.get(tool_name, "_default")
        alt_def = self._alternatives.get(category, self._alternatives["_default"])

        # Format the reason template with available context
        format_vars = {
            "tool_name": tool_name,
            "policy_name": policy_name or "unknown",
            **{k: str(v)[:100] for k, v in arguments.items()},
        }
        try:
            reason = alt_def["reason_template"].format_map(
                _SafeFormatDict(format_vars)
            )
        except Exception:
            reason = f"Action '{tool_name}' was blocked by security policy."

        return SafePlanSuggestion(
            tool_name=tool_name,
            reason=reason,
            alternatives=list(alt_def["alternatives"]),
            risk_level=risk_level,
            policy_name=policy_name,
            original_args=arguments,
        )

    def suggest_for_exception(self, exc: Exception,
                              tool_name: str = "",
                              arguments: Optional[Dict] = None) -> SafePlanSuggestion:
        """Generate a suggestion from an AgentArmor exception.

        Useful for wrapping exceptions from HITL gate, tool firewall, etc.
        """
        exc_type = type(exc).__name__
        exc_msg = str(exc)

        # Infer category from exception type
        category_map = {
            "HumanApprovalDenied": "_default",
            "HumanApprovalRequired": "_default",
            "ToolCallBlocked": "_default",
            "MCPViolation": "_default",
            "TaintViolation": "data_export",
            "DataExfiltrationDetected": "data_export",
            "InsecureCodeDetected": "shell_exec",
            "HoneytoolTriggered": "credential_access",
        }
        category = category_map.get(exc_type, "_default")
        alt_def = self._alternatives.get(category, self._alternatives["_default"])

        return SafePlanSuggestion(
            tool_name=tool_name or "unknown",
            reason=exc_msg,
            alternatives=list(alt_def["alternatives"]),
            risk_level="high",
            policy_name=exc_type,
            original_args=arguments or {},
        )


class _SafeFormatDict(dict):
    """Dict that returns '{key}' for missing keys instead of raising KeyError."""

    def __missing__(self, key):
        return f"{{{key}}}"
