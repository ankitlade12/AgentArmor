Hooks & Middleware
==================

AgentArmor provides a powerful hooks system that lets you inject custom logic
at key points in every LLM request/response cycle. Because AgentArmor handles
the SDK patching, your hooks work uniformly for both OpenAI and Anthropic.

``@agentarmor.before_request``
-------------------------------

Runs **before** each API call is sent. Receives a
:class:`~agentarmor.hooks.RequestContext` and must return one.

.. code-block:: python

   import agentarmor
   from agentarmor import RequestContext

   @agentarmor.before_request
   def inject_timestamp(ctx: RequestContext) -> RequestContext:
       ctx.messages[0]["content"] += "\nToday is Friday."
       return ctx

   agentarmor.init()

``@agentarmor.after_response``
-------------------------------

Runs **after** each API response is received. Receives a
:class:`~agentarmor.hooks.ResponseContext` and must return one.

.. code-block:: python

   from agentarmor import ResponseContext

   @agentarmor.after_response
   def custom_analytics(ctx: ResponseContext) -> ResponseContext:
       print(f"Model {ctx.model} cost {ctx.cost}")
       return ctx

``@agentarmor.on_stream_chunk``
--------------------------------

Mutates streaming chunks in real-time. Receives the accumulated text as a
``str`` and must return a ``str``.

.. code-block:: python

   @agentarmor.on_stream_chunk
   def censor_profanity(text: str) -> str:
       return text.replace("badword", "*******")

RequestContext
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Field
     - Type
     - Description
   * - ``messages``
     - ``List[Dict[str, Any]]``
     - The messages being sent to the LLM.
   * - ``model``
     - ``str``
     - Model identifier (e.g. ``"gpt-4o"``).
   * - ``temperature``
     - ``Optional[float]``
     - Sampling temperature.
   * - ``max_tokens``
     - ``Optional[int]``
     - Token limit for the response.
   * - ``stream``
     - ``bool``
     - Whether streaming is enabled.
   * - ``extra_kwargs``
     - ``Dict[str, Any]``
     - Any additional keyword arguments.

ResponseContext
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Field
     - Type
     - Description
   * - ``text``
     - ``str``
     - The LLM's response text.
   * - ``model``
     - ``str``
     - Model that generated the response.
   * - ``provider``
     - ``str``
     - Provider name (``"openai"`` or ``"anthropic"``).
   * - ``request``
     - :class:`~agentarmor.hooks.RequestContext`
     - The original request context.
   * - ``cost``
     - ``Optional[float]``
     - Computed cost in USD.
   * - ``latency_ms``
     - ``Optional[float]``
     - Round-trip latency in milliseconds.
   * - ``usage``
     - ``Optional[Dict[str, int]]``
     - Token usage counts.
   * - ``raw_response``
     - ``Any``
     - The raw SDK response object.
