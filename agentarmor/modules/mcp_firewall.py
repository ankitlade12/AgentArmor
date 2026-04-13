"""
MCP Policy Engine v2 --- secures agent-tool communication by validating
MCP servers, enforcing per-tool policies, scanning tool descriptions for
injection attempts, and extracting server identity from mcp_tool_use blocks.

v2 additions over v1:
- Server identity extraction from Anthropic mcp_tool_use content blocks
- Per-server toolset allowlists (which tools may a given server expose)
- Tool result validation (scan tool results for injection/exfiltration)
- Auth-aware server configs (require auth tokens per server)
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
        # v2 additions
        server_toolsets: Optional[Dict[str, List[str]]] = None,
        server_auth: Optional[Dict[str, str]] = None,
        validate_tool_results: bool = False,
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
            server_toolsets: Per-server tool allowlists, e.g.
                {"filesystem-server": ["file_read", "file_write"]}.
                If a server invokes a tool not in its allowlist, it's a violation.
            server_auth: Required auth token per server, e.g.
                {"private-server": "Bearer xyz"}. Validated via validate_server_auth().
            validate_tool_results: If True, scan tool result text for injection patterns.
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

        # v2 state
        self.server_toolsets: Dict[str, List[str]] = server_toolsets or {}
        self.server_auth: Dict[str, str] = server_auth or {}
        self.validate_tool_results: bool = validate_tool_results
        self.server_call_log: List[Dict[str, Any]] = []

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

    def validate_server_auth(self, server_name: str, auth_token: Optional[str] = None) -> bool:
        """Validate that a server provides the expected auth credentials.

        Returns True if no auth is required or the token matches.
        """
        expected = self.server_auth.get(server_name)
        if expected is None:
            return True  # No auth required for this server
        if auth_token != expected:
            self._handle_violation(
                f"Auth mismatch for MCP server '{server_name}': "
                f"expected valid token, got {'<none>' if auth_token is None else '<invalid>'}"
            )
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

            # v2: Per-server toolset enforcement
            if server_name in self.server_toolsets:
                allowed_tools = self.server_toolsets[server_name]
                if tool_name not in allowed_tools:
                    self._handle_violation(
                        f"Tool '{tool_name}' not in allowed toolset "
                        f"for server '{server_name}'. "
                        f"Allowed: {allowed_tools}"
                    )
                    return False

        # Tool-level policy check
        if not self._check_tool_policy(tool_name, arguments):
            self._handle_violation(
                f"Tool policy violation: {tool_name} with args {arguments}"
            )
            return False

        # Log the call
        self.server_call_log.append({
            "tool": tool_name,
            "server": server_name,
            "args_keys": list(arguments.keys()),
        })

        return True

    def validate_tool_result(self, tool_name: str, result_text: str,
                             server_name: Optional[str] = None) -> bool:
        """Scan a tool result for injection patterns or exfiltration signals.

        Returns True if the result is clean, False if suspicious content found.
        """
        if not self.validate_tool_results:
            return True

        for pattern in _INJECTION_RE:
            if pattern.search(result_text):
                self._handle_violation(
                    f"Injection detected in tool result from '{tool_name}'"
                    f"{f' (server: {server_name})' if server_name else ''}: "
                    f"{result_text[:80]}"
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

    def pre_check(self, ctx) -> Any:
        """Before-request hook: scan tool_result messages for injection.

        When validate_tool_results is enabled, scans the content of any
        tool_result messages in the conversation for injection patterns.
        This catches indirect prompt injection via poisoned tool outputs.
        """
        if not self.validate_tool_results:
            return ctx
        for msg in ctx.messages:
            role = msg.get("role", "")
            if role == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    tool_id = msg.get("tool_call_id", "unknown")
                    self.validate_tool_result(
                        tool_name=tool_id, result_text=content,
                    )
        return ctx

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook: inspects tool_use and mcp_tool_use blocks.

        Enforces: max tool calls, per-tool policies, server identity,
        server auth (when server_name is present), and tool result
        scanning on the response text.
        """
        tool_calls = self._extract_tool_calls(ctx)
        if not tool_calls:
            # Even without tool calls, scan response text for tool results
            if self.validate_tool_results and ctx.text:
                self.validate_tool_result("response_text", ctx.text)
            return ctx

        # Enforce max tool calls per request
        if len(tool_calls) > self.max_tool_calls_per_request:
            self._handle_violation(
                f"Too many tool calls ({len(tool_calls)}) in a single request "
                f"(max {self.max_tool_calls_per_request})"
            )

        for call_info in tool_calls:
            name = call_info["name"]
            arguments = call_info["arguments"]
            server = call_info.get("server_name")

            # Server auth check (when server identity is available)
            if server and self.server_auth:
                auth_token = call_info.get("auth_token")
                self.validate_server_auth(server, auth_token)

            self.validate_tool_call(name, arguments, server_name=server)

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
    def _extract_tool_calls(ctx: ResponseContext) -> List[Dict[str, Any]]:
        """Returns a list of dicts with name, arguments, and optional server_name."""
        calls: List[Dict[str, Any]] = []
        raw = ctx.raw_response
        if raw is None:
            return calls

        # Anthropic format: look for both tool_use and mcp_tool_use blocks
        try:
            content = getattr(raw, "content", None)
            if isinstance(content, list):
                for block in content:
                    block_type = getattr(block, "type", None)

                    # Standard tool_use
                    if block_type == "tool_use":
                        name = getattr(block, "name", None)
                        args = getattr(block, "input", {}) or {}
                        if name:
                            calls.append({
                                "name": name,
                                "arguments": args,
                            })

                    # v2: mcp_tool_use — carries server_name
                    elif block_type == "mcp_tool_use":
                        name = getattr(block, "name", None)
                        args = getattr(block, "input", {}) or {}
                        server = getattr(block, "server_name", None)
                        if name:
                            calls.append({
                                "name": name,
                                "arguments": args,
                                "server_name": server,
                            })

                if calls:
                    return calls
        except (AttributeError, TypeError):
            pass

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
                        calls.append({"name": name, "arguments": args})
                if calls:
                    return calls
        except (AttributeError, IndexError, TypeError):
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
            "server_toolsets": {k: list(v) for k, v in self.server_toolsets.items()},
            "server_call_log_size": len(self.server_call_log),
            "validate_tool_results": self.validate_tool_results,
        }
