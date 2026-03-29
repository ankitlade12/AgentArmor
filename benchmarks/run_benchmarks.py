#!/usr/bin/env python3
"""
AgentArmor Benchmark Suite
===========================
Evaluates detection accuracy across all safety modules with precision,
recall, F1 score, and per-category breakdowns.

Usage:
    python benchmarks/run_benchmarks.py                # Run all benchmarks
    python benchmarks/run_benchmarks.py --module shield # Run specific module
    python benchmarks/run_benchmarks.py --verbose       # Show per-sample results
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common import BenchmarkResult, load_dataset, print_result, print_summary, export_results


# ---------------------------------------------------------------------------
# Module benchmarks
# ---------------------------------------------------------------------------

def bench_shield(verbose: bool = False) -> BenchmarkResult:
    """Benchmark regex-based prompt injection shield."""
    from agentarmor.modules.shield import ShieldModule

    samples = load_dataset("prompt_injection")
    result = BenchmarkResult(module="Shield (Regex)")
    shield = ShieldModule(on_detect="block")
    start = time.time()

    for sample in samples:
        text = sample["text"]
        expected_injection = sample["label"] == "injection"
        category = sample.get("category", "unknown")
        result.total += 1

        detected = False
        try:
            from agentarmor.hooks import RequestContext
            ctx = RequestContext(
                messages=[{"role": "user", "content": text}],
                model="gpt-4"
            )
            shield.pre_check(ctx)
        except Exception:
            detected = True

        if expected_injection and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_injection and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"  MISS [{category}]: {text[:80]}...")
        elif not expected_injection and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"  FALSE POS [{category}]: {text[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_ml_shield(verbose: bool = False) -> BenchmarkResult:
    """Benchmark ML-based prompt injection shield."""
    try:
        from agentarmor.modules.ml_shield import MLShieldModule
    except ImportError:
        result = BenchmarkResult(module="ML Shield (TF-IDF)")
        result.errors.append("scikit-learn not installed. Run: pip install agentarmor[ml]")
        return result

    samples = load_dataset("prompt_injection")
    result = BenchmarkResult(module="ML Shield (TF-IDF)")
    shield = MLShieldModule(on_detect="block", threshold=0.5)
    start = time.time()

    for sample in samples:
        text = sample["text"]
        expected_injection = sample["label"] == "injection"
        category = sample.get("category", "unknown")
        result.total += 1

        detected = False
        try:
            from agentarmor.hooks import RequestContext
            ctx = RequestContext(
                messages=[{"role": "user", "content": text}],
                model="gpt-4"
            )
            shield.pre_check(ctx)
        except Exception:
            detected = True

        if expected_injection and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_injection and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"  MISS [{category}]: {text[:80]}...")
        elif not expected_injection and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"  FALSE POS [{category}]: {text[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_toxicity(verbose: bool = False) -> BenchmarkResult:
    """Benchmark toxicity detection module."""
    from agentarmor.modules.toxicity import ToxicityModule

    samples = load_dataset("toxicity")
    result = BenchmarkResult(module="Toxicity Filter")
    module = ToxicityModule(on_detect="block")
    start = time.time()

    for sample in samples:
        text = sample["text"]
        expected_toxic = sample["label"] == "toxic"
        category = sample.get("category", "unknown")
        result.total += 1

        findings = module.scan_text(text)
        detected = len(findings) > 0

        if expected_toxic and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_toxic and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"  MISS [{category}]: {text[:80]}...")
        elif not expected_toxic and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"  FALSE POS [{category}]: {text[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_code_shield(verbose: bool = False) -> BenchmarkResult:
    """Benchmark code safety scanning module."""
    from agentarmor.modules.code_shield import CodeShieldModule

    samples = load_dataset("code_safety")
    result = BenchmarkResult(module="Code Shield")
    module = CodeShieldModule(on_detect="block")
    start = time.time()

    for sample in samples:
        code = sample["code"]
        language = sample.get("language", None)
        expected_insecure = sample["label"] == "insecure"
        category = sample.get("category", "unknown")
        result.total += 1

        findings = module.scan_code(code, language=language)
        detected = len(findings) > 0

        if expected_insecure and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_insecure and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"  MISS [{language}/{category}]: {code[:80]}...")
        elif not expected_insecure and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"  FALSE POS [{language}/{category}]: {code[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_grounding(verbose: bool = False) -> BenchmarkResult:
    """Benchmark hallucination/grounding detection."""
    from agentarmor.modules.grounding import GroundingGuardModule

    samples = load_dataset("grounding")
    result = BenchmarkResult(module="Grounding Guard")
    start = time.time()

    for sample in samples:
        source = sample["source"]
        response = sample["response"]
        expected_hallucinated = sample["label"] == "hallucinated"
        result.total += 1

        module = GroundingGuardModule(
            sources=[source],
            threshold=0.6,
            on_detect="block",
            check_claims=True,
            check_numbers=True,
            check_names=True,
        )

        score = module._compute_grounding_score(response, [source])
        detected_hallucination = score < 0.6

        if expected_hallucinated and detected_hallucination:
            result.true_positives += 1
        elif expected_hallucinated and not detected_hallucination:
            result.false_negatives += 1
            if verbose:
                print(f"  MISS [score={score:.3f}]: {response[:80]}...")
        elif not expected_hallucinated and detected_hallucination:
            result.false_positives += 1
            if verbose:
                print(f"  FALSE POS [score={score:.3f}]: {response[:80]}...")
        else:
            result.true_negatives += 1

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_cot_auditor(verbose: bool = False) -> BenchmarkResult:
    """Benchmark chain-of-thought reasoning auditor."""
    from agentarmor.modules.cot_auditor import CoTAuditorModule

    samples = load_dataset("cot_reasoning")
    result = BenchmarkResult(module="CoT Auditor")
    module = CoTAuditorModule(on_detect="block")
    start = time.time()

    for sample in samples:
        text = sample["text"]
        expected_misaligned = sample["label"] == "misaligned"
        category = sample.get("category", "unknown")
        result.total += 1

        findings = module.audit_text(text)
        detected = len(findings) > 0

        if expected_misaligned and detected:
            result.true_positives += 1
            result.add_category(category, tp=1)
        elif expected_misaligned and not detected:
            result.false_negatives += 1
            result.add_category(category, fn=1)
            if verbose:
                print(f"  MISS [{category}]: {text[:80]}...")
        elif not expected_misaligned and detected:
            result.false_positives += 1
            result.add_category(category, fp=1)
            if verbose:
                print(f"  FALSE POS [{category}]: {text[:80]}...")
        else:
            result.true_negatives += 1
            result.add_category(category, tn=1)

    result.duration_ms = (time.time() - start) * 1000
    return result


def bench_filter(verbose: bool = False) -> BenchmarkResult:
    """Benchmark PII and secrets filter."""
    from agentarmor.modules.filter import FilterModule

    samples = load_dataset("pii_secrets")
    result = BenchmarkResult(module="PII/Secrets Filter")
    module = FilterModule(rules=["pii", "secrets"])
    start = time.time()

    for sample in samples:
        text = sample["text"]
        expected_contains = sample["label"] != "clean"
        result.total += 1

        scanned = module._scan(text)
        detected = "[REDACTED:" in scanned

        if expected_contains and detected:
            result.true_positives += 1
        elif expected_contains and not detected:
            result.false_negatives += 1
            if verbose:
                print(f"  MISS [{sample['label']}]: {text[:80]}...")
        elif not expected_contains and detected:
            result.false_positives += 1
            if verbose:
                print(f"  FALSE POS: {text[:80]}...")
        else:
            result.true_negatives += 1

    result.duration_ms = (time.time() - start) * 1000
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

BENCHMARKS = {
    "shield": bench_shield,
    "ml_shield": bench_ml_shield,
    "toxicity": bench_toxicity,
    "code_shield": bench_code_shield,
    "grounding": bench_grounding,
    "cot_auditor": bench_cot_auditor,
    "filter": bench_filter,
}


def main():
    parser = argparse.ArgumentParser(description="AgentArmor Benchmark Suite")
    parser.add_argument("--module", choices=list(BENCHMARKS.keys()),
                        help="Run benchmark for a specific module only")
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-sample miss/false-positive details")
    parser.add_argument("--export", type=str, default=None,
                        help="Export results to JSON file")
    args = parser.parse_args()

    print("\n  AgentArmor Benchmark Suite")
    print("  " + "─" * 40)

    if args.module:
        benchmarks = {args.module: BENCHMARKS[args.module]}
    else:
        benchmarks = BENCHMARKS

    results = []
    for name, bench_fn in benchmarks.items():
        print(f"\n  Running {name}...", end="", flush=True)
        try:
            result = bench_fn(verbose=args.verbose)
            results.append(result)
            if not result.errors:
                print(f" done ({result.duration_ms:.0f}ms)")
            else:
                print(f" skipped")
        except Exception as e:
            print(f" error: {e}")
            r = BenchmarkResult(module=name)
            r.errors.append(str(e))
            results.append(r)

    for result in results:
        print_result(result)

    if len(results) > 1:
        print_summary(results)

    if args.export:
        export_results(results, args.export)


if __name__ == "__main__":
    main()
