# examples/gemini_example.py
# Demonstrates AgentArmor with Google Gemini (google-generativeai SDK).
#
# Install: pip install agentarmor[gemini]
# Set GOOGLE_API_KEY in your environment before running.

import agentarmor
import google.generativeai as genai

def main():
    # Configure the Gemini SDK with your API key
    genai.configure(api_key="your-key")

    # Initialize AgentArmor with budget, shield, and PII filtering
    armor = agentarmor.init(budget=1.00, shield=True, filter=["pii"])

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Hello, how are you?")
        print("Response:", response.text)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("\nSafety Report:")
        print(agentarmor.report())
        agentarmor.teardown()


if __name__ == "__main__":
    main()
