"""Head-to-head comparison runner — CLI entrypoint (SPEC v4 DoD-1, DoD-7, DoD-3).

Composes: config loader (secret allow-list + startup key check), taxonomy
rubric (``ensure_complete``), per-dataset projection for OpenAI Moderation,
sequential ``run_cell``, per-metric bootstrap CIs with pinned seeds, and
summary JSON writer.

Usage
-----
    python -m benchmarks.run_head_to_head --run-dir benchmarks/results/runs/<ts>
    python -m benchmarks.run_head_to_head --dry-run
    python -m benchmarks.run_head_to_head --baseline mock_scored --dataset toxigen
    python -m benchmarks.run_head_to_head --resume --run-dir <existing>

``--dry-run`` prints the cost projection (``$0`` in v1 per D40 — all baselines
free-tier) and exits without any API call.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .baselines.base import BaselineChecker, get_baseline, list_baselines

# Force-import to register baselines.
from .baselines import llamaguard  # noqa: F401
from .baselines import openai_moderation  # noqa: F401
from .baselines import perspective_api  # noqa: F401
from .baselines import mock  # noqa: F401
from .baselines import agentarmor_modules  # noqa: F401

from .common import HeadToHeadResult, compute_adapter_version
from .config import (
    check_required_keys,
    compute_config_hash,
    load_config,
)
from .metrics import (
    cell_bootstrap_seed,
    compute_balanced_accuracy_ci,
    compute_f1_ci,
    compute_mcc_ci,
    fpr_from_counts,
    precision_from_counts,
    recall_from_counts,
)
from .runner import RunLogger, run_cell
from .schema_io import dump_summary
from .taxonomy_applicability import (
    APPLIES,
    RUBRIC_VERSION,
    ensure_complete,
    get_projection,
)

SUMMARY_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Adapter loading
# ---------------------------------------------------------------------------


def _load_adapters_module():
    """Force-register all production adapters; return the adapters package."""
    import benchmarks.adapters as adapters_pkg

    # Force-import all adapters so @register_adapter fires.
    from benchmarks.adapters import (  # noqa: F401
        advbench,
        harmbench,
        jailbreakbench,
        realtoxicity,
        toxigen,
        xstest,
    )
    return adapters_pkg


# Main-comparison datasets per SPEC v4 scope.
MAIN_DATASETS: List[str] = [
    "xstest",
    "realtoxicity",
    "toxigen",
    "harmbench",
    "jailbreakbench",
    "advbench",
]

MAIN_BASELINES: List[str] = [
    # AgentArmor modules (left-hand side of the comparison)
    "agentarmor_shield",
    "agentarmor_ml_shield",
    "agentarmor_toxicity",
    # External safety/toxicity baselines
    "llamaguard",
    "openai_moderation",
    # Perspective API excluded from v1 — Google/Jigsaw shutdown 2026-12-31.
    # Rubric entries remain as does_not_apply for transparency.
]


# ---------------------------------------------------------------------------
# Baseline instantiation per cell
# ---------------------------------------------------------------------------


def build_baseline_for_cell(
    baseline_name: str,
    dataset_name: str,
    config: Dict[str, Any],
) -> BaselineChecker:
    """Construct a baseline with any per-cell parameters (D37 projection).

    OpenAI Moderation reads its projection from the rubric; other baselines
    take only their config section.
    """
    section = (config.get("baselines") or {}).get(baseline_name) or {}
    if baseline_name == "openai_moderation":
        from .baselines.openai_moderation import OpenAIModerationBaseline

        projection = get_projection(baseline_name, dataset_name)
        return OpenAIModerationBaseline(projection=projection, config=section)
    if baseline_name == "perspective":
        from .baselines.perspective_api import PerspectiveBaseline

        return PerspectiveBaseline(config=section)
    if baseline_name == "llamaguard":
        from .baselines.llamaguard import LlamaGuardBaseline

        return LlamaGuardBaseline(config=section)
    # Mock or unknown — use registry default-construction.
    return get_baseline(baseline_name)


# ---------------------------------------------------------------------------
# Cell metric computation
# ---------------------------------------------------------------------------


def _latency_percentiles(result: HeadToHeadResult) -> Tuple[Optional[float], Optional[float]]:
    latencies = [
        s.latency_ms
        for s in result.samples
        if not s.skipped and s.error is None
    ]
    if not latencies:
        return (None, None)
    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(0.50 * n)]
    p95 = latencies[min(int(0.95 * n), n - 1)]
    return (p50, p95)


def compute_cell_metrics(result: HeadToHeadResult, iters: int) -> Dict[str, Any]:
    """Return the per-cell metric dict consumed by the summary writer."""
    seed = cell_bootstrap_seed(result.baseline, result.dataset)
    samples = result.samples

    f1 = compute_f1_ci(samples, iters=iters, seed=seed)
    mcc = compute_mcc_ci(samples, iters=iters, seed=seed)
    bal = compute_balanced_accuracy_ci(samples, iters=iters, seed=seed)

    tp, fp = result.true_positives, result.false_positives
    tn, fn = result.true_negatives, result.false_negatives
    precision = precision_from_counts(tp, fp, tn, fn)
    recall = recall_from_counts(tp, fp, tn, fn)
    fpr = fpr_from_counts(tp, fp, tn, fn)

    p50, p95 = _latency_percentiles(result)
    errors_count = sum(1 for s in samples if s.error is not None)
    skipped_count = sum(1 for s in samples if s.skipped)

    degenerate = f1 is None

    return {
        "baseline": result.baseline,
        "dataset": result.dataset,
        "n_samples": result.total,
        "adapter_version": result.adapter_version,
        "baseline_config_hash": result.baseline_config_hash,
        "score_emitting": result.score_emitting,
        "operating_point": result.baseline,
        "f1": f1.point if f1 else None,
        "f1_ci_low": f1.ci_low if f1 else None,
        "f1_ci_high": f1.ci_high if f1 else None,
        "mcc": mcc.point if mcc else None,
        "mcc_ci_low": mcc.ci_low if mcc else None,
        "mcc_ci_high": mcc.ci_high if mcc else None,
        "balanced_accuracy": bal.point if bal else None,
        "balanced_accuracy_ci_low": bal.ci_low if bal else None,
        "balanced_accuracy_ci_high": bal.ci_high if bal else None,
        "precision": precision,
        "recall": recall,
        "fpr": fpr,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "degenerate_flag": degenerate,
        "errors_count": errors_count,
        "skipped_count": skipped_count,
        "duration_ms": result.duration_ms,
    }


# ---------------------------------------------------------------------------
# Summary JSON writer
# ---------------------------------------------------------------------------


def _agentarmor_version() -> str:
    try:
        import agentarmor

        return getattr(agentarmor, "__version__", "unknown")
    except ImportError:
        return "unknown"


def write_summary(
    run_dir: Path,
    cells: List[Dict[str, Any]],
    config: Dict[str, Any],
    run_id: str,
) -> Path:
    """Write ``head_to_head_summary.json`` at the run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "agentarmor_version": _agentarmor_version(),
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "rubric_version": RUBRIC_VERSION,
        "config_echo": config,
        "cells": cells,
        "tolerances": {
            "same_day_spread_95p": None,
            "one_week_drift_max": None,
            "calibration_run_dates": [],
        },
    }
    path = run_dir / "head_to_head_summary.json"
    dump_summary(path, payload)
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _resolve_adapter(dataset_name: str):
    """Indirection point so tests can patch a single hook."""
    from benchmarks.adapters import get_adapter

    return get_adapter(dataset_name)


def _resolve_adapter_module(dataset_name: str):
    """Import the adapter module for ``compute_adapter_version`` (patchable)."""
    import importlib

    return importlib.import_module(f"benchmarks.adapters.{dataset_name}")


def _collect_applicable_cells(
    baselines_filter: Optional[List[str]],
    datasets_filter: Optional[List[str]],
) -> List[Tuple[str, str]]:
    """Return sorted (baseline, dataset) pairs with verdict=applies, honoring filters."""
    cells: List[Tuple[str, str]] = []
    for (b, d), applicability in APPLIES.items():
        if applicability.verdict != "applies":
            continue
        if baselines_filter and b not in baselines_filter:
            continue
        if datasets_filter and d not in datasets_filter:
            continue
        cells.append((b, d))
    return sorted(cells)


def _new_run_dir(base: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / f"runs/{ts}"


def run_main(
    run_dir: Path,
    config: Dict[str, Any],
    baselines: List[str],
    datasets: List[str],
    sample_size: Optional[int],
    seed: int,
    bootstrap_iters: int,
    dry_run: bool = False,
    verbose: bool = False,
) -> Path:
    """Core orchestration entry (unit-testable; CLI ``main()`` wraps this)."""
    _load_adapters_module()

    # Ensure the rubric is complete for the cells we'll touch.
    ensure_complete(baselines, datasets)

    if not dry_run:
        # Only check keys for the baselines that actually have gated entries.
        applicable_config = {
            "baselines": {
                k: v
                for k, v in (config.get("baselines") or {}).items()
                if k in baselines
            }
        }
        check_required_keys(applicable_config)

    cells = _collect_applicable_cells(baselines, datasets)
    if verbose:
        print(f"[run] {len(cells)} applicable cells: {cells}")

    if dry_run:
        api_baselines = [b for b in baselines if b in ("openai_moderation", "perspective")]
        print(f"[dry-run] {len(cells)} cells would run.")
        print(f"[dry-run] API-baseline cells: {len(api_baselines)} (all free-tier in v1).")
        print(f"[dry-run] Projected spend: $0.00 (per SPEC v4 D40).")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "dry_run.txt").write_text(
            f"cells={len(cells)}; api_baselines={api_baselines}; projected_usd=0\n"
        )
        return run_dir

    run_logger = RunLogger(run_dir / "run.jsonl")
    results: List[HeadToHeadResult] = []

    for baseline_name, dataset_name in cells:
        if verbose:
            print(f"[run] {baseline_name} @ {dataset_name} …", flush=True)
        adapter = _resolve_adapter(dataset_name)
        adapter_module = _resolve_adapter_module(dataset_name)
        adapter_version = compute_adapter_version(adapter_module)
        baseline_config_hash = compute_config_hash(config, baseline_name)

        try:
            samples = adapter.load(sample_size=sample_size, seed=seed)
        except Exception as exc:
            run_logger.error(
                baseline_name,
                dataset_name,
                None,
                type(exc).__name__,
                f"adapter load failed: {exc}",
            )
            continue

        try:
            baseline = build_baseline_for_cell(baseline_name, dataset_name, config)
        except Exception as exc:
            run_logger.error(
                baseline_name,
                dataset_name,
                None,
                type(exc).__name__,
                f"baseline construction failed: {exc}",
            )
            continue

        result = run_cell(
            baseline=baseline,
            baseline_name=baseline_name,
            dataset_name=dataset_name,
            samples=samples,
            adapter_name=dataset_name,
            adapter_version=adapter_version,
            baseline_config_hash=baseline_config_hash,
            run_dir=run_dir,
            run_logger=run_logger,
            verbose=verbose,
        )
        results.append(result)

    run_id = run_dir.name
    cells_out = [compute_cell_metrics(r, iters=bootstrap_iters) for r in results]
    summary_path = write_summary(run_dir, cells_out, config, run_id)
    if verbose:
        print(f"[run] summary → {summary_path}")
    return run_dir


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Head-to-head benchmark runner")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Directory for sidecars/verdicts/run.jsonl/summary.json. Default: new timestamped dir under benchmarks/results/runs/",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        action="append",
        default=None,
        help="Limit to one baseline (repeatable).",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        action="append",
        default=None,
        help="Limit to one dataset (repeatable).",
    )
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-iters", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    config = load_config()
    baselines = args.baseline or MAIN_BASELINES
    datasets = args.dataset or MAIN_DATASETS
    run_dir = args.run_dir or _new_run_dir(Path("benchmarks/results"))

    try:
        run_main(
            run_dir=run_dir,
            config=config,
            baselines=baselines,
            datasets=datasets,
            sample_size=args.sample_size,
            seed=args.seed,
            bootstrap_iters=args.bootstrap_iters,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
