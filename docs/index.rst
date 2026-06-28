AgentArmor 🛡️
==============

**Local-first runtime controls for Python LLM apps and agents.**

Budget circuit breakers, PII/secrets redaction, tool-call policy checks, rate
limits, and audit traces — wrapped around your existing OpenAI / Anthropic /
Gemini calls in two lines, with no hosted proxy.

AgentArmor is an open-source Python SDK that adds runtime controls around your
LLM calls: a hard budget circuit breaker, PII/secrets redaction, tool-call
policy checks, rate limiting, and a local debug/replay log. Optional
defense-in-depth detectors (prompt injection, toxicity, and more) are
documented per-feature, with their limits stated honestly — they reduce risk
but are not a complete security boundary.

.. code-block:: python

   import agentarmor
   import openai

   agentarmor.init(
       budget="$5.00",
       shield=True,
       filter=["pii", "secrets"],
       record=True,
   )

   # Your existing code — no changes needed!
   client = openai.OpenAI()
   response = client.chat.completions.create(
       model="gpt-4o",
       messages=[{"role": "user", "content": "Analyze this market..."}],
   )

Key Features
------------

💰 **Budget Circuit Breaker** — Stop unexpected massive bills with real-time dollar-denominated tracking.

🛡️ **Prompt Shield** — Pattern-based filter for common jailbreak phrasings; defense-in-depth, not a complete defense.

🔒 **Output Firewall** — Automatically redact PII, secrets, and API keys from LLM responses.

📼 **Flight Recorder** — Local debug/replay log of every API call with inputs, outputs, and latency.

🔌 **Hooks & Middleware** — Inject custom logic before requests and after responses.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   why_agentarmor
   quickstart
   shields
   hooks
   integrations
   framework_setup_matrix
   architecture_overview
   complementary_tooling
   benchmark_summary
   benchmark_methodology_narrative
   observability_exports
   mcp_security_checklist
   mcp_policy_presets
   launch_week_tracker
   owasp_mapping

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
