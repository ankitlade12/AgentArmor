import pytest
from agentarmor.hooks import HookRegistry, RequestContext, ResponseContext

def test_hook_registry_before_request():
    registry = HookRegistry()
    
    @registry.register_before_request
    def mutate_request(ctx: RequestContext) -> RequestContext:
        ctx.messages.append({"role": "system", "content": "injected"})
        ctx.model = "gpt-4"
        return ctx

    req = RequestContext(messages=[], model="gpt-3.5")
    res_req = registry.execute_before_request(req)
    
    assert res_req.model == "gpt-4"
    assert len(res_req.messages) == 1
    assert res_req.messages[0]["content"] == "injected"

def test_hook_registry_after_response():
    registry = HookRegistry()
    
    @registry.register_after_response
    def mutate_response(ctx: ResponseContext) -> ResponseContext:
        ctx.text += " (modified)"
        ctx.cost = 0.5
        return ctx

    req = RequestContext(messages=[], model="gpt-4o")
    res = ResponseContext(text="Hello", model="gpt-4o", provider="openai", request=req)
    
    res_out = registry.execute_after_response(res)
    assert res_out.text == "Hello (modified)"
    assert res_out.cost == 0.5

def test_hook_registry_stream_chunk():
    registry = HookRegistry()
    
    @registry.register_on_stream_chunk
    def filter_chunk(text: str) -> str:
        return text.replace("bad", "***")

    assert registry.execute_on_stream_chunk("this is a bad word") == "this is a *** word"

def test_hook_returns_wrong_type():
    registry = HookRegistry()
    
    @registry.register_before_request
    def bad_hook(ctx: RequestContext):
        return None  # forgot to return RequestContext
        
    req = RequestContext(messages=[], model="gpt-3.5")
    
    with pytest.raises(TypeError):
        registry.execute_before_request(req)

def test_hook_raises_exception():
    registry = HookRegistry()
    
    class CustomError(Exception):
        pass
    
    @registry.register_after_response
    def crash_hook(ctx: ResponseContext):
        raise CustomError("Hook crashed")
        
    req = RequestContext(messages=[], model="gpt-4o")
    res = ResponseContext(text="Hello", model="gpt-4o", provider="openai", request=req)
    
    with pytest.raises(CustomError):
        registry.execute_after_response(res)
