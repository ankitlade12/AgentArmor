from ..pricing import get_cost
from ..exceptions import BudgetExhausted
from ..hooks import RequestContext, ResponseContext
from ..utils import estimate_tokens

class BudgetModule:
    def __init__(self, limit: str):
        """
        Initializes the budget tracker.
        
        Args:
            limit: Dollar amount threshold (e.g. '$5.00').
        """
        self.limit: float = float(limit.replace("$", "").strip())
        self.spent = 0.0
        self.calls = []

    @property
    def remaining(self) -> float:
        """Returns the remaining budget in dollars."""
        return max(0.0, self.limit - self.spent)

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        estimated = self._estimate_input_cost(ctx.model, ctx.messages)
        if self.spent + estimated > self.limit:
            raise BudgetExhausted(
                f"Budget exhausted. Spent: ${self.spent:.4f} / ${self.limit:.2f}"
            )
        return ctx

    def post_record(self, ctx: ResponseContext) -> ResponseContext:
        cost = self._actual_cost(ctx)
        self.spent += cost
        ctx.cost = cost
        # Track per-call metadata so reports can aggregate by provider.
        self.calls.append({
            "model": ctx.model,
            "provider": getattr(ctx, "provider", "unknown"),
            "cost": cost,
            "usage": ctx.usage or {},
        })
        return ctx

    def _estimate_input_cost(self, model: str, messages: list) -> float:
        input_tokens = estimate_tokens(messages)
        prices = get_cost(model)
        return (input_tokens / 1000) * prices["input"]

    def _actual_cost(self, ctx: ResponseContext) -> float:
        try:
            prices = get_cost(ctx.model)
            
            if ctx.usage and "input_tokens" in ctx.usage and "output_tokens" in ctx.usage:
                input_cost = (ctx.usage["input_tokens"] / 1000) * prices["input"]
                output_cost = (ctx.usage["output_tokens"] / 1000) * prices["output"]
                return input_cost + output_cost
                
            if ctx.raw_response and hasattr(ctx.raw_response, 'usage') and ctx.raw_response.usage:
                usage = ctx.raw_response.usage
                input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', 0))
                output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', 0))
                if input_tokens > 0 or output_tokens > 0:
                    return ((input_tokens / 1000) * prices["input"]) + ((output_tokens / 1000) * prices["output"])
                    
            in_tokens = estimate_tokens(ctx.request.messages)
            out_tokens = max(1, len(ctx.text) // 4)
            return ((in_tokens / 1000) * prices["input"]) + ((out_tokens / 1000) * prices["output"])
            
        except Exception:
            return 0.0

    def report(self):
        by_provider = {}
        for call in self.calls:
            provider = call.get("provider") or "unknown"
            entry = by_provider.setdefault(provider, {"calls": 0, "spent": 0.0})
            entry["calls"] += 1
            entry["spent"] += float(call.get("cost", 0.0))

        # Format provider summaries as simple, human-readable values.
        by_provider_formatted = {
            provider: {
                "calls": data["calls"],
                "spent": f"${data['spent']:.4f}",
            }
            for provider, data in by_provider.items()
        }

        return {
            "spent": f"${self.spent:.4f}",
            "limit": f"${self.limit:.2f}",
            "remaining": f"${self.remaining:.4f}",
            "calls": len(self.calls),
            "by_provider": by_provider_formatted,
        }
