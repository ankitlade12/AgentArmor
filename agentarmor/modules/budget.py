from ..pricing import get_cost
from ..exceptions import BudgetExhausted

class BudgetModule:
    def __init__(self, limit: str):
        # Parse "$5.00" → 5.0
        self.limit = float(limit.replace("$", "").strip())
        self.spent = 0.0
        self.calls = []

    @property
    def remaining(self):
        return max(0.0, self.limit - self.spent)

    def pre_check(self, model, messages):
        estimated = self._estimate_cost(model, messages)
        if self.spent + estimated > self.limit:
            raise BudgetExhausted(
                f"Budget exhausted. Spent: ${self.spent:.4f} / ${self.limit:.2f}"
            )

    def post_record(self, model, response):
        cost = self._actual_cost(model, response)
        self.spent += cost
        self.calls.append({"model": model, "cost": cost})

    def _estimate_cost(self, model, messages):
        # Rough token estimate: 4 chars ≈ 1 token
        total_chars = sum(len(m.get("content", "")) for m in messages)
        input_tokens = total_chars // 4
        prices = get_cost(model)
        return (input_tokens / 1000) * prices["input"]

    def _actual_cost(self, model, response):
        try:
            usage = response.usage
            prices = get_cost(model)
            input_cost = (usage.prompt_tokens / 1000) * prices["input"]
            output_cost = (usage.completion_tokens / 1000) * prices["output"]
            return input_cost + output_cost
        except Exception:
            return 0.0

    def report(self):
        return {
            "spent": f"${self.spent:.4f}",
            "limit": f"${self.limit:.2f}",
            "remaining": f"${self.remaining:.4f}",
            "calls": len(self.calls)
        }
