# AgentArmor 🛡️

**Local-first runtime controls for Python LLM apps and agents.**

[![PyPI](https://img.shields.io/pypi/v/agentarmor.svg)](https://pypi.org/project/agentarmor/)
[![Downloads](https://img.shields.io/pypi/dm/agentarmor.svg)](https://pypistats.org/packages/agentarmor)
[![Python versions](https://img.shields.io/pypi/pyversions/agentarmor.svg)](https://pypi.org/project/agentarmor/)
[![CI](https://github.com/ankitlade12/AgentArmor/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitlade12/AgentArmor/actions/workflows/ci.yml)
[![SDK & Framework Compatibility](https://github.com/ankitlade12/AgentArmor/actions/workflows/framework-integration.yml/badge.svg)](https://github.com/ankitlade12/AgentArmor/actions/workflows/framework-integration.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Budget circuit breakers, PII/secrets redaction, tool-call policy checks, rate limits, and audit traces — wrapped around your existing OpenAI / Anthropic / Gemini calls in two lines. No hosted proxy, no account, no extra network hops.**

Links: [Support Matrix](SUPPORT_MATRIX.md) | [Security Policy](SECURITY.md) | [Examples](examples/README.md)

![AgentArmor demo: a budget circuit breaker firing at its dollar limit and an unsafe call being blocked](docs/_static/readme-demo.gif)

> **Status (v1.6).** The budget circuit breaker, output redaction, rate limiter, context guard, and flight recorder are deterministic and production-ready. The detectors — prompt injection, toxicity, unicode, exfiltration, and more — are heuristic, defense-in-depth checks: they reduce risk but are **not a complete security boundary**, and pattern-based detection is bypassable by design. See [Benchmarks & limitations](#benchmarks) and [SECURITY.md](SECURITY.md). Adversarial test cases and edge-case reports are very welcome.

## What is AgentArmor?

AgentArmor is an open-source Python SDK that adds runtime controls around your LLM calls: a hard budget circuit breaker, PII/secrets redaction, tool-call policy checks, rate limiting, and a complete local audit trail of every interaction.

It hooks into the `openai` and `anthropic` client libraries in-process, so the controls apply to your existing code — and anything built on those SDKs — without proxies, accounts, or rewrites. Optional defense-in-depth detectors (prompt injection, toxicity, and more) are documented per-feature below, with their limits stated honestly.

---

## Quickstart

**Drop-in Mode (Recommended)**
Two lines. Zero code changes to your existing agent.

```python
import agentarmor
import openai

# 1. Initialize your shields
agentarmor.init(
    budget="$5.00",            # Circuit breaker — kills runaway spend
    shield=True,               # Prompt injection detection
    # ml_shield=True,          # ML-powered injection detection (requires agentarmor[ml])
    filter=["pii", "secrets"], # Output firewall — blocks leaks
    record=True,               # Flight recorder — replay any session
    rate_limit="10/min",       # Rate limiter — Sliding-window throttling
    context_guard=0.95         # Context guard — Pre-flight token limit
)

# 2. Your existing code — no changes needed!
client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Analyze this market..."}]
)

# 3. Get your safety and cost report
print(agentarmor.spent())      # e.g. 0.0035
print(agentarmor.remaining())  # e.g. 4.9965
print(agentarmor.report())     # Full cost/security breakdown

# 4. Tear down the shields
agentarmor.teardown()
```

`agentarmor.init()` patches the OpenAI and Anthropic SDKs in-process, so every call is tracked and the configured controls are applied automatically.

**Works with Google Gemini too — zero code changes:**

```python
import agentarmor
from google import genai

agentarmor.init(budget="$5.00", shield=True, filter=["pii", "secrets"])

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Analyze this market..."
)

print(agentarmor.report())  # Gemini calls tracked automatically
```

---

## Install

```bash
pip install agentarmor
```
*Requires Python 3.10+. No external infrastructure dependencies.*

### Optional Dependencies

```bash
pip install agentarmor[gemini]    # Google Gemini support
pip install agentarmor[ml]        # ML-based injection detection (scikit-learn)
pip install agentarmor[toxicity]  # ML-based toxicity detection (detoxify)
pip install agentarmor[drift]     # Semantic drift detection (sentence-transformers)
pip install agentarmor[all]       # All providers + optional features
```

---

## Drop-in API

| Function | Description |
| :--- | :--- |
| `agentarmor.init(...)` | Start tracking. Patches OpenAI/Anthropic/Gemini SDKs. Loads chosen shields. |
| `agentarmor.init_from_config(path)` | Initialize AgentArmor from a YAML/JSON configuration file. |
| `agentarmor.spent()` | Total dollars spent so far in this session. |
| `agentarmor.remaining()` | Dollars left in the budget. |
| `agentarmor.report()` | Full security and cost breakdown as a dictionary. |
| `agentarmor.teardown()` | Stop tracking, unpatch SDKs, and clean up. |
| `agentarmor.validate_mcp_server(name)` | Check if an MCP server is trusted. |
| `agentarmor.validate_mcp_tool(name, args)` | Validate an MCP tool call against policies. |
| `agentarmor.authenticate_mcp_server(name, token)` | Pre-authenticate an MCP server with an auth token. |
| `agentarmor.spawn_agent(id, parent_id, budget)` | Register a sub-agent with inherited safety constraints. |
| `agentarmor.end_agent(id)` | End a sub-agent and roll up its stats to its parent. |
| `agentarmor.compliance_report(framework)` | Export control-mapped compliance evidence (SOC2/HIPAA/GDPR). |
| `agentarmor.init(strict=True)` | (v1.3) Raise `ConfigurationError` on typo'd kwargs with "did you mean?" suggestions. |
| `agentarmor.demo_attacks()` | (v1.3) Run ~21 synthetic attacks through active config locally; reports per-module block rates. |
| `agentarmor.last_trace()` | (v1.4) Returns the most recent Explain Mode trace. |
| `agentarmor.find_trace(e)` | (v1.4) Recover trace from a wrapped exception. |
| `agentarmor.last_trace_status()` | (v1.4) Diagnostic — answers "why is `last_trace()` None?". |

---

## Strict Mode (v1.3+)

Catches typo'd kwargs at `init()` time so misconfigured shields don't silently do nothing.

```python
import agentarmor

# Typo: "unicode_sheild" instead of "unicode_shield"
agentarmor.init(strict=True, unicode_sheild=True)
# raises ConfigurationError: unknown kwarg 'unicode_sheild'. Did you mean 'unicode_shield'?
```

Without `strict=True` (the default), typo'd kwargs emit a one-time `UserWarning` and continue — preserving backwards compatibility. Use `strict=True` in production to catch silent misconfigurations.

Strict mode also hard-rejects case-typos on the `strict` kwarg itself (`Strict=True`, `STRICT=True`) because silently dropping those would defeat the entire validation.

---

## Demo Attacks (v1.3+)

Instantly see your shields working against ~21 hand-curated synthetic attacks — no LLM calls, no API keys needed.

```python
import agentarmor

agentarmor.init(shield=True, filter=["pii"], toxicity=True)
report = agentarmor.demo_attacks()
print(report)
# AgentArmor — Attack Demo Results
# ================================
# shield (prompt injection):    18/20 blocked  (90%)
# filter (PII):                 5/5  blocked  (100%)
# toxicity:                     12/15 blocked  (80%)
# OVERALL:                      35/40 blocked  (87.5%)
```

`demo_attacks()` runs each sample through your active `before_request` hooks locally and reports per-module block rates. It snapshots and restores module state so it won't pollute your `report()`. This is a smoke test, NOT a security evaluation — see the [benchmarks](benchmarks/README.md) for measured F1/precision/recall against industry datasets.

---

## Explain Mode (v1.4+)

When a shield blocks (or modifies) an LLM call, `agentarmor.last_trace()` shows you which shields ran, what each decided, and why. Off by default; near-zero overhead when off; production-safe (PII-redacted by default).

```python
import agentarmor

agentarmor.init(shield=True, filter=["pii"], explain=True)

# Your existing OpenAI / Anthropic / Gemini code, no changes
client.chat.completions.create(...)

trace = agentarmor.last_trace()
print(trace.blocked_by)         # "shield" — module that fired (or None)
print(trace.events)              # list of (module, decision, detail, latency_us)
print(trace.silent_modules)      # modules that ran without recording detail
print(trace.closed_reason)       # "after_response" | "blocked" | "stream_close" | "timeout"
```

When a shield raises, the exception carries the trace:

```python
try:
    client.chat.completions.create(...)
except agentarmor.InjectionDetected as e:
    print(e.trace.blocked_by)    # "shield"
    print(e.trace.events[0].detail)  # {"exception_type": "...", "message": "..."}
```

If a framework wraps your exception (FastAPI, Celery, Sentry), recover the trace via `find_trace`:

```python
except Exception as e:
    trace = agentarmor.find_trace(e) or agentarmor.last_trace()
```

Full Explain Mode reference — module detail coverage, performance numbers, OpenTelemetry export, redaction security notes, troubleshooting, and version compatibility — lives in [FEATURES.md](FEATURES.md#explain-mode-reference).

---

## Features

AgentArmor's controls fall into three tiers, and the tier tells you how much to trust each one:

- **Core controls** (below, in full) — deterministic and production-ready: they do exactly what they say on every call.
- **More deterministic controls** — same rule-based reliability, summarized in a table here and documented in full in [FEATURES.md](FEATURES.md).
- **Defense-in-depth detectors** and **experimental modules** — heuristic checks and newer research-grade work. Useful as additional layers, bypassable by a determined attacker, never a complete security boundary. See [Benchmarks](#benchmarks) for measured detection and false-positive rates.

### 💰 Budget Circuit Breaker
**Stop unexpected massive bills.** 
Tracks real-time dollar-denominated token usage across requests. When the configured limit is exceeded, it trips the circuit breaker and raises a `BudgetExhausted` exception.

```python
import agentarmor
from agentarmor.exceptions import BudgetExhausted

agentarmor.init(budget="$5.00")

try:
    # Run your massive agent loop
    run_agent_loop()
except BudgetExhausted:
    print("Agent stopped. Budget limit reached!")
```

### 🔒 Output Firewall
**Stop sensitive data leaks.**
Automatically scans the LLM's response output before it is returned to your application. Redacts PII (Emails, SSNs, phone numbers) and secrets (API Keys, tokens) on the fly. 

```python
agentarmor.init(filter=["pii", "secrets"])

# If the LLM tries to output: "Contact me at admin@company.com or use key sk-123456"
# Your app actually receives: "Contact me at [REDACTED:EMAIL] or use key [REDACTED:API_KEY]"
```

### 📼 Flight Recorder
**Total observability and auditability.**
Silently records the exact inputs, outputs, models, timestamps, and latency of every API call to a local JSONL session file. Perfect for debugging rogue agents or maintaining compliance standards.

```python
agentarmor.init(record=True)
# Sessions are automatically streamed to `.agentarmor/sessions/session_xyz.jsonl`
```

### 🚦 Rate Limiter
**Prevent API spam and abuse.**
Sliding-window throttling ensures your agents don't exceed your designated request thresholds (e.g., `10/min`, `5/sec`).

```python
agentarmor.init(rate_limit="10/min")
```

### 🧠 Context Window Guard
**Pre-flight token checks.**
Automatically estimates tokens before sending the prompt to the API. If the prompt plus `max_tokens` exceeds the model's safe context limit (e.g., 95% of total allowed), the request is immediately blocked with a `ContextOverflow` exception, saving you from failed requests and truncated contexts.

```python
from agentarmor.exceptions import ContextOverflow
agentarmor.init(context_guard=0.95)

try:
    # Big prompt that exceeds limits
    client.chat.completions.create(...)
except ContextOverflow:
    print("Prompt too large for the model's context window!")
```

### 🔥 Tool-Call Firewall
**Control which tools your LLM can invoke.**
Enforces an allow/block list on tool calls (function calls) returned by the model. Unauthorized tool invocations are either blocked (raising `ToolCallBlocked`) or silently stripped from the response — preventing your agent from executing dangerous actions it was never meant to take.

```python
import agentarmor
from agentarmor.exceptions import ToolCallBlocked

# Allow-list mode — only these tools are permitted
agentarmor.init(tool_firewall={"allow": ["search", "calculator"], "on_violation": "block"})

# Or block-list mode — block specific dangerous tools
agentarmor.init(tool_firewall={"block": ["execute_code", "delete_file"], "on_violation": "strip"})

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Delete all files"}],
        tools=[...]
    )
except ToolCallBlocked as e:
    print(f"Blocked unauthorized tool call: {e}")
```

### More deterministic controls

Rule-based and reliable, like the core six — full docs with examples in [FEATURES.md](FEATURES.md#more-deterministic-controls).

| Control | What it does | Enable with |
|:---|:---|:---|
| [Latency Circuit Breaker](FEATURES.md#latency-circuit-breaker) | Trips a breaker after N consecutive slow calls; tracks avg/p95 latency. | `latency_breaker={...}` |
| [Provider-Aware Cost Analytics](FEATURES.md#provider-aware-cost-analytics) | Per-provider spend breakdown (OpenAI vs. Anthropic vs. Gemini) in `report()`. | automatic with `budget=` |
| [Canary Token Injection](FEATURES.md#canary-token-injection) | Injects a unique token into system prompts; blocks the response if it leaks. | `canary=True` |
| [Cost Attribution Tags](FEATURES.md#cost-attribution-tags) | Per-tag cost attribution (`set_tag("code-gen")`) for multi-tenant or A/B spend. | `cost_tags=True` |
| [Semantic Dedup (Replay Shield)](FEATURES.md#semantic-dedup-replay-shield) | Hash-blocks identical repeated prompt+model calls — the loop killer. | `dedup=True` |
| [Model Downgrade Cascade](FEATURES.md#model-downgrade-cascade) | Auto-downgrades to cheaper models as the budget depletes. | `cascade=[...]` |
| [MCP Server Security (v2)](FEATURES.md#mcp-server-security-v2) | MCP server allow/blocklists, per-tool path & argument policies, result validation. | `mcp_firewall={...}` |
| [Human-in-the-Loop (HITL) Policy Gate](FEATURES.md#human-in-the-loop-hitl-policy-gate) | Risk-tiered human approval for tool calls, with timeouts and auto-deny. | `hitl_gate={...}` |

### Defense-in-depth detectors (heuristic)

Pattern- and classifier-based checks. Bypassable by design — pair them with the deterministic tiers and see [Benchmarks](#benchmarks) for false-positive rates. Full docs in [FEATURES.md](FEATURES.md#defense-in-depth-detectors-heuristic).

| Control | What it does | Enable with |
|:---|:---|:---|
| [Prompt Shield (pattern-based injection filter)](FEATURES.md#prompt-shield-pattern-based-injection-filter) | Regex denylist of known jailbreak phrasings — cheap first filter. | `shield=True` |
| [ML-Powered Injection Shield](FEATURES.md#ml-powered-injection-shield) | TF-IDF + logistic-regression classifier; ensemble with the regex layer. | `ml_shield=True` |
| [Code Safety Shield](FEATURES.md#code-safety-shield) | Pattern-scans generated Python/JS/SQL/shell for dangerous constructs. | `code_shield=True` |
| [Toxicity & Content Safety Filter](FEATURES.md#toxicity--content-safety-filter) | 7-category toxicity patterns; optional `detoxify` ML mode. | `toxicity=True` |
| [Hallucination / Grounding Guard](FEATURES.md#hallucination--grounding-guard) | n-gram / number / proper-noun overlap vs. source docs to flag hallucinations. | `grounding={...}` |
| [Data Exfiltration Guard](FEATURES.md#data-exfiltration-guard) | Flags base64/hex/zero-width/URL-encoded data smuggling in outputs. | `exfiltration_guard=True` |
| [Tool-Policy & Capability-Request Detection](FEATURES.md#tool-policy--capability-request-detection) | Hard `allowed_tools` allowlist + heuristic scan for capability-escalation phrasing. | `privilege_escalation=True` |
| [Unicode Injection Shield](FEATURES.md#unicode-injection-shield) | Zero-width, homoglyph, and bidi-control tricks in inputs. | `unicode_shield=True` |
| [Semantic Drift Detector](FEATURES.md#semantic-drift-detector) | Embedding-based topic-drift tracking across conversation turns. | `semantic_drift={...}` |

### Experimental modules

The newest, most research-grade work — APIs and behavior may evolve. Full docs in [FEATURES.md](FEATURES.md#experimental-modules).

| Control | What it does | Enable with |
|:---|:---|:---|
| [Multi-Agent Graph Safety (v2)](FEATURES.md#multi-agent-graph-safety-v2) | Budget and policy inheritance across spawned sub-agent trees. | `agent_graph={...}` |
| [Chain-of-Thought Auditor](FEATURES.md#chain-of-thought-auditor) | Scans extended-thinking / reasoning traces for misalignment phrasing. | `cot_auditor=True` |
| [Prompt Fuzzer (Red Team Testing)](FEATURES.md#prompt-fuzzer-red-team-testing) | Built-in red-team generator to fuzz your own shields. | `tools/prompt_fuzzer` |
| [Runtime Taint Tracking](FEATURES.md#runtime-taint-tracking) | Data-provenance labels with sink policies (e.g., no PII into `send_email`). | `taint_tracker={...}` |
| [Honeytools (Deception Rail)](FEATURES.md#honeytools-deception-rail) | Fake tools and credentials as tripwires for compromised agents. | `honeytools=True` |
| [Safe-Plan Engine](FEATURES.md#safe-plan-engine) | Structured "why blocked + safer alternative" guidance on blocks. | `SafePlanEngine` |
| [Echo-Chamber Detector](FEATURES.md#echo-chamber-detector) | Flags hallucinated claims circulating between agents as fake confirmation. | `echo_chamber={...}` |
| [Compliance Evidence Export (SOC2 / HIPAA / GDPR)](FEATURES.md#compliance-evidence-export-soc2--hipaa--gdpr) | Maps safety events to SOC2/HIPAA/GDPR control families; JSON evidence export. | `compliance={...}` |

---

## 📄 Policy-as-Code Configuration

Store your agent's safety parameters in a declarative YAML or JSON file instead of hard-coding them. AgentArmor automatically detects `.agentarmor.yml` in your working directory.

**`.agentarmor.yml`**
```yaml
budget: 5.00
shield: true
filter:
  - pii
  - secrets
record: true
rate_limit: "10/min"
context_guard: 0.95
```

```python
import agentarmor
# Loads .agentarmor.yml and initializes all shields
agentarmor.init_from_config()
```

---

## Integrations

AgentArmor works well with many major Python AI frameworks that route through
supported SDK surfaces.

Because AgentArmor monkey-patches the underlying `openai`, `anthropic`, and
`google-genai` clients directly at the network level, you often do not need
framework-specific callbacks or middleware. Just initialize
`agentarmor.init()` at the top of your script and it will automatically
protect frameworks and SDK scripts that use those patched clients.

See [`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md) for the tested provider surfaces
and evidence level behind each compatibility claim.

Current ecosystem examples and support notes include:

- **LiteLLM**
- **Pydantic AI**
- **Google ADK**
- **LangChain / LangGraph**
- **LlamaIndex**
- **CrewAI**
- **Agno / Phidata**
- **Autogen**
- **SmolAgents**
- **Google Gemini** (via `google-genai`)
- Custom raw SDK scripts

---

## Hooks & Middleware

AgentArmor is highly extensible. You can write custom logic that runs exactly before a request leaves or exactly after a response arrives. Because AgentArmor handles the patching, your hooks work uniformly and safely for both OpenAI and Anthropic.

```python
import agentarmor
from agentarmor import RequestContext, ResponseContext

@agentarmor.before_request
def inject_timestamp(ctx: RequestContext) -> RequestContext:
    # Invisibly append context to the system prompt
    ctx.messages[0]["content"] += f"\nToday is Friday."
    return ctx

@agentarmor.after_response
def custom_analytics(ctx: ResponseContext) -> ResponseContext:
    # Send cost and latency data to your custom dashboard
    print(f"Model {ctx.model} cost {ctx.cost}")
    return ctx

@agentarmor.on_stream_chunk
def censor_profanity(text: str) -> str:
    # Mutate streaming chunks in real-time
    return text.replace("badword", "*******")
    
agentarmor.init()
```

---

## Supported Models

Built-in automated tracking for standard models across the major providers. Supports both the Chat Completions API and the newer OpenAI Responses/Agents API surface.

| Provider | Models | API Surfaces |
| :--- | :--- | :--- |
| **OpenAI** | `gpt-4.5`, `o3-mini`, `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo` | Chat Completions, Responses API |
| **Anthropic** | `claude-4`, `claude-opus-4`, `claude-sonnet-4-5`, `claude-haiku-4-5` | Messages |
| **Google** | `gemini-2.0-pro`, `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash` | GenerateContent |

*Note: For models not explicitly listed, generic conservative fallback pricing is used.*

---

## Benchmarks

These are reproducible evals on public datasets, run with the shipping configuration — shown with false-positive rates and the places we lose, not just the wins. High recall on some sets (AdvBench, HarmBench) comes with real false-positive cost on others (JailbreakBench, RealToxicityPrompts, HaluEval). The detectors are defense-in-depth, not a security guarantee.

Tested against **10 industry datasets + 2 synthetic benchmarks** (5,100+ samples) spanning prompt injection, toxicity, hallucination, data exfiltration, and unicode attacks. Full results at [`benchmarks/README.md`](benchmarks/README.md).

**Head-to-head comparison** — AgentArmor vs LlamaGuard 3 and OpenAI Moderation across six datasets with bootstrap F1 CIs, balance-aware metrics (MCC + balanced-accuracy on imbalanced sets), per-dataset operating-point naming, and honest loss annotations: [`BENCHMARKS_HEAD_TO_HEAD.md`](BENCHMARKS_HEAD_TO_HEAD.md). (Perspective API was dropped from v1 — Google/Jigsaw announced sunset with API EOL 2026-12-31.) Methodology in [`tasks/head-to-head-report/SPEC.md`](tasks/head-to-head-report/SPEC.md); operations in [`RUNBOOK.md`](RUNBOOK.md).

### Harmful Content Detection (Combined: Shield + ML Shield + Toxicity)

| Benchmark | Samples | Precision | Recall | F1 | FP Rate |
|:----------|--------:|----------:|-------:|---:|--------:|
| **AdvBench** | 200 | 100.0% | 91.9% | **95.8%** | 0.0% |
| **HarmBench** | 200 | 100.0% | 90.0% | **94.7%** | 0.0% |
| **Fuzzer Self-Test** | 148 | 97.4% | 86.7% | **91.7%** | 15.0% |
| **JailbreakBench** | 200 | 70.2% | 73.0% | **71.6%** | 31.0% |

### Toxicity & Bias Detection (Built-in ML classifier)

| Benchmark | Type | Precision | Recall | F1 | FP Rate |
|:----------|:-----|----------:|-------:|---:|--------:|
| **ToxiGen** | Implicit hate speech (13 groups) | 100.0% | 58.5% | **73.8%** | 0.0% |
| **RealToxicityPrompts** | Subtle toxicity | 54.8% | 51.0% | **52.8%** | 42.0% |

### Hallucination Detection (Grounding + TF-IDF semantic similarity)

| Benchmark | Type | Precision | Recall | F1 | FP Rate |
|:----------|:-----|----------:|-------:|---:|--------:|
| **TruthfulQA** | Factual grounding (817 Q&A) | 100.0% | 56.9% | **72.5%** | 0.0% |
| **HaluEval** | QA/dialogue/summarization | 62.7% | 84.0% | **71.8%** | 50.0% |

### Specialized Detectors

| Benchmark | Type | Precision | Recall | F1 | FP Rate |
|:----------|:-----|----------:|-------:|---:|--------:|
| **Exfiltration** | Base64/hex/steganography/URL | 100.0% | 100.0% | **100.0%** | 0.0% |
| **Unicode Injection** | Zero-width/homoglyph/bidi/tags | 100.0% | 91.2% | **95.4%** | 0.0% |

> Run benchmarks yourself: `pip install datasets scikit-learn && python benchmarks/run_industry_benchmarks.py`

---

## The Problem

AI agents are unpredictable by design. A user might try to hijack your system prompt. The model might hallucinate an API key. An agent might get stuck in an infinite loop and make 300 LLM calls.

1. **The Hijack Problem** — Users type `"ignore previous instructions"` and take control of your LLM.
2. **The Output Leak Problem** — Your agent accidently regurgitates a real customer's SSN or an OpenAI API key it saw in context.
3. **The Loop Problem** — A stuck agent makes 200 LLM calls in 10 minutes. $50-$200 down the drain before anyone notices.
4. **The Invisible Spend** — Tokens aren't dollars. `gpt-4o` costs 15x more than `gpt-4o-mini`.

**AgentArmor fills the gap:** real-time, in-memory, deterministic controls that cap spend, redact secrets, and kill runaway sessions — plus defense-in-depth detectors for injection and unsafe output as an additional layer.

## Design Philosophy

- **Zero infrastructure.** No Redis, no servers, no cloud accounts. AgentArmor is a pure Python library that runs entirely in your process.
- **Zero code changes.** You don't rewrite your codebase to use a special client. Just call `agentarmor.init()` and the controls apply to your existing code.
- **Data stays local.** Everything runs in-memory and on-disk. Your prompts and responses never leave your machine.
- **Framework agnostic.** Works with any framework that uses the `openai`, `anthropic`, or `google-genai` SDKs under the hood — no vendor lock-in.

---

## License

**MIT License** 

Ship your agents with confidence. Set a budget. Set your shields. Move on.
