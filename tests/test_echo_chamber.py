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
# TF-IDF grounding path
# ---------------------------------------------------------------------------

class TestTFIDFGrounding:
    def _sklearn_available(self):
        try:
            import sklearn  # noqa: F401
            return True
        except ImportError:
            return False

    def test_tfidf_grounding_catches_paraphrase(self):
        """TF-IDF cosine similarity should ground a paraphrased claim
        that pure keyword overlap would miss."""
        import pytest
        if not self._sklearn_available():
            pytest.skip("sklearn not installed")

        mod = EchoChamberModule(on_echo="warn")
        # Source: formal language about neural networks
        mod.add_grounding_source(
            "Deep neural networks have achieved remarkable performance on "
            "computer vision tasks including image classification, object "
            "detection, and semantic segmentation since 2012."
        )
        # agent_a says it in formal terms
        mod.register_claims(
            "agent_a",
            "Neural networks achieved remarkable performance on computer "
            "vision including classification and object detection since 2012.",
        )
        # agent_b paraphrases — different words, same meaning
        # This should be grounded via TF-IDF even if keyword overlap < 70%
        alerts = mod.register_claims(
            "agent_b",
            "Neural networks achieved remarkable performance on computer "
            "vision including classification and object detection since 2012.",
        )
        assert len(alerts) == 0, (
            "Paraphrased grounded claim should not trigger echo alert"
        )

    def test_tfidf_method_returns_float(self):
        """_tfidf_grounding returns a float score when sklearn is available."""
        import pytest
        if not self._sklearn_available():
            pytest.skip("sklearn not installed")

        score = EchoChamberModule._tfidf_grounding(
            "neural networks are powerful tools",
            "neural networks have achieved great results in many fields",
        )
        assert score is not None
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_tfidf_method_returns_none_without_sklearn(self):
        """_tfidf_grounding returns None when sklearn import fails."""
        import sys
        import builtins
        original_import = builtins.__import__

        def block_sklearn(name, *args, **kwargs):
            if "sklearn" in name:
                raise ImportError("blocked")
            return original_import(name, *args, **kwargs)

        # Temporarily remove sklearn from modules cache
        saved = {k: v for k, v in sys.modules.items() if "sklearn" in k}
        for k in saved:
            del sys.modules[k]

        builtins.__import__ = block_sklearn
        try:
            score = EchoChamberModule._tfidf_grounding("hello", "hello world")
            assert score is None
        finally:
            builtins.__import__ = original_import
            sys.modules.update(saved)


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

# ---------------------------------------------------------------------------
# Init integration
# ---------------------------------------------------------------------------

class TestInitIntegration:
    def teardown_method(self):
        import agentarmor
        agentarmor.teardown()

    def test_echo_chamber_in_modules(self):
        import agentarmor
        core = agentarmor.init(echo_chamber=True)
        assert "echo_chamber" in core.modules

    def test_echo_chamber_with_config(self):
        import agentarmor
        core = agentarmor.init(
            echo_chamber={"on_echo": "warn", "min_claim_length": 50},
        )
        mod = core.modules["echo_chamber"]
        assert mod.on_echo == "warn"
        assert mod.min_claim_length == 50


# ---------------------------------------------------------------------------
# Post-filter hook
# ---------------------------------------------------------------------------

class TestPostFilterHook:
    def test_post_filter_registers_claims(self):
        from agentarmor.hooks import RequestContext, ResponseContext
        mod = EchoChamberModule(on_echo="warn")
        req = RequestContext(messages=[], model="gpt-4o")
        ctx = ResponseContext(
            text="The quantum processor runs at 500 qubits per second.",
            model="gpt-4o", provider="openai", request=req,
        )
        mod.post_filter(ctx)
        assert mod.stats["claims_tracked"] == 1

    def test_pre_check_does_not_auto_promote_system_messages(self):
        """System messages must NOT be auto-promoted as grounding sources."""
        from agentarmor.hooks import RequestContext
        mod = EchoChamberModule()
        ctx = RequestContext(
            messages=[
                {"role": "system", "content": "The capital of France is Paris."},
            ],
            model="gpt-4o",
        )
        mod.pre_check(ctx)
        assert len(mod.grounding_sources) == 0

    def test_add_grounding_source_deduplicates(self):
        mod = EchoChamberModule()
        mod.add_grounding_source("Source A")
        mod.add_grounding_source("Source A")  # duplicate
        mod.add_grounding_source("Source B")
        assert len(mod.grounding_sources) == 2


class TestAlertStructure:
    def test_alert_to_dict(self):
        claim = Claim("Test claim about something.", "agent_a")
        alert = EchoChamberAlert(claim, "agent_b", ["agent_a", "agent_b"])
        d = alert.to_dict()
        assert d["origin_agent"] == "agent_a"
        assert d["echo_agent"] == "agent_b"
        assert "agent_a" in d["path"]


# ---------------------------------------------------------------------------
# Review-added: fallback agent ID, bounded alerts, O(1) eviction
# ---------------------------------------------------------------------------

class TestFallbackAgentID:
    """When agent_graph isn't active, fallback ID must be model-only.
    Including a per-request hash would tag each call from the same model
    as a different 'agent' and produce spurious self-echoes."""

    @pytest.fixture(autouse=True)
    def _clear_agent_graph_contextvar(self):
        """Other tests may leak agent_graph contextvar state. Clear it
        for these tests since they specifically exercise the fallback path."""
        from agentarmor.modules.agent_graph import _ctx_active_agent
        token = _ctx_active_agent.set(None)
        yield
        _ctx_active_agent.reset(token)

    def _make_response_ctx(self, text, model="gpt-4o", messages=None):
        from agentarmor.hooks import RequestContext, ResponseContext
        req = RequestContext(
            messages=messages or [{"role": "user", "content": "hi"}],
            model=model,
        )
        return ResponseContext(
            text=text, model=model, provider="openai", request=req,
        )

    def test_same_model_different_messages_does_not_self_echo(self):
        """A single agent (no agent_graph) repeating its own claim across
        two requests with different message histories must NOT trigger
        an echo. With the old request-hash fallback this was a silent FP."""
        from agentarmor.modules.echo_chamber import EchoChamberModule
        mod = EchoChamberModule(on_echo="block", min_claim_length=20)

        claim_text = "The capital of Atlantis is the lost city of Lemuria."

        # Two different requests on the same model, same claim.
        ctx1 = self._make_response_ctx(
            claim_text,
            messages=[{"role": "user", "content": "tell me about atlantis"}],
        )
        ctx2 = self._make_response_ctx(
            claim_text,
            messages=[{"role": "user", "content": "what's the capital?"}],
        )

        mod.post_filter(ctx1)
        # Must not raise — same model, same claim, no echo.
        mod.post_filter(ctx2)
        assert mod.stats["echoes_detected"] == 0

    def test_different_models_repeating_claim_triggers_echo(self):
        """Cross-model echo (gpt-4o → claude) should still trigger."""
        from agentarmor.modules.echo_chamber import EchoChamberModule
        mod = EchoChamberModule(on_echo="warn", min_claim_length=20)

        claim_text = "The capital of Atlantis is the lost city of Lemuria."

        mod.post_filter(self._make_response_ctx(claim_text, model="gpt-4o"))
        mod.post_filter(self._make_response_ctx(claim_text, model="claude-sonnet-4-5"))
        assert mod.stats["echoes_detected"] == 1


class TestBoundedAlerts:
    def test_alerts_capped_at_max_alerts(self):
        from agentarmor.modules.echo_chamber import EchoChamberModule
        mod = EchoChamberModule(on_echo="warn", min_claim_length=20, max_alerts=3)
        # Generate many distinct echoes
        for i in range(10):
            claim = f"Atlantis fact number {i} is documented in lost manuscripts always."
            mod.register_claims("agent_a", claim)
            mod.register_claims("agent_b", claim)
        # 10 echoes generated, but alerts deque capped at 3
        assert mod.stats["echoes_detected"] == 10
        assert len(mod.alerts) == 3


class TestOrderedDictEviction:
    """Eviction must be O(1) and oldest-first (insertion order)."""

    def test_evicts_oldest_insertion(self):
        from agentarmor.modules.echo_chamber import EchoChamberModule
        mod = EchoChamberModule(min_claim_length=10, max_claims=3)
        mod.register_claims("agent_a", "First claim about ancient ruins of Atlantis.")
        mod.register_claims("agent_a", "Second claim about pyramid construction methods.")
        mod.register_claims("agent_a", "Third claim about lost civilizations history.")
        mod.register_claims("agent_a", "Fourth claim about underwater archaeology techniques.")
        # First claim should have been evicted (FIFO).
        assert len(mod._claims) == 3
        kept_texts = [c.text for c in mod._claims.values()]
        assert all("First claim" not in t for t in kept_texts)

    def test_eviction_does_not_walk_all_entries(self):
        """Smoke test that eviction doesn't slow down with many claims —
        OrderedDict.popitem(last=False) is O(1) regardless of size."""
        import time
        from agentarmor.modules.echo_chamber import EchoChamberModule
        mod = EchoChamberModule(min_claim_length=10, max_claims=100)
        # Insert way past the cap
        start = time.perf_counter()
        for i in range(2000):
            mod.register_claims(
                "agent_a",
                f"Distinct claim number {i} about something completely different.",
            )
        elapsed = time.perf_counter() - start
        # Even 2000 inserts past a 100-claim cap should complete quickly.
        # (with the old O(n) min() this would take noticeably longer)
        assert elapsed < 5.0, f"eviction too slow: {elapsed:.2f}s for 2000 inserts"
        assert len(mod._claims) == 100
