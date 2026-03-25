# AgentArmor Benchmarks

Evaluation suite measuring detection accuracy across all safety modules.

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

### Key Takeaways

- **ML Shield** achieves 95% F1 on prompt injection — a significant uplift over regex-only (56.1% F1). Use `ml_shield=True` or `ensemble=True` for production.
- **Toxicity Filter** has zero false positives (100% precision) across all 7 categories.
- **Code Shield** catches insecure patterns across Python, JavaScript, SQL, and Shell at 93.7% F1.
- **PII/Secrets Filter** achieves perfect scores — every email, SSN, credit card, API key, JWT, and AWS key is caught.
- **Grounding Guard** catches 100% of hallucinations at threshold=0.6 with only 1 false positive.
- **CoT Auditor** detects deception, goal deviation, and manipulation at 93.3% F1 with zero false positives.

### Shield (Regex) — Why 40% Recall?

The regex shield is intentionally lightweight — it catches known patterns fast with near-zero latency. It is **not** designed for comprehensive coverage. For production use, enable the ML Shield (`ml_shield=True`) which achieves 95% recall, or use ensemble mode (`shield=True, ml_shield={"ensemble": True}`) for maximum coverage.

## Running Benchmarks

```bash
# Run all benchmarks
python benchmarks/run_benchmarks.py

# Run a specific module
python benchmarks/run_benchmarks.py --module ml_shield

# Verbose output (show misses and false positives)
python benchmarks/run_benchmarks.py --verbose

# Export results to JSON (for CI/CD)
python benchmarks/run_benchmarks.py --export benchmarks/results.json
```

## Datasets

All benchmark datasets are in `benchmarks/datasets/`:

| Dataset | File | Samples | Description |
|---------|------|---------|-------------|
| Prompt Injection | `prompt_injection.json` | 70 | Direct overrides, jailbreaks, indirect injections, multilingual, prompt leaks, and safe prompts |
| Toxicity | `toxicity.json` | 55 | Hate speech, violence, self-harm, sexual content, harassment, illegal activity, and safe text |
| Code Safety | `code_safety.json` | 49 | Insecure patterns in Python, JS, SQL, Shell and safe code |
| Grounding | `grounding.json` | 16 | Source-response pairs: grounded vs hallucinated |
| CoT Reasoning | `cot_reasoning.json` | 52 | Aligned vs misaligned reasoning traces across 5 categories |
| PII/Secrets | `pii_secrets.json` | 30 | Emails, SSNs, credit cards, API keys, JWTs, AWS keys, and clean text |

## Metrics

- **Precision**: Of all detections, how many were correct? (Low false positives)
- **Recall**: Of all actual threats, how many were caught? (Low false negatives)
- **F1 Score**: Harmonic mean of precision and recall
- **Accuracy**: Overall correct classifications

## Contributing

To add benchmark samples:
1. Add entries to the relevant JSON file in `benchmarks/datasets/`
2. Run `python benchmarks/run_benchmarks.py --verbose` to verify
3. Submit a PR with the updated dataset and results
