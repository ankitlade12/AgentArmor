import pytest
from unittest.mock import MagicMock
import asyncio

import agentarmor
from agentarmor.hooks import RequestContext, ResponseContext

openai = pytest.importorskip("openai")

def test_sync_patching():
    # Setup mock client
    client = openai.OpenAI(api_key="mock")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "mocked reply"
    mock_response.usage = None
    
    # Mock the inner create method
    original_create = openai.resources.chat.completions.Completions.create
    openai.resources.chat.completions.Completions.create = MagicMock(return_value=mock_response)
    
    try:
        # Initialize AgentArmor (this applies the patch)
        core = agentarmor.init()
        
        # NOTE: Using core.registry.register_after_response instead of agentarmor.after_response
        # because init() was already called and it cloned the global registry.
        hook_ran = False
        @core.registry.register_after_response
        def cb(ctx: ResponseContext):
            nonlocal hook_ran
            hook_ran = True
            assert ctx.text == "mocked reply"
            return ctx
            
        client.chat.completions.create(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "hi"}],
        )
        
        assert hook_ran is True
    finally:
        # Cleanup
        agentarmor.teardown()
        openai.resources.chat.completions.Completions.create = original_create

@pytest.mark.asyncio
async def test_async_patching():
    aclient = openai.AsyncOpenAI(api_key="mock")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "async mocked reply"
    mock_response.usage = None
    
    original_create = openai.resources.chat.completions.AsyncCompletions.create
    async def mock_create(*args, **kwargs):
        return mock_response
    openai.resources.chat.completions.AsyncCompletions.create = MagicMock(side_effect=mock_create)
    
    try:
        core = agentarmor.init()
        
        hook_ran = False
        @core.registry.register_after_response
        def cb(ctx: ResponseContext):
            nonlocal hook_ran
            hook_ran = True
            assert ctx.text == "async mocked reply"
            return ctx
            
        await aclient.chat.completions.create(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "async hi"}],
        )
        
        assert hook_ran is True
    finally:
        agentarmor.teardown()
        openai.resources.chat.completions.AsyncCompletions.create = original_create

def test_stream_sync_patching():
    client = openai.OpenAI(api_key="mock")
    
    # Create chunks
    c1 = MagicMock()
    c1.choices = [MagicMock()]
    c1.choices[0].delta.content = "hello "
    c1.usage = None
    
    c2 = MagicMock()
    c2.choices = [MagicMock()]
    c2.choices[0].delta.content = "stream"
    c2.usage = None
    
    c3 = MagicMock()
    c3.choices = [MagicMock()]
    c3.choices[0].delta.content = ""
    c3.usage = MagicMock()
    c3.usage.prompt_tokens = 10
    c3.usage.completion_tokens = 2
    
    def mock_stream():
        yield c1
        yield c2
        yield c3
    
    original_create = openai.resources.chat.completions.Completions.create
    openai.resources.chat.completions.Completions.create = MagicMock(return_value=mock_stream())
    
    try:
        core = agentarmor.init()
        
        chunks_hook_called = 0
        @core.registry.register_on_stream_chunk
        def s_hook(chunk_text: str):
            nonlocal chunks_hook_called
            chunks_hook_called += 1
            return chunk_text
            
        after_hook_called = False
        final_usage = None
        @core.registry.register_after_response
        def a_hook(ctx: ResponseContext):
            nonlocal after_hook_called, final_usage
            after_hook_called = True
            final_usage = ctx.usage
            assert ctx.text == "hello stream"
            return ctx
            
        res = client.chat.completions.create(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "hi"}],
            stream=True
        )
        
        output = ""
        for chunk in res:
            if chunk.choices and chunk.choices[0].delta.content:
                output += chunk.choices[0].delta.content
                
        assert output == "hello stream"
        assert chunks_hook_called == 2
        assert after_hook_called is True
        assert final_usage["input_tokens"] == 10
        assert final_usage["output_tokens"] == 2
    finally:
        agentarmor.teardown()
        openai.resources.chat.completions.Completions.create = original_create
