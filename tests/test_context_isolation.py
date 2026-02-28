import pytest
import asyncio
import agentarmor

@pytest.mark.asyncio
async def test_context_isolation():
    # Helper async function to simulate concurrent requests
    async def simulate_request(budget_limit, cost_to_spend):
        # 1. Init AgentArmor for this current thread/task context
        core = agentarmor.init(budget=budget_limit)
        
        # 2. Simulate spending
        # We manually modify the spent to simulate an LLM call accumulating costs
        core.modules["budget"].spent += cost_to_spend
        
        # 3. Simulate an async network delay
        await asyncio.sleep(0.1)
        
        # 4. Check that the isolated context preserved its own spent amount
        spent = agentarmor.spent()
        remaining = agentarmor.remaining()
        
        # Clean up
        agentarmor.teardown()
        
        return spent, remaining

    # Run two parallel requests that each initialize their own Core in their own Context
    # Since asyncio.gather runs them as separate tasks, contextvars handle isolation automatically
    results = await asyncio.gather(
        simulate_request("$10.00", 2.0),
        simulate_request("$5.00", 4.0)
    )
    
    # Request 1
    assert results[0][0] == 2.0  # spent
    assert results[0][1] == 8.0  # remaining (10 - 2)
    
    # Request 2
    assert results[1][0] == 4.0  # spent
    assert results[1][1] == 1.0  # remaining (5 - 4)

def test_get_core_without_init():
    assert agentarmor.get_core() is None
    assert agentarmor.spent() == 0.0
    assert agentarmor.remaining() is None
    assert agentarmor.report() is None
