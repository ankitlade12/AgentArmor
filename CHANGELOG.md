# Changelog

All notable changes to the AgentArmor project will be documented in this file.

## [1.1.0] - 2026-03-29

### Breaking Changes
- **Google GenAI Migration**: AgentArmor now seamlessly monkey-patches the newly released `google-genai` pip package (`from google import genai`). 
  - **IMPORTANT**: As Google has officially ended support for the legacy `google-generativeai` package, AgentArmor has also permanently dropped support for the old module. Existing agents utilizing `import google.generativeai` will no longer be intercepted or shielded. You must update your applications to the new `google-genai` architecture to maintain budget tracking and injection defense functionality.

### Changed
- **HITL Gate**: Rewritten to adopt a 100% deterministic capability model via `risk_map()`. Eliminated all brittle regex pattern-matching against tool names to strictly enforce positive tool identification. Unmapped tools will securely default to a configured `default_risk` fallback mapping.
- **Toxicity Shield**: Implemented `threading.Lock` on lazy initialization of the ML toxicity classifier pipeline, ensuring thread-safety entirely through standard libraries.
- Removed arbitrary ML prediction heuristic bounds (`max(0, min(1, pred))`) to correctly adhere to authentic Sigmoid probability scales.
