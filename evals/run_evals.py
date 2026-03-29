#!/usr/bin/env python3
"""
AgentArmor SmokeTest Suite
===========================
Evaluates detection accuracy across all safety modules with precision,
recall, F1 score, and per-category breakdowns.

Usage:
    python evals/run_evals.py                # Run all smoke_tests
    python evals/run_evals.py --module shield # Run specific module
    python evals/run_evals.py --verbose       # Show per-sample results
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class SmokeTestResult:
    module: str
    total: int = 0
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    category_results: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        correct = self.true_positives + self.true_negatives
        return correct / self.total if self.total > 0 else 0.0

    def add_category(self, category: str, tp: int = 0, fp: int = 0, tn: int = 0, fn: int = 0):
        if category not in self.category_results:
            self.category_results[category] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        self.category_results[category]["tp"] += tp
        self.category_results[category]["fp"] += fp
        self.category_results[category]["tn"] += tn
        self.category_results[category]["fn"] += fn


def load_dataset(name: str) -> list:
    path = DATASETS_DIR / f"{name}.json"
    with open(path) as f:
        data = json.load(f)
    return data["samples"]


# ---------------------------------------------------------------------------
# Module smoke_tests
# ---------------------------------------------------------------------------

def bench_shield(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest regex-based prompt injection shield."""
    from agentarmor.modules.shield import ShieldModule

    samples = load_dataset("prompt_injection")
    result = SmokeTestResult(module="Shield (Regex)")
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


def bench_ml_shield(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest ML-based prompt injection shield."""
    try:
        from agentarmor.modules.ml_shield import MLShieldModule
    except ImportError:
        result = SmokeTestResult(module="ML Shield (TF-IDF)")
        result.errors.append("scikit-learn not installed. Run: pip install agentarmor[ml]")
        return result

    samples = load_dataset("prompt_injection")
    result = SmokeTestResult(module="ML Shield (TF-IDF)")
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


def bench_toxicity(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest toxicity detection module."""
    from agentarmor.modules.toxicity import ToxicityModule

    samples = load_dataset("toxicity")
    result = SmokeTestResult(module="Toxicity Filter")
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


def bench_code_shield(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest code safety scanning module."""
    from agentarmor.modules.code_shield import CodeShieldModule

    samples = load_dataset("code_safety")
    result = SmokeTestResult(module="Code Shield")
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


def bench_grounding(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest hallucination/grounding detection."""
    from agentarmor.modules.grounding import GroundingGuardModule

    samples = load_dataset("grounding")
    result = SmokeTestResult(module="Grounding Guard")
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


def bench_cot_auditor(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest chain-of-thought reasoning auditor."""
    from agentarmor.modules.cot_auditor import CoTAuditorModule

    samples = load_dataset("cot_reasoning")
    result = SmokeTestResult(module="CoT Auditor")
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


def bench_filter(verbose: bool = False) -> SmokeTestResult:
    """SmokeTest PII and secrets filter."""
    from agentarmor.modules.filter import FilterModule

    samples = load_dataset("pii_secrets")
    result = SmokeTestResult(module="PII/Secrets Filter")
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
# Output formatting
# ---------------------------------------------------------------------------

def print_result(result: SmokeTestResult):
    """Print formatted smoke_test results."""
    print(f"\n{'='*70}")
    print(f"  {result.module}")
    print(f"{'='*70}")

    if result.errors:
        for err in result.errors:
            print(f"  ERROR: {err}")
        return

    print(f"  Samples: {result.total}  |  Time: {result.duration_ms:.1f}ms")
    print(f"  {'─'*66}")
    print(f"  {'Metric':<20} {'Value':>10}")
    print(f"  {'─'*66}")
    print(f"  {'Accuracy':<20} {result.accuracy:>10.1%}")
    print(f"  {'Precision':<20} {result.precision:>10.1%}")
    print(f"  {'Recall':<20} {result.recall:>10.1%}")
    print(f"  {'F1 Score':<20} {result.f1:>10.1%}")
    print(f"  {'─'*66}")
    print(f"  {'True Positives':<20} {result.true_positives:>10}")
    print(f"  {'True Negatives':<20} {result.true_negatives:>10}")
    print(f"  {'False Positives':<20} {result.false_positives:>10}")
    print(f"  {'False Negatives':<20} {result.false_negatives:>10}")

    if result.category_results:
        print(f"\n  {'Category':<25} {'Prec':>8} {'Recall':>8} {'F1':>8} {'TP':>5} {'FP':>5} {'FN':>5}")
        print(f"  {'─'*66}")
        for cat, counts in sorted(result.category_results.items()):
            tp = counts["tp"]
            fp = counts["fp"]
            fn = counts["fn"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            # Skip safe/general categories (they don't have TP)
            if tp == 0 and fn == 0 and fp == 0:
                continue
            print(f"  {cat:<25} {prec:>7.1%} {rec:>7.1%} {f1:>7.1%} {tp:>5} {fp:>5} {fn:>5}")


def print_summary(results: List[SmokeTestResult]):
    """Print summary table of all smoke_test results."""
    print(f"\n{'='*70}")
    print(f"  SMOKE_TEST SUMMARY — AgentArmor v1.1")
    print(f"{'='*70}")
    print(f"  {'Module':<25} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print(f"  {'─'*66}")

    for r in results:
        if r.errors:
            print(f"  {r.module:<25} {'SKIPPED':>10} {'—':>10} {'—':>10} {'—':>10}")
        else:
            print(f"  {r.module:<25} {r.accuracy:>10.1%} {r.precision:>10.1%} {r.recall:>10.1%} {r.f1:>10.1%}")

    total_time = sum(r.duration_ms for r in results)
    total_samples = sum(r.total for r in results)
    print(f"  {'─'*66}")
    print(f"  Total: {total_samples} samples in {total_time:.1f}ms")
    print()


def export_results(results: List[SmokeTestResult], output_path: str):
    """Export results to JSON for CI/CD integration."""
    export = {
        "version": "1.1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "modules": {}
    }
    for r in results:
        export["modules"][r.module] = {
            "accuracy": round(r.accuracy, 4),
            "precision": round(r.precision, 4),
            "recall": round(r.recall, 4),
            "f1": round(r.f1, 4),
            "total_samples": r.total,
            "true_positives": r.true_positives,
            "true_negatives": r.true_negatives,
            "false_positives": r.false_positives,
            "false_negatives": r.false_negatives,
            "duration_ms": round(r.duration_ms, 1),
            "errors": r.errors,
            "categories": {
                cat: {
                    "precision": round(c["tp"] / (c["tp"] + c["fp"]), 4) if (c["tp"] + c["fp"]) > 0 else 0,
                    "recall": round(c["tp"] / (c["tp"] + c["fn"]), 4) if (c["tp"] + c["fn"]) > 0 else 0,
                }
                for cat, c in r.category_results.items()
                if c["tp"] > 0 or c["fn"] > 0
            }
        }

    with open(output_path, "w") as f:
        json.dump(export, f, indent=2)
    print(f"  Results exported to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SMOKE_TESTS = {
    "shield": bench_shield,
    "ml_shield": bench_ml_shield,
    "toxicity": bench_toxicity,
    "code_shield": bench_code_shield,
    "grounding": bench_grounding,
    "cot_auditor": bench_cot_auditor,
    "filter": bench_filter,
}


def main():
    parser = argparse.ArgumentParser(description="AgentArmor SmokeTest Suite")
    parser.add_argument("--module", choices=list(SMOKE_TESTS.keys()),
                        help="Run smoke_test for a specific module only")
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-sample miss/false-positive details")
    parser.add_argument("--export", type=str, default=None,
                        help="Export results to JSON file")
    args = parser.parse_args()

    print("\n  AgentArmor SmokeTest Suite")
    print("  " + "─" * 40)

    if args.module:
        smoke_tests = {args.module: SMOKE_TESTS[args.module]}
    else:
        smoke_tests = SMOKE_TESTS

    results = []
    for name, bench_fn in smoke_tests.items():
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
            r = SmokeTestResult(module=name)
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
