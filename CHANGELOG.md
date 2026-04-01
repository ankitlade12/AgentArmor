# Changelog

All notable changes to the AgentArmor project will be documented in this file.

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
