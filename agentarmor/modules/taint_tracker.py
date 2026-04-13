"""
Runtime Data Lineage / Taint Tracking v1

Tracks data provenance through agent pipelines and enforces policies on
where tainted data can flow. v1 scope: detect when PII or raw user input
reaches privileged tool arguments.

Taint labels:
- "user_input"  : raw user-supplied text (auto-labeled from role="user")
- "pii"         : text containing PII (auto-detected via regex patterns)
- "rag"         : content with RAG markers (auto-detected from role="system"
                  messages containing Document/Source/Context keywords)
- "tool_output" : output returned by a tool call (auto-labeled from role="tool")
- "mcp"         : data from an MCP server (manual via register_taint())

Each label can be restricted from flowing into specific tool arguments
via the `sink_policies` configuration.

v1 limitations:
- "mcp" taint requires manual register_taint() calls; automatic MCP
  server output labeling is planned for v2.
- Taint tracking is text-based (substring/token overlap); semantic
  paraphrase detection is not yet supported.
"""

import re
import threading
from typing import Any, Dict, List, Optional, Set

from ..hooks import RequestContext, ResponseContext

# PII detection patterns (lightweight, zero-dependency)
_PII_PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "phone": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
    "api_key": re.compile(
        r'\b(?:sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})\b'
    ),
}

# Default taint labels
TAINT_USER_INPUT = "user_input"
TAINT_PII = "pii"
TAINT_RAG = "rag"
TAINT_TOOL_OUTPUT = "tool_output"
TAINT_MCP = "mcp"


class TaintedData:
    """A piece of data with provenance labels attached."""

    __slots__ = ("text", "labels", "source")

    def __init__(self, text: str, labels: Set[str], source: str = ""):
        self.text = text
        self.labels = set(labels)
        self.source = source

    def __repr__(self) -> str:
        return f"TaintedData(labels={self.labels}, source={self.source!r}, len={len(self.text)})"


class TaintViolation(Exception):
    """Raised when tainted data reaches a restricted sink."""
    pass


class TaintTrackerModule:
    """Tracks data provenance and enforces taint flow policies.

    v1 scope:
    - Auto-labels user messages as 'user_input'
    - Auto-detects PII in messages and labels as 'pii'
    - Scans tool call arguments in responses for tainted content
    - Enforces sink_policies: which taint labels are blocked from which tools
    """

    def __init__(
        self,
        sink_policies: Optional[Dict[str, List[str]]] = None,
        auto_detect_pii: bool = True,
        on_violation: str = "block",
        track_rag: bool = True,
    ):
        """
        Args:
            sink_policies: Maps tool names to list of blocked taint labels.
                e.g. {"send_email": ["pii"], "web_search": ["pii", "user_input"]}
                Special key "*" applies to all tools.
            auto_detect_pii: Automatically scan messages for PII patterns.
            on_violation: "block" raises TaintViolation, "warn" logs warning.
            track_rag: Auto-label system/context messages as 'rag'.
        """
        self.sink_policies = sink_policies or {}
        self.auto_detect_pii = auto_detect_pii
        self.on_violation = on_violation
        self.track_rag = track_rag

        self._lock = threading.Lock()
        self._tainted_strings: List[TaintedData] = []
        self.violations: List[Dict[str, Any]] = []
        self.stats = {
            "requests_scanned": 0,
            "responses_scanned": 0,
            "pii_detected": 0,
            "taint_violations": 0,
        }

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Before-request hook: label incoming messages with taint.

        Taint accumulates across the session (not cleared per request)
        to support multi-step lineage tracking. Call reset() explicitly
        to clear taint state.
        """
        with self._lock:
            self.stats["requests_scanned"] += 1

        for msg in ctx.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            labels: Set[str] = set()

            # User messages are always tainted as user_input
            if role == "user":
                labels.add(TAINT_USER_INPUT)

            # Tool result messages are automatically tainted as tool_output
            if role == "tool":
                labels.add(TAINT_TOOL_OUTPUT)

            # Only label as RAG if the message looks like retrieved context,
            # not every system message (which would over-taint normal prompts)
            if self.track_rag and self._looks_like_rag(content, role):
                labels.add(TAINT_RAG)

            # Auto-detect PII
            if self.auto_detect_pii and self._contains_pii(content):
                labels.add(TAINT_PII)
                with self._lock:
                    self.stats["pii_detected"] += 1

            if labels:
                td = TaintedData(text=content, labels=labels, source=role)
                with self._lock:
                    self._tainted_strings.append(td)

        return ctx

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook: check tool call args for tainted data."""
        with self._lock:
            self.stats["responses_scanned"] += 1

        tool_calls = self._extract_tool_calls(ctx.raw_response, ctx.provider)
        if not tool_calls:
            return ctx

        with self._lock:
            tainted = list(self._tainted_strings)

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            arguments = tc.get("arguments", {})
            self._check_sink(tool_name, arguments, tainted)

        return ctx

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_taint(self, text: str, labels: Set[str],
                       source: str = "manual") -> None:
        """Manually register tainted data (e.g. from a tool output)."""
        td = TaintedData(text=text, labels=labels, source=source)
        with self._lock:
            self._tainted_strings.append(td)

    def check_text(self, tool_name: str, text: str) -> List[str]:
        """Check if text contains tainted content for a given tool.

        Returns list of violated taint labels, empty if clean.
        """
        with self._lock:
            tainted = list(self._tainted_strings)

        violations = []
        blocked_labels = self._get_blocked_labels(tool_name)
        if not blocked_labels:
            return violations

        for td in tainted:
            matching_labels = td.labels & blocked_labels
            if matching_labels and self._text_overlaps(td.text, text):
                violations.extend(matching_labels)

        return list(set(violations))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_sink(self, tool_name: str, arguments: Dict[str, Any],
                    tainted: List[TaintedData]) -> None:
        """Check tool arguments against taint policies."""
        blocked_labels = self._get_blocked_labels(tool_name)
        if not blocked_labels:
            return

        for arg_name, arg_value in arguments.items():
            if not isinstance(arg_value, str):
                arg_value = str(arg_value)

            for td in tainted:
                matching_labels = td.labels & blocked_labels
                if not matching_labels:
                    continue

                if self._text_overlaps(td.text, arg_value):
                    violation = {
                        "tool": tool_name,
                        "argument": arg_name,
                        "taint_labels": sorted(matching_labels),
                        "taint_source": td.source,
                    }
                    with self._lock:
                        self.violations.append(violation)
                        self.stats["taint_violations"] += 1

                    if self.on_violation == "block":
                        raise TaintViolation(
                            f"Tainted data ({', '.join(sorted(matching_labels))}) "
                            f"from '{td.source}' reached tool '{tool_name}' "
                            f"argument '{arg_name}'"
                        )

    def _get_blocked_labels(self, tool_name: str) -> Set[str]:
        """Get the set of taint labels blocked for a tool."""
        blocked = set()
        # Wildcard policy applies to all tools
        if "*" in self.sink_policies:
            blocked.update(self.sink_policies["*"])
        if tool_name in self.sink_policies:
            blocked.update(self.sink_policies[tool_name])
        return blocked

    @staticmethod
    def _text_overlaps(tainted_text: str, target: str,
                       min_overlap: int = 20) -> bool:
        """Check if tainted text appears in or significantly overlaps target.

        Uses substring matching for short texts and token overlap for longer.
        """
        if not target or not tainted_text:
            return False

        t_lower = tainted_text.lower()
        target_lower = target.lower()

        # Direct substring match (most reliable)
        if len(tainted_text) <= 200:
            # For short tainted text, check if it's a substring
            if t_lower in target_lower or target_lower in t_lower:
                return True
        else:
            # For longer text, check if significant chunks appear
            # Use sliding window of min_overlap chars
            for i in range(0, len(tainted_text) - min_overlap + 1, min_overlap):
                chunk = t_lower[i:i + min_overlap]
                if chunk in target_lower:
                    return True

        # Token-level overlap for fuzzy matching
        t_words = set(t_lower.split())
        target_words = set(target_lower.split())
        if len(t_words) >= 3:
            overlap = t_words & target_words
            if len(overlap) / len(t_words) >= 0.5:
                return True

        return False

    @staticmethod
    def _looks_like_rag(content: str, role: str) -> bool:
        """Heuristic: does this message look like retrieved RAG context?

        Only labels as RAG if the message contains document/source markers
        or if the role is explicitly 'context'. Plain system prompts
        (e.g. 'You are a helpful assistant') are NOT labeled as RAG.
        """
        if role == "context":
            return True
        if role != "system":
            return False
        # Check for common RAG context markers
        lower = content.lower()[:200]
        rag_markers = (
            "document", "source", "context:", "reference",
            "retrieved", "passage", "excerpt", "chunk",
        )
        return any(marker in lower for marker in rag_markers)

    def reset(self) -> None:
        """Clear all taint state. Call between independent sessions."""
        with self._lock:
            self._tainted_strings.clear()

    @staticmethod
    def _contains_pii(text: str) -> bool:
        """Check if text contains PII patterns."""
        for pattern in _PII_PATTERNS.values():
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def _extract_tool_calls(raw_response: Any, provider: str) -> List[Dict]:
        """Extract tool calls from provider responses."""
        calls = []
        if raw_response is None:
            return calls

        try:
            if provider == "openai":
                for choice in getattr(raw_response, "choices", []):
                    msg = getattr(choice, "message", None)
                    for tc in getattr(msg, "tool_calls", []) or []:
                        fn = getattr(tc, "function", None)
                        if fn:
                            import json
                            name = getattr(fn, "name", "")
                            args_str = getattr(fn, "arguments", "{}")
                            try:
                                args = json.loads(args_str) if isinstance(args_str, str) else args_str or {}
                            except (json.JSONDecodeError, TypeError):
                                args = {}
                            calls.append({"name": name, "arguments": args})
            elif provider == "anthropic":
                for block in getattr(raw_response, "content", []):
                    btype = getattr(block, "type", "")
                    if btype in ("tool_use", "mcp_tool_use"):
                        calls.append({
                            "name": getattr(block, "name", ""),
                            "arguments": getattr(block, "input", {}) or {},
                        })
        except Exception:
            pass

        return calls

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self) -> dict:
        with self._lock:
            return {
                "stats": dict(self.stats),
                "violations": self.violations[-10:],
                "sink_policies": {
                    k: list(v) for k, v in self.sink_policies.items()
                },
                "active_tainted_items": len(self._tainted_strings),
            }
