import importlib.util
import time
import warnings
from typing import Any, Callable, Dict

from .hooks import RequestContext, ResponseContext, global_registry
from .trace import _ExplainSession, _config as _explain_config, wrap_async_stream, wrap_sync_stream
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
from .modules.unicode_shield import UnicodeShieldModule
from .modules.hitl_gate import HITLGateModule
from .modules.exfiltration_guard import ExfiltrationGuardModule
from .modules.privilege_escalation import PrivilegeEscalationModule
from .modules.compliance_reporter import ComplianceReporterModule
from .modules.semantic_drift import SemanticDriftModule
from .modules.taint_tracker import TaintTrackerModule
from .modules.honeytools import HoneytoolsModule
from .modules.echo_chamber import EchoChamberModule
from . import _http_intercept

# Chars held back from a streamed response before emission, so a redactable
# pattern forming across chunk boundaries is caught before any of it is sent.
# Covers email/SSN/phone/credit-card/most key formats; longer patterns may still
# leak (see tasks/streaming-redaction/SPEC.md — redaction stays defense-in-depth).
_STREAM_REDACTION_HOLDBACK = 48


class ArmorCore:
    def __init__(self, budget=None, shield=False, filter=None, record=False, rate_limit=None, context_guard=False, latency_breaker=None, canary=None, tool_firewall=None, cost_tags=None, dedup=None, cascade=None, ml_shield=None, agent_graph=None, mcp_firewall=None, code_shield=None, grounding=None, cot_auditor=None, toxicity=None, compliance=None, hitl_gate=None, exfiltration_guard=None, privilege_escalation=None, unicode_shield=None, semantic_drift=None, taint_tracker=None, honeytools=None, echo_chamber=None, explain=False, explain_redact=True, explain_max_detail_bytes=65536, explain_max_active_traces=10000, explain_max_trace_age_seconds=300, **kwargs):
        # Direct ArmorCore() construction also runs kwarg validation in
        # warn-only mode. This catches typos for users who bypass init().
        # Strict-mode escalation is owned by init().
        from ._strict import validate_kwargs
        validate_kwargs(kwargs.keys(), strict=False)

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
                self.registry.register_before_request(self.modules["mcp_firewall"].pre_check)
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
        if unicode_shield is not False and unicode_shield is not None:
            if isinstance(unicode_shield, dict):
                self.modules["unicode_shield"] = UnicodeShieldModule(**unicode_shield)
            elif isinstance(unicode_shield, bool) and unicode_shield:
                self.modules["unicode_shield"] = UnicodeShieldModule()
            if "unicode_shield" in self.modules:
                self.registry.register_before_request(self.modules["unicode_shield"].pre_check)
        if hitl_gate is not False and hitl_gate is not None:
            if isinstance(hitl_gate, dict):
                self.modules["hitl_gate"] = HITLGateModule(**hitl_gate)
            elif isinstance(hitl_gate, bool) and hitl_gate:
                self.modules["hitl_gate"] = HITLGateModule()
            if "hitl_gate" in self.modules:
                self.registry.register_after_response(self.modules["hitl_gate"].post_filter)
        if exfiltration_guard is not False and exfiltration_guard is not None:
            if isinstance(exfiltration_guard, dict):
                self.modules["exfiltration_guard"] = ExfiltrationGuardModule(**exfiltration_guard)
            elif isinstance(exfiltration_guard, bool) and exfiltration_guard:
                self.modules["exfiltration_guard"] = ExfiltrationGuardModule()
            if "exfiltration_guard" in self.modules:
                self.registry.register_after_response(self.modules["exfiltration_guard"].post_filter)
                self.registry.register_on_stream_chunk(self.modules["exfiltration_guard"].stream_filter)
        if privilege_escalation is not False and privilege_escalation is not None:
            if isinstance(privilege_escalation, dict):
                self.modules["privilege_escalation"] = PrivilegeEscalationModule(**privilege_escalation)
            elif isinstance(privilege_escalation, bool) and privilege_escalation:
                self.modules["privilege_escalation"] = PrivilegeEscalationModule()
            if "privilege_escalation" in self.modules:
                self.registry.register_after_response(self.modules["privilege_escalation"].post_filter)
        if compliance is not False and compliance is not None:
            if isinstance(compliance, dict):
                self.modules["compliance"] = ComplianceReporterModule(**compliance)
            elif isinstance(compliance, bool) and compliance:
                self.modules["compliance"] = ComplianceReporterModule()
            if "compliance" in self.modules:
                self.registry.register_after_response(self.modules["compliance"].post_record)
        if semantic_drift is not False and semantic_drift is not None:
            if isinstance(semantic_drift, dict):
                self.modules["semantic_drift"] = SemanticDriftModule(**semantic_drift)
            elif isinstance(semantic_drift, bool) and semantic_drift:
                self.modules["semantic_drift"] = SemanticDriftModule()
            if "semantic_drift" in self.modules:
                self.registry.register_before_request(self.modules["semantic_drift"].pre_check)
        if taint_tracker is not False and taint_tracker is not None:
            if isinstance(taint_tracker, dict):
                self.modules["taint_tracker"] = TaintTrackerModule(**taint_tracker)
            elif isinstance(taint_tracker, bool) and taint_tracker:
                self.modules["taint_tracker"] = TaintTrackerModule()
            if "taint_tracker" in self.modules:
                self.registry.register_before_request(self.modules["taint_tracker"].pre_check)
                self.registry.register_after_response(self.modules["taint_tracker"].post_filter)
        if honeytools is not False and honeytools is not None:
            if isinstance(honeytools, dict):
                self.modules["honeytools"] = HoneytoolsModule(**honeytools)
            elif isinstance(honeytools, bool) and honeytools:
                self.modules["honeytools"] = HoneytoolsModule()
            if "honeytools" in self.modules:
                self.registry.register_before_request(self.modules["honeytools"].pre_check)
                self.registry.register_after_response(self.modules["honeytools"].post_filter)
        if echo_chamber is not False and echo_chamber is not None:
            if isinstance(echo_chamber, dict):
                self.modules["echo_chamber"] = EchoChamberModule(**echo_chamber)
            elif isinstance(echo_chamber, bool) and echo_chamber:
                self.modules["echo_chamber"] = EchoChamberModule()
            if "echo_chamber" in self.modules:
                self.registry.register_before_request(self.modules["echo_chamber"].pre_check)
                self.registry.register_after_response(self.modules["echo_chamber"].post_filter)

    def _install(self, cls, attr: str, key: str, wrapper_factory) -> None:
        """Patch ``cls.attr``, always capturing the GENUINE original.

        If the current method is already an AgentArmor wrapper (init() called
        twice, or a previous core that wasn't torn down), recover the true
        original it recorded instead of capturing the wrapper. Otherwise
        ``teardown()`` would restore a wrapper and corrupt the SDK method
        permanently in-process. The ``is True`` check is deliberate: a
        ``MagicMock`` standing in for the SDK auto-creates any attribute, so a
        loose truthiness test would misread a mock as "already wrapped".
        """
        current = getattr(cls, attr)
        if getattr(current, "_agentarmor_wrapped", False) is True:
            original = current._agentarmor_original
        else:
            original = current
        self._originals[key] = original
        wrapped = self._with_sdk_flag(wrapper_factory(original))
        try:
            wrapped._agentarmor_wrapped = True
            wrapped._agentarmor_original = original
        except (AttributeError, TypeError):
            pass
        setattr(cls, attr, wrapped)

    def _with_sdk_flag(self, fn: Callable) -> Callable:
        """Wrap a patched SDK method so the httpx layer knows an SDK-level call
        is in flight (via the ``sdk_layer_active`` contextvar) and skips it —
        otherwise a normal openai/anthropic call would be counted twice (once by
        the SDK wrapper, once by the httpx wrapper underneath it)."""
        import inspect
        if inspect.iscoroutinefunction(fn):
            async def awrapper(*args, **kwargs):
                token = _http_intercept.sdk_layer_active.set(True)
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _http_intercept.sdk_layer_active.reset(token)
            return awrapper

        def wrapper(*args, **kwargs):
            token = _http_intercept.sdk_layer_active.set(True)
            try:
                return fn(*args, **kwargs)
            finally:
                _http_intercept.sdk_layer_active.reset(token)
        return wrapper

    def _restore(self, cls, attr: str, key: str) -> None:
        if key in self._originals:
            setattr(cls, attr, self._originals[key])

    def _warn_if_installed(self, package: str, error: Exception) -> None:
        """Warn loudly if an *installed* provider SDK could not be patched.

        Distinguishes "SDK not installed" (skip silently — expected) from "SDK
        installed but the patch target could not be resolved" — usually a
        renamed/moved private module in an unsupported SDK version, which would
        otherwise leave that provider's guardrails silently OFF with no signal.
        """
        try:
            installed = importlib.util.find_spec(package) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            installed = False
        if not installed:
            return
        warnings.warn(
            f"AgentArmor: {package} is installed but its patch target could not "
            f"be resolved ({error}); guardrails are INACTIVE for {package}. This "
            f"usually means an unsupported {package} SDK version — please report "
            f"it at https://github.com/ankitlade12/AgentArmor/issues.",
            RuntimeWarning,
            stacklevel=3,
        )

    def patch(self) -> None:
        """Monkey-patches the OpenAI, Anthropic, and Gemini SDKs."""
        try:
            from openai.resources.chat.completions import Completions, AsyncCompletions
            self._install(Completions, "create", "openai_sync",
                          lambda o: self._wrap_sync(o, provider="openai"))
            self._install(AsyncCompletions, "create", "openai_async",
                          lambda o: self._wrap_async(o, provider="openai"))
        except (ImportError, AttributeError) as e:
            self._warn_if_installed("openai", e)

        # OpenAI Responses API (Agents-era surface). Its absence is expected on
        # openai < 2.0, so a missing module here is NOT drift — stay silent.
        try:
            from openai.resources.responses import Responses, AsyncResponses
            self._install(Responses, "create", "openai_responses_sync",
                          self._wrap_responses_sync)
            self._install(AsyncResponses, "create", "openai_responses_async",
                          self._wrap_responses_async)
        except ImportError:
            pass

        try:
            from anthropic.resources.messages import Messages, AsyncMessages
            self._install(Messages, "create", "anthropic_sync",
                          lambda o: self._wrap_sync(o, provider="anthropic"))
            self._install(AsyncMessages, "create", "anthropic_async",
                          lambda o: self._wrap_async(o, provider="anthropic"))
        except (ImportError, AttributeError) as e:
            self._warn_if_installed("anthropic", e)

        try:
            # Import the submodule explicitly — `import google.genai` does not
            # guarantee the `.models` attribute is loaded, so relying on it made
            # patching depend on import order.
            from google.genai import models as genai_models
            self._install(genai_models.Models, "generate_content", "genai_sync",
                          lambda o: self._wrap_genai_sync(o, is_stream=False))
            self._install(genai_models.Models, "generate_content_stream", "genai_stream",
                          lambda o: self._wrap_genai_sync(o, is_stream=True))
            self._install(genai_models.AsyncModels, "generate_content", "genai_async",
                          lambda o: self._wrap_genai_async(o, is_stream=False))
            self._install(genai_models.AsyncModels, "generate_content_stream", "genai_async_stream",
                          lambda o: self._wrap_genai_async(o, is_stream=True))
        except (ImportError, AttributeError) as e:
            self._warn_if_installed("google.genai", e)

        # Generic httpx-layer catch-all for surfaces that bypass the SDK
        # methods above (LiteLLM, .parse()/.stream(), custom httpx clients).
        _http_intercept.install(self)

    def unpatch(self) -> None:
        """Restores original SDK methods."""
        try:
            from openai.resources.chat.completions import Completions, AsyncCompletions
            self._restore(Completions, "create", "openai_sync")
            self._restore(AsyncCompletions, "create", "openai_async")
        except ImportError:
            pass

        try:
            from openai.resources.responses import Responses, AsyncResponses
            self._restore(Responses, "create", "openai_responses_sync")
            self._restore(AsyncResponses, "create", "openai_responses_async")
        except ImportError:
            pass

        try:
            from anthropic.resources.messages import Messages, AsyncMessages
            self._restore(Messages, "create", "anthropic_sync")
            self._restore(AsyncMessages, "create", "anthropic_async")
        except ImportError:
            pass

        try:
            from google.genai import models as genai_models
            self._restore(genai_models.Models, "generate_content", "genai_sync")
            self._restore(genai_models.Models, "generate_content_stream", "genai_stream")
            self._restore(genai_models.AsyncModels, "generate_content", "genai_async")
            self._restore(genai_models.AsyncModels, "generate_content_stream", "genai_async_stream")
        except (ImportError, AttributeError):
            pass

        _http_intercept.uninstall()

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

    def _apply_request_context_to_kwargs(self, ctx: RequestContext, kwargs: dict, provider: str = None) -> None:
        kwargs["messages"] = ctx.messages
        kwargs["model"] = ctx.model
        if ctx.temperature is not None:
            kwargs["temperature"] = ctx.temperature
        if ctx.max_tokens is not None:
            kwargs["max_tokens"] = ctx.max_tokens
        kwargs["stream"] = ctx.stream
        kwargs.update(ctx.extra_kwargs)

        # OpenAI only emits token usage on a streamed response when the caller
        # opts in via stream_options={"include_usage": True}. Without it the
        # budget breaker silently under-meters every stream (input tokens ~0,
        # output cost a char-count guess), so inject it unless the caller has
        # already made an explicit choice.
        if provider == "openai" and ctx.stream:
            existing = kwargs.get("stream_options") or {}
            if "include_usage" not in existing:
                kwargs["stream_options"] = {**existing, "include_usage": True}

    def _wrap_sync(self, original_fn: Callable, provider: str):
        def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                ctx = self._build_request_context(provider, args, kwargs)
                ctx = self.registry.execute_before_request(ctx)
                self._apply_request_context_to_kwargs(ctx, kwargs, provider)

                t0 = time.perf_counter()
                response = original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if ctx.stream:
                    return wrap_sync_stream(
                        self._handle_stream_sync(response, provider, ctx, latency_ms),
                        session,
                    )

                result = self._handle_non_stream(response, provider, ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

        return wrapped

    def _wrap_async(self, original_fn: Callable, provider: str):
        async def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                ctx = self._build_request_context(provider, args, kwargs)
                ctx = self.registry.execute_before_request(ctx)
                self._apply_request_context_to_kwargs(ctx, kwargs, provider)

                t0 = time.perf_counter()
                response = await original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if ctx.stream:
                    return wrap_async_stream(
                        self._handle_stream_async(response, provider, ctx, latency_ms),
                        session,
                    )

                result = self._handle_non_stream(response, provider, ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

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

    def _wrap_genai_sync(self, original_fn: Callable, is_stream: bool):
        def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                model_name = args[1] if len(args) > 1 else kwargs.get("model", "unknown")
                contents = args[2] if len(args) > 2 else kwargs.get("contents", None)
                config = args[3] if len(args) > 3 else kwargs.get("config", None)
                messages = self._gemini_contents_to_messages(contents)

                ctx = RequestContext(
                    messages=messages,
                    model=model_name,
                    temperature=getattr(config, 'temperature', None) if config else None,
                    max_tokens=getattr(config, 'max_output_tokens', None) if config else None,
                    stream=is_stream,
                    extra_kwargs=kwargs,
                )
                ctx = self.registry.execute_before_request(ctx)

                t0 = time.perf_counter()
                response = original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if is_stream:
                    return wrap_sync_stream(
                        self._handle_stream_sync(response, "gemini", ctx, latency_ms),
                        session,
                    )

                result = self._handle_non_stream(response, "gemini", ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

        return wrapped

    def _wrap_genai_async(self, original_fn: Callable, is_stream: bool):
        async def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                model_name = args[1] if len(args) > 1 else kwargs.get("model", "unknown")
                contents = args[2] if len(args) > 2 else kwargs.get("contents", None)
                config = args[3] if len(args) > 3 else kwargs.get("config", None)
                messages = self._gemini_contents_to_messages(contents)

                ctx = RequestContext(
                    messages=messages,
                    model=model_name,
                    temperature=getattr(config, 'temperature', None) if config else None,
                    max_tokens=getattr(config, 'max_output_tokens', None) if config else None,
                    stream=is_stream,
                    extra_kwargs=kwargs,
                )
                ctx = self.registry.execute_before_request(ctx)

                t0 = time.perf_counter()
                response = await original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if is_stream:
                    return wrap_async_stream(
                        self._handle_stream_async(response, "gemini", ctx, latency_ms),
                        session,
                    )

                result = self._handle_non_stream(response, "gemini", ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

        return wrapped

    # ------------------------------------------------------------------
    # OpenAI Responses API wrappers
    # ------------------------------------------------------------------

    def _wrap_responses_sync(self, original_fn: Callable):
        def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                model = kwargs.get("model", "unknown")
                input_val = kwargs.get("input", "")
                had_instructions = "instructions" in kwargs
                instructions = kwargs.get("instructions", None)
                messages = self._responses_input_to_messages(input_val, instructions)

                ctx = RequestContext(
                    messages=messages,
                    model=model,
                    stream=kwargs.get("stream", False),
                    extra_kwargs=kwargs,
                )
                ctx = self.registry.execute_before_request(ctx)
                new_instructions, new_input = self._split_responses_messages(
                    ctx.messages, had_instructions,
                )
                kwargs["input"] = new_input
                if had_instructions:
                    kwargs["instructions"] = new_instructions

                t0 = time.perf_counter()
                response = original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if kwargs.get("stream", False):
                    return wrap_sync_stream(
                        self._handle_responses_stream_sync(response, ctx, latency_ms),
                        session,
                    )

                result = self._handle_responses_non_stream(response, ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

        return wrapped

    def _wrap_responses_async(self, original_fn: Callable):
        async def wrapped(*args, **kwargs):
            session = _ExplainSession() if _explain_config.enabled else None
            try:
                model = kwargs.get("model", "unknown")
                input_val = kwargs.get("input", "")
                had_instructions = "instructions" in kwargs
                instructions = kwargs.get("instructions", None)
                messages = self._responses_input_to_messages(input_val, instructions)

                ctx = RequestContext(
                    messages=messages,
                    model=model,
                    stream=kwargs.get("stream", False),
                    extra_kwargs=kwargs,
                )
                ctx = self.registry.execute_before_request(ctx)
                new_instructions, new_input = self._split_responses_messages(
                    ctx.messages, had_instructions,
                )
                kwargs["input"] = new_input
                if had_instructions:
                    kwargs["instructions"] = new_instructions

                t0 = time.perf_counter()
                response = await original_fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if kwargs.get("stream", False):
                    return wrap_async_stream(
                        self._handle_responses_stream_async(response, ctx, latency_ms),
                        session,
                    )

                result = self._handle_responses_non_stream(response, ctx, latency_ms)
                if session: session.close_normal()
                return result
            except BaseException as e:
                if session: session.attach_exception(e)
                raise

        return wrapped

    @staticmethod
    def _responses_input_to_messages(input_val: Any, instructions: Any = None) -> list:
        """Convert Responses API input + instructions to normalized messages list.

        The ``instructions`` field is the Responses API equivalent of a
        system prompt. When present, it is prepended as a system message
        so that before-request guardrails (shield, ml_shield, etc.) can
        scan it for injection attempts.
        """
        messages = []
        # Prepend instructions as system message so guardrails can scan it
        if instructions and isinstance(instructions, str):
            messages.append({"role": "system", "content": instructions})

        if isinstance(input_val, str):
            messages.append({"role": "user", "content": input_val})
        elif isinstance(input_val, list):
            for item in input_val:
                if isinstance(item, str):
                    messages.append({"role": "user", "content": item})
                elif isinstance(item, dict):
                    messages.append(item)
                else:
                    messages.append({"role": "user", "content": str(item)})
        else:
            messages.append({"role": "user", "content": str(input_val)})
        return messages

    @staticmethod
    def _split_responses_messages(messages: list, had_instructions: bool) -> tuple:
        """Split normalized messages back into (instructions, input).

        If the original call had an ``instructions`` field, the first
        system message is extracted back into instructions and the
        remaining messages become the input. This prevents duplication
        and ensures hook rewrites to the system message are reflected
        in the actual ``instructions`` kwarg sent to the provider.

        Returns (instructions_str_or_None, input_value).
        """
        instructions = None
        input_msgs = list(messages)

        if had_instructions and input_msgs:
            # Extract the first system message as instructions
            if input_msgs[0].get("role") == "system":
                instructions = input_msgs[0].get("content", "")
                input_msgs = input_msgs[1:]

        # Convert remaining messages to simple format if possible
        if len(input_msgs) == 1 and input_msgs[0].get("role") == "user":
            input_val = input_msgs[0].get("content", "")
        else:
            input_val = input_msgs

        return instructions, input_val

    def _handle_responses_non_stream(self, response: Any, req_ctx: RequestContext, latency_ms: float):
        output_text = self._extract_responses_output(response)
        usage = self._extract_responses_usage(response)

        res_ctx = ResponseContext(
            text=output_text,
            model=req_ctx.model,
            provider="openai",
            request=req_ctx,
            latency_ms=latency_ms,
            usage=usage,
            raw_response=response,
        )

        res_ctx = self.registry.execute_after_response(res_ctx)
        self._inject_responses_output(response, res_ctx.text)
        return response

    def _handle_responses_stream_sync(self, stream: Any, req_ctx: RequestContext, latency_ms: float):
        accumulated_text = ""
        current_safe_text = ""
        usage = None

        def generator():
            nonlocal accumulated_text, current_safe_text, usage
            last_content_event = None
            try:
                for event in stream:
                    delta = self._extract_responses_stream_delta(event)
                    if delta:
                        accumulated_text += delta
                        safe_delta, current_safe_text = self._streaming_safe_delta(
                            accumulated_text, current_safe_text
                        )
                        self._inject_responses_stream_delta(event, safe_delta)
                        last_content_event = event
                    yield event

                safe_delta, current_safe_text = self._streaming_safe_delta(
                    accumulated_text, current_safe_text, final=True
                )
                if safe_delta and last_content_event is not None:
                    self._inject_responses_stream_delta(last_content_event, safe_delta)
                    yield last_content_event
            finally:
                res_ctx = ResponseContext(
                    text=current_safe_text,
                    model=req_ctx.model,
                    provider="openai",
                    request=req_ctx,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                self.registry.execute_after_response(res_ctx)

        return generator()

    def _handle_responses_stream_async(self, stream: Any, req_ctx: RequestContext, latency_ms: float):
        accumulated_text = ""
        current_safe_text = ""
        usage = None

        async def async_generator():
            nonlocal accumulated_text, current_safe_text, usage
            last_content_event = None
            try:
                async for event in stream:
                    delta = self._extract_responses_stream_delta(event)
                    if delta:
                        accumulated_text += delta
                        safe_delta, current_safe_text = self._streaming_safe_delta(
                            accumulated_text, current_safe_text
                        )
                        self._inject_responses_stream_delta(event, safe_delta)
                        last_content_event = event
                    yield event

                safe_delta, current_safe_text = self._streaming_safe_delta(
                    accumulated_text, current_safe_text, final=True
                )
                if safe_delta and last_content_event is not None:
                    self._inject_responses_stream_delta(last_content_event, safe_delta)
                    yield last_content_event
            finally:
                res_ctx = ResponseContext(
                    text=current_safe_text,
                    model=req_ctx.model,
                    provider="openai",
                    request=req_ctx,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                self.registry.execute_after_response(res_ctx)

        return async_generator()

    @staticmethod
    def _extract_responses_output(response: Any) -> str:
        """Extract text from an OpenAI Responses API response."""
        # Try output_text first (convenience accessor)
        try:
            text = getattr(response, "output_text", None)
            if text:
                return text
        except Exception:
            pass
        # Fall back to iterating output items
        try:
            for item in getattr(response, "output", []):
                if getattr(item, "type", "") == "message":
                    for content in getattr(item, "content", []):
                        if getattr(content, "type", "") == "output_text":
                            return getattr(content, "text", "")
        except Exception:
            pass
        return ""

    @staticmethod
    def _inject_responses_output(response: Any, text: str) -> None:
        """Inject filtered text back into a Responses API response.

        Rewrites both the nested output[*].content[*].text AND the
        top-level output_text convenience accessor so filtered text
        is returned regardless of which accessor the caller uses.
        """
        try:
            for item in getattr(response, "output", []):
                if getattr(item, "type", "") == "message":
                    for content in getattr(item, "content", []):
                        if getattr(content, "type", "") == "output_text":
                            content.text = text
        except Exception:
            pass
        # Also rewrite the top-level convenience accessor
        try:
            if hasattr(response, "output_text"):
                response.output_text = text
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _extract_responses_stream_delta(event: Any) -> str:
        """Extract text delta from a Responses API streaming event."""
        try:
            etype = getattr(event, "type", "")
            if etype == "response.output_text.delta":
                return getattr(event, "delta", "") or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _inject_responses_stream_delta(event: Any, new_delta: str) -> None:
        """Rewrite the delta text in a Responses API streaming event."""
        try:
            if getattr(event, "type", "") == "response.output_text.delta":
                event.delta = new_delta
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _extract_responses_usage(response: Any) -> dict:
        """Extract usage from a Responses API response."""
        try:
            usage = getattr(response, "usage", None)
            if usage:
                return {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                }
        except Exception:
            pass
        return None

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

    def _streaming_safe_delta(self, accumulated_text: str, current_safe_text: str, final: bool = False):
        """Decide how much redacted text is safe to emit so far.

        Holds back the trailing ``_STREAM_REDACTION_HOLDBACK`` chars so a pattern
        still forming across the chunk boundary is redacted before any of it is
        emitted; on ``final`` (stream end) the whole accumulated text is flushed.
        The ``startswith`` guard ensures we never splice a non-prefix. Returns
        ``(delta_to_emit, new_current_safe_text)``.
        """
        if final:
            scan_target = accumulated_text
        elif len(accumulated_text) > _STREAM_REDACTION_HOLDBACK:
            scan_target = accumulated_text[:-_STREAM_REDACTION_HOLDBACK]
        else:
            scan_target = ""
        if not scan_target:
            # Nothing committed yet — don't fire stream hooks on empty text.
            return "", current_safe_text
        redacted = self.registry.execute_on_stream_chunk(scan_target)
        if redacted.startswith(current_safe_text) and len(redacted) > len(current_safe_text):
            return redacted[len(current_safe_text):], redacted
        return "", current_safe_text

    def _handle_stream_sync(self, stream: Any, provider: str, req_ctx: RequestContext, latency_ms: float):
        accumulated_text = ""
        current_safe_text = ""
        usage = None

        def generator():
            nonlocal accumulated_text, current_safe_text, usage
            last_content_chunk = None
            try:
                for chunk in stream:
                    delta = self._extract_chunk_delta(chunk, provider)
                    if delta:
                        accumulated_text += delta
                        safe_delta, current_safe_text = self._streaming_safe_delta(
                            accumulated_text, current_safe_text
                        )
                        self._inject_chunk_delta(chunk, provider, safe_delta)
                        last_content_chunk = chunk
                    usage = self._extract_stream_usage(chunk, provider, usage)
                    yield chunk

                # Stream complete: flush the held-back tail. (Not in finally —
                # a generator can't yield while being closed.)
                safe_delta, current_safe_text = self._streaming_safe_delta(
                    accumulated_text, current_safe_text, final=True
                )
                if safe_delta and last_content_chunk is not None:
                    self._inject_chunk_delta(last_content_chunk, provider, safe_delta)
                    yield last_content_chunk
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
            last_content_chunk = None
            try:
                async for chunk in stream:
                    delta = self._extract_chunk_delta(chunk, provider)
                    if delta:
                        accumulated_text += delta
                        safe_delta, current_safe_text = self._streaming_safe_delta(
                            accumulated_text, current_safe_text
                        )
                        self._inject_chunk_delta(chunk, provider, safe_delta)
                        last_content_chunk = chunk
                    usage = self._extract_stream_usage(chunk, provider, usage)
                    yield chunk

                # Stream complete: flush the held-back tail.
                safe_delta, current_safe_text = self._streaming_safe_delta(
                    accumulated_text, current_safe_text, final=True
                )
                if safe_delta and last_content_chunk is not None:
                    self._inject_chunk_delta(last_content_chunk, provider, safe_delta)
                    yield last_content_chunk
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
