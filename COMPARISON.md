# AgentArmor vs. Providers, Gateways, and Agent Frameworks

**TL;DR: AgentArmor is not a replacement for OpenAI, Anthropic, Gemini, LiteLLM, LangChain, LlamaIndex, CrewAI, Agno, Pydantic AI, Google ADK, AutoGen, or MCP.** It is the local, in-process runtime control layer you add when you want a hard budget circuit breaker, redaction, tool policy, and local audit traces without deploying a gateway or adopting a hosted control plane.

The honest wedge is narrow and useful:

- **Local-first:** runs inside your Python process.
- **Enforcing:** can stop a run, not just observe it.
- **Low wiring:** one import for budget, redaction, rate limits, audit, and tool policy.
- **Composable:** works underneath frameworks that call supported provider SDKs.

AgentArmor's prompt-injection and safety detectors are **defense-in-depth heuristics**, not a complete security boundary. If you need a best-in-class injection/jailbreak classifier, use a dedicated guardrail service and treat AgentArmor as the local runtime safety net around it.

## The Real Comparison

Most alternatives fit into one of four layers:

| Layer | Examples | What they are best at | Where AgentArmor fits |
|---|---|---|---|
| Model providers | OpenAI, Anthropic, Google Gemini | Model APIs, platform limits, model-level safety settings, hosted usage dashboards | Per-run local controls around the SDK call |
| Gateways | LiteLLM Proxy | Central provider routing, org/team/key budgets, gateway guardrails, shared policy | No-proxy local enforcement for small stacks and local dev |
| Frameworks | LangChain, LlamaIndex, CrewAI, Agno, Pydantic AI, ADK, AutoGen, SmolAgents | Agent orchestration, tools, memory, typed outputs, workflows | Runtime safety underneath the framework's model calls |
| Protocol/tool layer | MCP | Tool/resource connectivity and authorization patterns | Tool-call policy, approval gates, path/server allowlists, audit |

## Provider SDKs

AgentArmor directly supports these provider surfaces today:

| Provider | Native provider controls | What AgentArmor adds |
|---|---|---|
| OpenAI | Platform usage/cost dashboards, project budgets, moderation, and OpenAI Guardrails for input/output checks | Per-process budget breaker, local JSONL audit trail, redaction before your app sees output, one library across frameworks |
| Anthropic | API rate limits, spend limits, usage/cost reporting, model/tool-use controls | Local per-run stop conditions, provider-independent redaction/audit, same policy surface as OpenAI/Gemini calls |
| Google Gemini | Gemini safety settings and Google/Vertex platform controls | Local budget tracking, PII/secrets redaction, audit traces, and policy checks around Gemini calls |

Use AgentArmor with provider SDKs when you want the control to happen in your app process, at the exact run/workflow boundary, not only at the account/project dashboard level.

## Gateways

### LiteLLM

LiteLLM is the strongest overlap. LiteLLM Proxy already has real budgets, spend tracking, rate limits, routing, and guardrails such as Presidio PII masking and external prompt-injection providers. If you already run LiteLLM Proxy as your gateway, AgentArmor is optional.

AgentArmor is useful when:

- you are not ready to operate a gateway server,
- you want local enforcement during development or tests,
- you want a per-script/per-agent circuit breaker in addition to LiteLLM's central budgets,
- or you want the same local redaction/audit behavior across raw SDKs and non-LiteLLM framework calls.

**Do not pitch AgentArmor to LiteLLM users as "LiteLLM but safer."** Pitch it as "local runtime controls that can sit underneath or alongside your gateway."

## Frameworks

AgentArmor generally works at the provider SDK layer, not by owning each framework's lifecycle. That is powerful for quick adoption, but it also means framework maintainers may prefer native middleware/callback integrations before they list it officially.

| Framework | What the framework already gives users | Best AgentArmor angle |
|---|---|---|
| LangChain / LangGraph | Agent orchestration, callbacks, v1 middleware/guardrails patterns, rate limiting, LangSmith tracing | Local budget breaker + redaction + audit when users do not want hosted LangSmith-only visibility. For maintainer outreach, build a native callback/middleware example first. |
| LlamaIndex | RAG pipelines, data connectors, retrieval/eval/observability integrations | RAG safety wedge: poisoned context detection, source-aware audit traces, PII redaction on retrieved/output text. |
| CrewAI | Multi-agent crews, tasks, tools, process orchestration | Multi-agent runaway spend control and shared audit across a crew run. The cost-guard demo is the strongest artifact. |
| Agno / Phidata | Agent runtime, hooks, built-in guardrails for PII/prompt injection/moderation | Tool policy + local budget/audit as a complement to Agno guardrails. Lead with `agno_tool_policy_example.py`, not injection. |
| Pydantic AI | Typed agents, usage limits, retries, structured outputs, Logfire observability | Local budget/redaction/audit around typed agents, especially for users who want in-process controls without depending on hosted observability. |
| Google ADK | Code-first Google agent framework, callbacks, tool guardrails, deployment path to Google Cloud/Vertex | Local dev/runtime guard before ADK traffic reaches Gemini, plus policy checks for tools and a local audit trail. |
| AutoGen | Multi-agent conversation patterns and built-in tracing/observability | Cost tracking and local audit for multi-turn agent loops. Good secondary target, not the first outreach target. |
| SmolAgents | Lightweight agent framework and model/tool abstractions | Raw lightweight stack fit: one import for local budget/redaction/audit where users likely want minimal infrastructure. Dedicated example still needed. |

## MCP and Tool Policy

MCP is not a competitor to AgentArmor; it is a risk surface AgentArmor can help govern. MCP standardizes how agents reach tools and resources, which makes tool policy, approval requirements, path restrictions, server allowlists, and audit traces especially valuable.

The strongest AgentArmor MCP story is:

- allow trusted MCP servers,
- block or require approval for risky servers/tools,
- restrict filesystem paths,
- validate tool results before they are fed back to the model,
- log every policy decision locally.

Do not pitch this as "MCP security solved." Pitch it as a practical local policy layer for Python agent apps using MCP.

## Capability Matrix

| Capability | Provider APIs | LiteLLM Proxy | LangChain/LangSmith | Agent Frameworks | AgentArmor |
|---|---|---|---|---|---|
| Hard per-run budget breaker | Usually account/project-level, not per local run | Yes, centrally in proxy | Mostly tracking/observability unless user builds enforcement | Varies by framework | Yes, in-process |
| Spend tracking | Yes, dashboard/API level | Yes | Yes via callbacks/tracing | Varies | Yes, local |
| Rate limiting | Yes, platform limits | Yes | Yes in-process options | Varies | Yes |
| PII/secrets redaction | Varies; OpenAI Guardrails supports checks | Yes via guardrails like Presidio | Via middleware/integrations | Varies | Yes, built-in |
| Prompt-injection checks | Varies; use dedicated guardrails | Yes via providers such as Lakera | Via middleware/integrations | Varies | Heuristic defense-in-depth |
| Tool-call policy | Provider/tool APIs vary | Gateway-level and custom policy patterns | Middleware/agent logic | Varies | Yes, local policy checks |
| MCP policy | Not the provider's job | Emerging gateway/proxy patterns | App/framework logic | App/framework logic | Yes, local examples/presets |
| Audit trail | Dashboard/hosted logs | Gateway logs | LangSmith/other tracing | Varies | Local JSONL/report |
| Deployment model | Hosted provider platform | Gateway server | Framework + often hosted tracing | Framework runtime | `pip install`, local process |

## When to Reach for AgentArmor

- You are building with raw `openai`, `anthropic`, or `google-genai` SDKs.
- You use a framework but do not want to wire together multiple guardrail/tracing/rate-limit packages.
- You want a hard spend cutoff for a single agent run, demo, CI test, notebook, or local tool.
- You want local JSONL traces instead of sending every trace to a hosted service.
- You need tool-call or MCP policy checks close to the app code.
- You are doing privacy-sensitive or air-gapped work where "nothing leaves the process except the model call" matters.

## When to Use Something Else

- You need central org/team/key budgets across many apps: use LiteLLM Proxy or your provider platform.
- You already standardized on LangSmith, Logfire, or another tracing platform: keep using it; AgentArmor can still export/local-log.
- You need best-in-class prompt-injection/jailbreak detection: use a dedicated guardrail provider and treat AgentArmor as an extra local layer.
- You need deep framework-native lifecycle hooks: build or use a native callback/middleware integration, then let AgentArmor enforce underneath it.

## Outreach Implication

Do **not** ask LangChain, LiteLLM, or other maintainers to "use AgentArmor" first. They already have overlapping controls and mature ecosystems.

The better path:

1. Build and publish runnable examples that solve a specific user pain.
2. Lead with deterministic controls: budget breaker, PII/secrets redaction, tool policy, audit.
3. Submit community examples or cookbook PRs, not "please adopt us" issues.
4. Position AgentArmor as complementary: local enforcement for users who do not want another server or hosted control plane.

Best first outreach targets:

- raw SDK and small-stack developers,
- Agno/CrewAI/Pydantic AI users,
- MCP builders,
- LiteLLM users who are not running the proxy,
- LangChain/LangGraph later, after a native callback/middleware example exists.

## Reference Notes

- OpenAI: [Guardrails Python quickstart](https://openai.github.io/openai-guardrails-python/quickstart/), [PII check](https://openai.github.io/openai-guardrails-python/ref/checks/pii/), [prompt-injection check](https://openai.github.io/openai-guardrails-python/ref/checks/prompt_injection_detection/), [project budgets](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform).
- Anthropic: [rate limits and spend limits](https://docs.anthropic.com/en/api/rate-limits), [API overview](https://docs.anthropic.com/en/api/overview).
- Google Gemini: [safety settings](https://ai.google.dev/docs/safety_setting_gemini), [ADK safety and security](https://adk.dev/safety/).
- LiteLLM: [Proxy docs](https://docs.litellm.ai/), [budgets and rate limits](https://docs.litellm.ai/docs/proxy/users), [spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking), [guardrails quickstart](https://docs.litellm.ai/docs/proxy/guardrails/quick_start), [Presidio PII masking](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2).
- LangChain: [rate limiting](https://python.langchain.com/docs/how_to/chat_model_rate_limiting/), [guardrails](https://docs.langchain.com/oss/python/langchain/guardrails), [agent middleware](https://www.langchain.com/blog/agent-middleware).
- LlamaIndex: [observability](https://docs.llamaindex.ai/en/latest/module_guides/observability/).
- CrewAI: [documentation](https://docs.crewai.com/en/index), [crews](https://docs.crewai.com/en/concepts/crews).
- Agno: [guardrails](https://docs.agno.com/execution-control/guardrails/overview), [hooks](https://docs.agno.com/execution-control/hooks/overview).
- Pydantic AI: [Agent API](https://pydantic.dev/docs/ai/api/pydantic-ai/agent), [agents and usage limits](https://pydantic.dev/docs/ai/core-concepts/agent/), [Logfire AI observability](https://pydantic.dev/docs/logfire/get-started/ai-observability).
- MCP: [security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices), [authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).
- AutoGen: [tracing and observability](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tracing.html).
- SmolAgents: [Hugging Face smolagents docs](https://huggingface.co/docs/smolagents/index).
