# AgentArmor Smoke Tests

Curated evaluation suite measuring detection accuracy across core safety modules.

> **For industry-standard benchmarks** (AdvBench, HarmBench, TruthfulQA, ToxiGen, etc.), see [`benchmarks/README.md`](../benchmarks/README.md).

## Results — v1.1

**342 samples | 7 modules | 101ms total runtime**

| Module | Accuracy | Precision | Recall | F1 Score | Samples |
|--------|----------|-----------|--------|----------|---------|
| Shield (Regex) | 64.3% | 94.1% | 40.0% | 56.1% | 70 |
| ML Shield (TF-IDF) | **94.3%** | 95.0% | 95.0% | **95.0%** | 70 |
| Toxicity Filter | 89.1% | **100.0%** | 82.9% | 90.6% | 55 |
| Code Shield | 91.8% | 96.8% | 90.9% | 93.7% | 49 |
| Grounding Guard | 93.8% | 88.9% | **100.0%** | 94.1% | 16 |
| CoT Auditor | 92.3% | **100.0%** | 87.5% | 93.3% | 52 |
| PII/Secrets Filter | **100.0%** | **100.0%** | **100.0%** | **100.0%** | 30 |

## Running Smoke Tests

```bash
# Run all smoke tests
python evals/run_evals.py

# Run a specific module
python evals/run_evals.py --module ml_shield

# Verbose output (show misses and false positives)
python evals/run_evals.py --verbose

# Export results to JSON
python evals/run_evals.py --export evals/results.json
```

## Datasets

All datasets are in `evals/datasets/`:

| Dataset | Samples | Description |
|---------|---------|-------------|
| Prompt Injection | 70 | Direct overrides, jailbreaks, indirect injections, multilingual, prompt leaks |
| Toxicity | 55 | Hate speech, violence, self-harm, sexual content, harassment, illegal activity |
| Code Safety | 49 | Insecure patterns in Python, JS, SQL, Shell |
| Grounding | 16 | Source-response pairs: grounded vs hallucinated |
| CoT Reasoning | 52 | Aligned vs misaligned reasoning traces |
| PII/Secrets | 30 | Emails, SSNs, credit cards, API keys, JWTs, AWS keys |
