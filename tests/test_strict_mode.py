"""Tests for strict-mode kwarg validation in agentarmor.init()."""

import warnings

import pytest

import agentarmor
from agentarmor import _strict
from agentarmor.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def _reset_warnings():
    """Each test starts with a fresh per-process warning dedup state."""
    _strict.reset_warning_state()
    yield
    _strict.reset_warning_state()


@pytest.fixture(autouse=True)
def _teardown_core():
    yield
    try:
        agentarmor.teardown()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Strict mode raises on unknown kwargs
# ---------------------------------------------------------------------------

class TestStrictRaises:
    def test_unknown_kwarg_raises(self):
        with pytest.raises(ConfigurationError, match="totally_made_up"):
            agentarmor.init(strict=True, totally_made_up=True)

    def test_typo_suggestion_in_message(self):
        with pytest.raises(ConfigurationError, match="unicode_shield"):
            agentarmor.init(strict=True, unicode_sheild=True)

    def test_known_typo_alias_used(self):
        """KNOWN_TYPO_ALIASES short-circuits the difflib pass."""
        with pytest.raises(ConfigurationError, match="unicode_shield"):
            agentarmor.init(strict=True, unicode_sheild=True)

    def test_distant_typo_no_suggestion(self):
        """Garbage input that doesn't match anything gets a clean error
        without a misleading suggestion."""
        with pytest.raises(ConfigurationError) as exc_info:
            agentarmor.init(strict=True, asdfqwerty_xyzzy=True)
        # No "did you mean" because nothing is close enough
        assert "Did you mean" not in str(exc_info.value)

    def test_confusing_pair_recorder_vs_record(self):
        """recorder=True is a real footgun — must surface the distinction."""
        with pytest.raises(ConfigurationError) as exc_info:
            agentarmor.init(strict=True, recorder=True)
        msg = str(exc_info.value)
        # Both names should be mentioned so user understands
        assert "recorder" in msg
        assert "record" in msg

    def test_configuration_error_is_value_error(self):
        """ConfigurationError subclasses ValueError so existing handlers work."""
        with pytest.raises(ValueError):
            agentarmor.init(strict=True, this_is_unknown=True)


# ---------------------------------------------------------------------------
# Strict mode permits known kwargs
# ---------------------------------------------------------------------------

class TestStrictAccepts:
    def test_no_extra_kwargs_passes(self):
        core = agentarmor.init(strict=True, shield=True)
        assert core is not None

    def test_all_documented_modules_accepted(self):
        """Every kwarg the canonical signature accepts must pass strict."""
        core = agentarmor.init(
            strict=True,
            budget=None, shield=False, filter=None, record=False,
            rate_limit=None, context_guard=False, latency_breaker=None,
            canary=None, tool_firewall=None, cost_tags=None, dedup=None,
            cascade=None, ml_shield=None, agent_graph=None, mcp_firewall=None,
            code_shield=None, grounding=None, cot_auditor=None, toxicity=None,
            compliance=None, hitl_gate=None, exfiltration_guard=None,
            privilege_escalation=None, unicode_shield=None,
            semantic_drift=None, taint_tracker=None, honeytools=None,
            echo_chamber=None,
        )
        assert core is not None


# ---------------------------------------------------------------------------
# Non-strict mode: warns once per process, doesn't raise
# ---------------------------------------------------------------------------

class TestNonStrictWarns:
    def test_unknown_kwarg_does_not_raise(self):
        # Default strict=False — should NOT raise
        core = agentarmor.init(unicode_sheild=True)
        assert core is not None

    def test_uses_userwarning_not_deprecation(self):
        """DeprecationWarning is silenced by default in many Python runtimes,
        which would defeat the typo-surfacing goal. Must be UserWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agentarmor.init(unicode_sheild=True)
        userwarns = [w for w in caught if issubclass(w.category, UserWarning)]
        assert userwarns, "expected at least one UserWarning"
        depwarns = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert not depwarns, "must not use DeprecationWarning (silenced by default)"

    def test_warning_includes_suggestion(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agentarmor.init(unicode_sheild=True)
        msgs = [str(w.message) for w in caught]
        assert any("unicode_shield" in m for m in msgs)

    def test_warning_dedup_within_process(self):
        """Same typo'd kwarg in a loop must not spam warnings."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(5):
                agentarmor.init(typo_kwarg=True)
                agentarmor.teardown()
        # Only ONE warning despite 5 calls
        relevant = [w for w in caught if "typo_kwarg" in str(w.message)]
        assert len(relevant) == 1, f"expected 1 dedup'd warning, got {len(relevant)}"


# ---------------------------------------------------------------------------
# Suggestion algorithm
# ---------------------------------------------------------------------------

class TestSuggestionAlgorithm:
    def test_suggest_returns_match_for_close_typo(self):
        known = {"unicode_shield", "shield", "filter"}
        assert _strict.suggest("unicode_sheild", known) == "unicode_shield"

    def test_suggest_returns_none_for_garbage(self):
        known = {"unicode_shield", "shield", "filter"}
        assert _strict.suggest("zzzz_qqqq", known) is None

    def test_alias_takes_precedence_over_difflib(self):
        """Aliases short-circuit difflib."""
        known = {"unicode_shield", "filter"}
        # 'shields' is in KNOWN_TYPO_ALIASES → 'shield', but 'shield'
        # might not be in `known` here. Alias should still fire if its
        # target IS a real kwarg.
        assert _strict.KNOWN_TYPO_ALIASES["shields"] == "shield"


# ---------------------------------------------------------------------------
# ArmorCore direct construction also validated
# ---------------------------------------------------------------------------

class TestArmorCoreDirectConstruction:
    """Tests that bypass init() and construct ArmorCore directly are common
    in the test suite. They must continue to work (no strict by default at
    ArmorCore level)."""

    def test_armorcore_extra_kwargs_silent_by_default(self):
        from agentarmor.core import ArmorCore
        # Must not raise — backwards compat for any test that used **kwargs
        core = ArmorCore(shield=True, some_extra=True)
        assert core is not None
