"""Tests for the Multi-Agent Echo-Chamber Detector."""
import pytest

from agentarmor.modules.echo_chamber import (
    EchoChamberModule, EchoChamberDetected, Claim, EchoChamberAlert,
)


# ---------------------------------------------------------------------------
# Claim hashing
# ---------------------------------------------------------------------------

class TestClaimHashing:
    def test_identical_claims_same_hash(self):
        c1 = Claim("The capital of France is Paris.", "agent_a")
        c2 = Claim("The capital of France is Paris.", "agent_b")
        assert c1.hash == c2.hash

    def test_normalized_claims_same_hash(self):
        c1 = Claim("The capital of France is Paris.", "a")
        c2 = Claim("  the  capital of france  is  paris.  ", "b")
        assert c1.hash == c2.hash

    def test_different_claims_different_hash(self):
        c1 = Claim("The capital of France is Paris.", "a")
        c2 = Claim("The capital of Germany is Berlin.", "a")
        assert c1.hash != c2.hash


# ---------------------------------------------------------------------------
# Echo detection
# ---------------------------------------------------------------------------

class TestEchoDetection:
    def test_same_agent_no_echo(self):
        mod = EchoChamberModule()
        mod.register_claims("agent_a", "The quantum processor runs at 500 qubits per second.")
        alerts = mod.register_claims("agent_a", "The quantum processor runs at 500 qubits per second.")
        assert len(alerts) == 0

    def test_different_agent_triggers_echo(self):
        mod = EchoChamberModule(on_echo="warn")
        mod.register_claims("agent_a", "The quantum processor runs at 500 qubits per second.")
        alerts = mod.register_claims("agent_b", "The quantum processor runs at 500 qubits per second.")
        assert len(alerts) == 1
        assert alerts[0].origin_agent == "agent_a"
        assert alerts[0].echo_agent == "agent_b"

    def test_three_agent_chain(self):
        mod = EchoChamberModule(on_echo="warn")
        mod.register_claims("agent_a", "The new treatment cures cancer in 99 percent of cases.")
        mod.register_claims("agent_b", "The new treatment cures cancer in 99 percent of cases.")
        alerts = mod.register_claims("agent_c", "The new treatment cures cancer in 99 percent of cases.")
        # agent_c echoing a claim already seen by a and b
        assert len(alerts) == 1
        assert alerts[0].echo_agent == "agent_c"

    def test_block_mode_raises(self):
        mod = EchoChamberModule(on_echo="block")
        mod.register_claims("agent_a", "The company reported 500 billion dollars in revenue last quarter.")
        with pytest.raises(EchoChamberDetected, match="Circular confirmation"):
            mod.register_claims("agent_b", "The company reported 500 billion dollars in revenue last quarter.")

    def test_short_sentences_ignored(self):
        mod = EchoChamberModule(min_claim_length=30, on_echo="warn")
        mod.register_claims("agent_a", "Yes.")
        alerts = mod.register_claims("agent_b", "Yes.")
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Grounding exemption
# ---------------------------------------------------------------------------

class TestGroundingExemption:
    def test_grounded_claim_not_flagged(self):
        source = "The capital of France is Paris. France has 67 million people."
        mod = EchoChamberModule(
            grounding_sources=[source],
            on_echo="block",
        )
        mod.register_claims("agent_a", "The capital of France is Paris and it has 67 million people.")
        # Should NOT raise because the claim is grounded
        alerts = mod.register_claims("agent_b", "The capital of France is Paris and it has 67 million people.")
        assert len(alerts) == 0

    def test_ungrounded_claim_flagged(self):
        mod = EchoChamberModule(
            grounding_sources=["Unrelated source about cooking recipes."],
            on_echo="warn",
        )
        mod.register_claims("agent_a", "The secret alien base is located under Antarctica according to sources.")
        alerts = mod.register_claims("agent_b", "The secret alien base is located under Antarctica according to sources.")
        assert len(alerts) == 1

    def test_runtime_grounding_source_before_registration(self):
        """Grounding sources added before claims are registered take effect."""
        mod = EchoChamberModule(on_echo="warn")
        mod.add_grounding_source(
            "Python was created by Guido van Rossum in 1991 as a successor to ABC."
        )
        mod.register_claims(
            "agent_a",
            "Python was created by Guido van Rossum in 1991 as successor to ABC.",
        )
        alerts = mod.register_claims(
            "agent_b",
            "Python was created by Guido van Rossum in 1991 as successor to ABC.",
        )
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Ungrounded claims listing
# ---------------------------------------------------------------------------

class TestUngroundedClaims:
    def test_lists_ungrounded(self):
        mod = EchoChamberModule()
        mod.register_claims("agent_a", "The moon is made of green cheese according to recent studies.")
        claims = mod.get_ungrounded_claims()
        assert len(claims) == 1
        assert claims[0]["origin"] == "agent_a"

    def test_grounded_excluded(self):
        mod = EchoChamberModule(
            grounding_sources=["The moon orbits Earth at an average distance of 384400 km."],
        )
        mod.register_claims("a", "The moon orbits Earth at average distance of 384400 kilometers.")
        claims = mod.get_ungrounded_claims()
        assert len(claims) == 0


# ---------------------------------------------------------------------------
# Max claims eviction
# ---------------------------------------------------------------------------

class TestEviction:
    def test_evicts_oldest(self):
        mod = EchoChamberModule(max_claims=3, min_claim_length=5)
        mod.register_claims("a", "First claim about something interesting here.")
        mod.register_claims("a", "Second claim about another interesting topic here.")
        mod.register_claims("a", "Third claim about yet another topic here.")
        mod.register_claims("a", "Fourth claim which should evict the first one.")
        assert len(mod._claims) == 3


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_structure(self):
        mod = EchoChamberModule()
        r = mod.report()
        assert "stats" in r
        assert "active_claims" in r
        assert "alerts" in r

    def test_report_after_echo(self):
        mod = EchoChamberModule(on_echo="warn")
        mod.register_claims("a", "Hallucinated fact about quantum computing reaching singularity in 2025.")
        mod.register_claims("b", "Hallucinated fact about quantum computing reaching singularity in 2025.")
        r = mod.report()
        assert r["stats"]["echoes_detected"] == 1
        assert len(r["alerts"]) == 1


# ---------------------------------------------------------------------------
# Alert structure
# ---------------------------------------------------------------------------

class TestAlertStructure:
    def test_alert_to_dict(self):
        claim = Claim("Test claim about something.", "agent_a")
        alert = EchoChamberAlert(claim, "agent_b", ["agent_a", "agent_b"])
        d = alert.to_dict()
        assert d["origin_agent"] == "agent_a"
        assert d["echo_agent"] == "agent_b"
        assert "agent_a" in d["path"]
