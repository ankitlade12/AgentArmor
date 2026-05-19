# AgentArmor Compatibility Matrix

Verified SDK surfaces that AgentArmor intercepts at runtime.

## Provider SDK Surfaces

| Provider | SDK | Surface | Sync | Async | Streaming | Min Version | CI Tested |
|----------|-----|---------|:----:|:-----:|:---------:|-------------|:---------:|
| OpenAI | `openai` | `chat.completions.create` | Yes | Yes | Yes | `>=1.0.0` | Yes |
| OpenAI | `openai` | `responses.create` | Yes | Yes | Yes | `>=1.66.0` | Yes |
| Anthropic | `anthropic` | `messages.create` | Yes | Yes | Yes | `>=0.25.0` | Yes |
| Google | `google-genai` | `models.generate_content` | Yes | Yes | Yes | `>=1.0.0` | Yes |
| Google | `google-genai` | `models.generate_content_stream` | Yes | Yes | — | `>=1.0.0` | Yes |

## Framework Compatibility

AgentArmor patches at the **SDK transport layer**, not the framework layer.
Frameworks below are compatible because they use the patched SDKs under the
hood. The "Evidence" column indicates how we verified compatibility.

| Framework | Compatible | Evidence |
|-----------|:----------:|----------|
| LiteLLM | Yes | Example in `examples/litellm_example.py`; uses OpenAI-compatible transport underneath |
| LangChain / LangGraph | Yes | Examples in `examples/langchain_example.py` and `examples/langgraph_multistep_example.py`; uses OpenAI/Anthropic SDK surfaces |
| LlamaIndex | Yes | Example in `examples/llamaindex_example.py`; uses OpenAI SDK |
| CrewAI | Yes | Example in `examples/crewai_example.py`; uses OpenAI/Anthropic SDK |
| Autogen | Yes | Example in `examples/autogen_example.py`; uses OpenAI SDK |
| Pydantic AI | Yes | Example in `examples/pydantic_ai_example.py`; smoke-checked in `tests/test_examples_smoke.py`; uses OpenAI Responses |
| Google ADK | Yes | Example in `examples/google_adk_example.py`; smoke-checked in `tests/test_examples_smoke.py`; protects Gemini traffic once ADK executes the agent |
| Agno / Phidata | Yes | Examples in `examples/agno_example.py` and `examples/agno_tool_policy_example.py`; smoke-checked in `tests/test_examples_smoke.py`; uses OpenAI Responses SDK surface |
| MCP policy controls | Yes | Example in `examples/mcp_policy_example.py`; reusable presets in `agentarmor/mcp_presets.py`; smoke-checked in `tests/test_examples_smoke.py` |
| SmolAgents | Yes | Architecture-level (uses OpenAI/Anthropic SDK); no dedicated example yet |
| Raw SDK scripts | Yes | CI-tested in `tests/test_support_matrix.py` |

## Python Versions

| Version | CI Status |
|---------|:---------:|
| 3.10 | Tested |
| 3.11 | Tested |
| 3.12 | Tested |
| 3.13 | Tested |

## Regression Harness

`tests/test_support_matrix.py` contains automated regression tests for each
SDK surface. Tests auto-skip when the corresponding SDK is not installed.
Framework-level example smoke coverage lives in `tests/test_examples_smoke.py`,
and direct AWS Bedrock patching is not currently claimed as a first-class
runtime surface unless traffic routes through one of the patched provider SDKs
above.
