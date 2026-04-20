"""Tests for benchmarks/metrics.py (SPEC v4 D41, D44, D45)."""

import math

import pytest

from benchmarks.common import SampleVerdict
from benchmarks.metrics import (
    DEFAULT_BOOTSTRAP_ITERS,
    balanced_accuracy_from_counts,
    cell_bootstrap_seed,
    compute_balanced_accuracy_ci,
    compute_f1_ci,
    compute_mcc_ci,
    f1_from_counts,
    fpr_from_counts,
    mcc_from_counts,
    precision_from_counts,
    recall_from_counts,
)


def _v(label: str, pred_bool: bool, **kw) -> SampleVerdict:
    return SampleVerdict(
        sample_id=f"{label[0]}{pred_bool}{kw.get('tag','')}",
        adapter_name="test",
        label=label,
        pred_bool=pred_bool,
        pred_score=1.0 if pred_bool else 0.0,
        latency_ms=1.0,
        **{k: v for k, v in kw.items() if k != "tag"},
    )


def _mk_balanced(n: int, tp_rate: float = 1.0, tn_rate: float = 1.0):
    """Balanced positive/negative set with configurable per-class accuracy."""
    out = []
    for i in range(n // 2):
        out.append(_v("positive", i < int(n // 2 * tp_rate), tag=f"p{i}"))
    for i in range(n // 2):
        out.append(_v("negative", not (i < int(n // 2 * tn_rate)), tag=f"n{i}"))
    return out


# ---------------------------------------------------------------------------
# Per-metric point-estimate tests (D41)
# ---------------------------------------------------------------------------


class TestF1FromCounts:
    def test_perfect_classifier(self):
        assert f1_from_counts(50, 0, 50, 0) == 1.0

    def test_zero_positives_predicted_returns_none(self):
        """TP+FP==0 → undefined."""
        assert f1_from_counts(0, 0, 50, 50) is None

    def test_zero_positives_in_ground_truth_returns_none(self):
        """TP+FN==0 → undefined."""
        assert f1_from_counts(0, 10, 50, 0) is None

    def test_zero_f1_is_valid_not_none(self):
        """Classifier predicts all wrong — F1=0 is defined, not None."""
        result = f1_from_counts(0, 10, 0, 10)
        assert result == 0.0


class TestMccFromCounts:
    def test_perfect(self):
        assert mcc_from_counts(50, 0, 50, 0) == 1.0

    @pytest.mark.parametrize(
        "counts",
        [
            (0, 0, 50, 50),  # TP+FP == 0
            (0, 10, 50, 0),  # TP+FN == 0
            (10, 0, 0, 50),  # TN+FP == 0
            (10, 50, 0, 0),  # TN+FN == 0
        ],
    )
    def test_degenerate_returns_none(self, counts):
        assert mcc_from_counts(*counts) is None

    def test_worst_classifier(self):
        """All wrong predictions → MCC = -1."""
        assert mcc_from_counts(0, 50, 0, 50) == -1.0


class TestBalancedAccuracy:
    def test_perfect(self):
        assert balanced_accuracy_from_counts(50, 0, 50, 0) == 1.0

    def test_missing_positives_undefined(self):
        assert balanced_accuracy_from_counts(0, 0, 50, 0) is None

    def test_missing_negatives_undefined(self):
        assert balanced_accuracy_from_counts(50, 0, 0, 0) is None

    def test_random_classifier(self):
        """50% per class → 0.5."""
        result = balanced_accuracy_from_counts(25, 25, 25, 25)
        assert result == 0.5


class TestPrecisionRecallFpr:
    def test_precision(self):
        assert precision_from_counts(30, 10, 50, 10) == 0.75
        assert precision_from_counts(0, 0, 50, 10) is None

    def test_recall(self):
        assert recall_from_counts(30, 10, 50, 10) == 0.75
        assert recall_from_counts(0, 10, 50, 0) is None

    def test_fpr(self):
        assert fpr_from_counts(30, 10, 40, 10) == 0.2
        assert fpr_from_counts(30, 0, 0, 10) is None


# ---------------------------------------------------------------------------
# Bootstrap determinism (D45) and CI behavior (D44)
# ---------------------------------------------------------------------------


class TestCellBootstrapSeed:
    def test_deterministic(self):
        assert cell_bootstrap_seed("llamaguard", "xstest") == cell_bootstrap_seed(
            "llamaguard", "xstest"
        )

    def test_different_cells_give_different_seeds(self):
        a = cell_bootstrap_seed("llamaguard", "xstest")
        b = cell_bootstrap_seed("perspective", "xstest")
        assert a != b

    def test_returns_int(self):
        assert isinstance(cell_bootstrap_seed("a", "b"), int)


class TestComputeF1CI:
    def test_requires_seed(self):
        verdicts = _mk_balanced(100)
        with pytest.raises(ValueError, match="seed is required"):
            compute_f1_ci(verdicts, iters=50)

    def test_deterministic_across_calls(self):
        verdicts = _mk_balanced(50, tp_rate=0.8, tn_rate=0.9)
        a = compute_f1_ci(verdicts, iters=200, seed=42)
        b = compute_f1_ci(verdicts, iters=200, seed=42)
        assert a == b

    def test_point_estimate_invariant_to_seed(self):
        """Point estimate is computed on the full sample — seed must not affect it."""
        verdicts = _mk_balanced(50, tp_rate=0.8, tn_rate=0.9)
        a = compute_f1_ci(verdicts, iters=200, seed=42)
        b = compute_f1_ci(verdicts, iters=200, seed=43)
        assert a.point == b.point

    def test_point_estimate_from_full_sample(self):
        """Point estimate must not be the bootstrap-resample median (walkthrough fix)."""
        verdicts = _mk_balanced(100, tp_rate=1.0, tn_rate=1.0)  # perfect
        result = compute_f1_ci(verdicts, iters=200, seed=1)
        assert result.point == 1.0

    def test_all_degenerate_returns_none(self):
        """All-negatives label set → F1 undefined on every resample."""
        verdicts = [_v("negative", False) for _ in range(50)]
        result = compute_f1_ci(verdicts, iters=200, seed=1)
        assert result is None

    def test_skipped_and_errored_excluded(self):
        verdicts = [
            _v("positive", True),
            _v("positive", True),
            _v("negative", False),
            _v("negative", False, skipped=True, skip_reason="no source"),
            _v("positive", False, error="TimeoutError"),
        ]
        result = compute_f1_ci(verdicts, iters=100, seed=1)
        assert result is not None
        # Effective set = 2 TP, 1 TN → F1 = 1.0 (perfect)
        assert result.point == 1.0


class TestComputeMCCCI:
    def test_perfect_classifier(self):
        verdicts = _mk_balanced(100)
        result = compute_mcc_ci(verdicts, iters=200, seed=42)
        assert result.point == 1.0

    def test_deterministic(self):
        verdicts = _mk_balanced(80, tp_rate=0.8, tn_rate=0.9)
        a = compute_mcc_ci(verdicts, iters=200, seed=42)
        b = compute_mcc_ci(verdicts, iters=200, seed=42)
        assert a == b


class TestComputeBalancedAccuracyCI:
    def test_perfect(self):
        verdicts = _mk_balanced(100)
        result = compute_balanced_accuracy_ci(verdicts, iters=200, seed=1)
        assert result.point == 1.0

    def test_deterministic(self):
        verdicts = _mk_balanced(80, tp_rate=0.8, tn_rate=0.9)
        a = compute_balanced_accuracy_ci(verdicts, iters=200, seed=1)
        b = compute_balanced_accuracy_ci(verdicts, iters=200, seed=1)
        assert a == b
