# Anthropic-Exclusive Features (Acquisition-Oriented)

This document describes **novel features that exist only for the Anthropic/Claude API** in AgentArmor. They are not available for OpenAI, Google, or other providers. The goal is to make AgentArmor the obvious safety and governance layer for teams building on Claude, and to create unique value that could justify acquisition.

---

## 1. **Prompt Cache Guard & Cache-Aware Budget** (Anthropic-only)

**Why it’s exclusive:** Only Anthropic’s API exposes prompt caching with distinct token types: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. No other major provider exposes this in the same way.

**What to build:**

- **Cache-aware cost calculation**  
  Use Anthropic’s usage object when `provider == "anthropic"`:
  - `cache_creation_input_tokens` → 1.25× input price  
  - `cache_read_input_tokens` → 0.10× input price  
  - `input_tokens` → 1× input price  
  So budget and `spent()` reflect real Claude API cost, including cache discounts.

- **Cache Guard (optional)**  
  - `agentarmor.init(anthropic_cache_guard=True)` (or similar)  
  - Enforce policies such as: “reject request if prompt is above N tokens and cache_control is not set” (to avoid accidental full-context billing).  
  - Or: “warn / metric when cache_read is 0 on a long prompt” (missing cache).

- **Cache analytics in `report()`**  
  For Anthropic only, add to session report:
  - `cache_creation_tokens`, `cache_read_tokens`, `regular_input_tokens`
  - Optional: `cache_savings_estimate` (dollars saved vs non-cached).

**Novelty:** No other SDK wraps Claude’s caching semantics into budget and policy. This is **Anthropic-exclusive** and directly aligned with their product.

---

## 2. **Extended Thinking Guard** (Anthropic-only)

**Why it’s exclusive:** Claude’s API returns `content` blocks of type `thinking` and `text`. No other major provider has this “extended thinking” block structure.

**What to build:**

- **Thinking-block isolation**  
  When `provider == "anthropic"` and response has multiple content blocks:
  - Parse `content[]` and separate `type: "thinking"` from `type: "text"`.
  - Expose only the concatenated `text` blocks to the rest of AgentArmor (filters, recorder, etc.) so that:
    - PII/filter rules apply only to the final answer, not to thinking.
    - Flight recorder can optionally record thinking separately (e.g. for debugging) or omit it for compliance.

- **Thinking leak prevention**  
  - Option: `anthropic_hide_thinking=True` (default for non-dev?).  
  - When returning the response to the app, strip or redact `thinking` blocks so downstream code never sees them unless explicitly allowed.  
  - Prevents accidental logging or display of internal reasoning.

- **Thinking budget**  
  - If the request includes `thinking={"type": "enabled", "budget_tokens": N}`, AgentArmor can:
    - Track “thinking tokens” separately in usage (if exposed by API).
    - Enforce a cap: e.g. “total thinking tokens per session &lt; X” to avoid runaway reasoning cost.

**Novelty:** Only Claude has thinking blocks. A “thinking guard” that isolates, redacts, or caps them is **Anthropic-exclusive** and directly supports safe deployment of extended thinking.

---

## 3. **Tool-Use Boundary Guard** (Anthropic-only)

**Why it’s exclusive:** Claude’s message format uses `tool_use` and `tool_result` content blocks with a specific schema. Cross-boundary injection (e.g. user content forging a `tool_use`) is a Claude-specific attack surface.

**What to build:**

- **Request-side: validate tool_result blocks**  
  Before sending a request to the API, if `provider == "anthropic"` and messages contain blocks with `type == "tool_result"`:
  - Ensure each `tool_result` has a valid `tool_use_id` that matches a prior assistant `tool_use` in the same conversation.
  - Optionally: scan `content` of `tool_result` for prompt-injection patterns (e.g. “ignore previous instructions”) and block or flag.

- **Response-side: validate tool_use blocks**  
  After receiving a response, validate that every `tool_use` block comes from the model (e.g. no user-injected `tool_use` in the message list). This is mostly defensive; the main win is request-side validation of `tool_result` content.

- **Allow-list of tool names**  
  - `agentarmor.init(anthropic_tool_allowlist=["get_weather", "search_db"])`.  
  - If the model returns a `tool_use` with `name` not in the allow-list, AgentArmor blocks or raises before the app executes it.  
  - Reduces risk of prompt-injection-induced tool calls.

**Novelty:** Tool-use structure and validation are specific to Claude’s message format. **Anthropic-exclusive** and improves safety of agentic workflows.

---

## 4. **Claude Refusal Analytics** (Anthropic-only)

**Why it’s exclusive:** Claude returns `stop_reason: "refusal"` (and possibly other stop reasons) in a well-defined way. No other provider uses this exact contract.

**What to build:**

- **Refusal detection**  
  When `provider == "anthropic"`, inspect `stop_reason` (and any refusal-related fields in the response). If present, treat the response as a refusal.

- **Refusal metrics in `report()`**  
  For Anthropic only, add:
  - `refusal_count` (number of refusals in the session),
  - Optional: `refusal_examples` (e.g. last N request snippets that led to refusal, with PII redacted).

- **Optional callback**  
  - `agentarmor.init(anthropic_on_refusal=my_handler)`.  
  - Called when a refusal is detected; app can log to SIEM, adjust UX, or trigger alerts.

**Novelty:** First-class handling of Claude refusals for observability and product behavior is **Anthropic-exclusive** and helps enterprises understand and react to safety stops.

---

## 5. **Anthropic-Specific Audit Log (Compliance)** (Anthropic-only)

**Why it’s exclusive:** Compliance teams care about “all Claude API usage.” An audit log that speaks Anthropic’s language (model names, token types, cache, stop_reason) is provider-specific.

**What to build:**

- **Extended session record for Anthropic**  
  When `record=True` and `provider == "anthropic"`, persist:
  - All existing fields (model, messages, cost, etc.),
  - `usage` broken down as: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`,
  - `stop_reason`,
  - Optional: `thinking_blocks_included` (boolean or count).

- **Export format**  
  - Optional export to a schema (e.g. JSON) labeled “Anthropic Claude API audit” for compliance (SOC2, etc.), with clear field definitions.

**Novelty:** An audit trail that matches Anthropic’s API semantics (including cache and refusals) is **Anthropic-exclusive** and supports enterprise and acquisition narrative.

---

## 6. **System Prompt Best-Practice Check (Anthropic)** (Anthropic-only)

**Why it’s exclusive:** Anthropic documents best practices for system prompts (length, structure, XML, etc.). A pre-flight check that validates only when using Claude is provider-specific.

**What to build:**

- **Pre-request validation when provider is Anthropic**  
  Before sending, if the first message is a “system” role (or Anthropic’s system block):
  - Optional: max length (e.g. warn if &gt; 10k chars).
  - Optional: check for dangerous patterns (e.g. “ignore instructions” inside the system prompt).
  - Optional: suggest or enforce use of `<policy>` or similar tags if configured.

- **Config**  
  - `agentarmor.init(anthropic_system_prompt_guard=True)` (or similar).  
  - Only runs for Anthropic requests; no effect for OpenAI/Google.

**Novelty:** Tying system-prompt checks to Anthropic’s documented best practices makes this **Anthropic-exclusive** and positions AgentArmor as the “safe deployment” layer for Claude.

---

## Implementation Notes

- **Provider gating:** Every feature above must be guarded by `if provider != "anthropic": return` (or equivalent) so they never run for OpenAI, Google, or others.
- **Init surface:** New init options can be namespaced, e.g.:
  - `anthropic_cache_guard=True`
  - `anthropic_hide_thinking=True`
  - `anthropic_tool_allowlist=[...]`
  - `anthropic_on_refusal=callable`
  - `anthropic_system_prompt_guard=True`
- **Backward compatibility:** All new options default to `False` or `None` so existing users are unchanged.
- **Docs and positioning:** README and docs should clearly state “Anthropic-exclusive features” and list them; this differentiates the product and supports an acquisition story (“the safety layer for Claude”).

---

## Summary Table

| Feature                     | Anthropic-only | Novel (not elsewhere) | Acquisition value                          |
|----------------------------|----------------|----------------------|--------------------------------------------|
| Cache-aware budget & guard | Yes            | Yes                  | Aligns with Anthropic’s caching product    |
| Extended thinking guard    | Yes            | Yes                  | Safe deployment of extended thinking       |
| Tool-use boundary guard    | Yes            | Yes                  | Agent safety for Claude agents             |
| Refusal analytics          | Yes            | Yes                  | Observability and enterprise feedback      |
| Anthropic audit log        | Yes            | Yes                  | Compliance and enterprise                   |
| System prompt guard        | Yes            | Yes                  | Best-practice enforcement for Claude       |

These features should **not** be implemented for OpenAI or Google; they rely on Claude/Anthropic-specific API shapes and semantics. Keeping them exclusive maximizes differentiation and acquisition appeal.
