Why AgentArmor?
===============

AgentArmor is a local-first runtime safety layer for Python AI agents.

It is designed for teams that already have an agent application and need
practical controls around:

- runaway spend
- prompt injection
- PII or secret leakage
- unsafe tool calls
- MCP server and tool policy
- auditability and traces

What makes it different is the operating model: AgentArmor sits inside the
Python process, patches supported SDK surfaces, and adds controls without
requiring a hosted gateway, separate account, or framework rewrite.

Where It Fits
-------------

AgentArmor fits best when you want a lightweight safety layer around an agent
that already uses:

- raw OpenAI, Anthropic, or Gemini SDKs
- LiteLLM
- LlamaIndex
- LangChain / LangGraph
- CrewAI
- custom Python agent stacks

It can complement other tools rather than replace them. For example:

- use AgentArmor for runtime guardrails and spend control
- use tracing or observability tools for dashboards and replay
- use evaluation tools for offline benchmarking and red-team workflows

Why Local-first Matters
-----------------------

Many teams do not want to move production traffic through a hosted proxy just
to get basic runtime safety. Local-first controls help when you need:

- lower operational overhead
- fewer moving parts
- simpler local development and testing
- direct visibility inside the application process
- easier adoption in existing Python stacks

Hosted Proxy vs Local-first
---------------------------

Both approaches can be valid. The trade-off is operational shape:

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Approach
     - Strengths
     - Trade-offs
   * - Local-first runtime layer
     - Fast adoption inside an existing Python app, fewer moving parts, and
       easier local development
     - Policy is applied where the app runs, so each deployment still owns its
       runtime configuration
   * - Hosted proxy / gateway
     - Centralized control and shared enforcement across many applications
     - Additional infrastructure, routing changes, and more operational
       coupling between app traffic and the control plane

Complementary Tools
-------------------

AgentArmor complements several nearby tool categories:

- tracing tools for dashboards, search, and replay
- evaluation tools for offline red-teaming and benchmark workflows
- orchestration frameworks for graph execution, memory, and tool loops

That is usually the cleanest story: AgentArmor is the runtime control point,
not the whole stack.

Primary Wedges
--------------

The strongest immediate use cases are:

1. stop runaway agent spend with a budget circuit breaker
2. block prompt-injection attempts before unsafe tool use
3. redact secrets and PII from model outputs
4. enforce tool and MCP policy without rewriting the framework

What AgentArmor Is Not
----------------------

AgentArmor is not trying to be:

- a hosted security control plane
- a generic replacement for every guardrail framework
- a framework-specific orchestration layer

Instead, it focuses on runtime protection and operational controls that are
useful across many Python agent ecosystems.
