# AgentArmor Compatibility Matrix

Verified SDK surfaces that AgentArmor intercepts at runtime.

## Provider SDK Surfaces

| Provider | SDK | Surface | Sync | Async | Streaming | Min Version | CI Tested |
|----------|-----|---------|:----:|:-----:|:---------:|-------------|:---------:|
| OpenAI | `openai` | `chat.completions.create` | Yes | Yes | Yes | `>=1.0.0` | Yes |
| OpenAI | `openai` | `responses.create` | Yes | Yes | Yes | `>=1.66.0` | Pending* |
| Anthropic | `anthropic` | `messages.create` | Yes | Yes | Yes | `>=0.25.0` | Yes |
| Google | `google-genai` | `models.generate_content` | Yes | Yes | Yes | `>=1.0.0` | Yes |
| Google | `google-genai` | `models.generate_content_stream` | Yes | Yes | — | `>=1.0.0` | Yes |

*Responses API patching is implemented and tested on `feature/openai-responses-api`. CI coverage on this branch will pass after that branch merges.

## Framework Compatibility

AgentArmor patches at the **SDK transport layer**, not the framework layer.
Frameworks below are compatible because they use the patched SDKs under the
hood. The "Evidence" column indicates how we verified compatibility.

| Framework | Compatible | Evidence |
|-----------|:----------:|----------|
| LangChain / LangGraph | Yes | Example in `examples/langchain_example.py`; uses OpenAI/Anthropic SDK |
| LlamaIndex | Yes | Example in `examples/llamaindex_example.py`; uses OpenAI SDK |
| CrewAI | Yes | Example in `examples/crewai_example.py`; uses OpenAI/Anthropic SDK |
| Autogen | Yes | Example in `examples/autogen_example.py`; uses OpenAI SDK |
| Agno / Phidata | Yes | Architecture-level (uses OpenAI SDK); no dedicated example yet |
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
Framework-level integration tests are tracked as a separate deliverable.
