Framework Setup Matrix
======================

This page is the fast setup companion to ``SUPPORT_MATRIX.md``.
Use it for practical wiring notes; use the support matrix for evidence and
compatibility scope.

.. list-table::
   :header-rows: 1
   :widths: 18 18 26 20 18

   * - Framework / SDK
     - Provider Surface
     - Minimal Setup
     - Caveats
     - Example
   * - Raw OpenAI SDK
     - ``openai``
     - Call ``agentarmor.init()`` before creating the client.
     - Best coverage today; patch surface is CI-tested.
     - ``examples/basic.py``
   * - Google Gemini
     - ``google-genai``
     - Initialize AgentArmor before creating ``genai.Client()``.
     - Use the modern ``google-genai`` SDK surface, not older Gemini SDKs.
     - ``examples/gemini_example.py``
   * - LiteLLM
     - ``openai``-style unified completion layer
     - Initialize AgentArmor before calling ``litellm.completion()``.
     - Works best when the underlying provider path routes through a patched
       SDK surface.
     - ``examples/litellm_example.py``
   * - LangChain / LangGraph
     - Usually ``openai`` or ``anthropic`` wrappers
     - Initialize AgentArmor before constructing the LLM wrapper.
     - Framework tool abstractions may need targeted examples beyond plain LLM
       calls.
     - ``examples/langchain_example.py`` and
       ``examples/langgraph_multistep_example.py``
   * - LlamaIndex
     - Provider wrapper over OpenAI or other SDKs
     - Initialize AgentArmor before creating the LLM object.
     - Retrieved text is still untrusted input; RAG pipelines benefit from
       explicit poisoning examples.
     - ``examples/llamaindex_example.py`` and
       ``examples/llamaindex_rag_poisoning_example.py``
   * - CrewAI
     - Typically LangChain or provider wrappers
     - Initialize AgentArmor before crew construction.
     - Multi-step runs are a strong fit for budget and recorder modules.
     - ``examples/crewai_example.py`` and
       ``examples/crewai_cost_guard_example.py``
   * - AutoGen
     - Provider config routed to provider SDK
     - Initialize AgentArmor before agent chat begins.
     - Framework-owned tool loops may need separate, higher-fidelity smoke
       tests if you rely on heavy tool usage.
     - ``examples/autogen_example.py``
   * - Pydantic AI
     - OpenAI Responses or other provider models
     - Initialize AgentArmor before creating or running the agent.
     - Responses-surface compatibility matters more than framework internals.
     - ``examples/pydantic_ai_example.py``
   * - Google ADK
     - Gemini via the ADK model registry and ``google-genai``
     - Initialize AgentArmor inside the ADK project before the root agent
       runs.
     - Project-style wiring is slightly different from a one-file script demo.
     - ``examples/google_adk_example.py``
   * - Agno
     - OpenAI Responses or other model adapters
     - Initialize AgentArmor before running the agent.
     - Tool-heavy flows should pair with ``tool_firewall`` or MCP policy.
     - ``examples/agno_example.py`` and
       ``examples/agno_tool_policy_example.py``
   * - MCP policy flows
     - MCP tool and server calls
     - Configure ``mcp_firewall`` in ``agentarmor.init()``.
     - Pre-auth, server toolsets, and tool-result validation deserve explicit
       policy defaults.
     - ``examples/mcp_policy_example.py``

Common Pattern
--------------

For most frameworks, the adoption shape is:

1. import ``agentarmor``
2. call ``agentarmor.init(...)`` once near process startup
3. construct the framework objects as usual
4. run the agent / workflow and read ``agentarmor.report()``

This works best when the framework eventually routes through a provider surface
that AgentArmor already patches.

Things To Watch
---------------

- framework-specific built-in tool layers may still need targeted examples
- support claims should stay aligned with tested provider surfaces
- multi-provider frameworks may require per-provider setup notes
- project-style frameworks such as Google ADK need a slightly different
  example shape than single-script SDK wrappers
- direct AWS Bedrock patching is not currently a first-class runtime surface;
  if a framework routes to Bedrock without using a patched provider SDK, treat
  that as a separate support track rather than assuming drop-in coverage
