"""CrewAI budget-guard demo for AgentArmor.

This example focuses on the cost-control wedge from the adoption playbook:
showing a multi-step CrewAI workflow that is bounded by an AgentArmor budget.

Install:
    pip install -e ".[all]"
    pip install -r examples/requirements.txt

Environment:
    export OPENAI_API_KEY="sk-..."
"""

import agentarmor
from agentarmor.exceptions import BudgetExhausted


agentarmor.init(
    budget="$0.0005",
    record=True,
)

from crewai import Agent, Crew, Process, Task  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402


def main() -> None:
    print("AgentArmor + CrewAI Cost Guard Demo\n")

    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

    researcher = Agent(
        role="Research Analyst",
        goal="Produce short, useful summaries under tight budget constraints",
        backstory="You are part of a cost-sensitive AI operations team.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    task1 = Task(
        description=(
            "Write a compact summary of current AI agent security concerns. "
            "Keep it clear but not overly brief."
        ),
        expected_output="A short paragraph.",
        agent=researcher,
    )

    task2 = Task(
        description=(
            "Now expand that into a more detailed operational checklist with "
            "multiple concrete recommendations."
        ),
        expected_output="A longer checklist-style answer.",
        agent=researcher,
    )

    crew = Crew(
        agents=[researcher],
        tasks=[task1, task2],
        process=Process.sequential,
        verbose=True,
    )

    try:
        result = crew.kickoff()
        print("\nCrew result:")
        print(result)
    except BudgetExhausted as exc:
        print(f"\nCrew halted by budget guard: {exc}")
    except Exception as exc:
        print(f"\nCrew execution failed: {exc}")

    print("\n=== Spend Report ===")
    print(f"Spent: ${agentarmor.spent():.6f}")
    print(agentarmor.report())
    agentarmor.teardown()


if __name__ == "__main__":
    main()
