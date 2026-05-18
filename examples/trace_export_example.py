"""Trace export example for AgentArmor Explain Mode.

This example shows how to serialize the last AgentArmor trace as JSON and how
to attach the normalized attributes to an OpenTelemetry span.

Install:
    pip install -e ".[all]"
    pip install -r examples/requirements.txt

Environment:
    export OPENAI_API_KEY="sk-..."
"""

import json

import agentarmor
import openai
from opentelemetry import trace as otel_trace


def main() -> None:
    agentarmor.init(
        budget="$2.00",
        shield=True,
        record=True,
        explain=True,
    )

    client = openai.OpenAI()

    try:
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": "Summarize why local-first runtime safety matters.",
                }
            ],
        )

        trace = agentarmor.last_trace()
        if trace is None:
            print("No trace captured.")
            return

        print("=== JSON export ===")
        print(json.dumps(trace.to_dict(), cls=agentarmor.TraceJSONEncoder, indent=2))

        print("\n=== OpenTelemetry attributes ===")
        tracer = otel_trace.get_tracer("agentarmor.examples")
        with tracer.start_as_current_span("agentarmor_llm_call") as span:
            span.set_attributes(trace.to_otel_attributes())
            print(trace.to_otel_attributes())
    finally:
        agentarmor.teardown()


if __name__ == "__main__":
    main()
