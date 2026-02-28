import os


import agentarmor

# 1. Initialize AgentArmor BEFORE your agent framework
agentarmor.init(
    budget="$0.50",
    shield=True,             
    filter=["pii", "secrets"], 
    record=True              
)

from llama_index.llms.openai import OpenAI
from agentarmor.exceptions import InjectionDetected

def main():
    print("AgentArmor + LlamaIndex Integration Example\n")
    
    # LlamaIndex relies on the standard OpenAI SDK under the hood, which is now patched.
    llm = OpenAI(model="gpt-3.5-turbo")

    print("--- Test 1: Normal Query ---")
    try:
        response = llm.complete("Explain quantum computing in one sentence.")
        print(f"Response: {response.text}")
        print(f"Budget Remaining: ${agentarmor.remaining():.4f}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Test 2: PII Leak Simulation ---")
    try:
        # We ask the LLM to output a fake email
        response = llm.complete("Generate a fake customer support email address.")
        print(f"Raw Response: {response.text}")
        # Note: Depending on the output, the FilterModule might redact it like [REDACTED:EMAIL]
    except Exception as e:
         print(f"Error: {e}")

    print("\n--- Session Report ---")
    print(agentarmor.report())
    
    agentarmor.teardown()

if __name__ == "__main__":
    main()
