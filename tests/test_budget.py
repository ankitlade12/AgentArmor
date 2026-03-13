import pytest
from agentarmor.modules.budget import BudgetModule
from agentarmor.exceptions import BudgetExhausted
from agentarmor.hooks import RequestContext, ResponseContext

def test_budget_initialization():
    module = BudgetModule(limit="$5.00")
    assert module.limit == 5.0
    assert module.spent == 0.0

def test_budget_estimation():
    module = BudgetModule(limit="$0.01")
    messages = [{"role": "user", "content": "hello world! " * 1000}]  # Lots of text
    
    ctx = RequestContext(messages=messages, model="gpt-4o")
    with pytest.raises(BudgetExhausted):
        module.pre_check(ctx)

def test_budget_recording():
    class MockUsage:
        prompt_tokens = 100
        completion_tokens = 50

    class MockResponse:
        usage = MockUsage()

    module = BudgetModule(limit="$5.00")

    req = RequestContext(messages=[], model="gpt-4o")
    res = ResponseContext(
        text="test",
        model="gpt-4o",
        provider="openai",
        request=req,
        raw_response=MockResponse(),
    )
    module.post_record(res)
    
    assert module.spent > 0.0
    assert len(module.calls) == 1
    
    report = module.report()
    assert report["calls"] == 1
