# AgentArmor Examples

This directory contains examples of how to integrate `agentarmor` with various popular AI frameworks.

## Setup

To run these examples, you should install `agentarmor` and the required frameworks in your virtual environment.

```bash
# 1. Install agentarmor (from the root of the repository)
pip install -e ".[all]"

# 2. Install the example dependencies
pip install -r examples/requirements.txt
```

## Running the Examples

Make sure you have your API keys set before running the examples. Most examples use OpenAI models.

```bash
export OPENAI_API_KEY="sk-..."
```

### `litellm_example.py`
Demonstrates the highest-leverage integration path for adoption: AgentArmor wrapping LiteLLM's unified provider interface with a budget circuit breaker, prompt-injection blocking, and an audit report. This is the best starting point if you want one example that generalizes across many upstream model providers.

```bash
python examples/litellm_example.py
```

### `mcp_policy_example.py`
Demonstrates AgentArmor's MCP policy engine without requiring a live MCP deployment. It shows trusted-vs-blocked servers, pre-authentication for a private server, and path-based tool restrictions for a filesystem-style tool.

```bash
python examples/mcp_policy_example.py
```

### `mcp_result_validation_example.py`
Shows how to scan MCP tool results before they are reused by an agent. It simulates a clean result and a poisoned result that tries to inject new instructions.

```bash
python examples/mcp_result_validation_example.py
```

### `trace_export_example.py`
Shows how to serialize the last Explain Mode trace as JSON and how to attach
the normalized fields to an OpenTelemetry span.

```bash
python examples/trace_export_example.py
```

### `llamaindex_rag_poisoning_example.py`
Simulates a poisoned retrieval chunk in a LlamaIndex-style RAG flow. The retrieved text includes instruction-like content, and AgentArmor blocks it before the prompt reaches the model wrapper.

```bash
python examples/llamaindex_rag_poisoning_example.py
```

### `rag_provenance_example.py`
Demonstrates a local provenance pattern for retrieved chunks. It tags sources,
rejects poisoned retrieval text, and builds an answer only from accepted chunks.

```bash
python examples/rag_provenance_example.py
```

### `exfiltration_case_study_example.py`
Simulates a model response that tries to smuggle a secret to an outbound sink
with base64 encoding. AgentArmor blocks the encoded leak locally.

```bash
python examples/exfiltration_case_study_example.py
```

### `basic.py`
Demonstrates the lowest-level usage of AgentArmor. It initializes the core shields (Budget, Shield, Filter, Record) and sends two raw `openai` client requests: one normal request, and one simulated prompt injection attack to show how the `ShieldModule` intercepts and blocks it.

```bash
python examples/basic.py
```

### `langchain_example.py`
Demonstrates AgentArmor wrapping LangChain's `ChatOpenAI` provider path. It executes a normal query to show cost tracking, and a prompt injection to show LangChain surfacing an `InjectionDetected` exception.

```bash
python examples/langchain_example.py
```

### `langgraph_multistep_example.py`
Shows AgentArmor wrapping a small LangGraph flow with multiple model hops. A
planner node and a writer node both run through the protected provider path,
and a prompt-injection attempt is blocked inside the graph execution.

```bash
python examples/langgraph_multistep_example.py
```

### `llamaindex_example.py`
Demonstrates LlamaIndex integration. It uses the `OpenAI` LLM wrapper to answer a query, and then requests the generation of a fake email address to trigger the `FilterModule` which redacts the PII on the fly before LlamaIndex receives the final string.

```bash
python examples/llamaindex_example.py
```

### `crewai_example.py`
Proves that AgentArmor's deep patch securely intercepts complex, multi-agent frameworks. It creates a CrewAI `Agent` running on a LangChain LLM and executes a `Task`. AgentArmor tracks the exact dollars spent silently in the background across the entire Crew execution.

```bash
python examples/crewai_example.py
```

### `crewai_cost_guard_example.py`
Focuses specifically on cost control in a multi-step CrewAI workflow. It uses a deliberately tiny budget so AgentArmor can halt the run with a `BudgetExhausted` exception before the crew burns more spend than intended.

```bash
python examples/crewai_cost_guard_example.py
```

### `pydantic_ai_example.py`
Shows AgentArmor protecting a modern Pydantic AI agent running through OpenAI's Responses API surface. It demonstrates a normal request, a blocked prompt-injection attempt, and a final spend/report summary.

```bash
python examples/pydantic_ai_example.py
```

### `google_adk_example.py`
Defines a minimal Google ADK `root_agent` with AgentArmor initialized first so underlying Gemini traffic is protected once the ADK agent runs. When executed directly, it prints the quick steps for dropping the file into an ADK project and launching it with `adk web`.

```bash
python examples/google_adk_example.py
```

### `google_adk_project/`
Provides a copy-paste Google ADK project layout with `agent.py`, `.env.example`,
and `adk web` startup notes.

```bash
cp -R examples/google_adk_project ./agentarmor-adk-demo
```

### `agno_example.py`
Demonstrates Agno using OpenAI's Responses API through `OpenAIResponses`. It shows a normal request, then a blocked prompt-injection attempt, while AgentArmor tracks the full run.

```bash
python examples/agno_example.py
```

### `agno_tool_policy_example.py`
Focuses on tool governance in Agno. It defines one safe tool path and one
blocked tool path so the `tool_firewall` configuration is easy to see.

```bash
python examples/agno_tool_policy_example.py
```

### `autogen_example.py`
Shows integration with AutoGen's conversational agents. A `UserProxyAgent` asks an `AssistantAgent` to write a Python script. AgentArmor tracks the cost of the multi-turn conversational loop, proving the patch successfully secures AutoGen's internal LLM router.

```bash
python examples/autogen_example.py
```

### `gemini_example.py`
Demonstrates AgentArmor with Google Gemini using the modern `google-genai` SDK. Shows budget tracking and shield protection working seamlessly with Gemini models.

```bash
export GEMINI_API_KEY="..."
python examples/gemini_example.py
```

### `hooks_example.py`
A deep dive into the Middleware/Hooks system. It registers custom `@before_request`, `@after_response`, and `@on_stream_chunk` decorators to invisibly inject context into prompts, log external analytics, and censor profanity during real-time streaming.

```bash
python examples/hooks_example.py
```

### `hitl_example.py`
Demonstrates the Human-in-the-Loop Policy Gate. Shows how to configure risk levels, approval callbacks, and auto-approve/deny rules for tool calls. Includes examples of blocking dangerous actions and auto-approving safe ones.

```bash
python examples/hitl_example.py
```

### `compliance_example.py`
Shows how to enable the compliance reporter alongside existing modules, capture a compliance-relevant data event, and generate a SOC2/GDPR report from the active session.

```bash
python examples/compliance_example.py
```
