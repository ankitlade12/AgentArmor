"""Generic httpx-layer interception (observe-first).

The SDK-method patching in ``core.py`` covers ``openai``/``anthropic``/
``google-genai`` calls made through their client classes. It does NOT cover
calls that reach a provider over httpx without going through a patched method:
LiteLLM (SDK mode), OpenAI ``.parse()`` / ``.stream()`` /
``with_streaming_response``, or any custom httpx client. Those previously ran
with the guardrails silently off.

This module wraps ``httpx.Client.send`` / ``httpx.AsyncClient.send`` so the
deterministic controls (budget breaker, cost tracking, audit recording, and
non-streaming response redaction) apply generically. It:

- runs only for known provider hosts (never touches non-LLM traffic),
- skips calls already handled by the SDK layer (``sdk_layer_active`` guard) so
  a normal openai/anthropic call is never double-counted,
- defers streaming (text/event-stream) response handling to a follow-up.
"""
import contextvars
import json

from .hooks import RequestContext, ResponseContext

# Set True by the SDK-level wrappers for the duration of a patched call, so the
# httpx layer does not re-process (double-count) a call the SDK layer handled.
sdk_layer_active = contextvars.ContextVar("_agentarmor_sdk_layer_active", default=False)

# The currently-active core and host config. Module-level (not closed over) so a
# second init() updates them even though httpx is only wrapped once.
_active_core = None
_extra_hosts = None

# First-party LLM API hosts whose wire format we understand. Gemini is omitted
# on purpose — google-genai is handled at the SDK layer. A user behind an
# OpenAI-compatible proxy (e.g. a LiteLLM proxy on a custom host) can register
# it via extra_hosts={"my-proxy:4000": "openai"}.
_HOST_PROVIDERS = {
    "api.openai.com": "openai",
    "api.anthropic.com": "anthropic",
    "openrouter.ai": "openai",
}


def _provider_for(host, extra_hosts):
    host = (host or "").lower()
    table = dict(_HOST_PROVIDERS)
    if extra_hosts:
        table.update({str(h).lower(): p for h, p in extra_hosts.items()})
    for known, provider in table.items():
        if host == known or host.endswith("." + known):
            return provider
    return None


def _request_context(request):
    try:
        data = json.loads(request.content or b"{}")
    except Exception:
        return None
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    model = data.get("model")
    if not isinstance(model, str):
        model = "unknown"
    return RequestContext(messages=messages, model=model, stream=bool(data.get("stream")))


def _parse_response(data, provider):
    """Return (text, usage) extracted from a provider's JSON response body."""
    if provider == "anthropic":
        text = "".join(
            b.get("text", "")
            for b in (data.get("content") or [])
            if isinstance(b, dict) and b.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return text, {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
    # openai / openrouter (openai-compatible)
    text = ""
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        text = (choices[0].get("message") or {}).get("content") or ""
    usage = data.get("usage") or {}
    return text, {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def _write_back(data, new_text, provider):
    if provider == "anthropic":
        for b in data.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "text":
                b["text"] = new_text
                break
    else:
        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            choices[0].setdefault("message", {})["content"] = new_text
    return data


def _run_before(core, request, provider):
    ctx = _request_context(request)
    if ctx is None:
        return
    # Blocking controls (budget breaker, shield, rate limit) intentionally raise
    # here; the exception propagates to the caller — that is the breaker firing.
    core.registry.execute_before_request(ctx)


def _run_after(core, request, response, provider):
    try:
        if "text/event-stream" in response.headers.get("content-type", ""):
            return response  # streaming deferred to a follow-up
        data = response.json()
    except Exception:
        return response  # not JSON / unreadable — leave untouched

    try:
        text, usage = _parse_response(data, provider)
        req_ctx = _request_context(request) or RequestContext(messages=[], model="unknown")
        model = data.get("model")
        resp_ctx = ResponseContext(
            text=text,
            model=model if isinstance(model, str) else req_ctx.model,
            provider=provider,
            request=req_ctx,
            usage=usage,
        )
    except Exception:
        return response  # unsupported JSON shape — leave untouched

    resp_ctx = core.registry.execute_after_response(resp_ctx)
    if resp_ctx.text != text:
        try:
            response._content = json.dumps(
                _write_back(data, resp_ctx.text, provider)
            ).encode("utf-8")
            if "content-length" in response.headers:
                response.headers["content-length"] = str(len(response._content))
        except Exception:
            pass
    return response


def install(core, extra_hosts=None):
    """Wrap httpx send methods. Idempotent; safe to call on every init().

    The active core/host config live at module level, so a second init() simply
    rebinds them — httpx is only wrapped once and the wrappers read the current
    values at call time.
    """
    global _active_core, _extra_hosts
    _active_core = core
    _extra_hosts = extra_hosts
    try:
        import httpx
    except ImportError:
        return
    if getattr(httpx.Client.send, "_agentarmor_wrapped", False) is True:
        return  # already wrapped; the active-core rebind above is enough

    orig_sync = httpx.Client.send
    orig_async = httpx.AsyncClient.send

    def send(self, request, *args, **kwargs):
        core = _active_core
        if core is None or sdk_layer_active.get():
            return orig_sync(self, request, *args, **kwargs)
        provider = _provider_for(request.url.host, _extra_hosts)
        if provider is None:
            return orig_sync(self, request, *args, **kwargs)
        _run_before(core, request, provider)
        response = orig_sync(self, request, *args, **kwargs)
        return _run_after(core, request, response, provider)

    async def asend(self, request, *args, **kwargs):
        core = _active_core
        if core is None or sdk_layer_active.get():
            return await orig_async(self, request, *args, **kwargs)
        provider = _provider_for(request.url.host, _extra_hosts)
        if provider is None:
            return await orig_async(self, request, *args, **kwargs)
        _run_before(core, request, provider)
        response = await orig_async(self, request, *args, **kwargs)
        return _run_after(core, request, response, provider)

    for fn, orig in ((send, orig_sync), (asend, orig_async)):
        fn._agentarmor_wrapped = True
        fn._agentarmor_original = orig
    httpx.Client.send = send
    httpx.AsyncClient.send = asend


def uninstall():
    global _active_core
    _active_core = None
    try:
        import httpx
    except ImportError:
        return
    for cls in (httpx.Client, httpx.AsyncClient):
        cur = getattr(cls, "send", None)
        if getattr(cur, "_agentarmor_wrapped", False) is True:
            cls.send = cur._agentarmor_original
