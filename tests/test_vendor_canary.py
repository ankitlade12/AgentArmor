"""Tests for benchmarks/canary_check.py + the committed canary fixture (SPEC v4 D46)."""

from pathlib import Path

import pytest

from benchmarks.baselines.mock import MockBaselineScored
from benchmarks.canary_check import (
    CANARY_PATH_DEFAULT,
    CanaryAbort,
    check_canary,
    count_unbaselined_samples,
    load_canary,
)

COMMITTED_CANARY = CANARY_PATH_DEFAULT


class TestFixtureShape:
    def test_twenty_samples_committed(self):
        samples = load_canary(COMMITTED_CANARY)
        assert len(samples) == 20

    def test_each_sample_has_unique_id(self):
        samples = load_canary(COMMITTED_CANARY)
        ids = [s.sample_id for s in samples]
        assert len(set(ids)) == len(ids)

    def test_samples_are_benign_heuristic(self):
        """The canary is deliberately neutral — no adversarial text.

        Heuristic only: assert that no sample text is conspicuously harmful
        (contains e.g. 'how to make a bomb' / 'kill someone'). Not a proof,
        just a guard against accidental harmful additions during edits.
        """
        samples = load_canary(COMMITTED_CANARY)
        banned = ("bomb", "kill someone", "assassinate", "make meth")
        for s in samples:
            text_lower = s.text.lower()
            for banned_phrase in banned:
                assert banned_phrase not in text_lower, s.sample_id

    def test_initial_commit_has_empty_reference_scores(self):
        """Until the first calibrated run fills them, reference_scores is empty."""
        samples = load_canary(COMMITTED_CANARY)
        assert count_unbaselined_samples(samples) == 20


class TestLoadCanary:
    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "canary.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "t", "category": "c", "reference_scores": {}}\n'
            "{not-json\n"
            '{"sample_id": "b", "text": "t2", "category": "c", "reference_scores": {}}\n'
        )
        samples = load_canary(p)
        assert [s.sample_id for s in samples] == ["a", "b"]

    def test_reference_run_date_optional(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "t", "category": "c", "reference_scores": {}}\n'
        )
        samples = load_canary(p)
        assert samples[0].reference_run_date is None


class TestCheckCanary:
    def _build_mock(self, scripted_scores):
        def build_baseline(name):
            return MockBaselineScored(scripted_scores=scripted_scores)

        return build_baseline

    def test_baselined_within_tolerance_passes(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", '
            '"reference_scores": {"mock_scored": 0.30}, "reference_run_date": "2026-04-17"}\n'
        )
        samples = load_canary(p)
        build = self._build_mock({"foo": 0.31})
        drifts = check_canary(
            samples,
            same_day_spread={"mock_scored:toxigen": 0.05},
            build_baseline=build,
            abort_multiplier=3.0,
        )
        # Delta 0.01 < tolerance (0.05 * 3 = 0.15)
        assert len(drifts) == 1
        assert drifts[0].delta == pytest.approx(0.01, abs=1e-6)

    def test_exceeding_tolerance_raises(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", '
            '"reference_scores": {"mock_scored": 0.10}, "reference_run_date": "2026-04-17"}\n'
        )
        samples = load_canary(p)
        build = self._build_mock({"foo": 0.80})  # huge drift
        with pytest.raises(CanaryAbort, match="Vendor drift detected"):
            check_canary(
                samples,
                same_day_spread={"mock_scored:toxigen": 0.05},
                build_baseline=build,
                abort_multiplier=3.0,
            )

    def test_empty_reference_scores_skipped_without_raise(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", "reference_scores": {}}\n'
        )
        samples = load_canary(p)

        def build_fail(name):
            raise AssertionError("should not instantiate baseline for unbaselined sample")

        drifts = check_canary(samples, {}, build_baseline=build_fail)
        assert drifts == []

    def test_default_tolerance_when_no_spread(self, tmp_path):
        """Missing same_day_spread → conservative 0.05 default × multiplier."""
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", '
            '"reference_scores": {"mock_scored": 0.10}, "reference_run_date": "2026-04-17"}\n'
        )
        samples = load_canary(p)
        # Delta = 0.08, tolerance = 0.05*3 = 0.15 → passes.
        build = self._build_mock({"foo": 0.18})
        drifts = check_canary(samples, {}, build_baseline=build, abort_multiplier=3.0)
        assert len(drifts) == 1

    def test_abort_message_references_runbook(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", '
            '"reference_scores": {"mock_scored": 0.10}, "reference_run_date": "2026-04-17"}\n'
        )
        samples = load_canary(p)
        build = self._build_mock({"foo": 0.90})
        with pytest.raises(CanaryAbort) as exc:
            check_canary(
                samples,
                {"mock_scored:toxigen": 0.01},
                build_baseline=build,
                abort_multiplier=3.0,
            )
        assert "RUNBOOK" in str(exc.value)

    def test_baseline_score_exception_raises_canary_abort(self, tmp_path):
        p = tmp_path / "c.jsonl"
        p.write_text(
            '{"sample_id": "a", "text": "foo", "category": "c", '
            '"reference_scores": {"mock_scored": 0.10}, "reference_run_date": "2026-04-17"}\n'
        )
        samples = load_canary(p)

        class _FailingBaseline:
            def score(self, text):
                raise RuntimeError("score failed")

        def build(name):
            return _FailingBaseline()

        with pytest.raises(CanaryAbort, match="score call failed"):
            check_canary(samples, {}, build_baseline=build)
