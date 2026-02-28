import dataclasses
from typing import List, Dict, Any, Callable, Optional

@dataclasses.dataclass
class RequestContext:
    """Context object representing an outbound request to an LLM provider."""
    messages: List[Dict[str, Any]]
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    extra_kwargs: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.messages, list):
            raise TypeError("messages must be a list")
        if not isinstance(self.model, str):
            raise TypeError("model must be a string")

@dataclasses.dataclass
class ResponseContext:
    """Context object representing an inbound response from an LLM provider."""
    text: str
    model: str
    provider: str
    request: RequestContext
    cost: Optional[float] = None
    latency_ms: Optional[float] = None
    usage: Optional[Dict[str, int]] = None
    raw_response: Any = None

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.model, str):
            raise TypeError("model must be a string")
        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not isinstance(self.request, RequestContext):
            raise TypeError("request must be a RequestContext instance")

class HookRegistry:
    """Registry for managing and executing middleware hooks."""
    def __init__(self):
        self._before_request: List[Callable[[RequestContext], RequestContext]] = []
        self._after_response: List[Callable[[ResponseContext], ResponseContext]] = []
        self._on_stream_chunk: List[Callable[[str], str]] = []

    def register_before_request(self, func: Callable[[RequestContext], RequestContext]) -> Callable[[RequestContext], RequestContext]:
        self._before_request.append(func)
        return func

    def register_after_response(self, func: Callable[[ResponseContext], ResponseContext]) -> Callable[[ResponseContext], ResponseContext]:
        self._after_response.append(func)
        return func

    def register_on_stream_chunk(self, func: Callable[[str], str]) -> Callable[[str], str]:
        self._on_stream_chunk.append(func)
        return func

    def execute_before_request(self, ctx: RequestContext) -> RequestContext:
        for hook in self._before_request:
            ctx = hook(ctx)
            if not isinstance(ctx, RequestContext):
                raise TypeError(f"Hook {hook.__name__} must return a RequestContext object.")
        return ctx

    def execute_after_response(self, ctx: ResponseContext) -> ResponseContext:
        for hook in self._after_response:
            try:
                ctx = hook(ctx)
            except Exception as e:
                raise e
            if not isinstance(ctx, ResponseContext):
                raise TypeError(f"Hook {hook.__name__} must return a ResponseContext object.")
        return ctx

    def execute_on_stream_chunk(self, accumulated_text: str) -> str:
        for hook in self._on_stream_chunk:
            accumulated_text = hook(accumulated_text)
        return accumulated_text

    def clone(self) -> 'HookRegistry':
        """Creates a shallow copy of this registry."""
        new_registry = HookRegistry()
        new_registry._before_request = list(self._before_request)
        new_registry._after_response = list(self._after_response)
        new_registry._on_stream_chunk = list(self._on_stream_chunk)
        return new_registry

# Global hook registry exported via the package root
global_registry = HookRegistry()
before_request = global_registry.register_before_request
after_response = global_registry.register_after_response
on_stream_chunk = global_registry.register_on_stream_chunk
