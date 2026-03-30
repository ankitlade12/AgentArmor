import json

import agentarmor
import openai
from agentarmor.exceptions import FilterViolation


def main():
    core = agentarmor.init(
        record=True,
        filter=["pii", "secrets"],
        compliance={
            "organization": "Acme AI",
            "frameworks": ["soc2", "gdpr"],
        },
    )

    try:
        client = openai.OpenAI()

        print("Sending request that may contain sensitive content...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": "Draft a support reply that includes jane@example.com for follow-up.",
                }
            ],
        )
        response_text = response.choices[0].message.content
        if "[REDACTED:" in response_text:
            core.modules["compliance"].record_data_event(
                "pii_redacted",
                "Sensitive content was redacted from the model response.",
                module="filter",
                severity="warning",
            )
        print("Response:", response_text)
    except FilterViolation as exc:
        core.modules["compliance"].record_data_event(
            "pii_redacted",
            str(exc),
            module="filter",
            severity="warning",
        )
        print(f"Compliance-relevant event recorded: {exc}")
    except Exception as exc:
        print(f"Exception (could be missing API key): {exc}")
    finally:
        report = agentarmor.compliance_report()
        print("\nCompliance Report:")
        print(json.dumps(report, indent=2))
        agentarmor.teardown()


if __name__ == "__main__":
    main()
