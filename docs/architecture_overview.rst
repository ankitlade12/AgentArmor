Architecture Overview
=====================

AgentArmor is a local-first runtime safety layer that lives inside the Python
application process. It does not require a hosted proxy or a separate control
plane to intercept model traffic.

High-level Flow
---------------

.. code-block:: text

   App / Agent Framework
           |
           v
   LangChain / LiteLLM / LlamaIndex / CrewAI / Pydantic AI / raw SDK
           |
           v
   Supported provider client
   (openai / anthropic / google-genai)
           |
           v
   AgentArmor runtime hooks
     - before_request
     - policy modules
     - after_response
     - stream hooks
           |
           v
   Provider API call
           |
           v
   AgentArmor reporting / audit / budget accounting

Control Surfaces
----------------

The runtime hook shape creates a few distinct places to enforce policy:

1. **Before request**: reject unsafe prompts, oversized contexts, duplicate
   requests, or exhausted budgets before additional cost is incurred
2. **During streaming**: redact or block partial output while tokens are still
   arriving
3. **After response**: inspect final text, tool calls, MCP activity, and
   provider usage metadata
4. **Reporting layer**: record costs, audit trails, compliance views, and
   explain-mode traces for later analysis

What Gets Enforced
------------------

At runtime, AgentArmor can apply:

- budget checks before additional spend is incurred
- prompt-injection and harmful-input detection before the request leaves the
  process
- output filtering for secrets, PII, and policy-defined patterns
- MCP server and tool policy validation
- request / response recording for auditability

Why This Shape Matters
----------------------

This architecture is especially useful when a team:

- already has an agent application and wants controls with minimal rewrites
- wants to keep production traffic in-process instead of routing through a
  separate gateway
- needs a safety layer that works across multiple Python agent frameworks

How Frameworks Fit
------------------

Frameworks like LiteLLM, LangChain, LlamaIndex, CrewAI, Pydantic AI, Google
ADK, and Agno typically sit above provider SDK calls. When they eventually
route through supported provider surfaces, AgentArmor can protect those calls
without requiring framework-specific middleware in many cases.

The exact evidence behind each compatibility claim lives in
``SUPPORT_MATRIX.md``. The quick-start wiring notes live in
``framework_setup_matrix.rst``.

Operational Model
-----------------

AgentArmor is best thought of as:

- a runtime safety and spend-control layer
- a policy enforcement point for model and tool traffic
- an audit trail generator for requests, responses, and events

It is not intended to replace hosted observability, offline evaluation, or
framework orchestration systems. In practice it often complements them.

Partner Talking Points
----------------------

Useful external framing:

- AgentArmor is an in-process runtime control layer
- it can often be added without rewriting the surrounding framework
- it is strongest where provider interception, spend control, tool policy, and
  leakage prevention matter more than centralized traffic brokering
