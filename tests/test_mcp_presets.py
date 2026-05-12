import pytest

from agentarmor import MCP_PRESETS, get_mcp_preset, merge_mcp_presets
from agentarmor.exceptions import MCPViolation
from agentarmor.modules.mcp_firewall import MCPFirewallModule


def test_exported_preset_names_are_stable():
    assert set(MCP_PRESETS) == {
        "browser_readonly",
        "filesystem_readonly",
        "http_guarded",
        "shell_restricted",
        "sql_readonly",
    }


def test_get_mcp_preset_returns_deep_copy():
    preset = get_mcp_preset("filesystem_readonly")
    preset["tool_policies"]["file_read"]["allow_paths"].append("/unsafe/")

    assert "/unsafe/" not in MCP_PRESETS["filesystem_readonly"]["tool_policies"]["file_read"]["allow_paths"]


def test_get_mcp_preset_rejects_unknown_name():
    with pytest.raises(KeyError, match="Unknown MCP preset"):
        get_mcp_preset("unknown")


def test_merge_mcp_presets_unions_lists_and_overrides_scalars():
    merged = merge_mcp_presets(
        "filesystem_readonly",
        {
            "trusted_servers": ["filesystem-server", "private-server"],
            "server_toolsets": {
                "filesystem-server": ["file_read", "file_stat"],
                "private-server": ["db_query"],
            },
            "server_auth": {"private-server": "Bearer one"},
            "tool_policies": {
                "file_read": {
                    "allow_paths": ["/data/"],
                },
                "db_query": {
                    "allowed_values": {"mode": ["read"]},
                },
            },
            "validate_tool_results": True,
        },
        {
            "server_auth": {"private-server": "Bearer two"},
            "validate_tool_results": False,
        },
    )

    assert set(merged["trusted_servers"]) == {"filesystem-server", "private-server"}
    assert merged["server_toolsets"]["filesystem-server"] == ["file_read", "file_stat"]
    assert merged["server_toolsets"]["private-server"] == ["db_query"]
    assert merged["server_auth"]["private-server"] == "Bearer two"
    assert set(merged["tool_policies"]["file_read"]["allow_paths"]) == {
        "./",
        "/workspace/",
        "/tmp/",
        "/data/",
    }
    assert merged["tool_policies"]["db_query"]["allowed_values"]["mode"] == ["read"]
    assert merged["validate_tool_results"] is False


def test_merged_preset_enforces_server_toolsets_and_tool_policies():
    merged = merge_mcp_presets(
        "filesystem_readonly",
        "shell_restricted",
        {
            "trusted_servers": ["filesystem-server", "shell-server"],
            "server_auth": {"shell-server": "Bearer shell-dev"},
        },
    )
    firewall = MCPFirewallModule(on_violation="block", **merged)

    assert firewall.validate_server_auth("shell-server", "Bearer shell-dev") is True
    assert firewall.validate_tool_call(
        "file_read",
        {"path": "./notes.txt"},
        server_name="filesystem-server",
    ) is True

    with pytest.raises(MCPViolation, match="allowed toolset"):
        firewall.validate_tool_call(
            "run_shell",
            {"command": "echo hi"},
            server_name="filesystem-server",
        )

    with pytest.raises(MCPViolation, match="Tool policy violation"):
        firewall.validate_tool_call(
            "run_shell",
            {"command": "sudo reboot now"},
            server_name="shell-server",
        )
