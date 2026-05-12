MCP Policy Presets
==================

AgentArmor ships reusable MCP policy presets for common tool categories so
teams do not have to start from a blank config every time.

Available Presets
-----------------

- ``filesystem_readonly``
- ``shell_restricted``
- ``browser_readonly``
- ``sql_readonly``
- ``http_guarded``

Basic usage
-----------

.. code-block:: python

   import agentarmor

   mcp_config = agentarmor.merge_mcp_presets(
       "filesystem_readonly",
       "sql_readonly",
   )

   agentarmor.init(mcp_firewall=mcp_config)

You can also start from one preset and then layer local overrides on top:

.. code-block:: python

   config = agentarmor.merge_mcp_presets("http_guarded")
   config["trusted_servers"] = ["http-server"]
   config["tool_policies"]["fetch_url"]["blocked_patterns"]["url"] = (
       r"(?i)(localhost|127\\.0\\.0\\.1|169\\.254\\.169\\.254|internal\\.corp)"
   )

   agentarmor.init(mcp_firewall=config)

What The Presets Do
-------------------

- **filesystem_readonly**: allows a read-only file tool with path allowlists
  and blocks sensitive areas like ``/etc/`` and ``~/.ssh/``
- **shell_restricted**: keeps a shell tool available but blocks destructive or
  obviously dangerous command patterns
- **browser_readonly**: limits browser usage to navigation, text extraction,
  and screenshots while blocking special local URL schemes
- **sql_readonly**: restricts a SQL tool to read-style queries by blocking
  common mutation verbs
- **http_guarded**: blocks localhost and metadata-service style destinations
  and adds a simple secret-like payload check for POST bodies

These are conservative defaults, not a full security policy. You should still
set your own:

- server names
- tool names
- path allowlists
- hostname allowlists
- approval rules for high-risk tools

Companion APIs
--------------

- ``agentarmor.MCP_PRESETS``
- ``agentarmor.get_mcp_preset(name)``
- ``agentarmor.merge_mcp_presets(...)``

See also ``examples/mcp_policy_example.py`` and
``docs/mcp_security_checklist.rst``.

