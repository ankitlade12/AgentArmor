# AgentArmor Benchmark Results

Auto-generated from benchmark runs. Do not edit manually.

## Overview

AgentArmor benchmarks are organized in three tiers:
- **Tier A: Smoke Tests** — 272 curated samples, runs in <1s, zero dependencies
- **Tier B: Industry Benchmarks** — Evaluated against JailbreakBench, XSTest, HarmBench, HaluEval, RealToxicityPrompts, ToxiGen, and more
- **Tier C: E2E Multi-Provider** — End-to-end tests across OpenAI, Anthropic, and Google models

## Tier A: Curated Smoke Tests

### Curated Smoke Tests

| Module | Samples | Accuracy | Precision | Recall | F1 | Time |
|--------|---------|----------|-----------|--------|----|------|
| Shield (Regex) | 70 | 64.3% | 94.1% | 40.0% | **56.1%** | 1ms |
| ML Shield (TF-IDF) | 70 | 94.3% | 95.0% | 95.0% | **95.0%** | 627ms |
| Toxicity Filter | 55 | 89.1% | 100.0% | 82.9% | **90.6%** | 2ms |
| Code Shield | 49 | 91.8% | 96.8% | 90.9% | **93.8%** | 1ms |
| Grounding Guard | 16 | 93.8% | 88.9% | 100.0% | **94.1%** | 2ms |
| CoT Auditor | 52 | 92.3% | 100.0% | 87.5% | **93.3%** | 3ms |
| PII/Secrets Filter | 30 | 100.0% | 100.0% | 100.0% | **100.0%** | 0ms |

## Methodology

- **Sampling**: Large datasets (>1K samples) are stratified-sampled to 500 by default (seed=42)
- **Metrics**: Standard binary classification — Precision, Recall, F1 Score, Accuracy
- **Thresholds**: ML Shield threshold=0.5, Grounding threshold=0.6, Toxicity uses pattern matching
- **Reproducibility**: All benchmarks use fixed random seeds. Results may vary with model updates.

## Running Benchmarks

```bash
# Tier A: Smoke tests (no deps)
python benchmarks/run_benchmarks.py

# Tier B: Industry benchmarks (needs: pip install datasets)
python benchmarks/run_industry_benchmarks.py

# Tier C: E2E (needs API keys in .env)
python benchmarks/run_e2e_benchmarks.py
```
