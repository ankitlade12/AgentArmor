Observability & Trace Export
============================

AgentArmor's Explain Mode is designed to complement observability systems,
not replace them. The runtime layer makes decisions in-process; your tracing
or analytics stack remains the place to aggregate, search, and alert on those
decisions across services.

Core Export Shapes
------------------

AgentArmor exposes two practical formats out of the box:

- ``trace.to_dict()`` for structured JSON export
- ``trace.to_otel_attributes()`` for span attributes in OpenTelemetry flows

Minimal JSON export
-------------------

.. code-block:: python

   import json
   import agentarmor

   trace = agentarmor.last_trace()
   if trace:
       payload = json.dumps(
           trace.to_dict(),
           cls=agentarmor.TraceJSONEncoder,
           indent=2,
       )
       print(payload)

OpenTelemetry pattern
---------------------

.. code-block:: python

   import agentarmor
   from opentelemetry import trace as otel_trace

   tracer = otel_trace.get_tracer("agentarmor")
   trace = agentarmor.last_trace()

   with tracer.start_as_current_span("llm_call") as span:
       if trace:
           span.set_attributes(trace.to_otel_attributes())

Langfuse / Helicone / Phoenix Notes
-----------------------------------

These platforms can work well with AgentArmor, but they solve a different
problem:

- AgentArmor decides whether a request or tool path is safe to execute
- observability tools store the resulting metadata, traces, and dashboards

Practical integration shapes:

- **Langfuse**: attach ``trace.to_dict()`` as metadata on the observation or
  generation record
- **Helicone**: forward selected values such as ``blocked_by``,
  ``closed_reason``, or cost metadata as request properties or headers in your
  surrounding app instrumentation
- **Phoenix**: log the serialized trace as span metadata or attach the key
  decision fields to evaluation rows for later analysis

Redaction Guidance
------------------

Explain Mode redacts trace detail by default when ``explain_redact=True``.
That default is the safer starting point for shipping trace data into any
external system.

Only disable redaction for local debugging sessions where the trace payload
will not leave a trusted environment.

Companion Example
-----------------

See ``examples/trace_export_example.py`` for a small end-to-end script.
