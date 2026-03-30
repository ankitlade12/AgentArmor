# examples/gemini_example.py
# Demonstrates AgentArmor with Google Gemini (google-genai SDK).
#
# Install: pip install agentarmor[gemini]
# Set GEMINI_API_KEY in your environment before running.

import os
import agentarmor
from google import genai

def main():
    # Require API key
    if not os.getenv("GEMINI_API_KEY"):
        print("Please set GEMINI_API_KEY")
        return

    # Initialize the modern Gemini Client
    client = genai.Client()

    # Initialize AgentArmor with budget, shield, and PII filtering
    agentarmor.init(budget=1.00, shield=True, filter=["pii"])

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents="Hello, how are you?"
        )
        print("Response:", response.text)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("\nSafety Report:")
        print(agentarmor.report())
        agentarmor.teardown()


if __name__ == "__main__":
    main()
