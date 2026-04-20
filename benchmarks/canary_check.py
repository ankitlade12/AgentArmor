"""Pre-publish vendor-drift canary (SPEC v4 D46).

Re-scores the 20 committed canary samples against each live baseline at
publish time; aborts publication if any cell's delta from the reference score
exceeds ``abort_multiplier × same_day_spread`` for that baseline.

Reference scores live in ``benchmarks/fixtures/vendor_canary.jsonl``. When a
canary entry has an empty ``reference_scores`` dict (initial commit), the
check for that baseline is skipped with a warning — the canary is intended
to be re-baselined after the first calibrated publication run.

See RUNBOOK #7 for re-baselining procedure.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

CANARY_PATH_DEFAULT = Path(__file__).resolve().parent / "fixtures" / "vendor_canary.jsonl"


class CanaryAbort(RuntimeError):
    """Raised when vendor drift exceeds the publish abort threshold."""


@dataclass(frozen=True)
class CanarySample:
    sample_id: str
    text: str
    category: str
    reference_scores: Dict[str, float]
    reference_run_date: Optional[str]


@dataclass(frozen=True)
class CanaryDrift:
    sample_id: str
    baseline: str
    live_score: float
    reference_score: float
    delta: float
    tolerance: float


def load_canary(path: Path = CANARY_PATH_DEFAULT) -> List[CanarySample]:
    """Parse the committed canary JSONL; skip malformed lines."""
    out: List[CanarySample] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(
                CanarySample(
                    sample_id=row["sample_id"],
                    text=row["text"],
                    category=row.get("category", "unknown"),
                    reference_scores=dict(row.get("reference_scores") or {}),
                    reference_run_date=row.get("reference_run_date"),
                )
            )
    return out


def _tolerance_for(
    baseline: str, same_day_spread: Dict[str, float], abort_multiplier: float
) -> float:
    """Largest spread observed for the baseline across cells × ``abort_multiplier``."""
    relevant = [s for k, s in same_day_spread.items() if k.startswith(f"{baseline}:")]
    base = max(relevant) if relevant else 0.05
    return abort_multiplier * base


def _score_fn_for(baseline_name: str, build_baseline) -> Callable[[str], float]:
    """Return a ``score`` callable for the named baseline.

    ``build_baseline`` is injected so tests can substitute mock builders.
    """
    b = build_baseline(baseline_name)
    return b.score


def check_canary(
    samples: List[CanarySample],
    same_day_spread: Dict[str, float],
    build_baseline: Callable[[str], object],
    abort_multiplier: float = 3.0,
) -> List[CanaryDrift]:
    """Score canary samples against live baselines; return drifts exceeding tolerance.

    If ``same_day_spread`` is empty, uses a conservative 0.05 default per baseline.
    Raises ``CanaryAbort`` on the first drift past the multiplier so operators
    see the failure before wasting more time.
    """
    drifts: List[CanaryDrift] = []
    for sample in samples:
        if not sample.reference_scores:
            continue  # placeholder entry; skip until re-baselined
        for baseline, reference_score in sorted(sample.reference_scores.items()):
            score_fn = _score_fn_for(baseline, build_baseline)
            try:
                live_score = float(score_fn(sample.text))
            except Exception as exc:  # noqa: BLE001 — canary tolerates per-sample errors
                raise CanaryAbort(
                    f"canary score call failed for {baseline}/{sample.sample_id}: {exc}"
                ) from exc
            tolerance = _tolerance_for(baseline, same_day_spread, abort_multiplier)
            delta = abs(live_score - reference_score)
            if delta > tolerance:
                drift = CanaryDrift(
                    sample_id=sample.sample_id,
                    baseline=baseline,
                    live_score=live_score,
                    reference_score=reference_score,
                    delta=delta,
                    tolerance=tolerance,
                )
                raise CanaryAbort(
                    f"Vendor drift detected: {baseline} sample {sample.sample_id} "
                    f"scored {live_score:.4f}, reference {reference_score:.4f}, "
                    f"delta {delta:.4f}, tolerance {tolerance:.4f}. "
                    f"See RUNBOOK #7."
                )
            drifts.append(
                CanaryDrift(
                    sample_id=sample.sample_id,
                    baseline=baseline,
                    live_score=live_score,
                    reference_score=reference_score,
                    delta=delta,
                    tolerance=tolerance,
                )
            )
    return drifts


def count_unbaselined_samples(samples: List[CanarySample]) -> int:
    """Return how many samples still have an empty reference_scores dict."""
    return sum(1 for s in samples if not s.reference_scores)
