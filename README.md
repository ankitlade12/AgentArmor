# AgentArmor

> The full-stack safety layer for AI agents. One install. Four shields.

AgentArmor provides prompt injection defense, budget limits, output filtering, and session recording out of the box with just two lines of code.

## Quickstart

```python
import agentarmor

agentarmor.init(
    budget="$5.00",            # Circuit breaker — kills runaway spend
    shield=True,               # Prompt injection detection
    filter=["pii", "secrets"], # Output firewall — blocks leaks
    record=True                # Flight recorder — replay any session
)
```

No proxy. No account. No framework lock-in. Every OpenAI and Anthropic API call is now silently protected.

## Why AgentArmor?

Existing tools require you to swap out your LLM provider for a proxy URL, manage API keys in external platforms, or rewrite your application logic to route through their custom client wrappers.

AgentArmor hooks directly into the core networking libraries of `openai` and `anthropic`, placing an invisible firewall right inside your Python process. Zero added infrastructure.

## Features

- **Budget Limit**: Prevents unexpected massive bills by tracking usage and stopping requests when they exceed a configurable dollar limit.
- **Shield (Prompt Injection)**: Uses pattern matching to block known jailbreaks like "ignore previous instructions".
- **Filter (Output redaction)**: Automatically redacts PII like emails, SSNs, credit cards, and secrets before they enter your app or database.
- **Recorder (Flight Recorder)**: Dumps complete inputs, outputs, models, and latency into local JSONL files for audit and debug.

## Installation

```bash
pip install agentarmor
```

## Documentation & Examples

Check out the `/examples` directory for basic usage and error handling demonstrations.

### API Reference

- `agentarmor.init(...)`: Initialize the monkey-patch and load the requested modules.
- `agentarmor.report()`: Return a summary JSON object detailing spend, shield catches, reductions, etc.
- `agentarmor.spent()`: Returns the total exact dollar spend tracked so far.
- `agentarmor.remaining()`: Returns the exact dollar amount remaining on the budget.
- `agentarmor.teardown()`: Revert all monkey-patches.
