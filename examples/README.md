# AgentArmor Examples

This directory contains examples of how to integrate `agentarmor` with various popular AI frameworks.

## Setup

To run these examples, you should install `agentarmor` and the required frameworks in your virtual environment.

```bash
# 1. Install agentarmor (from the root of the repository)
pip install -e .

# 2. Install the example dependencies
pip install -r examples/requirements.txt
```

## Running the Examples

Make sure you have your API keys set before running the examples. Most examples use OpenAI models.

```bash
export OPENAI_API_KEY="sk-..."
```

### `basic.py`
Demonstrates the lowest-level usage of AgentArmor. It initializes the core shields (Budget, Shield, Filter, Record) and sends two raw `openai` client requests: one normal request, and one simulated prompt injection attack to show how the `ShieldModule` intercepts and blocks it.

```bash
python examples/basic.py
```

### `langchain_example.py`
Demonstrates that AgentArmor perfectly patches LangChain's `ChatOpenAI` wrapper. It executes a normal query to show cost tracking, and a prompt injection to show LangChain throwing a `InjectionDetected` exception.

```bash
python examples/langchain_example.py
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

### `autogen_example.py`
Shows integration with AutoGen's conversational agents. A `UserProxyAgent` asks an `AssistantAgent` to write a Python script. AgentArmor tracks the cost of the multi-turn conversational loop, proving the patch successfully secures AutoGen's internal LLM router.

```bash
python examples/autogen_example.py
```

### `hooks_example.py`
A deep dive into the V1.0 Middleware/Hooks system. It registers custom `@before_request`, `@after_response`, and `@on_stream_chunk` decorators to invisibly inject context into prompts, log external analytics, and censor profanity during real-time streaming.

```bash
python examples/hooks_example.py
```
