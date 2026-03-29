import re
import threading
from typing import Optional, List, Dict, Any, Set
from ..exceptions import PrivilegeEscalationDetected
from ..hooks import RequestContext, ResponseContext


# Patterns indicating privilege escalation attempts in LLM outputs
ESCALATION_PATTERNS = {
    "tool_request": [
        re.compile(r"(?:i need|i require|give me|grant me|enable|activate|add)\s+(?:access to\s+)?(?:the\s+|a\s+)?(?:\w+\s+)*?(?:tool|function|capability|permission|api)", re.IGNORECASE),
        re.compile(r"(?:can you|please)\s+(?:add|enable|give|grant|unlock)\s+(?:the\s+)?(?:tool|function|capability|api|access)", re.IGNORECASE),
        re.compile(r"(?:i should have|i need to have|i want)\s+(?:access|permission|ability|capability)\s+to", re.IGNORECASE),
    ],
    "instruction_modification": [
        re.compile(r"(?:update|change|modify|edit|rewrite|override)\s+(?:my|the|your)?\s*(?:system\s+)?(?:instructions|prompt|rules|guidelines|configuration|config)", re.IGNORECASE),
        re.compile(r"(?:my|the)\s+(?:instructions|rules|guidelines)\s+(?:should|need to|must)\s+(?:be\s+)?(?:changed|updated|modified)", re.IGNORECASE),
        re.compile(r"(?:new|updated)\s+system\s+(?:prompt|instructions|message)", re.IGNORECASE),
        re.compile(r"(?:ignore|disregard|bypass|skip|disable)\s+(?:the\s+)?(?:safety|security|restriction|filter|guard|check|rule)", re.IGNORECASE),
    ],
    "self_delegation": [
        re.compile(r"(?:i(?:'ll| will| shall| am going to))\s+(?:create|spawn|start|launch|run)\s+(?:a\s+)?(?:new\s+)?(?:agent|subprocess|worker|task|instance|thread)", re.IGNORECASE),
        re.compile(r"(?:spawn|create|start|initialize)\s+(?:a\s+)?(?:sub-?agent|child\s+agent|new\s+agent|worker|helper)", re.IGNORECASE),
        re.compile(r"(?:delegate|hand off|pass)\s+(?:this\s+)?(?:to|task)\s+(?:another|a new|a different)\s+(?:agent|process|worker)", re.IGNORECASE),
    ],
    "capability_probing": [
        re.compile(r"(?:what|which|list|show|tell me)\s+(?:tools|functions|capabilities|permissions|apis|actions)\s+(?:do i|can i|are|i)\s+(?:have|use|access|available)", re.IGNORECASE),
        re.compile(r"(?:what\s+(?:can|am)\s+i\s+(?:able to|allowed to|permitted to)\s+(?:do|access|use|call))", re.IGNORECASE),
        re.compile(r"(?:list|enumerate|show)\s+(?:all\s+)?(?:my\s+)?(?:available\s+|accessible\s+)?(?:tools|functions|capabilities|permissions)", re.IGNORECASE),
    ],
    "scope_expansion": [
        re.compile(r"(?:access|read|write|modify|delete|open|connect to)\s+(?:the\s+)?(?:file system|database|network|internet|external|admin|root)", re.IGNORECASE),
        re.compile(r"(?:sudo|admin|root|superuser|elevated|privileged)\s+(?:access|mode|privileges|rights|permissions)", re.IGNORECASE),
        re.compile(r"(?:escalate|elevate|increase|expand)\s+(?:my\s+)?(?:privileges|permissions|access|scope|rights|role)", re.IGNORECASE),
    ],
    "safety_bypass": [
        re.compile(r"(?:disable|turn off|deactivate|remove|bypass)\s+(?:the\s+)?(?:safety|security|content|moderation|filtering|guardrails|restrictions)", re.IGNORECASE),
        re.compile(r"(?:without|no)\s+(?:safety|security|content|moderation)\s+(?:checks|filters|restrictions|measures|guardrails)", re.IGNORECASE),
        re.compile(r"(?:override|bypass|circumvent|work around)\s+(?:the\s+)?(?:safety|security|access|permission)\s+(?:controls|checks|system|measures)", re.IGNORECASE),
    ],
}


class PrivilegeEscalationModule:
    """Detects privilege escalation attempts in LLM outputs and tool calls."""

    def __init__(self, on_detect: str = "block",
                 allowed_tools: Optional[List[str]] = None,
                 check_output: bool = True,
                 check_tool_calls: bool = True,
                 categories: Optional[List[str]] = None,
                 custom_patterns: Optional[Dict[str, List[str]]] = None):
        """
        Args:
            on_detect: 'block' or 'warn'
            allowed_tools: Whitelist of tool names the agent is allowed to call
            check_output: Whether to scan LLM text output for escalation language
            check_tool_calls: Whether to validate tool calls against allowed_tools
            categories: Which categories to check (None = all)
            custom_patterns: Additional patterns per category
        """
        self.on_detect = on_detect
        self.allowed_tools: Optional[Set[str]] = set(allowed_tools) if allowed_tools else None
        self.check_output = check_output
        self.check_tool_calls = check_tool_calls
        self.active_categories = set(categories) if categories else set(ESCALATION_PATTERNS.keys())
        self._lock = threading.Lock()
        self.detections: List[Dict[str, Any]] = []

        # Build pattern list
        self.patterns: Dict[str, List[re.Pattern]] = {}
        for category in self.active_categories:
            if category in ESCALATION_PATTERNS:
                self.patterns[category] = list(ESCALATION_PATTERNS[category])

        if custom_patterns:
            for category, pattern_strs in custom_patterns.items():
                if category not in self.patterns:
                    self.patterns[category] = []
                self.patterns[category].extend(
                    [re.compile(p, re.IGNORECASE) for p in pattern_strs]
                )

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Post-response hook: scan output for privilege escalation."""
        findings = []

        if self.check_output and ctx.text:
            text_findings = self._scan_text(ctx.text)
            findings.extend(text_findings)

        if self.check_tool_calls and ctx.raw_response:
            tool_findings = self._check_tool_calls(ctx.raw_response, ctx.provider)
            findings.extend(tool_findings)

        if findings:
            with self._lock:
                self.detections.extend(findings)
            if self.on_detect == "block":
                raise PrivilegeEscalationDetected(
                    f"Privilege escalation detected: {findings[0]['category']} - {findings[0]['detail'][:150]}"
                )

        return ctx

    def _scan_text(self, text: str) -> List[Dict[str, Any]]:
        """Scan text for privilege escalation patterns."""
        findings = []
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    findings.append({
                        "category": category,
                        "detail": f"Pattern matched: '{match.group()}'",
                        "matched_text": match.group(),
                        "position": match.start(),
                    })
                    break  # One finding per category is enough
        return findings

    def _check_tool_calls(self, raw_response: Any, provider: str) -> List[Dict[str, Any]]:
        """Check if tool calls attempt to use unauthorized tools."""
        if self.allowed_tools is None:
            return []

        findings = []
        tool_names = self._extract_tool_names(raw_response, provider)

        for tool_name in tool_names:
            if tool_name not in self.allowed_tools:
                findings.append({
                    "category": "unauthorized_tool",
                    "detail": f"Agent attempted to call unauthorized tool: '{tool_name}'",
                    "tool_name": tool_name,
                })

        return findings

    def _extract_tool_names(self, raw_response: Any, provider: str) -> List[str]:
        """Extract tool call names from provider responses."""
        names = []
        try:
            if provider == "openai":
                for choice in getattr(raw_response, 'choices', []):
                    msg = getattr(choice, 'message', None)
                    if msg:
                        for tc in getattr(msg, 'tool_calls', []) or []:
                            fn = getattr(tc, 'function', None)
                            if fn:
                                names.append(getattr(fn, 'name', ''))
            elif provider == "anthropic":
                for block in getattr(raw_response, 'content', []):
                    if getattr(block, 'type', '') == 'tool_use':
                        names.append(getattr(block, 'name', ''))
            elif provider == "gemini":
                for candidate in getattr(raw_response, 'candidates', []):
                    content = getattr(candidate, 'content', None)
                    if content:
                        for part in getattr(content, 'parts', []):
                            fc = getattr(part, 'function_call', None)
                            if fc:
                                names.append(getattr(fc, 'name', ''))
        except Exception:
            pass
        return names

    def report(self) -> dict:
        with self._lock:
            by_category: Dict[str, int] = {}
            for d in self.detections:
                cat = d.get("category", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1

            return {
                "detections": len(self.detections),
                "by_category": by_category,
                "samples": self.detections[:5],
            }
