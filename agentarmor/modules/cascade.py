"""
Model Downgrade Cascade — automatically switches to cheaper models
as the budget depletes, based on a user-defined tier strategy.
"""

from typing import Any, Dict, List, Optional

from ..hooks import RequestContext


class CascadeModule:
    """Pre-request hook that swaps the model based on budget usage tiers."""

    def __init__(self, tiers: List[Dict[str, Any]], budget_ref: Optional[Any] = None):
        self._validate_tiers(tiers)
        self.tiers = tiers
        self.budget_ref = budget_ref
        self.downgrades = 0
        self.original_models: List[Dict[str, str]] = []

    @staticmethod
    def _validate_tiers(tiers: List[Dict[str, Any]]) -> None:
        if not tiers:
            raise ValueError("cascade tiers must be a non-empty list.")

        prev = 0
        for i, tier in enumerate(tiers):
            if "model" not in tier or "until_percent" not in tier:
                raise ValueError(
                    f"Each tier must have 'model' and 'until_percent' keys. "
                    f"Tier {i} is missing one: {tier}"
                )
            pct = tier["until_percent"]
            if pct <= prev:
                raise ValueError(
                    f"Tiers must be sorted by ascending until_percent. "
                    f"Tier {i} has {pct} but previous was {prev}."
                )
            prev = pct

        if tiers[-1]["until_percent"] != 100:
            raise ValueError(
                f"Last tier must have until_percent=100, got {tiers[-1]['until_percent']}."
            )

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Swaps the model based on current budget usage percentage.

        Note: ctx.model is mutated in place. If you inspect ctx.model after
        the call, it will reflect the downgraded model, not the originally
        requested one. Check report()['recent_swaps'] to see what was swapped.
        If budget_ref is not set, this hook is a no-op.
        """
        if not self.budget_ref or self.budget_ref.limit <= 0:
            return ctx

        percent_used = (self.budget_ref.spent / self.budget_ref.limit) * 100

        tier_model = self._resolve_tier(percent_used)
        if tier_model and tier_model != ctx.model:
            self.original_models.append({
                "requested": ctx.model,
                "used": tier_model,
            })
            ctx.model = tier_model
            self.downgrades += 1

        return ctx

    def _resolve_tier(self, percent_used: float) -> Optional[str]:
        """Returns the model for the current budget usage tier."""
        for tier in self.tiers:
            if percent_used < tier["until_percent"]:
                return tier["model"]
        # At or beyond 100% — use the last tier
        return self.tiers[-1]["model"]

    def report(self) -> dict:
        percent_used = 0.0
        if self.budget_ref and self.budget_ref.limit > 0:
            percent_used = (self.budget_ref.spent / self.budget_ref.limit) * 100

        current_tier = self._resolve_tier(percent_used) if self.budget_ref else None

        return {
            "downgrades": self.downgrades,
            "current_tier_model": current_tier,
            "recent_swaps": self.original_models[-5:],
        }
