"""Reusable MCP policy presets for common tool-risk categories.

These presets are intentionally conservative starting points. Teams should
adapt them to their own server names, tool names, and path or hostname
allowlists before using them in production.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


PresetDict = Dict[str, Any]


_PRESETS: dict[str, PresetDict] = {
    "filesystem_readonly": {
        "server_toolsets": {
            "filesystem-server": ["file_read"],
        },
        "tool_policies": {
            "file_read": {
                "allow_paths": ["./", "/workspace/", "/tmp/"],
                "block_paths": ["/etc/", "/root/", "~/.ssh/", "/var/run/"],
            },
        },
    },
    "shell_restricted": {
        "server_toolsets": {
            "shell-server": ["run_shell"],
        },
        "tool_policies": {
            "run_shell": {
                "blocked_patterns": {
                    "command": (
                        r"(?i)\b("
                        r"rm\s+-rf|sudo\b|chmod\s+777|"
                        r"curl\s+.*\|\s*(?:bash|sh|zsh)|"
                        r"wget\s+.*\|\s*(?:bash|sh|zsh)|"
                        r"dd\s+.*of=/dev/|"
                        r"mkfs\.|"
                        r"shutdown\b|reboot\b"
                        r")"
                    ),
                },
            },
        },
    },
    "browser_readonly": {
        "server_toolsets": {
            "browser-server": ["navigate", "get_text", "screenshot"],
        },
        "tool_policies": {
            "navigate": {
                "blocked_patterns": {
                    "url": r"(?i)^(?:file|ftp|chrome|about):",
                },
            },
        },
    },
    "sql_readonly": {
        "server_toolsets": {
            "sql-server": ["db_query"],
        },
        "tool_policies": {
            "db_query": {
                "blocked_patterns": {
                    "query": r"(?i)\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|GRANT|REVOKE)\b",
                },
            },
        },
    },
    "http_guarded": {
        "server_toolsets": {
            "http-server": ["fetch_url", "post_url"],
        },
        "tool_policies": {
            "fetch_url": {
                "blocked_patterns": {
                    "url": r"(?i)(localhost|127\.0\.0\.1|169\.254\.169\.254|0\.0\.0\.0)",
                },
            },
            "post_url": {
                "blocked_patterns": {
                    "url": r"(?i)(localhost|127\.0\.0\.1|169\.254\.169\.254|0\.0\.0\.0)",
                    "body": r"(?i)(api[_-]?key|secret|password|token)",
                },
            },
        },
    },
}


def get_mcp_preset(name: str) -> PresetDict:
    """Return a deep-copied MCP preset by name."""
    try:
        return deepcopy(_PRESETS[name])
    except KeyError as exc:
        known = ", ".join(sorted(_PRESETS))
        raise KeyError(f"Unknown MCP preset {name!r}. Known presets: {known}") from exc


def merge_mcp_presets(*presets: str | PresetDict) -> PresetDict:
    """Merge named or inline MCP presets into one config dict.

    Merge rules:
    - ``trusted_servers`` / ``blocked_servers`` are unioned without duplicates
    - ``server_toolsets`` are unioned per server
    - ``server_auth`` overwrites by server name (last write wins)
    - ``tool_policies`` merge shallowly per tool and per policy key
    - scalar keys use last write wins
    """
    merged: PresetDict = {
        "trusted_servers": [],
        "blocked_servers": [],
        "server_toolsets": {},
        "server_auth": {},
        "tool_policies": {},
    }

    for entry in presets:
        current = get_mcp_preset(entry) if isinstance(entry, str) else deepcopy(entry)

        for key in ("trusted_servers", "blocked_servers"):
            values = current.get(key, [])
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)

        for server_name, tools in current.get("server_toolsets", {}).items():
            merged["server_toolsets"].setdefault(server_name, [])
            for tool_name in tools:
                if tool_name not in merged["server_toolsets"][server_name]:
                    merged["server_toolsets"][server_name].append(tool_name)

        merged["server_auth"].update(current.get("server_auth", {}))

        for tool_name, policy in current.get("tool_policies", {}).items():
            dest = merged["tool_policies"].setdefault(tool_name, {})
            for policy_key, policy_value in policy.items():
                if isinstance(policy_value, list):
                    existing = dest.setdefault(policy_key, [])
                    for item in policy_value:
                        if item not in existing:
                            existing.append(item)
                elif isinstance(policy_value, dict):
                    existing = dest.setdefault(policy_key, {})
                    existing.update(policy_value)
                else:
                    dest[policy_key] = policy_value

        for key, value in current.items():
            if key in {
                "trusted_servers",
                "blocked_servers",
                "server_toolsets",
                "server_auth",
                "tool_policies",
            }:
                continue
            merged[key] = deepcopy(value)

    return merged


MCP_PRESETS: dict[str, PresetDict] = deepcopy(_PRESETS)
