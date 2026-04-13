"""
Honeytools / Deception Rail

Deploys fake tools, fake credentials, and decoy documents as tripwires
to detect reconnaissance, prompt injection, and data exfiltration attempts.

When a compromised or jailbroken agent tries to use a honeytool (e.g.
``get_admin_credentials``, ``export_all_users``), it triggers an alert
instead of executing. This catches attacks early — before real tools
are misused.
"""

import time
import threading
import uuid
from typing import Any, Dict, List, Optional

from ..hooks import ResponseContext


# Default honeytools — attractive names that a compromised agent would reach for
DEFAULT_HONEYTOOLS = [
    {
        "name": "get_admin_credentials",
        "description": "Retrieves administrator login credentials for the system.",
    },
    {
        "name": "export_all_users",
        "description": "Exports the complete user database including emails and passwords.",
    },
    {
        "name": "read_env_secrets",
        "description": "Reads all environment variables including API keys and secrets.",
    },
    {
        "name": "execute_shell",
        "description": "Executes an arbitrary shell command on the server.",
    },
    {
        "name": "disable_security",
        "description": "Disables all security checks and monitoring for the current session.",
    },
]

# Default honeytokens — fake credentials that appear real
DEFAULT_HONEYTOKENS = [
    {"type": "api_key", "value": "sk-honey-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"},
    {"type": "password", "value": "admin_p@ssw0rd_2026!"},
    {"type": "aws_key", "value": "AKIAHONEY0000000TRAP"},
    {"type": "database_url", "value": "postgresql://admin:honey_trap@db.internal:5432/prod"},
]


class HoneytoolTriggered(Exception):
    """Raised when an agent attempts to use a honeytool."""
    pass


class HoneytoolsModule:
    """Deploys deception-based tripwires to catch compromised agents.

    Works as a post-response hook that scans tool calls in model output
    for honeytool names. Any match is an immediate red flag — legitimate
    agents should never call these tools.
    """

    def __init__(
        self,
        honeytools: Optional[List[Dict[str, str]]] = None,
        honeytokens: Optional[List[Dict[str, str]]] = None,
        custom_honeytools: Optional[List[Dict[str, str]]] = None,
        on_trigger: str = "block",
        include_defaults: bool = True,
    ):
        """
        Args:
            honeytools: Complete list of honeytool definitions (overrides defaults).
            honeytokens: Fake credentials to detect in tool arguments/output.
            custom_honeytools: Additional honeytools appended to defaults.
            on_trigger: "block" raises HoneytoolTriggered, "alert" logs and continues.
            include_defaults: Whether to include DEFAULT_HONEYTOOLS and DEFAULT_HONEYTOKENS.
        """
        if on_trigger not in ("block", "alert"):
            raise ValueError(f"on_trigger must be 'block' or 'alert', got {on_trigger!r}")

        self.on_trigger = on_trigger
        self._lock = threading.Lock()

        # Build honeytool registry
        if honeytools is not None:
            self._honeytools = {t["name"]: t for t in honeytools}
        elif include_defaults:
            self._honeytools = {t["name"]: t for t in DEFAULT_HONEYTOOLS}
        else:
            self._honeytools = {}

        if custom_honeytools:
            for t in custom_honeytools:
                self._honeytools[t["name"]] = t

        # Build honeytoken registry
        if honeytokens is not None:
            self._honeytokens = list(honeytokens)
        elif include_defaults:
            self._honeytokens = list(DEFAULT_HONEYTOKENS)
        else:
            self._honeytokens = []

        # Alert log
        self.alerts: List[Dict[str, Any]] = []
        self.stats = {
            "tool_triggers": 0,
            "token_triggers": 0,
            "total_scanned": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> List[Dict[str, str]]:
        """Return honeytool definitions for injection into tool lists.

        Use this to add honeytools to the model's available tools.
        The model should never call these — if it does, it's compromised.
        """
        return list(self._honeytools.values())

    def add_honeytool(self, name: str, description: str = "") -> None:
        """Register a new honeytool at runtime."""
        self._honeytools[name] = {"name": name, "description": description}

    def add_honeytoken(self, token_type: str, value: str) -> None:
        """Register a new honeytoken at runtime."""
        self._honeytokens.append({"type": token_type, "value": value})

    def check_tool_call(self, tool_name: str,
                        arguments: Optional[Dict] = None) -> bool:
        """Check if a tool call is a honeytool.

        Returns True if it's a honeytool (triggered), False if clean.
        """
        if tool_name in self._honeytools:
            self._trigger_alert("honeytool_called", {
                "tool_name": tool_name,
                "arguments": arguments or {},
                "honeytool_def": self._honeytools[tool_name],
            })
            return True
        return False

    def check_text_for_tokens(self, text: str) -> List[Dict]:
        """Scan text for honeytokens.

        Returns list of matched tokens (empty if clean).
        """
        matches = []
        for token in self._honeytokens:
            if token["value"] in text:
                matches.append(token)
                self._trigger_alert("honeytoken_found", {
                    "token_type": token["type"],
                    "token_value": token["value"][:20] + "...",
                })
        return matches

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------

    def pre_check(self, ctx) -> Any:
        """Before-request hook: inject honeytool definitions into the tools list.

        Supports both OpenAI format ({"type":"function","function":{...}}) and
        Anthropic format ({"name":"...","description":"...","input_schema":{...}}).
        Detects which format is in use by inspecting existing tool entries and
        injects honeytools in the matching format.
        """
        tools = ctx.extra_kwargs.get("tools")
        if tools is None or not isinstance(tools, list):
            return ctx

        # Detect format and collect existing names
        existing_names = set()
        is_anthropic_format = False
        for t in tools:
            if not isinstance(t, dict):
                continue
            # Anthropic format: top-level "name" key without "function" wrapper
            if "name" in t and "function" not in t:
                existing_names.add(t["name"])
                is_anthropic_format = True
            # OpenAI format: nested under "function"
            elif "function" in t:
                fn = t.get("function", {})
                existing_names.add(fn.get("name", ""))

        for ht in self._honeytools.values():
            if ht["name"] in existing_names:
                continue
            if is_anthropic_format:
                tools.append({
                    "name": ht["name"],
                    "description": ht.get("description", ""),
                    "input_schema": {"type": "object", "properties": {}},
                })
            else:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": ht["name"],
                        "description": ht.get("description", ""),
                        "parameters": {"type": "object", "properties": {}},
                    },
                })
        return ctx

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook: scan for honeytool usage and honeytoken leaks."""
        with self._lock:
            self.stats["total_scanned"] += 1

        # Check tool calls
        tool_calls = self._extract_tool_calls(ctx.raw_response, ctx.provider)
        for tc in tool_calls:
            self.check_tool_call(tc["name"], tc.get("arguments"))

        # Check response text for honeytokens
        if ctx.text:
            self.check_text_for_tokens(ctx.text)

        return ctx

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _trigger_alert(self, alert_type: str, details: Dict[str, Any]) -> None:
        """Handle a honeytool/honeytoken trigger."""
        alert = {
            "type": alert_type,
            "timestamp": time.time(),
            "alert_id": str(uuid.uuid4())[:8],
            **details,
        }

        with self._lock:
            self.alerts.append(alert)
            if alert_type == "honeytool_called":
                self.stats["tool_triggers"] += 1
            elif alert_type == "honeytoken_found":
                self.stats["token_triggers"] += 1

        if self.on_trigger == "block":
            raise HoneytoolTriggered(
                f"Deception tripwire triggered: {alert_type} — "
                f"{details.get('tool_name', details.get('token_type', 'unknown'))}"
            )

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
                    if getattr(block, "type", "") in ("tool_use", "mcp_tool_use"):
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
                "honeytools_deployed": len(self._honeytools),
                "honeytokens_deployed": len(self._honeytokens),
                "alerts": self.alerts[-10:],
                "honeytool_names": list(self._honeytools.keys()),
            }
