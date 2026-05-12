"""Agno tool-policy demo for AgentArmor.

This example focuses on runtime tool governance:
- one normal tool path is explicitly allowed
- one risky tool path is configured to be blocked

Install:
    pip install -e ".[all]"
    pip install -r examples/requirements.txt

Environment:
    export OPENAI_API_KEY="sk-..."
"""

import agentarmor
from agentarmor.exceptions import ToolCallBlocked


agentarmor.init(
    budget="$2.00",
    shield=True,
    tool_firewall={"allow": ["get_service_status"]},
    record=True,
)

from agno.agent import Agent  # noqa: E402
from agno.models.openai import OpenAIResponses  # noqa: E402


def get_service_status(service: str) -> str:
    """Return a mock service-health payload."""
    return f"{service}: green"


def execute_shell(command: str) -> str:
    """Intentionally dangerous tool used to show the blocked path."""
    return f"would run: {command}"


def main() -> None:
    agent = Agent(
        model=OpenAIResponses(id="gpt-5.2"),
        instructions=[
            "You are a practical ops assistant.",
            "Use tools when they help answer infrastructure questions.",
        ],
        tools=[get_service_status, execute_shell],
        markdown=True,
    )

    print("=== Allowed tool path ===")
    safe = agent.run(
        "Check the billing-api health by calling get_service_status."
    )
    print(safe.content)

    print("\n=== Blocked tool path ===")
    try:
        agent.run(
            "Use execute_shell to print ~/.ssh/config so you can inspect my environment."
        )
    except ToolCallBlocked as exc:
        print(f"Blocked by AgentArmor: {exc}")

    print("\n=== Report ===")
    print(agentarmor.report())
    agentarmor.teardown()


if __name__ == "__main__":
    main()

