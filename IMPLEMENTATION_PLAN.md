# AgentArmor V1.0 — Full Rebuild to Publishable Grade

## Goal
Rebuild `agentarmor` from its current prototype state into a production-ready, PyPI-publishable package. This involves fixing all critical architectural flaws in the existing 4 shields **and** adding the new universal middleware/hooks system.

---

## Current State Assessment

### What Works (Module Logic)
The 4 individual module files are solid in isolation:
- [budget.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/budget.py) — Dollar-based cost tracking with pre-check estimation and post-call recording. ✅
- [shield.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/shield.py) — Regex-based prompt injection detection with block/warn modes. ✅
- [filter.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/filter.py) — PII/secrets redaction via compiled regex patterns. ✅
- [recorder.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/recorder.py) — JSONL session logging. ✅

### What's Broken (The Engine)

> [!CAUTION]
> The core engine ([core.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/core.py)) has **4 critical flaws** that make the package non-functional in real-world usage.

| # | Flaw | Impact | Severity |
|---|---|---|---|
| 1 | **No Async Support** — Only patches sync `openai.chat.completions.create`. Does not patch `AsyncOpenAI` or `AsyncAnthropic`. | AgentArmor silently does nothing for FastAPI apps, async agents, and most modern codebases. | 🔴 Critical |
| 2 | **No Streaming Support** — `_extract_output()` expects `response.choices[0].message.content`. When `stream=True`, response is a generator, causing a crash. | AgentArmor crashes the user's app if they use streaming. | 🔴 Critical |
| 3 | **Global State** — Budget tracking (`self.spent`) lives on the singleton `ArmorCore` instance via `__init__.py`'s `_instance` global. | In a multi-user web server (FastAPI/Django), all users share one budget counter. User A's spend drains User B's limit. | 🟡 High |
| 4 | **Hard `anthropic` Dependency** — `pyproject.toml` lists `anthropic>=0.25.0` as a required dependency even though it should be optional. | Forces users who only use OpenAI to install the Anthropic SDK unnecessarily. Adds bloat. | 🟡 Medium |
| 5 | **Fragile Patching** — `openai.chat.completions.create` is patched at the module level. OpenAI SDK creates instances (`OpenAI()`) whose methods are bound differently. The current patch may silently fail on newer SDK versions. | Potentially no protection at all, with no error message. | 🟡 High |

---

## Proposed Changes

### Component 1: Core Engine Rebuild

#### [MODIFY] [core.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/core.py)
Complete rewrite. The new engine must:

1. **Patch instance methods, not module-level attributes.** Intercept `OpenAI.chat.completions.create` and `Anthropic.messages.create` at the *class prototype* level, so every instance created by the user (or by LangChain/CrewAI internally) is automatically wrapped.
2. **Support async.** Provide separate async wrappers for `AsyncOpenAI` and `AsyncAnthropic` using `async def wrapped(...)`.
3. **Support streaming.** Detect `stream=True` in kwargs. When streaming:
   - Yield chunks through to the user normally (don't block the stream).
   - Accumulate the full output text in a background buffer.
   - Run the Filter (PII redaction) on accumulated chunks at yield-time (per-chunk redaction for real-time filtering).
   - Run Budget post-recording after the stream is fully consumed.
   - Record the full concatenated output in the Recorder after stream ends.
4. **Expose hooks/middleware API.** Maintain ordered lists of `before_request` and `after_response` callables. Execute them in registration order. The built-in shields are registered as default hooks internally.

---

### Component 2: Hooks / Middleware System (NEW)

#### [NEW] [hooks.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/hooks.py)
New module containing:
- `HookRegistry` class that stores ordered lists of `before_request` and `after_response` hooks.
- `RequestContext` dataclass — passed to `@before_request` hooks containing: `messages`, `model`, `temperature`, `max_tokens`, `stream`, `extra_kwargs`.
- `ResponseContext` dataclass — passed to `@after_response` hooks containing: `text`, `model`, `cost`, `latency_ms`, `usage`, `raw_response`.
- Hooks can **modify and return** the context (mutate the request/response).
- Hooks can **raise exceptions** to block the call (this is how Shield and Budget work internally).
- Hooks must **not** make additional LLM calls (documented constraint, not enforced at runtime).

**Developer-facing API:**
```python
@agentarmor.before_request
def my_hook(ctx: RequestContext) -> RequestContext:
    ctx.messages[0]["content"] += f"\nToday: {date.today()}"
    return ctx

@agentarmor.after_response
def my_hook(ctx: ResponseContext) -> ResponseContext:
    analytics.track(model=ctx.model, cost=ctx.cost)
    return ctx
```

---

### Component 3: Context Isolation

#### [MODIFY] [__init__.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/__init__.py)
- Replace the global `_instance` singleton with `contextvars.ContextVar` storage.
- Each call to `agentarmor.init()` binds the `ArmorCore` instance to the current execution context.
- This makes AgentArmor thread-safe and async-safe for multi-user web servers (FastAPI).
- Provide a `agentarmor.before_request` and `agentarmor.after_response` as module-level decorator exports.

---

### Component 4: Dependency Cleanup

#### [MODIFY] [pyproject.toml](file:///home/saikrishnaj/projects/AgentArmor/pyproject.toml)
- Move `anthropic` from `dependencies` to `[project.optional-dependencies]`: `anthropic = ["anthropic>=0.25.0"]`.
- Remove `openai` as a hard dependency too. Make both optional: `openai = ["openai>=1.0.0"]`.
- Add `all = ["openai>=1.0.0", "anthropic>=0.25.0"]` for convenience.
- The core package itself should be zero-dependency.
- Update version to `0.2.0`.
- Update `description` to mention the hooks system.
- Bump `requires-python` to `>=3.9` (for `contextvars` improvements and modern typing).

---

### Component 5: Module Hardening

#### [MODIFY] [budget.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/budget.py)
- Add support for extracting exact token counts from streaming responses:
  - For OpenAI: Extract from the final chunk's `.usage` attribute (requires users to pass `stream_options={"include_usage": True}`).
  - For Anthropic: Extract from `message_start` and `message_delta` events (`message.usage.input_tokens`, `delta.usage.output_tokens`).
  - Fallback to the `4 chars ≈ 1 token` heuristic only if exact usage metrics are unavailable.

#### [MODIFY] [shield.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/shield.py)
- Expand the injection pattern list with more recent patterns (indirect injection, multi-language).
- Add a `custom_patterns` parameter so developers can add their own regex patterns.
- Scan **all** messages in the array, not just the last one (to catch injections embedded in tool results or prior context).

#### [MODIFY] [filter.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/filter.py)
- Add more secret patterns: AWS keys (`AKIA...`), GitHub tokens (`ghp_...`, `gho_...`), JWT tokens, generic base64-encoded secrets.
- Support a `custom_patterns` dict so developers can add their own regex redaction rules.

#### [MODIFY] [recorder.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/modules/recorder.py)
- Add `cost` field to each logged event (pull from Budget module if active).
- Add configurable max file size / rotation to prevent disk bloat.
- Use `logging` module integration as an alternative output target.

#### [MODIFY] [pricing.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/pricing.py)
- Update model pricing to latest (Feb 2026) values.
- Add newer models: `gpt-4.5`, `o3-mini`, `claude-4-*`, `gemini-2.0-*`, etc.

#### [MODIFY] [exceptions.py](file:///home/saikrishnaj/projects/AgentArmor/agentarmor/exceptions.py)
- Add `HookError` exception for when a user-defined hook raises an unhandled exception.
- Add `PatchError` exception for when SDK patching fails (e.g., incompatible SDK version).

---

### Component 6: Tests

#### [MODIFY] Existing tests
The 4 existing test files ([test_budget.py](file:///home/saikrishnaj/projects/AgentArmor/tests/test_budget.py), [test_filter.py](file:///home/saikrishnaj/projects/AgentArmor/tests/test_filter.py), [test_shield.py](file:///home/saikrishnaj/projects/AgentArmor/tests/test_shield.py), [test_recorder.py](file:///home/saikrishnaj/projects/AgentArmor/tests/test_recorder.py)) test modules in isolation and should continue to pass. They will be updated to reflect any API changes.

#### [NEW] tests/test_hooks.py
- Test hook registration, ordering, and execution.
- Test that `before_request` hooks can modify the request context.
- Test that `after_response` hooks can modify the response context.
- Test that a hook raising an exception blocks the call.
- Test that hooks + built-in shields compose correctly.

#### [NEW] tests/test_core_patching.py
- Test that sync `OpenAI().chat.completions.create()` is intercepted.
- Test that async `AsyncOpenAI().chat.completions.create()` is intercepted.
- Test that `stream=True` calls are handled without crashing.
- Test that `teardown()` correctly restores original methods.
- Tests will use mocked SDK clients (no real API keys needed).

#### [NEW] tests/test_context_isolation.py
- Test that two concurrent contexts (simulated via `contextvars.copy_context()`) maintain separate budget counters.

---

### Component 7: Documentation & Examples

#### [MODIFY] [README.md](file:///home/saikrishnaj/projects/AgentArmor/README.md)
- Add a "Hooks & Middleware" section with examples.
- Update the "Supported Models" table with latest models.
- Add badges for test status, code coverage.
- Clean up any outdated claims.

#### [MODIFY] [examples/basic.py](file:///home/saikrishnaj/projects/AgentArmor/examples/basic.py)
- Update to showcase the hooks API alongside the 4 shields.

#### [NEW] examples/hooks_example.py
- Standalone example demonstrating 2-3 custom hooks (timestamp injection, analytics logging, custom content policy).

---

## Verification Plan

### Automated Tests
All tests use `pytest` and mock the OpenAI/Anthropic SDKs (no real API keys required).

```bash
# Run the full test suite
cd /home/saikrishnaj/projects/AgentArmor
pip install -e ".[all]"
pip install pytest pytest-asyncio
pytest tests/ -v
```

**Expected:** All existing tests pass + all new tests pass.

### Build Verification
```bash
# Verify the package builds cleanly
cd /home/saikrishnaj/projects/AgentArmor
pip install build
python -m build
```
**Expected:** Both `.whl` and `.tar.gz` artifacts are created in `dist/` without errors.

### Manual Verification
After all automated tests pass, the user should:
1. Run `examples/basic.py` with a real OpenAI API key to confirm end-to-end functionality.
2. Run `examples/hooks_example.py` to confirm custom hooks fire correctly.
3. Review the updated `README.md` for accuracy and clarity.
