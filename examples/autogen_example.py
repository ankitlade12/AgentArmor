import os


import agentarmor

# 1. Initialize AgentArmor BEFORE importing AutoGen
agentarmor.init(
    budget="$1.50",
    shield=True,             
    filter=["secrets"], 
    record=True              
)

import autogen  # noqa: E402
from agentarmor.exceptions import InjectionDetected, BudgetExhausted  # noqa: E402

def main():
    print("AgentArmor + AutoGen Integration Example\n")
    
    # Configure AutoGen. Note: It still calls the underlying openai SDK inside.
    llm_config = {
        "config_list": [{"model": "gpt-4o-mini", "api_key": os.environ.get("OPENAI_API_KEY", "mock")}]
    }

    assistant = autogen.AssistantAgent(
        name="assistant",
        llm_config=llm_config,
    )

    user_proxy = autogen.UserProxyAgent(
        name="user_proxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=1,
        is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
        code_execution_config=False,
    )

    print("--- Starting AutoGen Conversation ---")
    try:
        # Note: If no real API key is set, this will fail with an Auth error, 
        # but the request WILL have passed through the AgentArmor shields first!
        user_proxy.initiate_chat(
            assistant,
            message="Write a python function to print hello world, then say TERMINATE."
        )
    except InjectionDetected as e:
        print(f"🛡️ Blocked by AgentArmor: {e}")
    except BudgetExhausted as e:
        print(f"💰 Agent loop terminated due to budget limits: {e}")
    except Exception as e:
        print(f"\nCaught standard Exception (likely mock API key): {e}")

    print("\n--- Session Report ---")
    print(agentarmor.report())
    
    agentarmor.teardown()

if __name__ == "__main__":
    main()
