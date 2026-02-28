from datetime import datetime

import agentarmor
import openai
from agentarmor import RequestContext, ResponseContext

# 1. Define custom hooks BEFORE initialization
# They will be picked up automatically when agentarmor.init() is called.

@agentarmor.before_request
def inject_timestamp(ctx: RequestContext) -> RequestContext:
    """Injects the current date into the system prompt invisibly."""
    print(f"[Hook] Intercepted outbound request to {ctx.model}")
    if ctx.messages and ctx.messages[0].get("role") == "system":
        ctx.messages[0]["content"] += f"\nToday's date is {datetime.now().strftime('%Y-%m-%d')}."
    return ctx

@agentarmor.after_response
def log_analytics(ctx: ResponseContext) -> ResponseContext:
    """Logs the cost and latency to a custom analytics backend."""
    cost_str = f"${ctx.cost:.4f}" if ctx.cost is not None else "Unknown"
    print(f"[Hook] Call to {ctx.model} took {ctx.latency_ms:.1f}ms and cost {cost_str}")
    return ctx

@agentarmor.on_stream_chunk
def censor_profanity(text: str) -> str:
    """A naive profanity filter that applies in real-time during streaming."""
    return text.replace("badword", "*******")

def main():
    # 2. Initialize AgentArmor
    # This automatically patches the SDK and applies our hooks
    agentarmor.init(
        budget="$1.00"
    )
    
    try:
        client = openai.OpenAI()
        
        print("\nSending request...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello! What is today's date?"}
            ]
        )
        print("Response:", response.choices[0].message.content)
        
    except Exception as e:
        print(f"Exception (could be missing API key): {e}")
    finally:
        agentarmor.teardown()

if __name__ == "__main__":
    main()
