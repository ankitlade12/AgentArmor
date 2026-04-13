# AgentArmor Compatibility Matrix

Verified SDK surfaces that AgentArmor intercepts at runtime.

## Provider SDK Surfaces

| Provider | SDK | Surface | Sync | Async | Streaming | Min Version |
|----------|-----|---------|:----:|:-----:|:---------:|-------------|
| OpenAI | `openai` | `chat.completions.create` | Yes | Yes | Yes | `>=1.0.0` |
| OpenAI | `openai` | `responses.create` | Yes | Yes | Yes | `>=1.66.0` |
| Anthropic | `anthropic` | `messages.create` | Yes | Yes | Yes | `>=0.25.0` |
| Google | `google-genai` | `models.generate_content` | Yes | Yes | Yes | `>=1.0.0` |
| Google | `google-genai` | `models.generate_content_stream` | Yes | Yes | — | `>=1.0.0` |

## Framework Compatibility

AgentArmor works with any framework that uses the above SDKs under the hood.
No framework-specific adapters are needed.

| Framework | Tested | Notes |
|-----------|:------:|-------|
| LangChain / LangGraph | Yes | Via OpenAI or Anthropic SDK |
| LlamaIndex | Yes | Via OpenAI SDK |
| CrewAI | Yes | Via OpenAI or Anthropic SDK |
| Autogen | Yes | Via OpenAI SDK |
| Agno / Phidata | Yes | Via OpenAI SDK |
| SmolAgents | Yes | Via OpenAI or Anthropic SDK |
| Raw SDK scripts | Yes | Direct patching |

## Python Versions

| Version | CI Status |
|---------|:---------:|
| 3.10 | Tested |
| 3.11 | Tested |
| 3.12 | Tested |
| 3.13 | Tested |

## What Gets Patched

AgentArmor patches at the **SDK transport layer**, not the framework layer.
This means every request/response flowing through a supported SDK is
intercepted regardless of which framework wraps it. The `agentarmor.init()`
call applies patches once; no per-framework configuration is needed.

## Regression Harness

The `tests/test_support_matrix.py` file contains automated regression tests
for each surface listed above. Tests auto-skip when the corresponding SDK
is not installed and run against real SDK imports (not mocks) where possible.
