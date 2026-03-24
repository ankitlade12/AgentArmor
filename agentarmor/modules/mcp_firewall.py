"""
MCP (Model Context Protocol) Server Firewall --- secures agent-tool
communication by validating MCP servers, enforcing per-tool policies,
and scanning tool descriptions for injection attempts.
"""

import re
import warnings
from typing import Any, Dict, List, Optional

from ..exceptions import MCPViolation
from ..hooks import ResponseContext
from ..modules.shield import INJECTION_PATTERNS

# Pre-compiled injection patterns reused from the shield module
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


class MCPFirewallModule:
    """Post-response hook that inspects MCP tool calls and enforces security policies."""

    def __init__(
        self,
        trusted_servers: Optional[List[str]] = None,
        blocked_servers: Optional[List[str]] = None,
        tool_policies: Optional[Dict[str, Dict]] = None,
        scan_descriptions: bool = True,
        max_tool_calls_per_request: int = 10,
        on_violation: str = "block",
    ):
        """
        Args:
            trusted_servers: Allowlist of MCP server names/URIs.
            blocked_servers: Blocklist of MCP server names/URIs.
            tool_policies: Per-tool policies, e.g.
                {"file_read": {"allow_paths": ["/safe/"], "block_paths": ["/etc/"]}}.
            scan_descriptions: Scan MCP tool descriptions for injection attempts.
            max_tool_calls_per_request: Max tool calls in a single agent turn.
            on_violation: "block" raises MCPViolation, "warn" logs a warning.
        """
        if on_violation not in ("block", "warn"):
            raise ValueError(
                f"on_violation must be 'block' or 'warn', got {on_violation!r}."
            )

        self.trusted_servers: set = set(trusted_servers or [])
        self.blocked_servers: set = set(blocked_servers or [])
        self.tool_policies: Dict[str, Dict] = tool_policies or {}
        self.scan_descriptions: bool = scan_descriptions
        self.max_tool_calls_per_request: int = max_tool_calls_per_request
        self.on_violation: str = on_violation
        self.violations: List[str] = []
        self.scanned_tools: int = 0
        self.blocked_calls: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_server(self, server_name: str, server_uri: Optional[str] = None) -> bool:
        """Check if an MCP server is trusted.

        Returns True if the server passes validation, False otherwise.
        """
        if self.blocked_servers and server_name in self.blocked_servers:
            self._handle_violation(f"Blocked MCP server: {server_name}")
            return False
        if self.trusted_servers and server_name not in self.trusted_servers:
            self._handle_violation(f"Untrusted MCP server: {server_name}")
            return False
        return True

    def validate_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        server_name: Optional[str] = None,
    ) -> bool:
        """Validate an MCP tool call against policies.

        Returns True if the call is allowed, False otherwise.
        """
        self.scanned_tools += 1

        # Server-level check
        if server_name is not None:
            if not self.validate_server(server_name):
                return False

        # Tool-level policy check
        if not self._check_tool_policy(tool_name, arguments):
            self._handle_violation(
                f"Tool policy violation: {tool_name} with args {arguments}"
            )
            return False

        return True

    def scan_tool_description(self, tool_name: str, description: str) -> bool:
        """Scan an MCP tool description for hidden injection attempts.

        Returns True if the description is safe, False if injection detected.
        """
        self.scanned_tools += 1
        for pattern in _INJECTION_RE:
            if pattern.search(description):
                self._handle_violation(
                    f"Injection detected in tool description for '{tool_name}': "
                    f"{description[:80]}"
                )
                return False
        return True

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook that inspects tool_use blocks and validates them.

        Note: server-level validation does not happen here because the MCP server
        identity is not available in the response body. Use :meth:`validate_server`
        at tool-registration time for server-level checks.
        """
        tool_calls = self._extract_tool_calls(ctx)
        if not tool_calls:
            return ctx

        # Enforce max tool calls per request
        if len(tool_calls) > self.max_tool_calls_per_request:
            self._handle_violation(
                f"Too many tool calls ({len(tool_calls)}) in a single request "
                f"(max {self.max_tool_calls_per_request})"
            )

        # Delegate to validate_tool_call so scanned_tools & policies are
        # applied consistently and do not double-count with direct API calls.
        for name, arguments in tool_calls:
            self.validate_tool_call(name, arguments)

        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_violation(self, reason: str):
        self.violations.append(reason)
        self.blocked_calls += 1
        if self.on_violation == "block":
            raise MCPViolation(reason)
        else:
            warnings.warn(
                f"[AgentArmor] MCP WARNING: {reason}",
                stacklevel=3,
            )

    def _check_tool_policy(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Check tool-specific argument policies."""
        policy = self.tool_policies.get(tool_name, {})
        if not policy:
            return True

        # Check path-based policies
        allow_paths = policy.get("allow_paths", [])
        block_paths = policy.get("block_paths", [])

        for _key, value in arguments.items():
            if isinstance(value, str):
                # Check blocked paths
                for blocked in block_paths:
                    if value.startswith(blocked) or blocked in value:
                        return False
                # Check allowed paths (if allowlist specified, path must match)
                if allow_paths:
                    if not any(value.startswith(p) for p in allow_paths):
                        return False

        # Check argument value restrictions
        allowed_values = policy.get("allowed_values", {})
        for key, allowed in allowed_values.items():
            if key in arguments and arguments[key] not in allowed:
                return False

        # Check blocked argument patterns (regex)
        blocked_patterns = policy.get("blocked_patterns", {})
        for key, pattern in blocked_patterns.items():
            if key in arguments:
                if re.search(pattern, str(arguments[key])):
                    return False

        return True

    @staticmethod
    def _extract_tool_calls(ctx: ResponseContext) -> List[tuple]:
        """Returns a list of (tool_name, arguments) tuples from the raw response."""
        calls: List[tuple] = []
        raw = ctx.raw_response
        if raw is None:
            return calls

        # OpenAI format: response.choices[0].message.tool_calls
        try:
            tool_calls = getattr(
                getattr(raw.choices[0], "message", None), "tool_calls", None
            )
            if tool_calls:
                import json as _json

                for tc in tool_calls:
                    func = getattr(tc, "function", None)
                    name = getattr(func, "name", None)
                    args_str = getattr(func, "arguments", "{}")
                    if name:
                        try:
                            args = _json.loads(args_str) if isinstance(args_str, str) else args_str or {}
                        except (ValueError, TypeError):
                            args = {}
                        calls.append((name, args))
                if calls:
                    return calls
        except (AttributeError, IndexError, TypeError):
            pass

        # Anthropic format: response.content -- list of blocks with type=="tool_use"
        try:
            content = getattr(raw, "content", None)
            if isinstance(content, list):
                for block in content:
                    if getattr(block, "type", None) == "tool_use":
                        name = getattr(block, "name", None)
                        args = getattr(block, "input", {}) or {}
                        if name:
                            calls.append((name, args))
        except (AttributeError, TypeError):
            pass

        return calls

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self) -> dict:
        return {
            "scanned_tools": self.scanned_tools,
            "blocked_calls": self.blocked_calls,
            "violations": self.violations[-10:],
            "trusted_servers": list(self.trusted_servers),
            "blocked_servers": list(self.blocked_servers),
        }
