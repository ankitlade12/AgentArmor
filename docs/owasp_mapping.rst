OWASP Mapping
=============

This page is a practical control mapping, not a certification claim.

It shows how AgentArmor modules line up with common OWASP GenAI and agentic-AI
risk themes so users can reason about coverage, gaps, and where additional
controls may still be needed.

Risk Theme Mapping
------------------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Risk theme
     - Relevant AgentArmor modules
     - Notes
   * - Prompt injection and instruction override
     - ``shield``, ``ml_shield``, ``unicode_shield``, ``grounding``
     - Helps catch direct jailbreaks, indirect instruction-like payloads, and
       suspicious context before or after a model call.
   * - Sensitive information disclosure
     - ``filter``, ``canary``, ``exfiltration_guard``, ``toxicity``
     - Focuses on redaction, leakage detection, and suspicious outbound
       content patterns.
   * - Excessive agency / unsafe actions
     - ``tool_firewall``, ``mcp_firewall``, ``hitl_gate``,
       ``privilege_escalation``
     - Covers tool authorization, MCP trust, approval gates, and escalation
       attempts.
   * - Resource abuse / denial of wallet
     - ``budget``, ``rate_limiter``, ``latency_breaker``, ``cascade``
     - Helps bound cost, throughput, and degraded-response patterns.
   * - Insecure code generation or execution
     - ``code_shield``, ``tool_firewall``, ``mcp_firewall``
     - Useful when an agent can emit code or trigger code-executing tools.
   * - Hallucination / ungrounded answers
     - ``grounding``, ``semantic_drift``, ``echo_chamber``
     - Helps detect ungrounded claims, topic drift, and circular
       multi-agent false confirmation.
   * - Multi-agent coordination failures
     - ``agent_graph``, ``echo_chamber``, ``budget``
     - Adds lineage, cost accounting, and cross-agent safety visibility.
   * - Insufficient logging and traceability
     - ``recorder``, ``cost_tags``, ``compliance``, ``explain``
     - Supports replay, spend analysis, compliance reporting, and decision
       tracing.

Where AgentArmor Is Strongest
-----------------------------

AgentArmor is strongest on runtime controls that are easy to apply inside a
Python process:

- blocking prompt injection before provider calls
- bounding cost and unsafe tool use
- filtering sensitive output
- adding session-level traces and audit artifacts

Where You May Need More
-----------------------

AgentArmor is not a full governance or security program by itself. Depending
on your environment, you may also need:

- identity and access controls outside the agent runtime
- network-level controls or hosted gateways
- offline red-team and evaluation pipelines
- human review processes and incident response playbooks
- framework- or business-specific policy enforcement around external systems

Recommended Practice
--------------------

Use this page as a threat-model helper:

1. identify the highest-risk agent behaviors in your system
2. enable the AgentArmor modules that directly address those behaviors
3. document any remaining gaps outside the runtime layer
4. add example tests or attack simulations for the controls you depend on
