"""Per-cell metric computation with bootstrap CIs (SPEC v4 D41, D44, D45).

Provides F1, MCC, balanced-accuracy with 95% CI via bootstrap resampling.
Each metric has its own degenerate-resample guard — F1/MCC/balanced-acc fail
to be defined under different conditions (D41). When >10% of resamples are
degenerate for a metric, the metric returns ``None`` ("insufficient data for
CI"); a caller may still compute the point estimate directly.

Determinism (D45):
- Bootstrap seed per cell = ``int.from_bytes(sha256(f'{baseline}|{dataset}').digest()[:8], 'big')``
- Sampling uses ``random.Random``, not ``numpy.random``; Python's RNG is
  stable across patch versions, numpy's legacy vs Generator split is not.
- Point estimate is computed on the full sample, not the bootstrap median
  (TYPE_WALKTHROUGH bug-fix).
"""

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .common import SampleVerdict

DEFAULT_BOOTSTRAP_ITERS = 5000
DEGENERATE_FRACTION_LIMIT = 0.10


@dataclass(frozen=True)
class MetricCI:
    """Point estimate + 95% CI + fraction of degenerate resamples."""

    point: float
    ci_low: float
    ci_high: float
    degenerate_fraction: float


def cell_bootstrap_seed(baseline: str, dataset: str) -> int:
    """D45: deterministic per-cell seed, byte-stable across machines."""
    h = hashlib.sha256(f"{baseline}|{dataset}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _counts(verdicts: List[SampleVerdict]) -> Tuple[int, int, int, int]:
    """Returns (tp, fp, tn, fn) on valid (non-skipped, non-errored) verdicts."""
    tp = fp = tn = fn = 0
    for v in verdicts:
        if v.skipped or v.error is not None:
            continue
        if v.label == "positive":
            if v.pred_bool:
                tp += 1
            else:
                fn += 1
        else:
            if v.pred_bool:
                fp += 1
            else:
                tn += 1
    return tp, fp, tn, fn


# ---------------------------------------------------------------------------
# Per-metric point estimates and degenerate conditions (D41)
# ---------------------------------------------------------------------------


def f1_from_counts(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    """F1 undefined if TP+FP==0 or TP+FN==0 (no predictions or no positives)."""
    if (tp + fp) == 0 or (tp + fn) == 0:
        return None
    prec = tp / (tp + fp)
    rec = tp / (tp + fn)
    if (prec + rec) == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def mcc_from_counts(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    """MCC undefined if any of the four marginal sums is 0."""
    if (tp + fp) == 0 or (tp + fn) == 0 or (tn + fp) == 0 or (tn + fn) == 0:
        return None
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / denom


def balanced_accuracy_from_counts(
    tp: int, fp: int, tn: int, fn: int
) -> Optional[float]:
    """Balanced-acc undefined if TP+FN==0 or TN+FP==0 (missing either class)."""
    if (tp + fn) == 0 or (tn + fp) == 0:
        return None
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    return (sensitivity + specificity) / 2


def precision_from_counts(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    if (tp + fp) == 0:
        return None
    return tp / (tp + fp)


def recall_from_counts(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    if (tp + fn) == 0:
        return None
    return tp / (tp + fn)


def fpr_from_counts(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    if (fp + tn) == 0:
        return None
    return fp / (fp + tn)


# ---------------------------------------------------------------------------
# Bootstrap engine (D44, D45)
# ---------------------------------------------------------------------------


MetricFn = Callable[[int, int, int, int], Optional[float]]


def _bootstrap_metric(
    verdicts: List[SampleVerdict],
    metric_fn: MetricFn,
    iters: int,
    seed: int,
) -> Optional[MetricCI]:
    """Generic bootstrap CI for a counts-based metric.

    Returns ``None`` if > ``DEGENERATE_FRACTION_LIMIT`` of resamples are
    degenerate (metric undefined) — the caller flags the cell as "insufficient
    data for CI."
    """
    valid = [v for v in verdicts if not v.skipped and v.error is None]
    if not valid:
        return None

    # Point estimate on the full (non-resampled) sample.
    tp, fp, tn, fn = _counts(valid)
    point = metric_fn(tp, fp, tn, fn)
    if point is None:
        # Even the full sample is degenerate for this metric.
        return None

    rng = random.Random(seed)
    n = len(valid)
    samples: List[float] = []
    degenerate = 0
    for _ in range(iters):
        resample = [valid[rng.randrange(n)] for _ in range(n)]
        rtp, rfp, rtn, rfn = _counts(resample)
        rm = metric_fn(rtp, rfp, rtn, rfn)
        if rm is None:
            degenerate += 1
            continue
        samples.append(rm)
    degenerate_fraction = degenerate / iters
    if degenerate_fraction > DEGENERATE_FRACTION_LIMIT or not samples:
        return None
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[int(0.975 * len(samples))]
    return MetricCI(
        point=point,
        ci_low=lo,
        ci_high=hi,
        degenerate_fraction=degenerate_fraction,
    )


def compute_f1_ci(
    verdicts: List[SampleVerdict],
    iters: int = DEFAULT_BOOTSTRAP_ITERS,
    seed: Optional[int] = None,
) -> Optional[MetricCI]:
    """1000-then-5000-iter bootstrap 95% CI on F1. None if >10% resamples degenerate."""
    if seed is None:
        raise ValueError("seed is required for deterministic bootstrap (SPEC v4 D45)")
    return _bootstrap_metric(verdicts, f1_from_counts, iters, seed)


def compute_mcc_ci(
    verdicts: List[SampleVerdict],
    iters: int = DEFAULT_BOOTSTRAP_ITERS,
    seed: Optional[int] = None,
) -> Optional[MetricCI]:
    if seed is None:
        raise ValueError("seed is required for deterministic bootstrap (SPEC v4 D45)")
    return _bootstrap_metric(verdicts, mcc_from_counts, iters, seed)


def compute_balanced_accuracy_ci(
    verdicts: List[SampleVerdict],
    iters: int = DEFAULT_BOOTSTRAP_ITERS,
    seed: Optional[int] = None,
) -> Optional[MetricCI]:
    if seed is None:
        raise ValueError("seed is required for deterministic bootstrap (SPEC v4 D45)")
    return _bootstrap_metric(verdicts, balanced_accuracy_from_counts, iters, seed)
