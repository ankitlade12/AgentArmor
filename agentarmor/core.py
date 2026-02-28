import time
from typing import Any, Callable, Dict

from .hooks import RequestContext, ResponseContext, global_registry
from .modules.budget import BudgetModule
from .modules.shield import ShieldModule
from .modules.filter import FilterModule
from .modules.recorder import RecorderModule

class ArmorCore:
    def __init__(self, budget=None, shield=False, filter=None, record=False, **kwargs):
        self.modules: Dict[str, Any] = {}
        self.registry = global_registry.clone()
        
        self._originals: Dict[str, Callable] = {}

        if budget:
            self.modules["budget"] = BudgetModule(limit=budget)
            self.registry.register_before_request(self.modules["budget"].pre_check)
            self.registry.register_after_response(self.modules["budget"].post_record)
        if shield:
            self.modules["shield"] = ShieldModule()
            self.registry.register_before_request(self.modules["shield"].pre_check)
        if filter:
            self.modules["filter"] = FilterModule(rules=filter)
            self.registry.register_after_response(self.modules["filter"].post_filter)
            self.registry.register_on_stream_chunk(self.modules["filter"].stream_filter)
        if record:
            self.modules["recorder"] = RecorderModule()
            self.registry.register_after_response(self.modules["recorder"].post_record)

    def patch(self) -> None:
        """Monkey-patches the OpenAI and Anthropic SDKs."""
        try:
            from openai.resources.chat.completions import Completions, AsyncCompletions
            self._originals["openai_sync"] = Completions.create
            Completions.create = self._wrap_sync(self._originals["openai_sync"], provider="openai")
            
            self._originals["openai_async"] = AsyncCompletions.create
            AsyncCompletions.create = self._wrap_async(self._originals["openai_async"], provider="openai")
        except ImportError:
            pass
            
        try:
            from anthropic.resources.messages import Messages, AsyncMessages
            self._originals["anthropic_sync"] = Messages.create
            Messages.create = self._wrap_sync(self._originals["anthropic_sync"], provider="anthropic")
            
            self._originals["anthropic_async"] = AsyncMessages.create
            AsyncMessages.create = self._wrap_async(self._originals["anthropic_async"], provider="anthropic")
        except ImportError:
            pass

    def unpatch(self) -> None:
        """Restores original SDK methods."""
        try:
            from openai.resources.chat.completions import Completions, AsyncCompletions
            if "openai_sync" in self._originals:
                Completions.create = self._originals["openai_sync"]
            if "openai_async" in self._originals:
                AsyncCompletions.create = self._originals["openai_async"]
        except ImportError:
            pass
            
        try:
            from anthropic.resources.messages import Messages, AsyncMessages
            if "anthropic_sync" in self._originals:
                Messages.create = self._originals["anthropic_sync"]
            if "anthropic_async" in self._originals:
                AsyncMessages.create = self._originals["anthropic_async"]
        except ImportError:
            pass

    def _build_request_context(self, provider: str, args: tuple, kwargs: dict) -> RequestContext:
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        stream = kwargs.get("stream", False)
        
        return RequestContext(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            extra_kwargs=kwargs
        )

    def _apply_request_context_to_kwargs(self, ctx: RequestContext, kwargs: dict) -> None:
        kwargs["messages"] = ctx.messages
        kwargs["model"] = ctx.model
        if ctx.temperature is not None:
            kwargs["temperature"] = ctx.temperature
        if ctx.max_tokens is not None:
            kwargs["max_tokens"] = ctx.max_tokens
        kwargs["stream"] = ctx.stream
        kwargs.update(ctx.extra_kwargs)

    def _wrap_sync(self, original_fn: Callable, provider: str):
        def wrapped(*args, **kwargs):
            ctx = self._build_request_context(provider, args, kwargs)
            ctx = self.registry.execute_before_request(ctx)
            self._apply_request_context_to_kwargs(ctx, kwargs)

            t0 = time.perf_counter()
            response = original_fn(*args, **kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000

            if ctx.stream:
                return self._handle_stream_sync(response, provider, ctx, latency_ms)

            return self._handle_non_stream(response, provider, ctx, latency_ms)

        return wrapped

    def _wrap_async(self, original_fn: Callable, provider: str):
        async def wrapped(*args, **kwargs):
            ctx = self._build_request_context(provider, args, kwargs)
            ctx = self.registry.execute_before_request(ctx)
            self._apply_request_context_to_kwargs(ctx, kwargs)

            t0 = time.perf_counter()
            response = await original_fn(*args, **kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000

            if ctx.stream:
                return self._handle_stream_async(response, provider, ctx, latency_ms)

            return self._handle_non_stream(response, provider, ctx, latency_ms)

        return wrapped

    def _handle_non_stream(self, response: Any, provider: str, req_ctx: RequestContext, latency_ms: float):
        output_text = self._extract_output(response, provider)
        usage = self._extract_non_stream_usage(response)

        res_ctx = ResponseContext(
            text=output_text,
            model=req_ctx.model,
            provider=provider,
            request=req_ctx,
            latency_ms=latency_ms,
            usage=usage,
            raw_response=response
        )

        res_ctx = self.registry.execute_after_response(res_ctx)
        self._inject_output(response, provider, res_ctx.text)
        return response

    def _handle_stream_sync(self, stream: Any, provider: str, req_ctx: RequestContext, latency_ms: float):
        accumulated_text = ""
        current_safe_text = ""
        usage = None
        
        def generator():
            nonlocal accumulated_text, current_safe_text, usage
            try:
                for chunk in stream:
                    delta = self._extract_chunk_delta(chunk, provider)
                    if delta:
                        accumulated_text += delta
                        new_safe_text = self.registry.execute_on_stream_chunk(accumulated_text)
                        
                        if len(new_safe_text) > len(current_safe_text):
                            safe_delta = new_safe_text[len(current_safe_text):]
                            self._inject_chunk_delta(chunk, provider, safe_delta)
                            current_safe_text = new_safe_text
                        else:
                            self._inject_chunk_delta(chunk, provider, "")
                            
                    usage = self._extract_stream_usage(chunk, provider, usage)
                    yield chunk
            finally:
                res_ctx = ResponseContext(
                    text=current_safe_text,
                    model=req_ctx.model,
                    provider=provider,
                    request=req_ctx,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                self.registry.execute_after_response(res_ctx)

        return generator()

    def _handle_stream_async(self, stream: Any, provider: str, req_ctx: RequestContext, latency_ms: float):
        accumulated_text = ""
        current_safe_text = ""
        usage = None
        
        async def async_generator():
            nonlocal accumulated_text, current_safe_text, usage
            try:
                async for chunk in stream:
                    delta = self._extract_chunk_delta(chunk, provider)
                    if delta:
                        accumulated_text += delta
                        new_safe_text = self.registry.execute_on_stream_chunk(accumulated_text)
                        
                        if len(new_safe_text) > len(current_safe_text):
                            safe_delta = new_safe_text[len(current_safe_text):]
                            self._inject_chunk_delta(chunk, provider, safe_delta)
                            current_safe_text = new_safe_text
                        else:
                            self._inject_chunk_delta(chunk, provider, "")
                            
                    usage = self._extract_stream_usage(chunk, provider, usage)
                    yield chunk
            finally:
                res_ctx = ResponseContext(
                    text=current_safe_text,
                    model=req_ctx.model,
                    provider=provider,
                    request=req_ctx,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                self.registry.execute_after_response(res_ctx)

        return async_generator()

    def _extract_output(self, response: Any, provider: str) -> str:
        try:
            if provider == "openai":
                return response.choices[0].message.content or ""
            elif provider == "anthropic":
                return response.content[0].text or ""
        except Exception:
            pass
        return ""

    def _inject_output(self, response: Any, provider: str, output_text: str) -> None:
        try:
            if provider == "openai":
                response.choices[0].message.content = output_text
            elif provider == "anthropic":
                response.content[0].text = output_text
        except Exception:
            pass

    def _extract_chunk_delta(self, chunk: Any, provider: str) -> str:
        try:
            if provider == "openai":
                if hasattr(chunk, "choices") and chunk.choices and hasattr(chunk.choices[0], "delta"):
                    return getattr(chunk.choices[0].delta, "content", "") or ""
            elif provider == "anthropic":
                if getattr(chunk, "type", "") == "content_block_delta":
                    delta_obj = getattr(chunk, "delta", None)
                    return getattr(delta_obj, "text", "") or ""
        except Exception:
            pass
        return ""

    def _inject_chunk_delta(self, chunk: Any, provider: str, new_delta: str) -> None:
        try:
            if provider == "openai":
                if hasattr(chunk, "choices") and chunk.choices and hasattr(chunk.choices[0], "delta"):
                    chunk.choices[0].delta.content = new_delta
            elif provider == "anthropic":
                if getattr(chunk, "type", "") == "content_block_delta":
                    delta_obj = getattr(chunk, "delta", None)
                    if delta_obj and hasattr(delta_obj, "text"):
                        delta_obj.text = new_delta
        except Exception:
            pass

    def _extract_non_stream_usage(self, response: Any) -> Dict[str, int]:
        usage = None
        if hasattr(response, "usage") and response.usage:
            input_tokens = getattr(response.usage, "prompt_tokens", getattr(response.usage, "input_tokens", 0))
            output_tokens = getattr(response.usage, "completion_tokens", getattr(response.usage, "output_tokens", 0))
            if input_tokens > 0 or output_tokens > 0:
                usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        return usage

    def _extract_stream_usage(self, chunk: Any, provider: str, current_usage: Dict[str, int]) -> Dict[str, int]:
        usage = current_usage or {"input_tokens": 0, "output_tokens": 0}
        try:
            if provider == "openai":
                if hasattr(chunk, "usage") and chunk.usage:
                    usage["input_tokens"] += getattr(chunk.usage, "prompt_tokens", 0)
                    usage["output_tokens"] += getattr(chunk.usage, "completion_tokens", 0)
            elif provider == "anthropic":
                if getattr(chunk, "type", "") == "message_start":
                    msg = getattr(chunk, "message", None)
                    if msg and hasattr(msg, "usage"):
                        usage["input_tokens"] += getattr(msg.usage, "input_tokens", 0)
                elif getattr(chunk, "type", "") == "message_delta":
                    usg = getattr(chunk, "usage", None)
                    if usg:
                        usage["output_tokens"] += getattr(usg, "output_tokens", 0)
        except Exception:
            pass
        
        if usage["input_tokens"] > 0 or usage["output_tokens"] > 0:
            return usage
        return current_usage

    def report(self) -> Dict[str, Any]:
        """Aggregates reports from all active modules."""
        r = {}
        for name, module in self.modules.items():
            if hasattr(module, "report"):
                r[name] = module.report()
        return r
