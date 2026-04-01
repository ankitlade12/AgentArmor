"""
Shared benchmark infrastructure: BenchmarkResult, formatters, and exporters.
Used by all benchmark runners (smoke tests, industry, E2E).
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class BenchmarkResult:
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

    @property
    def false_positive_rate(self) -> float:
        """FP / (FP + TN) — how often safe content is incorrectly flagged."""
        denom = self.false_positives + self.true_negatives
        return self.false_positives / denom if denom > 0 else 0.0

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


def print_result(result: BenchmarkResult):
    """Print formatted benchmark results."""
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
            if tp == 0 and fn == 0 and fp == 0:
                continue
            print(f"  {cat:<25} {prec:>7.1%} {rec:>7.1%} {f1:>7.1%} {tp:>5} {fp:>5} {fn:>5}")


def print_summary(results: List[BenchmarkResult], title: str = "BENCHMARK SUMMARY"):
    """Print summary table of all benchmark results."""
    print(f"\n{'='*84}")
    print(f"  {title}")
    print(f"{'='*84}")
    print(f"  {'Module':<25} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'FP Rate':>8} {'FPs':>6}")
    print(f"  {'─'*80}")

    for r in results:
        if r.errors:
            print(f"  {r.module:<25} {'SKIPPED':>10} {'—':>10} {'—':>10} {'—':>10} {'—':>8} {'—':>6}")
        else:
            print(f"  {r.module:<25} {r.accuracy:>10.1%} {r.precision:>10.1%} {r.recall:>10.1%} {r.f1:>10.1%} {r.false_positive_rate:>8.1%} {r.false_positives:>6}")

    total_time = sum(r.duration_ms for r in results)
    total_samples = sum(r.total for r in results)
    print(f"  {'─'*80}")
    print(f"  Total: {total_samples} samples in {total_time:.1f}ms")
    print()


def export_results(results: List[BenchmarkResult], output_path: str,
                   version: str = "2.0", result_type: str = "smoke_test"):
    """Export results to JSON for CI/CD integration."""
    export = {
        "version": version,
        "type": result_type,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "modules": {}
    }
    for r in results:
        export["modules"][r.module] = {
            "accuracy": round(r.accuracy, 4),
            "precision": round(r.precision, 4),
            "recall": round(r.recall, 4),
            "f1": round(r.f1, 4),
            "false_positive_rate": round(r.false_positive_rate, 4),
            "false_positives": r.false_positives,
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

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(export, f, indent=2)
    print(f"  Results exported to {output_path}")
