MCP Security Checklist
======================

This checklist is intended for teams using Model Context Protocol tools and
servers with AgentArmor's MCP policy engine.

The goal is to make MCP integrations safer by default, especially when tools
can read files, write data, execute commands, or affect external systems.

Before You Trust a Server
-------------------------

- Verify the server identity and origin
- Decide whether the server belongs on a trust allowlist
- Block known-dangerous or unnecessary servers explicitly
- Require authentication for private or privileged servers
- Record which tools a server is actually allowed to expose

Tool Risk Categories
--------------------

.. list-table::
   :header-rows: 1
   :widths: 28 32 40

   * - Tool category
     - Default policy posture
     - Examples
   * - Read-only local data
     - Allow with path constraints
     - ``file_read``, read-only knowledge access
   * - Write or mutate local state
     - Approve or tightly constrain
     - ``file_write``, config updates, ticket edits
   * - Network egress
     - Approve or log aggressively
     - ``fetch_url``, webhooks, outbound HTTP
   * - Shell or code execution
     - Block or require explicit approval
     - command execution, Python runner, terminal tools
   * - Credentials or secrets access
     - Block by default
     - vault reads, token export, key retrieval
   * - External side effects
     - Require approval and audit
     - payments, purchases, destructive SaaS actions

Recommended MCP Controls
------------------------

- Use ``trusted_servers`` and ``blocked_servers``
- Define ``server_toolsets`` so each server can expose only expected tools
- Require ``server_auth`` for private or privileged servers
- Use per-tool ``allow_paths`` and ``block_paths`` for filesystem-like tools
- Use ``blocked_patterns`` for risky argument payloads such as SQL or shell
  commands
- Enable ``validate_tool_results`` when tool output might feed back into the
  model as untrusted context

Minimal Example
---------------

.. code-block:: python

   import agentarmor

   agentarmor.init(mcp_firewall={
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
       "validate_tool_results": True,
   })

What to Audit
-------------

- Which servers were contacted
- Which tools were invoked
- Which calls were blocked and why
- Whether privileged servers were pre-authenticated
- Whether untrusted tool output was fed back into later prompts

Good Default Questions
----------------------

Ask these before shipping an MCP-enabled workflow:

- What tools can change state?
- What tools can reach the network?
- What tools can access secrets or credentials?
- What tool outputs could contain injected instructions?
- What actions require a human approval gate?
