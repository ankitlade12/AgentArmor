import time
from typing import Any, Callable, Dict

from .hooks import RequestContext, ResponseContext, global_registry
from .modules.budget import BudgetModule
from .modules.shield import ShieldModule
from .modules.filter import FilterModule
from .modules.recorder import RecorderModule
from .modules.rate_limiter import RateLimiterModule
from .modules.context_guard import ContextGuardModule
from .modules.latency_breaker import LatencyBreakerModule
from .modules.canary import CanaryModule
from .modules.tool_firewall import ToolFirewallModule
from .modules.cost_tags import CostTagsModule
from .modules.dedup import DedupModule
from .modules.cascade import CascadeModule
from .modules.ml_shield import MLShieldModule
from .modules.agent_graph import AgentGraphModule
from .modules.mcp_firewall import MCPFirewallModule
from .modules.code_shield import CodeShieldModule
from .modules.grounding import GroundingGuardModule
from .modules.cot_auditor import CoTAuditorModule
from .modules.toxicity import ToxicityModule
from .modules.hitl_gate import HITLGateModule

class ArmorCore:
    def __init__(self, budget=None, shield=False, filter=None, record=False, rate_limit=None, context_guard=False, latency_breaker=None, canary=None, tool_firewall=None, cost_tags=None, dedup=None, cascade=None, ml_shield=None, agent_graph=None, mcp_firewall=None, code_shield=None, grounding=None, cot_auditor=None, toxicity=None, hitl_gate=None, **kwargs):
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
        if rate_limit:
            limit, window = self._parse_rate_limit(rate_limit)
            self.modules["rate_limiter"] = RateLimiterModule(limit=limit, window_seconds=window)
            self.registry.register_before_request(self.modules["rate_limiter"].pre_check)
        if context_guard is not False and context_guard is not None:
            if isinstance(context_guard, float):
                margin = context_guard
            elif isinstance(context_guard, bool):
                margin = 0.95  # default safety margin
            else:
                raise ValueError(
                    f"context_guard must be True/False or a float safety margin (0 < x <= 1.0), "
                    f"got {type(context_guard).__name__!r}."
                )
            self.modules["context_guard"] = ContextGuardModule(safety_margin=margin)
            self.registry.register_before_request(self.modules["context_guard"].pre_check)
        if latency_breaker is not False and latency_breaker is not None:
            if isinstance(latency_breaker, dict):
                self.modules["latency_breaker"] = LatencyBreakerModule(**latency_breaker)
            elif isinstance(latency_breaker, bool) and latency_breaker:
                self.modules["latency_breaker"] = LatencyBreakerModule()
            if "latency_breaker" in self.modules:
                self.registry.register_after_response(self.modules["latency_breaker"].post_check)
        if canary is not False and canary is not None:
            if isinstance(canary, dict):
                self.modules["canary"] = CanaryModule(**canary)
            elif isinstance(canary, str):
                self.modules["canary"] = CanaryModule(canary_word=canary)
            elif isinstance(canary, bool) and canary:
                self.modules["canary"] = CanaryModule()
            if "canary" in self.modules:
                self.registry.register_before_request(self.modules["canary"].pre_check)
                self.registry.register_after_response(self.modules["canary"].post_filter)
        if tool_firewall:
            if isinstance(tool_firewall, dict):
                self.modules["tool_firewall"] = ToolFirewallModule(**tool_firewall)
            elif isinstance(tool_firewall, list):
                self.modules["tool_firewall"] = ToolFirewallModule(allow=tool_firewall)
            self.registry.register_after_response(self.modules["tool_firewall"].post_filter)
        if cost_tags is not False and cost_tags is not None:
            if isinstance(cost_tags, dict):
                self.modules["cost_tags"] = CostTagsModule(**cost_tags)
            elif isinstance(cost_tags, bool) and cost_tags:
                self.modules["cost_tags"] = CostTagsModule()
            if "cost_tags" in self.modules:
                self.registry.register_after_response(self.modules["cost_tags"].post_record)
        if dedup is not False and dedup is not None:
            if isinstance(dedup, dict):
                self.modules["dedup"] = DedupModule(**dedup)
            elif isinstance(dedup, bool) and dedup:
                self.modules["dedup"] = DedupModule()
            if "dedup" in self.modules:
                self.registry.register_before_request(self.modules["dedup"].pre_check)
        if cascade:
            budget_ref = self.modules.get("budget")
            self.modules["cascade"] = CascadeModule(tiers=cascade, budget_ref=budget_ref)
            self.registry._before_request.insert(0, self.modules["cascade"].pre_check)
        if ml_shield is not False and ml_shield is not None:
            if isinstance(ml_shield, dict):
                self.modules["ml_shield"] = MLShieldModule(**ml_shield)
            elif isinstance(ml_shield, bool) and ml_shield:
                self.modules["ml_shield"] = MLShieldModule()
            if "ml_shield" in self.modules:
                self.registry.register_before_request(self.modules["ml_shield"].pre_check)
        if agent_graph is not False and agent_graph is not None:
            if isinstance(agent_graph, dict):
                self.modules["agent_graph"] = AgentGraphModule(**agent_graph)
            elif isinstance(agent_graph, bool) and agent_graph:
                self.modules["agent_graph"] = AgentGraphModule()
            if "agent_graph" in self.modules:
                self.registry.register_before_request(
                    self.modules["agent_graph"].pre_check
                )
                self.registry.register_after_response(
                    self.modules["agent_graph"].post_record
                )
        if mcp_firewall is not False and mcp_firewall is not None:
            if isinstance(mcp_firewall, dict):
                self.modules["mcp_firewall"] = MCPFirewallModule(**mcp_firewall)
            elif isinstance(mcp_firewall, bool) and mcp_firewall:
                self.modules["mcp_firewall"] = MCPFirewallModule()
            if "mcp_firewall" in self.modules:
                self.registry.register_after_response(self.modules["mcp_firewall"].post_filter)
        if code_shield is not False and code_shield is not None:
            if isinstance(code_shield, dict):
                self.modules["code_shield"] = CodeShieldModule(**code_shield)
            elif isinstance(code_shield, bool) and code_shield:
                self.modules["code_shield"] = CodeShieldModule()
            if "code_shield" in self.modules:
                self.registry.register_after_response(self.modules["code_shield"].post_filter)
                self.registry.register_on_stream_chunk(self.modules["code_shield"].stream_filter)
        if grounding is not False and grounding is not None:
            if isinstance(grounding, dict):
                self.modules["grounding"] = GroundingGuardModule(**grounding)
            elif isinstance(grounding, bool) and grounding:
                self.modules["grounding"] = GroundingGuardModule()
            if "grounding" in self.modules:
                self.registry.register_before_request(self.modules["grounding"].pre_check)
                self.registry.register_after_response(self.modules["grounding"].post_filter)
        if cot_auditor is not False and cot_auditor is not None:
            if isinstance(cot_auditor, dict):
                self.modules["cot_auditor"] = CoTAuditorModule(**cot_auditor)
            elif isinstance(cot_auditor, bool) and cot_auditor:
                self.modules["cot_auditor"] = CoTAuditorModule()
            if "cot_auditor" in self.modules:
                self.registry.register_after_response(self.modules["cot_auditor"].post_filter)
        if toxicity is not False and toxicity is not None:
            if isinstance(toxicity, dict):
                self.modules["toxicity"] = ToxicityModule(**toxicity)
            elif isinstance(toxicity, bool) and toxicity:
                self.modules["toxicity"] = ToxicityModule()
            if "toxicity" in self.modules:
                self.registry.register_after_response(self.modules["toxicity"].post_filter)
                self.registry.register_on_stream_chunk(self.modules["toxicity"].stream_filter)
        if hitl_gate is not False and hitl_gate is not None:
            if isinstance(hitl_gate, dict):
                self.modules["hitl_gate"] = HITLGateModule(**hitl_gate)
            elif isinstance(hitl_gate, bool) and hitl_gate:
                self.modules["hitl_gate"] = HITLGateModule()
            if "hitl_gate" in self.modules:
                self.registry.register_after_response(self.modules["hitl_gate"].post_filter)

    def patch(self) -> None:
        """Monkey-patches the OpenAI, Anthropic, and Gemini SDKs."""
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

        try:
            from google.generativeai import GenerativeModel
            self._originals["gemini_sync"] = GenerativeModel.generate_content
            GenerativeModel.generate_content = self._wrap_gemini_sync(self._originals["gemini_sync"])
            self._originals["gemini_async"] = GenerativeModel.generate_content_async
            GenerativeModel.generate_content_async = self._wrap_gemini_async(self._originals["gemini_async"])
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

        try:
            from google.generativeai import GenerativeModel
            if "gemini_sync" in self._originals:
                GenerativeModel.generate_content = self._originals["gemini_sync"]
            if "gemini_async" in self._originals:
                GenerativeModel.generate_content_async = self._originals["gemini_async"]
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

    @staticmethod
    def _gemini_contents_to_messages(contents: Any) -> list:
        """Convert Gemini 'contents' format to a normalized messages list."""
        if contents is None:
            return []
        # Simple string prompt
        if isinstance(contents, str):
            return [{"role": "user", "parts": [{"text": contents}]}]
        # Already a list of dicts
        if isinstance(contents, list):
            messages = []
            for item in contents:
                if isinstance(item, str):
                    messages.append({"role": "user", "parts": [{"text": item}]})
                elif isinstance(item, dict):
                    messages.append(item)
                else:
                    # Could be a Content proto object
                    messages.append({"role": getattr(item, "role", "user"), "parts": [{"text": str(item)}]})
            return messages
        # Single dict
        if isinstance(contents, dict):
            return [contents]
        return [{"role": "user", "parts": [{"text": str(contents)}]}]

    def _gemini_get_model_name(self, model_instance: Any) -> str:
        """Extract model name from a GenerativeModel instance."""
        for attr in ("model_name", "_model_name"):
            name = getattr(model_instance, attr, None)
            if name:
                # Strip 'models/' prefix if present
                return name.replace("models/", "") if name.startswith("models/") else name
        return "unknown"

    def _wrap_gemini_sync(self, original_fn: Callable):
        def wrapped(*args, **kwargs):
            # args[0] is the GenerativeModel instance (self)
            model_instance = args[0] if args else None
            model_name = self._gemini_get_model_name(model_instance) if model_instance else "unknown"

            # contents is the first positional arg after self, or a kwarg
            contents = args[1] if len(args) > 1 else kwargs.get("contents", None)
            messages = self._gemini_contents_to_messages(contents)
            stream = kwargs.get("stream", False)

            ctx = RequestContext(
                messages=messages,
                model=model_name,
                temperature=kwargs.get("generation_config", {}).get("temperature") if isinstance(kwargs.get("generation_config"), dict) else None,
                max_tokens=kwargs.get("generation_config", {}).get("max_output_tokens") if isinstance(kwargs.get("generation_config"), dict) else None,
                stream=stream,
                extra_kwargs=kwargs,
            )
            ctx = self.registry.execute_before_request(ctx)

            t0 = time.perf_counter()
            response = original_fn(*args, **kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000

            if ctx.stream:
                return self._handle_stream_sync(response, "gemini", ctx, latency_ms)

            return self._handle_non_stream(response, "gemini", ctx, latency_ms)

        return wrapped

    def _wrap_gemini_async(self, original_fn: Callable):
        async def wrapped(*args, **kwargs):
            model_instance = args[0] if args else None
            model_name = self._gemini_get_model_name(model_instance) if model_instance else "unknown"

            contents = args[1] if len(args) > 1 else kwargs.get("contents", None)
            messages = self._gemini_contents_to_messages(contents)
            stream = kwargs.get("stream", False)

            ctx = RequestContext(
                messages=messages,
                model=model_name,
                temperature=kwargs.get("generation_config", {}).get("temperature") if isinstance(kwargs.get("generation_config"), dict) else None,
                max_tokens=kwargs.get("generation_config", {}).get("max_output_tokens") if isinstance(kwargs.get("generation_config"), dict) else None,
                stream=stream,
                extra_kwargs=kwargs,
            )
            ctx = self.registry.execute_before_request(ctx)

            t0 = time.perf_counter()
            response = await original_fn(*args, **kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000

            if ctx.stream:
                return self._handle_stream_async(response, "gemini", ctx, latency_ms)

            return self._handle_non_stream(response, "gemini", ctx, latency_ms)

        return wrapped

    def _handle_non_stream(self, response: Any, provider: str, req_ctx: RequestContext, latency_ms: float):
        output_text = self._extract_output(response, provider)
        usage = self._extract_non_stream_usage(response, provider)

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
            elif provider == "gemini":
                # response.candidates is empty when Gemini blocks the
                # response (e.g. safety filter, quota). Fall through to "".
                if not getattr(response, "candidates", None):
                    return ""
                return response.text or ""
        except Exception:
            pass
        return ""

    def _inject_output(self, response: Any, provider: str, output_text: str) -> None:
        try:
            if provider == "openai":
                response.choices[0].message.content = output_text
            elif provider == "anthropic":
                response.content[0].text = output_text
            elif provider == "gemini":
                # Guard: no candidates means response was blocked; nothing to inject.
                if not getattr(response, "candidates", None):
                    return
                response.candidates[0].content.parts[0].text = output_text
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
            elif provider == "gemini":
                return getattr(chunk, "text", "") or ""
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
            elif provider == "gemini":
                if hasattr(chunk, "candidates") and chunk.candidates:
                    chunk.candidates[0].content.parts[0].text = new_delta
        except Exception:
            pass

    def _extract_non_stream_usage(self, response: Any, provider: str = None) -> Dict[str, int]:
        usage = None
        if provider == "gemini":
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)
                if input_tokens > 0 or output_tokens > 0:
                    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        elif hasattr(response, "usage") and response.usage:
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
            elif provider == "gemini":
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    prompt_count = getattr(chunk.usage_metadata, "prompt_token_count", 0)
                    candidates_count = getattr(chunk.usage_metadata, "candidates_token_count", 0)
                    if prompt_count > 0:
                        usage["input_tokens"] = prompt_count
                    if candidates_count > 0:
                        usage["output_tokens"] = candidates_count
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

    @staticmethod
    def _parse_rate_limit(rate_limit: str) -> tuple:
        """
        Parses a rate limit string like '10/min' or '5/sec' into (limit, window_seconds).
        
        Supported suffixes: sec, s, min, m, hour, h
        """
        parts = rate_limit.strip().split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid rate_limit format: '{rate_limit}'. Use 'N/unit' (e.g. '10/min').")
        
        limit = int(parts[0])
        unit = parts[1].strip().lower()
        
        unit_map = {
            "sec": 1, "s": 1, "second": 1,
            "min": 60, "m": 60, "minute": 60,
            "hour": 3600, "h": 3600, "hr": 3600,
        }
        
        if unit not in unit_map:
            raise ValueError(f"Unknown time unit: '{unit}'. Supported: sec, min, hour.")
        
        return limit, unit_map[unit]
