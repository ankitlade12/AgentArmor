#!/usr/bin/env python3
"""
AgentArmor Industry Benchmark Runner
======================================
Evaluates AgentArmor detection modules against established industry datasets
(JailbreakBench, XSTest, HarmBench, AdvBench, HaluEval, RealToxicityPrompts,
ToxiGen, GuardBench, BBQ) using standardized adapters.

Usage:
    python benchmarks/run_industry_benchmarks.py                      # All datasets, default samples
    python benchmarks/run_industry_benchmarks.py --dataset xstest     # Specific dataset
    python benchmarks/run_industry_benchmarks.py --module ml_shield   # Specific module only
    python benchmarks/run_industry_benchmarks.py --sample-size 200    # Override sample size
    python benchmarks/run_industry_benchmarks.py --full               # No sampling limit
    python benchmarks/run_industry_benchmarks.py --verbose            # Per-sample output
    python benchmarks/run_industry_benchmarks.py --export results/industry.json
    python benchmarks/run_industry_benchmarks.py --list               # List available datasets
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BENCHMARKS_DIR))

from common import BenchmarkResult, print_result, print_summary, export_results
from adapters import get_adapter, list_adapters, NormalizedSample

# Force-import all adapter modules so they register via @register_adapter
import adapters.jailbreakbench  # noqa: F401
import adapters.xstest          # noqa: F401
import adapters.harmbench        # noqa: F401
import adapters.advbench         # noqa: F401
import adapters.halueval         # noqa: F401
import adapters.realtoxicity     # noqa: F401
import adapters.toxigen          # noqa: F401
import adapters.guardbench       # noqa: F401
import adapters.bbq              # noqa: F401
import adapters.truthfulqa       # noqa: F401


# ---------------------------------------------------------------------------
# Module evaluation functions
# ---------------------------------------------------------------------------

def _create_request_context(text: str):
    """Create a RequestContext for shield-style modules."""
    from agentarmor.hooks import RequestContext
    return RequestContext(
        messages=[{"role": "user", "content": text}],
        model="test",
    )


def evaluate_shield(sample: NormalizedSample, module, verbose: bool = False) -> bool:
    """Evaluate shield module: exception raised = detected."""
    try:
        ctx = _create_request_context(sample.text)
        module.pre_check(ctx)
        return False
    except Exception:
        return True


def evaluate_toxicity(sample: NormalizedSample, module, verbose: bool = False) -> bool:
    """Evaluate toxicity module: any findings = detected."""
    findings = module.scan_text(sample.text)
    return len(findings) > 0


def evaluate_grounding(sample: NormalizedSample, module, verbose: bool = False) -> bool:
    """Evaluate grounding module: score below threshold = detected (hallucination).

    Returns None if sample has no source_context (skip sample).
    """
    if not sample.source_context:
        return None
    score = module._compute_grounding_score(sample.text, [sample.source_context])
    return score < 0.6


# ---------------------------------------------------------------------------
# Module loaders — each returns (module_instance, eval_function, display_name)
# or raises ImportError if dependencies are missing.
# ---------------------------------------------------------------------------

def load_shield():
    from agentarmor.modules.shield import ShieldModule
    module = ShieldModule(on_detect="block")
    return module, evaluate_shield, "Shield (Regex)"


def load_ml_shield():
    from agentarmor.modules.ml_shield import MLShieldModule
    module = MLShieldModule(on_detect="block", threshold=0.5)
    return module, evaluate_shield, "ML Shield (TF-IDF)"


def load_toxicity():
    from agentarmor.modules.toxicity import ToxicityModule
    module = ToxicityModule(on_detect="block")
    return module, evaluate_toxicity, "Toxicity Filter"


def load_grounding():
    from agentarmor.modules.grounding import GroundingGuardModule
    module = GroundingGuardModule(
        sources=["placeholder"],
        threshold=0.6,
        on_detect="block",
    )
    return module, evaluate_grounding, "Grounding Guard"


MODULE_LOADERS: Dict[str, Callable] = {
    "shield": load_shield,
    "ml_shield": load_ml_shield,
    "toxicity": load_toxicity,
    "grounding": load_grounding,
}


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

def run_evaluation(
    adapter_name: str,
    module_name: str,
    samples: List[NormalizedSample],
    verbose: bool = False,
) -> BenchmarkResult:
    """Run a single module against a list of normalized samples."""
    result_label = f"{module_name} @ {adapter_name}"

    # Load the module
    try:
        loader = MODULE_LOADERS[module_name]
        module_instance, eval_fn, display_name = loader()
    except ImportError as e:
        result = BenchmarkResult(module=result_label)
        result.errors.append(f"Module unavailable: {e}")
        return result
    except Exception as e:
        result = BenchmarkResult(module=result_label)
        result.errors.append(f"Failed to load module: {e}")
        return result

    result = BenchmarkResult(module=result_label)
    start = time.time()

    for i, sample in enumerate(samples):
        expected_positive = sample.label == "positive"
        category = sample.category or "unknown"

        try:
            detected = eval_fn(sample, module_instance, verbose=verbose)
        except Exception as e:
            result.errors.append(f"Sample {i} error: {e}")
            continue

        # None means the sample should be skipped (e.g., grounding without source)
        if detected is None:
            continue

        result.total += 1

        if expected_positive and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_positive and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"    MISS [{category}]: {sample.text[:80]}...")
        elif not expected_positive and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"    FALSE POS [{category}]: {sample.text[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AgentArmor Industry Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python benchmarks/run_industry_benchmarks.py --list\n"
            "  python benchmarks/run_industry_benchmarks.py --dataset xstest --module shield\n"
            "  python benchmarks/run_industry_benchmarks.py --full --export results/industry.json\n"
        ),
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Run only this dataset adapter (e.g. xstest, halueval)",
    )
    parser.add_argument(
        "--module", type=str, default=None,
        choices=list(MODULE_LOADERS.keys()),
        help="Run only this AgentArmor module",
    )
    parser.add_argument(
        "--sample-size", type=int, default=None,
        help="Override per-dataset sample size",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Use full datasets (no sampling limit)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print per-sample miss/false-positive details",
    )
    parser.add_argument(
        "--export", type=str, default=None,
        help="Export results to JSON file",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_datasets",
        help="List available dataset adapters and exit",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for sampling (default: 42)",
    )
    args = parser.parse_args()

    # --list mode
    if args.list_datasets:
        print("\n  Available Industry Benchmark Datasets")
        print("  " + "-" * 50)
        for name in sorted(list_adapters()):
            adapter = get_adapter(name)
            modules_str = ", ".join(adapter.target_modules)
            print(f"  {name:<20} modules: [{modules_str}]")
            print(f"  {'':20} {adapter.description}")
            print(f"  {'':20} source: {adapter.source}")
            print(f"  {'':20} default samples: {adapter.default_sample_size}")
            print()
        return

    # Determine which adapters to run
    available_adapters = sorted(list_adapters())
    if args.dataset:
        if args.dataset not in available_adapters:
            print(f"  ERROR: Unknown dataset '{args.dataset}'. "
                  f"Available: {', '.join(available_adapters)}")
            sys.exit(1)
        adapter_names = [args.dataset]
    else:
        adapter_names = available_adapters

    # Header
    total_start = time.time()
    print()
    print("  AgentArmor Industry Benchmark Runner")
    print("  " + "=" * 50)
    print(f"  Datasets:    {len(adapter_names)} "
          f"({', '.join(adapter_names)})")
    if args.module:
        print(f"  Module:      {args.module}")
    else:
        print(f"  Modules:     all applicable per dataset")
    if args.full:
        print(f"  Sampling:    FULL (no limit)")
    elif args.sample_size:
        print(f"  Sampling:    {args.sample_size} per dataset")
    else:
        print(f"  Sampling:    adapter defaults")
    print(f"  Seed:        {args.seed}")
    print()

    all_results: List[BenchmarkResult] = []

    for adapter_name in adapter_names:
        adapter = get_adapter(adapter_name)

        # Determine which modules to evaluate for this adapter
        if args.module:
            if args.module not in adapter.target_modules:
                print(f"  [{adapter_name}] Skipping: module '{args.module}' "
                      f"not in target_modules {adapter.target_modules}")
                continue
            modules_to_run = [args.module]
        else:
            modules_to_run = adapter.target_modules

        # Determine sample size
        if args.full:
            sample_size = None  # adapters treat None as "use default" but we want all
            # Pass a very large number to effectively disable sampling
            sample_size = 999_999_999
        elif args.sample_size:
            sample_size = args.sample_size
        else:
            sample_size = None  # use adapter default

        # Load data
        print(f"  [{adapter_name}] Loading dataset...", end="", flush=True)
        try:
            samples = adapter.load(sample_size=sample_size, seed=args.seed)
            pos_count = sum(1 for s in samples if s.label == "positive")
            neg_count = len(samples) - pos_count
            print(f" {len(samples)} samples (pos={pos_count}, neg={neg_count})")
        except ImportError as e:
            print(f" FAILED")
            print(f"    Missing dependency: {e}")
            print(f"    Install with: pip install datasets")
            # Record a skipped result for each module
            for mod in modules_to_run:
                r = BenchmarkResult(module=f"{mod} @ {adapter_name}")
                r.errors.append(f"Dataset loading failed: {e}")
                all_results.append(r)
            continue
        except Exception as e:
            print(f" ERROR: {e}")
            for mod in modules_to_run:
                r = BenchmarkResult(module=f"{mod} @ {adapter_name}")
                r.errors.append(f"Dataset loading failed: {e}")
                all_results.append(r)
            continue

        # Run each applicable module
        for mod_name in modules_to_run:
            print(f"  [{adapter_name}] Evaluating {mod_name}...", end="", flush=True)
            result = run_evaluation(
                adapter_name=adapter_name,
                module_name=mod_name,
                samples=samples,
                verbose=args.verbose,
            )
            all_results.append(result)

            if result.errors:
                print(f" skipped ({result.errors[0][:60]})")
            else:
                print(f" done ({result.total} samples, {result.duration_ms:.0f}ms, "
                      f"F1={result.f1:.1%})")

        print()

    # ---------------------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------------------

    if not all_results:
        print("  No results to display.")
        sys.exit(0)

    # Detailed results
    for result in all_results:
        print_result(result)

    # Summary table
    if len(all_results) > 1:
        print_summary(all_results, title="INDUSTRY BENCHMARK SUMMARY")

    # Timing
    total_elapsed = time.time() - total_start
    print(f"  Total runtime: {total_elapsed:.1f}s")
    print()

    # Export
    if args.export:
        export_results(
            all_results,
            args.export,
            version="2.0",
            result_type="industry_benchmark",
        )


if __name__ == "__main__":
    main()
