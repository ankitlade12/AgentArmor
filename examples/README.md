# AgentArmor Examples

These examples integrate `agentarmor` with popular AI frameworks and providers.

Each one **leads with a deterministic control** — a budget circuit breaker, PII/secrets redaction, a tool-call policy, or an audit trace. Those behave the same way on every run. AgentArmor also ships optional, pattern-based **detectors** (prompt injection, exfiltration, RAG poisoning); those are **defense-in-depth — useful as one layer, bypassable by design, and not a complete security boundary.** Examples that demonstrate a detector say so plainly and are grouped at the end.

## Setup

Install `agentarmor` and the frameworks you want in your virtual environment.

```bash
# 1. Install agentarmor (from the root of the repository)
pip install -e ".[all]"

# 2. Install the example dependencies
pip install -r examples/requirements.txt
```

Set your API keys before running. Most examples use OpenAI models.

```bash
export OPENAI_API_KEY="sk-..."
```

---

## Start here — deterministic controls

### `litellm_example.py`
The highest-leverage adoption path: AgentArmor wrapping LiteLLM's unified provider interface with a **budget circuit breaker**, **PII/secrets redaction**, and an **audit report** — one integration that generalizes across many upstream model providers. (Also runs the optional injection filter as a secondary, defense-in-depth check.)

```bash
python examples/litellm_example.py
```

### `crewai_cost_guard_example.py`
**Cost control in a multi-step CrewAI workflow.** Uses a deliberately tiny budget so AgentArmor halts the run with a `BudgetExhausted` exception before the crew overspends. Deterministic, and the easiest win to demo.

```bash
python examples/crewai_cost_guard_example.py
```

### `agno_tool_policy_example.py`
**Tool governance in Agno.** Defines one allowed tool path and one blocked tool path so the `tool_firewall` allow/deny boundary is easy to see. A real authorization boundary, not a heuristic.

```bash
python examples/agno_tool_policy_example.py
```

### `mcp_policy_example.py`
AgentArmor's **MCP policy engine** without a live MCP deployment: trusted-vs-blocked servers, pre-authentication for a private server, and path-based tool restrictions for a filesystem-style tool.

```bash
python examples/mcp_policy_example.py
```

### `llamaindex_example.py`
**On-the-fly PII redaction in a LlamaIndex flow.** Answers a query, then requests a fake email address to trigger the `FilterModule`, which redacts the PII before LlamaIndex receives the final string.

```bash
python examples/llamaindex_example.py
```

### `hitl_example.py`
**Human-in-the-loop policy gate.** Configures risk levels, approval callbacks, and auto-approve/deny rules for tool calls — blocking dangerous actions and auto-approving safe ones.

```bash
python examples/hitl_example.py
```

### `trace_export_example.py`
**Audit/observability.** Serializes the last Explain Mode trace as JSON and attaches the normalized fields to an OpenTelemetry span.

```bash
python examples/trace_export_example.py
```

### `compliance_example.py`
Enables the compliance reporter alongside existing modules, captures a compliance-relevant data event, and generates a SOC2/GDPR-style report from the active session.

```bash
python examples/compliance_example.py
```

---

## Framework integrations

These show AgentArmor's controls (budget tracking, redaction, audit) applied across each stack with no framework rewrite. Each also runs the optional injection filter as a clearly-labeled defense-in-depth step.

### `langchain_example.py`
Wraps LangChain's `ChatOpenAI` provider path. Tracks cost on a normal query, then runs the optional heuristic injection filter as a defense-in-depth step.

```bash
python examples/langchain_example.py
```

### `langgraph_multistep_example.py`
Wraps a small LangGraph flow with multiple model hops (planner node + writer node). Cost is tracked across the whole graph; the optional injection filter runs as a defense-in-depth step.

```bash
python examples/langgraph_multistep_example.py
```

### `crewai_example.py`
Shows AgentArmor's patch intercepting a complex multi-agent framework. A CrewAI `Agent` runs on a LangChain LLM and executes a `Task` while AgentArmor tracks the exact dollars spent across the whole Crew.

```bash
python examples/crewai_example.py
```

### `pydantic_ai_example.py`
Protects a Pydantic AI agent on OpenAI's Responses API surface: budget tracking, secrets redaction, and an audit report, plus the optional injection filter as a defense-in-depth step.

```bash
python examples/pydantic_ai_example.py
```

### `agno_example.py`
Agno on OpenAI's `OpenAIResponses`: budget tracking and an audit report across the run, plus the optional injection filter as a defense-in-depth step.

```bash
python examples/agno_example.py
```

### `autogen_example.py`
AutoGen conversational agents: a `UserProxyAgent` asks an `AssistantAgent` to write a script, and AgentArmor tracks the cost of the multi-turn loop — proving the patch secures AutoGen's internal LLM router.

```bash
python examples/autogen_example.py
```

### `google_adk_example.py`
A minimal Google ADK `root_agent` with AgentArmor initialized first, so the underlying Gemini traffic is covered (budget + tool policy) once the ADK agent runs. Prints the steps for dropping the file into an ADK project and launching it with `adk web`.

```bash
python examples/google_adk_example.py
```

### `google_adk_project/`
A copy-paste Google ADK project layout with `agent.py`, `.env.example`, and `adk web` startup notes.

```bash
cp -R examples/google_adk_project ./agentarmor-adk-demo
```

### `gemini_example.py`
AgentArmor with Google Gemini via the modern `google-genai` SDK: budget tracking and PII redaction working with Gemini models.

```bash
export GEMINI_API_KEY="..."
python examples/gemini_example.py
```

### `basic.py`
The lowest-level usage: initializes the core controls (budget, output filter, flight recorder) and sends a normal `openai` request, then runs the optional injection filter as a defense-in-depth step.

```bash
python examples/basic.py
```

### `hooks_example.py`
A deep dive into the middleware/hooks system. Registers custom `@before_request`, `@after_response`, and `@on_stream_chunk` decorators to inject context into prompts, log analytics, and censor profanity during streaming.

```bash
python examples/hooks_example.py
```

---

## Defense-in-depth detectors (heuristic — not a complete boundary)

These demonstrate the optional detectors. They catch the patterns shown here, but pattern/heuristic detection is bypassable by design — treat these as one layer, not a guarantee.

### `llamaindex_rag_poisoning_example.py`
Simulates a poisoned retrieval chunk in a LlamaIndex-style RAG flow: the retrieved text contains instruction-like content, and AgentArmor's detector flags it before the prompt reaches the model wrapper. Defense-in-depth — bypassable by reworded payloads.

```bash
python examples/llamaindex_rag_poisoning_example.py
```

### `rag_provenance_example.py`
A local provenance pattern for retrieved chunks: tags sources, rejects flagged retrieval text, and builds an answer only from accepted chunks.

```bash
python examples/rag_provenance_example.py
```

### `exfiltration_case_study_example.py`
Simulates a model response trying to smuggle a secret to an outbound sink via base64 encoding; AgentArmor's exfiltration detector flags the encoded leak locally. Defense-in-depth — covers the encodings it knows about.

```bash
python examples/exfiltration_case_study_example.py
```

### `mcp_result_validation_example.py`
Scans MCP tool results before an agent reuses them: a clean result passes, and a result that tries to inject new instructions is flagged. Defense-in-depth on the tool-result path.

```bash
python examples/mcp_result_validation_example.py
```
