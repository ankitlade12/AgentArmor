import pytest
from agentarmor.modules.cascade import CascadeModule
from agentarmor.hooks import RequestContext


# ---------------------------------------------------------------------------
# Mock budget reference
# ---------------------------------------------------------------------------

class MockBudget:
    def __init__(self, spent, limit):
        self.spent = spent
        self.limit = limit


TIERS = [
    {"model": "gpt-4o", "until_percent": 50},
    {"model": "gpt-4o-mini", "until_percent": 90},
    {"model": "gpt-3.5-turbo", "until_percent": 100},
]


def _make_ctx(model="gpt-4o"):
    return RequestContext(messages=[{"role": "user", "content": "hello"}], model=model)


# ---------------------------------------------------------------------------
# Basic tier resolution
# ---------------------------------------------------------------------------

def test_cascade_uses_first_tier_at_zero_spend():
    budget = MockBudget(spent=0.0, limit=10.0)
    module = CascadeModule(tiers=TIERS, budget_ref=budget)
    ctx = _make_ctx("gpt-4o")

    result = module.pre_check(ctx)
    # Already on the correct tier model — no downgrade
    assert result.model == "gpt-4o"
    assert module.downgrades == 0


def test_cascade_downgrades_at_threshold():
    budget = MockBudget(spent=6.0, limit=10.0)  # 60% spent
    module = CascadeModule(tiers=TIERS, budget_ref=budget)
    ctx = _make_ctx("gpt-4o")

    result = module.pre_check(ctx)
    assert result.model == "gpt-4o-mini"
    assert module.downgrades == 1


def test_cascade_final_tier_at_high_spend():
    budget = MockBudget(spent=9.5, limit=10.0)  # 95% spent
    module = CascadeModule(tiers=TIERS, budget_ref=budget)
    ctx = _make_ctx("gpt-4o")

    result = module.pre_check(ctx)
    assert result.model == "gpt-3.5-turbo"
    assert module.downgrades == 1


def test_cascade_no_downgrade_when_model_matches_tier():
    budget = MockBudget(spent=6.0, limit=10.0)  # 60% → gpt-4o-mini tier
    module = CascadeModule(tiers=TIERS, budget_ref=budget)
    ctx = _make_ctx("gpt-4o-mini")  # Already on the right model

    result = module.pre_check(ctx)
    assert result.model == "gpt-4o-mini"
    assert module.downgrades == 0


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------

def test_cascade_tracks_downgrades_count():
    budget = MockBudget(spent=6.0, limit=10.0)
    module = CascadeModule(tiers=TIERS, budget_ref=budget)

    for _ in range(3):
        ctx = _make_ctx("gpt-4o")
        module.pre_check(ctx)

    assert module.downgrades == 3
    assert len(module.original_models) == 3
    assert all(s["requested"] == "gpt-4o" and s["used"] == "gpt-4o-mini" for s in module.original_models)


# ---------------------------------------------------------------------------
# No budget ref
# ---------------------------------------------------------------------------

def test_cascade_without_budget_ref_passes_through():
    module = CascadeModule(tiers=TIERS, budget_ref=None)
    ctx = _make_ctx("gpt-4o")

    result = module.pre_check(ctx)
    assert result.model == "gpt-4o"
    assert module.downgrades == 0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_cascade_report():
    budget = MockBudget(spent=7.0, limit=10.0)
    module = CascadeModule(tiers=TIERS, budget_ref=budget)

    ctx = _make_ctx("gpt-4o")
    module.pre_check(ctx)

    report = module.report()
    assert report["downgrades"] == 1
    assert report["current_tier_model"] == "gpt-4o-mini"
    assert len(report["recent_swaps"]) == 1
    assert report["recent_swaps"][0]["requested"] == "gpt-4o"
    assert report["recent_swaps"][0]["used"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_cascade_invalid_tiers_not_sorted():
    with pytest.raises(ValueError, match="ascending"):
        CascadeModule(tiers=[
            {"model": "gpt-4o", "until_percent": 90},
            {"model": "gpt-4o-mini", "until_percent": 50},
            {"model": "gpt-3.5-turbo", "until_percent": 100},
        ])


def test_cascade_invalid_tiers_not_ending_100():
    with pytest.raises(ValueError, match="until_percent=100"):
        CascadeModule(tiers=[
            {"model": "gpt-4o", "until_percent": 50},
            {"model": "gpt-4o-mini", "until_percent": 80},
        ])


def test_cascade_empty_tiers():
    with pytest.raises(ValueError, match="non-empty"):
        CascadeModule(tiers=[])


def test_cascade_missing_keys():
    with pytest.raises(ValueError, match="missing"):
        CascadeModule(tiers=[{"model": "gpt-4o"}])
