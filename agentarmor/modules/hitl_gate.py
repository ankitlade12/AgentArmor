import re
import time
import threading
from typing import Optional, List, Dict, Any, Callable
from ..exceptions import HumanApprovalRequired, HumanApprovalDenied, HumanApprovalTimeout
from ..hooks import ResponseContext


class PolicyRule:
    """Defines a policy rule for matching tool calls."""

    def __init__(self, name: str, pattern: str, risk_level: str = "high",
                 description: str = "", arg_patterns: Optional[Dict[str, str]] = None):
        """
        Args:
            name: Rule name for audit trail
            pattern: Regex pattern to match tool/function names
            risk_level: 'low', 'medium', 'high', 'critical'
            description: Human-readable description of what this rule catches
            arg_patterns: Dict of arg_name -> regex pattern to match argument values
        """
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.risk_level = risk_level
        self.description = description
        self.arg_patterns = {}
        if arg_patterns:
            self.arg_patterns = {k: re.compile(v, re.IGNORECASE) for k, v in arg_patterns.items()}

    def matches(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a tool call matches this policy rule."""
        if not self.pattern.search(tool_name):
            return False
        if self.arg_patterns and arguments:
            for arg_name, arg_pattern in self.arg_patterns.items():
                arg_value = str(arguments.get(arg_name, ""))
                if arg_pattern.search(arg_value):
                    return True
            # If arg_patterns specified but none matched, only name matched
            return not self.arg_patterns
        return True


# Default high-risk policy rules
DEFAULT_POLICIES = [
    PolicyRule(
        name="file_delete",
        pattern=r"(?:delete|remove|rm|unlink).*(?:file|dir|folder|path)",
        risk_level="critical",
        description="File or directory deletion"
    ),
    PolicyRule(
        name="shell_execute",
        pattern=r"(?:exec|execute|run|shell|bash|cmd|system|subprocess)",
        risk_level="critical",
        description="Shell command execution"
    ),
    PolicyRule(
        name="email_send",
        pattern=r"(?:send|compose|draft).*(?:email|mail|message|notification)",
        risk_level="high",
        description="Sending emails or messages"
    ),
    PolicyRule(
        name="database_write",
        pattern=r"(?:drop|truncate|delete|alter|update|insert).*(?:table|database|collection|index)",
        risk_level="critical",
        description="Database write/destructive operations"
    ),
    PolicyRule(
        name="api_key_access",
        pattern=r"(?:get|read|access|fetch).*(?:secret|key|token|credential|password)",
        risk_level="high",
        description="Accessing secrets or credentials"
    ),
    PolicyRule(
        name="network_request",
        pattern=r"(?:http|fetch|request|curl|wget|post|put|patch)",
        risk_level="medium",
        description="Making network requests"
    ),
    PolicyRule(
        name="file_write",
        pattern=r"(?:write|create|save|overwrite|append).*(?:file|path|disk)",
        risk_level="medium",
        description="Writing files to disk"
    ),
    PolicyRule(
        name="permission_change",
        pattern=r"(?:chmod|chown|grant|revoke).*(?:permission|access|role)",
        risk_level="critical",
        description="Changing permissions or access controls"
    ),
]


class ApprovalRequest:
    """Represents a pending approval request."""

    def __init__(self, tool_name: str, arguments: Dict[str, Any],
                 rule: PolicyRule, context: Optional[str] = None):
        self.tool_name = tool_name
        self.arguments = arguments
        self.rule = rule
        self.risk_level = rule.risk_level
        self.context = context
        self.timestamp = time.time()
        self.decision: Optional[str] = None  # 'approved', 'denied', 'timeout'
        self.decided_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "rule_name": self.rule.name,
            "risk_level": self.risk_level,
            "description": self.rule.description,
            "context": self.context,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "decided_at": self.decided_at,
        }


class HITLGateModule:
    """Human-in-the-Loop gate that requires approval for high-risk actions."""

    def __init__(self, policies: Optional[List[Dict[str, Any]]] = None,
                 approval_callback: Optional[Callable[[ApprovalRequest], bool]] = None,
                 auto_approve_levels: Optional[List[str]] = None,
                 auto_deny_levels: Optional[List[str]] = None,
                 timeout_seconds: float = 300.0,
                 on_timeout: str = "deny",
                 use_defaults: bool = True):
        """
        Args:
            policies: List of policy rule dicts with keys: name, pattern, risk_level, description, arg_patterns
            approval_callback: Function that takes ApprovalRequest, returns True (approve) or False (deny)
            auto_approve_levels: Risk levels to auto-approve (e.g. ['low'])
            auto_deny_levels: Risk levels to auto-deny (e.g. ['critical'])
            timeout_seconds: How long to wait for approval
            on_timeout: 'deny' or 'approve' when timeout expires
            use_defaults: Whether to include default policy rules
        """
        self._lock = threading.Lock()
        self.timeout_seconds = timeout_seconds
        self.on_timeout = on_timeout
        self.approval_callback = approval_callback
        self.auto_approve_levels = set(auto_approve_levels or ["low"])
        self.auto_deny_levels = set(auto_deny_levels or [])

        self.policies: List[PolicyRule] = []
        if use_defaults:
            self.policies.extend(DEFAULT_POLICIES)
        if policies:
            for p in policies:
                self.policies.append(PolicyRule(**p))

        self.audit_log: List[Dict[str, Any]] = []
        self.stats = {
            "total_checks": 0,
            "approved": 0,
            "denied": 0,
            "auto_approved": 0,
            "auto_denied": 0,
            "timeouts": 0,
            "no_match": 0,
        }

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Post-response hook: check tool calls against policies."""
        tool_calls = self._extract_tool_calls(ctx.raw_response, ctx.provider)

        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            arguments = tool_call.get("arguments", {})

            with self._lock:
                self.stats["total_checks"] += 1

            matched_rule = self._match_policy(tool_name, arguments)
            if not matched_rule:
                with self._lock:
                    self.stats["no_match"] += 1
                continue

            request = ApprovalRequest(
                tool_name=tool_name,
                arguments=arguments,
                rule=matched_rule,
                context=ctx.text[:200] if ctx.text else None,
            )

            decision = self._evaluate(request)

            with self._lock:
                self.audit_log.append(request.to_dict())

            if decision == "denied":
                raise HumanApprovalDenied(
                    f"Action '{tool_name}' denied by policy '{matched_rule.name}' "
                    f"(risk: {matched_rule.risk_level}): {matched_rule.description}"
                )
            elif decision == "timeout":
                raise HumanApprovalTimeout(
                    f"Approval timed out for '{tool_name}' "
                    f"(policy: {matched_rule.name}, risk: {matched_rule.risk_level})"
                )
            elif decision == "pending":
                raise HumanApprovalRequired(
                    f"Action '{tool_name}' requires human approval "
                    f"(policy: {matched_rule.name}, risk: {matched_rule.risk_level}): "
                    f"{matched_rule.description}"
                )

        return ctx

    def _match_policy(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[PolicyRule]:
        """Find the first matching policy rule for a tool call."""
        for rule in self.policies:
            if rule.matches(tool_name, arguments):
                return rule
        return None

    def _evaluate(self, request: ApprovalRequest) -> str:
        """Evaluate an approval request and return decision."""
        # Auto-approve
        if request.risk_level in self.auto_approve_levels:
            request.decision = "approved"
            request.decided_at = time.time()
            with self._lock:
                self.stats["auto_approved"] += 1
            return "approved"

        # Auto-deny
        if request.risk_level in self.auto_deny_levels:
            request.decision = "denied"
            request.decided_at = time.time()
            with self._lock:
                self.stats["auto_denied"] += 1
            return "denied"

        # Call approval callback if provided
        if self.approval_callback:
            try:
                approved = self.approval_callback(request)
                request.decision = "approved" if approved else "denied"
                request.decided_at = time.time()
                with self._lock:
                    if approved:
                        self.stats["approved"] += 1
                    else:
                        self.stats["denied"] += 1
                return request.decision
            except TimeoutError:
                request.decision = "timeout"
                request.decided_at = time.time()
                with self._lock:
                    self.stats["timeouts"] += 1
                return "timeout"

        # No callback - raise for human approval
        request.decision = "pending"
        with self._lock:
            self.stats["denied"] += 1
        return "pending"

    def _extract_tool_calls(self, raw_response: Any, provider: str) -> List[Dict[str, Any]]:
        """Extract tool calls from provider-specific responses."""
        tool_calls = []
        try:
            if provider == "openai":
                for choice in getattr(raw_response, 'choices', []):
                    msg = getattr(choice, 'message', None)
                    if msg:
                        for tc in getattr(msg, 'tool_calls', []) or []:
                            fn = getattr(tc, 'function', None)
                            if fn:
                                import json
                                name = getattr(fn, 'name', '')
                                args_str = getattr(fn, 'arguments', '{}')
                                try:
                                    args = json.loads(args_str)
                                except (json.JSONDecodeError, TypeError):
                                    args = {}
                                tool_calls.append({"name": name, "arguments": args})
            elif provider == "anthropic":
                for block in getattr(raw_response, 'content', []):
                    if getattr(block, 'type', '') == 'tool_use':
                        tool_calls.append({
                            "name": getattr(block, 'name', ''),
                            "arguments": getattr(block, 'input', {}),
                        })
            elif provider == "gemini":
                for candidate in getattr(raw_response, 'candidates', []):
                    content = getattr(candidate, 'content', None)
                    if content:
                        for part in getattr(content, 'parts', []):
                            fc = getattr(part, 'function_call', None)
                            if fc:
                                tool_calls.append({
                                    "name": getattr(fc, 'name', ''),
                                    "arguments": dict(getattr(fc, 'args', {})),
                                })
        except Exception:
            pass
        return tool_calls

    def check_action(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """
        Standalone method to check an action against policies.
        Returns: 'approved', 'denied', 'pending', or 'no_match'
        """
        with self._lock:
            self.stats["total_checks"] += 1

        matched_rule = self._match_policy(tool_name, arguments)
        if not matched_rule:
            with self._lock:
                self.stats["no_match"] += 1
            return "no_match"

        request = ApprovalRequest(tool_name=tool_name, arguments=arguments or {}, rule=matched_rule)
        decision = self._evaluate(request)
        with self._lock:
            self.audit_log.append(request.to_dict())
        return decision

    def report(self) -> dict:
        with self._lock:
            return {
                "stats": dict(self.stats),
                "audit_log_size": len(self.audit_log),
                "recent_decisions": self.audit_log[-10:],
                "policies_count": len(self.policies),
            }
