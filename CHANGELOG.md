# Changelog

All notable changes to the AgentArmor project will be documented in this file.

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
