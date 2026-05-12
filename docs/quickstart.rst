Quickstart
==========

Installation
------------

.. code-block:: bash

   pip install agentarmor

*Requires Python 3.10+. No external infrastructure dependencies.*

To install with provider-specific support:

.. code-block:: bash

   pip install agentarmor[openai]       # OpenAI support
   pip install agentarmor[anthropic]    # Anthropic support
   pip install agentarmor[gemini]       # Google Gemini support
   pip install agentarmor[drift]        # Semantic drift detection
   pip install agentarmor[all]          # Everything

See ``SUPPORT_MATRIX.md`` in the repo root for tested SDK surfaces and
compatibility notes.

Drop-in Mode (Recommended)
---------------------------

Two lines. Zero code changes to your existing agent.

.. code-block:: python

   import agentarmor
   import openai

   # 1. Initialize your shields
   agentarmor.init(
       budget="$5.00",            # Circuit breaker — kills runaway spend
       shield=True,               # Prompt injection detection
       filter=["pii", "secrets"], # Output firewall — blocks leaks
       record=True,               # Flight recorder — replay any session
   )

   # 2. Your existing code — no changes needed!
   client = openai.OpenAI()
   response = client.chat.completions.create(
       model="gpt-4o",
       messages=[{"role": "user", "content": "Analyze this market..."}],
   )

   # 3. Get your safety and cost report
   print(agentarmor.spent())      # e.g. 0.0035
   print(agentarmor.remaining())  # e.g. 4.9965
   print(agentarmor.report())     # Full cost/security breakdown

   # 4. Tear down the shields
   agentarmor.teardown()

``agentarmor.init()`` seamlessly patches the OpenAI and Anthropic SDKs so
every call is tracked and protected automatically.

Drop-in API
-----------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Function
     - Description
   * - ``agentarmor.init(budget, shield, filter, record)``
     - Start tracking. Patches OpenAI/Anthropic SDKs. Loads chosen shields.
   * - ``agentarmor.spent()``
     - Total dollars spent so far in this session.
   * - ``agentarmor.remaining()``
     - Dollars left in the budget.
   * - ``agentarmor.report()``
     - Full security and cost breakdown as a dictionary.
   * - ``agentarmor.teardown()``
     - Stop tracking, unpatch SDKs, and clean up.
