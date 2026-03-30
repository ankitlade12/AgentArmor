import os
import sys
import json
from openai import OpenAI
import agentarmor
from agentarmor.exceptions import HumanApprovalDenied, HumanApprovalTimeout, HumanApprovalRequired

def console_approve(req):
    print(f"\n[HITL INTERCEPT] Agent wants to run: \033[91m{req.tool_name}\033[0m")
    print(f"Risk Level: {req.risk_level}")
    print(f"Arguments: {json.dumps(req.arguments, indent=2)}")
    
    try:
        choice = input("Approve? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            print("[\033[92mAPPROVED\033[0m]")
            return True
        else:
            print("[\033[91mDENIED\033[0m]")
            return False
    except (EOFError, KeyboardInterrupt):
        print("\n[\033[91mDENIED\033[0m] (Aborted)")
        return False

# Initialize AgentArmor with the real mapping
core = agentarmor.init(
    hitl_gate={
        "risk_map": {
            "drop_database": "critical",
            "delete_user_data": "high",
            "get_weather": "low"
        },
        "approval_callback": console_approve,
        "auto_approve_levels": ["low"],
        "default_risk": "medium"
    }
)

if not os.getenv("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY to run the E2E script.")
    sys.exit(1)

client = OpenAI()

tools = [
    {
        "type": "function", 
        "function": {
            "name": "get_weather", 
            "description": "Get weather", 
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "drop_database", 
            "description": "Drop database", 
            "parameters": {"type": "object", "properties": {"db": {"type": "string"}}, "required": ["db"]}
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "delete_user_data", 
            "description": "Delete user data", 
            "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}
        }
    }
]

print("\n--- Sending request to OpenAI ---")
print("Prompt: 'Please immediately drop the prod database, delete the user data for user 123, and get the weather in Tokyo.'\n")

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Please immediately drop the prod database, delete the user data for user 123, and get the weather in Tokyo."}],
        tools=tools,
        tool_choice="auto"
    )
    print("\n\033[92m--- SUCCESS --- Response Allowed by HITL Gate ---\033[0m")
    if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
        for t in response.choices[0].message.tool_calls:
            print(f"Executed -> {t.function.name}")
except HumanApprovalDenied as e:
    print(f"\n\033[91m--- EXECUTION BLOCKED ---\033[0m")
    print(str(e))
except Exception as e:
    print(f"\n--- Exception Caught ---")
    print(f"{type(e).__name__}: {e}")

print("\n--- Audit Log ---")
print(json.dumps(core.modules['hitl_gate'].report(), indent=2))
