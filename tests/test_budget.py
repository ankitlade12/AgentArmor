import pytest
from agentarmor.modules.budget import BudgetModule
from agentarmor.exceptions import BudgetExhausted

def test_budget_initialization():
    module = BudgetModule(limit="$5.00")
    assert module.limit == 5.0
    assert module.spent == 0.0

def test_budget_estimation():
    module = BudgetModule(limit="$0.01")
    messages = [{"role": "user", "content": "hello world! " * 1000}]  # Lots of text
    
    # Pre check should fail because it requires many tokens and limits is very small
    with pytest.raises(BudgetExhausted):
        module.pre_check("gpt-4o", messages)

def test_budget_recording():
    class MockUsage:
        prompt_tokens = 100
        completion_tokens = 50

    class MockResponse:
        usage = MockUsage()

    module = BudgetModule(limit="$5.00")
    module.post_record("gpt-4o", MockResponse())
    
    assert module.spent > 0.0
    assert len(module.calls) == 1
    
    report = module.report()
    assert report["calls"] == 1
