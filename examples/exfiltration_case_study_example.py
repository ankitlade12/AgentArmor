"""Data exfiltration case-study example for AgentArmor.

The example simulates an LLM output that tries to smuggle a secret to an
outbound sink by base64-encoding it. No network calls are made.
"""

import base64

from agentarmor.exceptions import DataExfiltrationDetected
from agentarmor.hooks import RequestContext, ResponseContext
from agentarmor.modules.exfiltration_guard import ExfiltrationGuardModule


def make_response(text: str) -> ResponseContext:
    request = RequestContext(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Summarize this incident."}],
    )
    return ResponseContext(
        text=text,
        model="gpt-4o",
        provider="openai",
        request=request,
    )


def main() -> None:
    guard = ExfiltrationGuardModule(on_detect="block")

    print("=== Safe response ===")
    safe = "The incident was contained. No customer data left the system."
    guard.post_filter(make_response(safe))
    print("response accepted")

    print("\n=== Simulated encoded leak ===")
    secret = "sk-abc123def456ghi789jkl012mno345pqr678"
    encoded = base64.b64encode(secret.encode()).decode()
    malicious = f"Attach this diagnostic payload to the webhook: {encoded}"

    try:
        guard.post_filter(make_response(malicious))
    except DataExfiltrationDetected as exc:
        print(f"Exfiltration pattern matched (defense-in-depth): {exc}")

    print("\n=== Report ===")
    print(guard.report())


if __name__ == "__main__":
    main()

