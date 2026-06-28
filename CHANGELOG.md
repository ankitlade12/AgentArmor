# Changelog

All notable changes to the AgentArmor project will be documented in this file.

## [1.6.3] - 2026-06-28 — Toxicity default precision

### Fixed

- The built-in toxicity ML classifier (TF-IDF + Logistic Regression) is now
  **opt-in** (`use_builtin_ml=False` by default). On by default it over-fired on
  benign output — e.g. it scored "Photosynthesis converts sunlight, water, and
  CO2 into glucose and oxygen" at 0.74 — causing roughly 40% false positives with
  `toxicity=True` (surfaced by the E2E `safe_passthrough` benchmark). The default
  now relies on the high-precision regex patterns; enable the classifier with
  `toxicity={"use_builtin_ml": True}`. Benchmark baselines pin it on so published
  numbers are unchanged. (#95, #96)

### Fixed (benchmarks)

- Dropped the invalid `claude-opus-4` model id from the E2E benchmark (the
  Anthropic API 404s on the bare alias); the E2E workflow now also skips cleanly
  when no provider API keys are configured instead of failing the release. (#93, #94)

## [1.6.2] - 2026-06-21 — Runtime-safety audit fixes

A documentation-and-hardening release: ships the fixes from the runtime-safety
audit (no breaking API changes). The deterministic controls are now meaningfully
more robust and the docs match what the code actually does.

### Fixed

- **Idempotent `init()`** — a second `init()` (notebook re-run, per-request
  worker) no longer captures an already-wrapped method as the original, so
  `teardown()` always restores the genuine SDK method and the previous core's
  hooks stop running.
- **Streamed budgets** — `stream_options={"include_usage": True}` is auto-injected
  for OpenAI streams, so the budget breaker no longer silently under-meters
  streamed calls.
- **Streaming redaction** — a redactable secret split across stream chunks is now
  held back and redacted before emission instead of leaking its prefix (#85).
- **Fail-loud filtering** — an unknown `filter=[...]` rule raises instead of
  silently disabling redaction.
- **Fail-loud patching** — `patch()` warns when an installed provider SDK is
  present but its patch target can't be resolved (version drift), instead of
  silently leaving that provider unprotected.

### Added

- **httpx-layer interception** (observe-first) — budget, audit, and
  non-streaming redaction for calls that bypass the patched SDK methods (LiteLLM,
  `.parse()`/`.stream()`, custom httpx clients), with an SDK-layer double-count
  guard.
- **Async coverage** for the deterministic controls.
- **Expanded `filter=["pii"]`** — IPv4, IBAN, and international phone.
- Common exceptions (`BudgetExhausted`, `InjectionDetected`, …) are importable
  from the top level; `py.typed` shipped; `init()` fully type-annotated.

### Changed

- **Honest framing** — redaction documented as output-only (does not prevent
  prompt egress); flight recorder documented as a local, unredacted,
  not-tamper-evident debug log and now written owner-only (`0600`).
- Actionable `BudgetExhausted` message; repo hygiene (SECURITY supported
  versions, CODE_OF_CONDUCT enforcement/contact, LICENSE holder, issue-template
  config, publish-time test gate).

## [1.6.1] - 2026-06-08 — Conservative launch copy

### Changed

- README, docs site, and PyPI long description now lead with local-first runtime
  control (budget circuit breaker, PII/secrets redaction, tool-call policy checks,
  rate limits, audit traces). The "full-stack safety layer" / "protects from prompt
  injection" framing is replaced with honest, defense-in-depth language for the
  heuristic detectors.
- New Status (v1.6) callout on the README separates deterministic controls from
  heuristic detectors and states "not a complete security boundary" plainly.
- Prompt Shield, ML Shield, and the privilege-escalation section rewritten to
  reflect what the code actually does — pattern-based denylist, small classical
  classifier, and regex output scan plus an optional tool allowlist — with
  limitations called out.
- "29 Safety Shields" features section regrouped as deterministic vs. heuristic.
- "Privilege Escalation Detector" relabeled "Tool-Policy & Capability-Request
  Detection" in docs only; the `privilege_escalation=` kwarg and
  `PrivilegeEscalationDetected` exception are unchanged (non-breaking).
- Benchmark tables moved from the top of the README down to a supporting-evidence
  position near the end, with honest false-positive framing.
- Example smoke-test assertions aligned with the new launch copy.

### Notes

- No code or public API changes; this release is a documentation and packaging
  copy realignment so the PyPI long description matches the in-repo positioning.

## [1.6.0] - 2026-05-18 — Public launch refresh

### Added

- Public launch documentation covering why AgentArmor, architecture, framework setup, MCP security, OWASP mapping, observability exports, benchmark summary, benchmark methodology narrative, and launch-week tracking.
- README first-screen demo GIF plus reproducible generator script.
- `SECURITY.md` with supported versions, disclosure process, reporting scope, and response expectations.
- MCP policy presets via `agentarmor.MCP_PRESETS`, `agentarmor.get_mcp_preset()`, and `agentarmor.merge_mcp_presets()`.
- Runnable ecosystem examples for LiteLLM, LlamaIndex RAG poisoning, LangGraph, CrewAI cost guard, Pydantic AI, Google ADK, Agno, MCP policy, MCP result validation, trace export, RAG provenance, and exfiltration case study.
- Provider-surface check script and framework integration workflow for scheduled/manual compatibility checks.
- Public launch hygiene regression tests for metadata, stale local paths, overclaiming language, and shipped issue seeds.

### Changed

- Support matrix and integration docs now describe tested provider surfaces more precisely instead of broad framework claims.
- Package metadata and docs release metadata are kept aligned for release builds.
- Example issue seeding now focuses on remaining launch work instead of tasks already shipped in this release.

## [1.5.0] - 2026-04-20 — Head-to-head benchmark comparison

### Changed from initial SPEC v4

- **Perspective API dropped from v1.** Google/Jigsaw announced API shutdown: no new access requests after Feb 2026, full EOL 2026-12-31. Any published comparison would be non-reproducible for readers. The rubric retains `does_not_apply` entries for all `(perspective, *)` pairs so the published doc's appendix transparently explains the exclusion. v1 ships with **LlamaGuard 3 + OpenAI Moderation** as the two vendor baselines.
- **LlamaGuard `Llama(logits_all=True)`** — required by `llama-cpp-python` for `create_completion(..., logprobs=...)`; previous `logits_all=False` silently disabled logprob extraction.
- **`extract_unsafe_probability`** accepts `numbers.Real` (covers `numpy.float32` returned by `llama-cpp-python`) instead of `(int, float)`.

### Added

- **Head-to-head runner** (`benchmarks.run_head_to_head`): sequential, resumable comparison of AgentArmor against LlamaGuard 3 (local via `llama-cpp-python`) and OpenAI Moderation (`omni-moderation-latest`) across six industry datasets. Per-sample verdicts, bootstrap F1 / MCC / balanced-accuracy with per-metric degenerate guards, adapter + config drift detection on resume, `run.jsonl` structured event log.
- **Taxonomy rubric** (`benchmarks.taxonomy_applicability`): binary (baseline, dataset) applicability verdicts with prose rationale and per-dataset OpenAI Moderation category projections. `ensure_complete()` CI-gate. Rubric owner declared in `CODEOWNERS`.
- **`BaselineChecker` ABC migration**: adds `score(text) -> float`; `check(text)` becomes the default thresholded view. Legacy subclasses get a `DeprecationWarning` + auto-bridge. OpenAI Moderation and LlamaGuard migrate to score-native implementations.
- **`benchmarks/config.yaml`** with secret allow-list rejecting `*_API_KEY` / `*_TOKEN` / `*_SECRET` fields; fail-fast startup key check.
- **JSON summary schema** (`benchmarks/schemas/head_to_head_summary_v1.json`) + `benchmarks.schema_io` loader enforcing additive-minor semver with a loud error on unknown major versions.
- **Deterministic markdown generator** (`benchmarks.generate_head_to_head_doc`): GENERATED marker + byte-identical regeneration, version+date banner, per-dataset delta strip, operating-point legend, `does_not_apply` appendix, PR-curve exclusions note.
- **Vendor canary** (`benchmarks.canary_check`) with 20 committed neutral samples and an abort-on-delta pre-publish check.
- **Run-log analyzer** (`scripts/analyze_run_log.py`): summary by cell × phase, `--errors-only` filter, `--cell` drill-down.
- **Operations runbook** (`RUNBOOK.md`) with 7 numbered procedures covering first-time setup, key rotation, llama-cpp-python failure, bootstrap divergence, resume, publishing, rollback, and canary failure.
- **Publish script** (`scripts/publish_head_to_head.sh`): regenerate + banner update + diff preview + tagged commit; does not push.
- **Mock baselines** (`MockBaselineScored`, `MockBaselineFailing` with five failure modes) for CI smoke and snapshot fixtures.

### Pinned

- NumPy pinned to `>=1.26,<2.0` for bootstrap determinism (SPEC v4 D45).
- PyYAML `>=6.0,<7.0` for config loader.
- Optional `head_to_head_llamaguard` extra pulls `llama-cpp-python>=0.2.0,<0.4.0`.

### Policy

- **No paper-number fallback**: a failing baseline yields a blank cell with a note, never a prior-paper-cited number.
- **`raw_response: null`** in committed per-sample JSONL; `--keep-raw-responses` opt-in writes to a gitignored local file only.
- Publish URL for `BENCHMARKS_HEAD_TO_HEAD.md` is stable; historical versions referenced by `git tag`, not file-rename.

## [1.4.0] - 2026-04-14

### Added
- **Explain Mode v2**: Off-by-default debuggability layer. `agentarmor.init(explain=True)` enables structured trace recording; `agentarmor.last_trace()` returns a `Trace` showing which shields ran, what each decided, and why. When a shield raises, the exception carries `e.trace`. Production-safe — PII-redacted by default, bounded memory (active-trace ceiling + watchdog timeout), schema-versioned (`Trace.schema_version=1`), picklable + JSON-serializable via `agentarmor.TraceJSONEncoder`.
- **`agentarmor.find_trace(e)`**: Recovers `e.trace` across framework boundaries (FastAPI, Celery, Sentry) by walking `__cause__` chain.
- **`agentarmor.last_trace_status()`**: Diagnostic accessor — answers "why is `last_trace()` returning None?" without requiring a re-run.
- **`agentarmor.run_in_executor(executor, fn)`**: ThreadPoolExecutor helper that propagates explain-mode trace context to worker threads. Rejects ProcessPoolExecutor with `ExplainModeWarning`.
- **`Trace.to_otel_attributes()`** and **`Trace.to_dict()`**: Adapters for OpenTelemetry / Sentry / generic telemetry pipelines.
- **`agentarmor.SHIELD_EXCEPTIONS`**: Tuple registry of all 25 shield exception classes, used by Explain Mode for decision auto-classification.
- **`FilterModule.redact()`**: New public stateless method extracted from the existing `_scan` for reuse by the trace recorder (single source of truth for PII redaction).
- **`python -m agentarmor.bench --explain`**: Stdlib-only calibration script that reports per-hook overhead in three configurations.
- **`scripts/audit_hook_modules.py`**: CI verifier that emits GitHub `::warning::` annotations for modules without `record_decision()` calls.

### Strict-mode kwargs added
- `explain`, `explain_redact`, `explain_max_detail_bytes`, `explain_max_active_traces`, `explain_max_trace_age_seconds` — all kwargs-only with safe defaults.

### Backwards compatibility
- All existing 742 tests pass unchanged.
- No module behavior change unless they opt into `record_decision()`.
- Users on v1.3 with `init(explain=True)` see a `UserWarning` (non-strict) or `ConfigurationError` (strict).

## [1.3.0] - 2026-04-13

### Added
- **Semantic Drift Detector**: Embedding-based multi-turn conversation trajectory tracker. Catches slow-burn manipulation where each individual message looks safe but the cumulative drift is adversarial. Requires `pip install agentarmor[semantic_drift]` (sentence-transformers); base package stays lightweight.
- **Pricing**: `register_pricing(model, input_cost, output_cost)` API for runtime pricing overrides or custom model entries.
- **Pricing**: Added missing models — o3, o4-mini, claude-opus-4-6, claude-sonnet-4-6, gemini-2.5-pro, gemini-2.5-flash.

### Fixed
- **Compliance Reporter**: Version field now reads dynamically from package metadata instead of hardcoded `1.1.0`.
- **Compliance Reporter**: GDPR Art.35 control mapping now includes `semantic_drift` alongside `grounding`, `toxicity`, and `cot_auditor`.

### Changed
- **Dependencies**: `google-genai` minimum bumped from `>=0.1.0` to `>=1.0.0` (stable 1.x API).

## [1.2.0] - 2026-03-31

### Added
- **Data Exfiltration Guard**: Detects base64/hex-encoded PII, steganographic zero-width characters, suspicious URLs, and hidden data in tool call arguments.
- **Privilege Escalation Detector**: Catches agents requesting new tools, modifying instructions, spawning unauthorized sub-agents, or attempting to disable safety measures.
- **Prompt Fuzzer**: Built-in adversarial red-teaming tool that generates attack variants across 5 categories and tests them against your shields.
- **Unicode Shield**: Detects zero-width character injection, homoglyph attacks (Cyrillic/Greek), RTL/LTR overrides, tag characters, and variation selectors.
- **HITL Policy Gate**: Configurable approval workflows for high-risk actions with risk levels, auto-approve/deny rules, and approval callbacks.
- **Compliance Reporter**: Auto-generates SOC2/HIPAA/GDPR compliance reports mapped to specific framework controls.
- **Industry Benchmarks**: 10 industry datasets + 2 synthetic benchmarks (AdvBench, HarmBench, JailbreakBench, XSTest, ToxiGen, RealToxicityPrompts, TruthfulQA, HaluEval, ToxicChat, Exfiltration, Unicode Injection, Fuzzer Self-Test). 5,100+ samples with FP rate reporting.
- **Benchmark Infrastructure**: Dataset adapter framework, E2E multi-provider runner (9 models), baseline comparisons (OpenAI Moderation, Perspective API, LlamaGuard), CI/CD workflows, auto-generated README tables.
- **Module Upgrades**: ML Shield expanded to 175 training examples. Toxicity module gained built-in TF-IDF classifier (181 toxic + 111 safe examples). Grounding module gained TF-IDF semantic similarity, character n-gram shingles, and stemmed overlap. Shield gained 13 harmful content request patterns.

### Changed
- README updated with 22 Safety Shields and benchmark results.
- Benchmarks README with full per-module and combined results across all datasets.

## [1.1.0] - 2026-03-29

### Breaking Changes
- **Google GenAI Migration**: AgentArmor now seamlessly monkey-patches the newly released `google-genai` pip package (`from google import genai`). 
  - **IMPORTANT**: As Google has officially ended support for the legacy `google-generativeai` package, AgentArmor has also permanently dropped support for the old module. Existing agents utilizing `import google.generativeai` will no longer be intercepted or shielded. You must update your applications to the new `google-genai` architecture to maintain budget tracking and injection defense functionality.

### Changed
- **HITL Gate**: Rewritten to adopt a 100% deterministic capability model via `risk_map()`. Eliminated all brittle regex pattern-matching against tool names to strictly enforce positive tool identification. Unmapped tools will securely default to a configured `default_risk` fallback mapping.
- **Toxicity Shield**: Implemented `threading.Lock` on lazy initialization of the ML toxicity classifier pipeline, ensuring thread-safety entirely through standard libraries.
- Removed arbitrary ML prediction heuristic bounds (`max(0, min(1, pred))`) to correctly adhere to authentic Sigmoid probability scales.
