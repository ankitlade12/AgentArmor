AgentArmor 🛡️
==============

**The full-stack safety layer for AI agents.**

One install. Four shields. Zero infrastructure to manage.

AgentArmor is an open-source Python SDK that wraps your LLM integrations with
real-time safety controls. It protects your applications from runaway costs,
prompt injection attacks, sensitive data leaks, and provides a complete audit
trail of every interaction.

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

🛡️ **Prompt Shield** — Block jailbreaks and prompt injection attacks before they reach the LLM.

🔒 **Output Firewall** — Automatically redact PII, secrets, and API keys from LLM responses.

📼 **Flight Recorder** — Full audit trail of every API call with inputs, outputs, and latency.

🔌 **Hooks & Middleware** — Inject custom logic before requests and after responses.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   quickstart
   shields
   hooks
   integrations

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
