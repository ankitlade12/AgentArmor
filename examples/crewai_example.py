

import agentarmor

# 1. Initialize AgentArmor BEFORE importing CrewAI
agentarmor.init(
    budget="$2.00",
    record=True              
)

from crewai import Agent, Task, Crew, Process  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

def main():
    print("AgentArmor + CrewAI Integration Example\n")
    
    # CrewAI agents often use LangChain LLMs or direct LLMs.
    # Since we patched the global OpenAI SDK, any wrapper will be protected.
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    researcher = Agent(
        role='Senior Research Analyst',
        goal='Uncover cutting-edge developments in AI',
        backstory="""You work at a leading tech think tank.""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    task1 = Task(
        description="Write a 1 paragraph summary of the state of AI safety.",
        expected_output="A brief summary paragraph.",
        agent=researcher
    )

    crew = Crew(
        agents=[researcher],
        tasks=[task1],
        verbose=True,
        process=Process.sequential
    )

    print("--- Starting Crew Execution ---")
    try:
        result = crew.kickoff()
        print("\n--- Execution Complete ---")
        print(f"Final Result: {result}")
    except Exception as e:
        print(f"\nExecution interupted (likely missing API key if not configured): {e}")

    print("\n--- AgentArmor Spending Report ---")
    print(f"Total Spent across all Crew Agents: ${agentarmor.spent():.4f}")
    print(agentarmor.report())
    
    agentarmor.teardown()

if __name__ == "__main__":
    main()
