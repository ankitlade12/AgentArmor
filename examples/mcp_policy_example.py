"""MCP policy example for AgentArmor.

This example uses AgentArmor's MCP policy engine directly to demonstrate:
- trusted vs blocked servers
- pre-authentication for private MCP servers
- path-based tool restrictions

The example is intentionally local and self-contained. It does not require a
live MCP server to show the policy behavior.
"""

import agentarmor
from agentarmor.exceptions import MCPViolation


def main() -> None:
    agentarmor.init(
        mcp_firewall={
            "trusted_servers": ["filesystem-server", "private-server"],
            "blocked_servers": ["remote-exec"],
            "server_toolsets": {
                "filesystem-server": ["file_read"],
                "private-server": ["db_query"],
            },
            "server_auth": {
                "private-server": "Bearer dev-token",
            },
            "tool_policies": {
                "file_read": {
                    "allow_paths": ["/safe/data/"],
                    "block_paths": ["/etc/", "/root/", "~/.ssh/"],
                },
                "db_query": {
                    "blocked_patterns": {"query": r"DROP|DELETE|TRUNCATE"},
                },
            },
        }
    )

    try:
        print("=== Trusted filesystem server ===")
        print(agentarmor.validate_mcp_server("filesystem-server"))

        print("\n=== Allowed filesystem read ===")
        print(
            agentarmor.validate_mcp_tool(
                "file_read",
                {"path": "/safe/data/report.txt"},
                server_name="filesystem-server",
            )
        )

        print("\n=== Blocked filesystem read ===")
        try:
            agentarmor.validate_mcp_tool(
                "file_read",
                {"path": "/etc/passwd"},
                server_name="filesystem-server",
            )
        except MCPViolation as exc:
            print(f"Blocked: {exc}")

        print("\n=== Pre-auth private server ===")
        print(agentarmor.authenticate_mcp_server("private-server", "Bearer dev-token"))

        print("\n=== Blocked server ===")
        try:
            agentarmor.validate_mcp_server("remote-exec")
        except MCPViolation as exc:
            print(f"Blocked: {exc}")
    finally:
        agentarmor.teardown()


if __name__ == "__main__":
    main()
