"""Google ADK integration example for AgentArmor.

This file is meant to be used as a minimal ADK `agent.py` style module.
AgentArmor is initialized first so the underlying Gemini traffic is protected
once ADK executes the agent.

Install:
    pip install -e ".[all]"
    pip install -r examples/requirements.txt

Environment:
    export GOOGLE_API_KEY="..."

Run:
    Copy this file into an ADK project as `agent.py`, then run:
    adk web
"""

import agentarmor


agentarmor.init(
    budget="$2.00",
    shield=True,
    record=True,
)

from google.adk.agents.llm_agent import Agent  # noqa: E402


def get_current_status(service: str) -> dict:
    """Return a mock service-health payload for the ADK demo."""
    return {"service": service, "status": "green"}


root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="Answers service-health questions with a tiny toolset.",
    instruction=(
        "You are a helpful ops assistant. Use the get_current_status tool "
        "when the user asks about service health."
    ),
    tools=[get_current_status],
)


def main() -> None:
    print("Google ADK example scaffold created.")
    print("Use this file as `agent.py` inside an ADK project, then run `adk web`.")
    print("AgentArmor will protect the underlying model calls once the agent runs.")


if __name__ == "__main__":
    main()
