import re
import time
import threading
from typing import Optional, List, Dict, Any, Callable
from ..exceptions import HumanApprovalRequired, HumanApprovalDenied, HumanApprovalTimeout
from ..hooks import ResponseContext


class PolicyRule:
    """Defines a policy rule for matching exact tool calls."""

    def __init__(self, name: str, tool_names: List[str], risk_level: str = "high",
                 description: str = "", arg_patterns: Optional[Dict[str, str]] = None):
        """
        Args:
            name: Rule name for audit trail
            tool_names: List of exact tool names this rule applies to
            risk_level: 'low', 'medium', 'high', 'critical'
            description: Human-readable description of what this rule catches
            arg_patterns: Dict of arg_name -> regex pattern to match argument values (optional)
        """
        self.name = name
        self.tool_names = set(tool_names)
        self.risk_level = risk_level
        self.description = description
        self.arg_patterns = {}
        if arg_patterns:
            self.arg_patterns = {k: re.compile(v, re.IGNORECASE) for k, v in arg_patterns.items()}

    def matches(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a tool call strictly matches this policy rule."""
        if tool_name not in self.tool_names:
            return False

        if self.arg_patterns and arguments:
            for arg_name, arg_pattern in self.arg_patterns.items():
                arg_value = str(arguments.get(arg_name, ""))
                if arg_pattern.search(arg_value):
                    return True
            return not self.arg_patterns
        return True


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
    """Human-in-the-Loop gate that requires approval for explicitly mapped tool actions."""

    def __init__(self, policies: Optional[List[Dict[str, Any]]] = None,
                 risk_map: Optional[Dict[str, str]] = None,
                 approval_callback: Optional[Callable[[ApprovalRequest], bool]] = None,
                 auto_approve_levels: Optional[List[str]] = None,
                 auto_deny_levels: Optional[List[str]] = None,
                 timeout_seconds: float = 300.0,
                 on_timeout: str = "deny",
                 default_risk: str = "low"):
        """
        Args:
            policies: List of policy rule dicts with keys: name, tool_names, risk_level, description, arg_patterns
            risk_map: Simplified dict mapping precise tool names to risk levels.
            approval_callback: Function that takes ApprovalRequest, returns True (approve) or False (deny)
            auto_approve_levels: Risk levels to auto-approve (e.g. ['low'])
            auto_deny_levels: Risk levels to auto-deny (e.g. ['critical'])
            timeout_seconds: How long to wait for approval
            on_timeout: 'deny' or 'approve' when timeout expires
            default_risk: The default risk level assigned to a tool if it has no mapping.
        """
        self._lock = threading.Lock()
        self.timeout_seconds = timeout_seconds
        self.on_timeout = on_timeout
        self.approval_callback = approval_callback
        self.auto_approve_levels = set(auto_approve_levels or ["low"])
        self.auto_deny_levels = set(auto_deny_levels or [])
        self.default_risk = default_risk

        self.policies: List[PolicyRule] = []
        
        # Load risk_map simplified definitions
        if risk_map:
            for tool_name, risk in risk_map.items():
                self.policies.append(PolicyRule(
                    name=f"implicit_{tool_name}",
                    tool_names=[tool_name],
                    risk_level=risk,
                    description=f"Action '{tool_name}' explicitly mapped to {risk} risk."
                ))
                
        # Load explicit wide policies
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
            "unmapped": 0,
        }

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Post-response hook: check tool calls against strictly explicit policies."""
        tool_calls = self._extract_tool_calls(ctx.raw_response, ctx.provider)

        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            arguments = tool_call.get("arguments", {})

            with self._lock:
                self.stats["total_checks"] += 1

            matched_rule = self._match_policy(tool_name, arguments)
            
            # Deterministic missing tool fallback
            if not matched_rule:
                with self._lock:
                    self.stats["unmapped"] += 1
                matched_rule = PolicyRule(
                    name="unmapped_tool",
                    tool_names=[tool_name],
                    risk_level=self.default_risk,
                    description=f"Tool '{tool_name}' was not explicitly registered. Defaulting to: {self.default_risk}"
                )

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
        """Find the first exactly mapped deterministic policy rule."""
        for rule in self.policies:
            if rule.matches(tool_name, arguments):
                return rule
        return None

    def _evaluate(self, request: ApprovalRequest) -> str:
        """Evaluate an approval request and return decision."""
        # Auto-approve completely skips the callback
        if request.risk_level in self.auto_approve_levels:
            request.decision = "approved"
            request.decided_at = time.time()
            with self._lock:
                self.stats["auto_approved"] += 1
            return "approved"

        # Auto-deny completely skips the callback
        if request.risk_level in self.auto_deny_levels:
            request.decision = "denied"
            request.decided_at = time.time()
            with self._lock:
                self.stats["auto_denied"] += 1
            return "denied"

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
            except Exception:
                request.decision = "denied"
                request.decided_at = time.time()
                with self._lock:
                    self.stats["denied"] += 1
                return "denied"

        # No callback given
        request.decision = "pending"
        with self._lock:
            self.stats["denied"] += 1
        return "pending"

    def _extract_tool_calls(self, raw_response: Any, provider: str) -> List[Dict[str, Any]]:
        """Extract tool calls from provider-specific responses."""
        tool_calls = []
        try:
            if provider == "openai":
                # Chat Completions format
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
                # Responses API format
                for item in getattr(raw_response, 'output', []):
                    if getattr(item, 'type', '') == 'function_call':
                        import json
                        name = getattr(item, 'name', '')
                        args_raw = getattr(item, 'arguments', '{}')
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw or {}
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
        Standalone method to manually check an action against explicit policies.
        Returns: 'approved', 'denied', or 'pending'
        """
        with self._lock:
            self.stats["total_checks"] += 1

        matched_rule = self._match_policy(tool_name, arguments)
        if not matched_rule:
            with self._lock:
                self.stats["unmapped"] += 1
            matched_rule = PolicyRule(
                name="unmapped_tool",
                tool_names=[tool_name],
                risk_level=self.default_risk,
                description=f"Tool not mapped"
            )

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
