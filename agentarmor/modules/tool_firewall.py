"""
Tool-Call Firewall — intercepts LLM tool/function calls and enforces
an allowlist or blocklist policy.
"""

import warnings
from typing import List, Optional

from ..exceptions import ToolCallBlocked
from ..hooks import ResponseContext


class ToolFirewallModule:
    """Post-response hook that inspects tool calls and blocks unauthorized ones."""

    def __init__(
        self,
        allow: Optional[List[str]] = None,
        block: Optional[List[str]] = None,
        on_violation: str = "block",
    ):
        if allow and block:
            raise ValueError(
                "Cannot specify both 'allow' and 'block'. Choose one mode."
            )
        if on_violation not in ("block", "strip"):
            raise ValueError(
                f"on_violation must be 'block' or 'strip', got {on_violation!r}."
            )

        self.allow = [n.lower() for n in allow] if allow else None
        self.block = [n.lower() for n in block] if block else None
        self.on_violation = on_violation
        self.violations = 0
        self.blocked_tools: List[str] = []

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook that checks tool calls against the policy."""
        tool_calls = self._extract_tool_calls(ctx)
        if not tool_calls:
            return ctx

        violating = self._find_violations(tool_calls)
        if not violating:
            return ctx

        self.violations += len(violating)
        self.blocked_tools.extend(violating)

        if self.on_violation == "block":
            raise ToolCallBlocked(
                f"Blocked tool call(s): {', '.join(violating)}"
            )

        # strip mode — remove violating tool calls from the response
        warnings.warn(
            f"[AgentArmor] Tool call(s) stripped from response: {', '.join(violating)}",
            stacklevel=2,
        )
        self._strip_tool_calls(ctx, violating)
        return ctx

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tool_calls(ctx: ResponseContext) -> List[str]:
        """Returns a list of tool/function names from the raw response."""
        names: List[str] = []
        raw = ctx.raw_response
        if raw is None:
            return names

        # OpenAI Chat Completions: choices[0].message.tool_calls
        try:
            tool_calls = getattr(
                getattr(raw.choices[0], "message", None), "tool_calls", None
            )
            if tool_calls:
                for tc in tool_calls:
                    name = getattr(getattr(tc, "function", None), "name", None)
                    if name:
                        names.append(name)
                if names:
                    return names
        except (AttributeError, IndexError, TypeError):
            pass

        # OpenAI Responses API: output[*] with type="function_call"
        try:
            for item in getattr(raw, "output", []):
                if getattr(item, "type", "") == "function_call":
                    name = getattr(item, "name", None)
                    if name:
                        names.append(name)
            if names:
                return names
        except (AttributeError, TypeError):
            pass

        # Anthropic format: response.content — list of blocks with type=="tool_use"
        try:
            content = getattr(raw, "content", None)
            if isinstance(content, list):
                for block in content:
                    if getattr(block, "type", None) == "tool_use":
                        name = getattr(block, "name", None)
                        if name:
                            names.append(name)
        except (AttributeError, TypeError):
            pass

        return names

    def _find_violations(self, tool_names: List[str]) -> List[str]:
        """Returns tool names that violate the current policy."""
        violating: List[str] = []
        for name in tool_names:
            lower = name.lower()
            if self.allow is not None and lower not in self.allow:
                violating.append(name)
            elif self.block is not None and lower in self.block:
                violating.append(name)
        return violating

    @staticmethod
    def _strip_tool_calls(ctx: ResponseContext, violating: List[str]) -> None:
        """Removes violating tool calls from the raw response in-place."""
        raw = ctx.raw_response
        if raw is None:
            return

        lower_set = {v.lower() for v in violating}

        # OpenAI format
        try:
            msg = raw.choices[0].message
            if msg.tool_calls:
                msg.tool_calls = [
                    tc
                    for tc in msg.tool_calls
                    if getattr(getattr(tc, "function", None), "name", "").lower()
                    not in lower_set
                ]
        except (AttributeError, IndexError, TypeError):
            pass

        # Anthropic format
        try:
            content = raw.content
            if isinstance(content, list):
                raw.content = [
                    block
                    for block in content
                    if not (
                        getattr(block, "type", None) == "tool_use"
                        and getattr(block, "name", "").lower() in lower_set
                    )
                ]
        except (AttributeError, TypeError):
            pass

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self) -> dict:
        return {
            "violations": self.violations,
            "blocked_tools": list(set(self.blocked_tools)),
        }
