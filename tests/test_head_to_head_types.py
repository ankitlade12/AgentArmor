"""Tests for head-to-head types (SPEC v4 D6, D7, D42, D49)."""

import pytest

from benchmarks.common import (
    HeadToHeadResult,
    SampleVerdict,
    compute_adapter_version,
    compute_sample_id,
)


class TestSampleVerdict:
    def test_construct_minimal(self):
        v = SampleVerdict(
            sample_id="abc123",
            adapter_name="xstest",
            label="positive",
            pred_bool=True,
            pred_score=0.85,
            latency_ms=12.3,
        )
        assert v.skipped is False
        assert v.skip_reason is None
        assert v.error is None
        assert v.raw_response is None  # D49 — always None in committed artifacts

    def test_skipped_sample(self):
        v = SampleVerdict(
            sample_id="def456",
            adapter_name="halueval",
            label="positive",
            pred_bool=False,
            pred_score=None,
            latency_ms=0.0,
            skipped=True,
            skip_reason="no source_context",
        )
        assert v.skipped is True
        assert v.skip_reason == "no source_context"

    def test_errored_sample(self):
        v = SampleVerdict(
            sample_id="err789",
            adapter_name="toxigen",
            label="negative",
            pred_bool=False,
            pred_score=None,
            latency_ms=30000.0,
            error="TimeoutError: mock timeout",
        )
        assert v.error == "TimeoutError: mock timeout"


class TestHeadToHeadResult:
    def _mk(self, label: str, pred_bool: bool, **kw) -> SampleVerdict:
        return SampleVerdict(
            sample_id="s" + label[0] + str(pred_bool),
            adapter_name="t",
            label=label,
            pred_bool=pred_bool,
            pred_score=1.0 if pred_bool else 0.0,
            latency_ms=1.0,
            **kw,
        )

    def test_counts_derived_from_samples(self):
        r = HeadToHeadResult(
            baseline="mock",
            dataset="toy",
            samples=[
                self._mk("positive", True),
                self._mk("positive", True),
                self._mk("positive", False),
                self._mk("negative", False),
                self._mk("negative", False),
                self._mk("negative", True),
            ],
        )
        assert r.total == 6
        assert r.true_positives == 2
        assert r.false_negatives == 1
        assert r.true_negatives == 2
        assert r.false_positives == 1

    def test_skipped_excluded_from_counts(self):
        r = HeadToHeadResult(
            baseline="mock",
            dataset="toy",
            samples=[
                self._mk("positive", True),
                self._mk("positive", False, skipped=True, skip_reason="no source"),
                self._mk("negative", False),
            ],
        )
        assert r.total == 2
        assert r.true_positives == 1
        assert r.false_negatives == 0
        assert r.true_negatives == 1

    def test_errored_excluded_from_counts(self):
        r = HeadToHeadResult(
            baseline="mock",
            dataset="toy",
            samples=[
                self._mk("positive", True),
                self._mk("negative", False, error="ConnectionError"),
                self._mk("negative", False),
            ],
        )
        assert r.total == 2

    def test_empty_result(self):
        r = HeadToHeadResult(baseline="mock", dataset="toy")
        assert r.total == 0
        assert r.true_positives == 0
        assert r.false_positives == 0


class TestSampleId:
    def test_deterministic(self):
        a = compute_sample_id("xstest", "a3f2b1c8", "same text")
        b = compute_sample_id("xstest", "a3f2b1c8", "same text")
        assert a == b

    def test_sixteen_chars(self):
        sid = compute_sample_id("xstest", "a3f2b1c8", "hello")
        assert len(sid) == 16
        int(sid, 16)  # valid hex

    def test_adapter_name_is_part_of_hash(self):
        a = compute_sample_id("xstest", "a3f2b1c8", "same text")
        b = compute_sample_id("toxigen", "a3f2b1c8", "same text")
        assert a != b

    def test_adapter_version_is_part_of_hash(self):
        a = compute_sample_id("xstest", "v1", "same text")
        b = compute_sample_id("xstest", "v2", "same text")
        assert a != b

    def test_text_is_part_of_hash(self):
        a = compute_sample_id("xstest", "v1", "text one")
        b = compute_sample_id("xstest", "v1", "text two")
        assert a != b

    def test_handles_unicode(self):
        sid = compute_sample_id("xstest", "v1", "ünïcödé 日本語 🔥")
        assert len(sid) == 16


class TestAdapterVersion:
    def test_returns_eight_char_hex(self):
        from benchmarks.adapters import xstest
        v = compute_adapter_version(xstest)
        assert len(v) == 8
        int(v, 16)

    def test_different_adapters_give_different_versions(self):
        from benchmarks.adapters import xstest, toxigen
        assert compute_adapter_version(xstest) != compute_adapter_version(toxigen)

    def test_deterministic(self):
        from benchmarks.adapters import xstest
        a = compute_adapter_version(xstest)
        b = compute_adapter_version(xstest)
        assert a == b


class TestScoreEmittingFlag:
    def test_base_has_default_true(self):
        from benchmarks.baselines.base import BaselineChecker
        assert BaselineChecker.score_emitting is True

    def test_legacy_bridge_sets_false(self):
        import warnings
        from benchmarks.baselines.base import BaselineChecker

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            class LegacyShape(BaselineChecker):
                name = "legacy_score_emitting_test"

                def check(self, text: str) -> bool:
                    return False

        assert LegacyShape.score_emitting is False
