# AgentArmor Benchmark Results

Evaluated against **10 industry-standard datasets** and 4,800+ samples across prompt injection, toxicity, hallucination detection, and bias.

## Tier A: Curated Smoke Tests

272 hand-curated samples, 7 modules, runs in <1s, zero dependencies.

| Module | Samples | Accuracy | Precision | Recall | F1 | Time |
|--------|--------:|:--------:|:---------:|:------:|---:|-----:|
| Shield (Regex) | 70 | 64.3% | 94.1% | 40.0% | **56.1%** | 1ms |
| ML Shield (TF-IDF) | 70 | 94.3% | 95.0% | 95.0% | **95.0%** | 627ms |
| Toxicity Filter | 55 | 89.1% | 100.0% | 82.9% | **90.6%** | 2ms |
| Code Shield | 49 | 91.8% | 96.8% | 90.9% | **93.8%** | 1ms |
| Grounding Guard | 16 | 93.8% | 88.9% | 100.0% | **94.1%** | 2ms |
| CoT Auditor | 52 | 92.3% | 100.0% | 87.5% | **93.3%** | 3ms |
| PII/Secrets Filter | 30 | 100.0% | 100.0% | 100.0% | **100.0%** | 0ms |

## Tier B: Industry Benchmarks

Tested against recognized academic and industry datasets. All results use 200 stratified samples per dataset (seed=42).

### Prompt Injection / Harmful Content Detection

| Benchmark | Module | Samples | Precision | Recall | F1 |
|:----------|:-------|--------:|:---------:|:------:|---:|
| AdvBench | **COMBINED** | 200 | 100.0% | 91.9% | **95.8%** |
| AdvBench | ML Shield | 200 | 100.0% | 81.7% | 89.9% |
| AdvBench | Toxicity ML | 200 | 100.0% | 89.8% | 94.7% |
| AdvBench | Shield (Regex) | 200 | 100.0% | 11.7% | 20.9% |
| HarmBench | **COMBINED** | 200 | 100.0% | 90.0% | **94.7%** |
| HarmBench | ML Shield | 200 | 100.0% | 79.5% | 88.6% |
| HarmBench | Toxicity ML | 200 | 100.0% | 79.5% | 88.6% |
| JailbreakBench | **COMBINED** | 200 | 70.2% | 73.0% | **71.6%** |
| JailbreakBench | ML Shield | 200 | 69.3% | 70.0% | 69.7% |

### Toxicity Detection

| Benchmark | Type | Samples | Precision | Recall | F1 |
|:----------|:-----|--------:|:---------:|:------:|---:|
| ToxiGen | Implicit hate (13 groups) | 200 | 100.0% | 58.5% | **73.8%** |
| BBQ | Bias (9 dimensions) | 200 | 64.7% | 73.2% | **68.7%** |
| RealToxicityPrompts | Subtle toxicity | 200 | 54.8% | 51.0% | **52.8%** |
| XSTest | Over-refusal test | 200 | 83.3% | 11.4% | **20.0%** |

### Hallucination / Grounding Detection

| Benchmark | Type | Samples | Precision | Recall | F1 |
|:----------|:-----|--------:|:---------:|:------:|---:|
| TruthfulQA | Factual grounding | 200 | 100.0% | 56.9% | **72.5%** |
| HaluEval | QA/dialogue/summarization | 200 | 62.7% | 84.0% | **71.8%** |

### Data Exfiltration Detection

| Benchmark | Type | Samples | Precision | Recall | F1 |
|:----------|:-----|--------:|:---------:|:------:|---:|
| Exfiltration | Base64/hex/steg/URL | 61 | 100.0% | 71.0% | **83.0%** |

## Datasets

| Dataset | Source | License | What It Tests |
|:--------|:-------|:--------|:-------------|
| [AdvBench](https://github.com/llm-attacks/llm-attacks) | GitHub | MIT | Adversarial harmful strings |
| [HarmBench](https://github.com/centerforaisafety/HarmBench) | GitHub/HuggingFace | MIT | 510 harmful behaviors (7 domains) |
| [JailbreakBench](https://jailbreakbench.github.io/) | HuggingFace | MIT | Jailbreak/injection detection |
| [XSTest](https://huggingface.co/datasets/Paul/XSTest) | HuggingFace | CC-BY-4.0 | Over-refusal / false positives |
| [ToxiGen](https://huggingface.co/datasets/toxigen/toxigen-data) | HuggingFace | Research | Implicit hate speech (13 groups) |
| [BBQ](https://huggingface.co/datasets/lighteval/bbq_helm) | HuggingFace | CC-BY-4.0 | Bias across 9 social dimensions |
| [RealToxicityPrompts](https://huggingface.co/datasets/allenai/real-toxicity-prompts) | HuggingFace | Apache 2.0 | 100K prompts with toxicity scores |
| [TruthfulQA](https://huggingface.co/datasets/truthfulqa/truthful_qa) | HuggingFace | Apache 2.0 | 817 factual Q&A pairs |
| [HaluEval](https://huggingface.co/datasets/pminervini/HaluEval) | HuggingFace | CC-BY-SA-4.0 | Hallucination detection (35K) |
| [ToxicChat](https://huggingface.co/datasets/lmsys/toxic-chat) | HuggingFace | Various | Real user-chatbot toxic conversations |
| Exfiltration | Synthetic (built-in) | MIT | Base64/hex/steganography/URL exfil |

## Key Takeaways

- **96% F1 on AdvBench** and **95% on HarmBench** — combined detection catches nearly all harmful content with zero false positives
- **100% precision** on most benchmarks — when AgentArmor flags content, it's almost always correct
- **74% on ToxiGen** — catches *implicit* hate speech, not just explicit slurs
- **73% on TruthfulQA** — TF-IDF semantic similarity enables hallucination detection
- **83% on exfiltration** — catches base64/hex-encoded PII, steganography, and URL exfiltration
- **83% precision on XSTest** — low false positive rate on safe prompts (up from 51%)
- **Regex Shield alone is weak** (0-21% F1) — always use `ml_shield=True` or combined mode for production

## Methodology

- **Sampling**: Large datasets stratified-sampled to 200 per benchmark (seed=42)
- **Metrics**: Standard binary classification — Precision, Recall, F1 Score, Accuracy
- **Combined scoring**: Detects if ANY module (shield, ML shield, toxicity) fires — reflects real production behavior
- **Thresholds**: ML Shield=0.55, Toxicity ML=0.6, Grounding=0.6
- **Reproducibility**: Fixed random seeds. `pip install datasets && python benchmarks/run_industry_benchmarks.py`
- **No LLM API calls needed**: All benchmarks run locally against AgentArmor's detection modules

## Running Benchmarks

```bash
# Tier A: Smoke tests (no deps, <1s)
python benchmarks/run_benchmarks.py

# Tier B: Industry benchmarks (needs: pip install datasets scikit-learn)
python benchmarks/run_industry_benchmarks.py

# List all available datasets
python benchmarks/run_industry_benchmarks.py --list

# Run a specific dataset
python benchmarks/run_industry_benchmarks.py --dataset truthfulqa --verbose

# Tier C: E2E multi-provider (needs API keys in .env)
python benchmarks/run_e2e_benchmarks.py --dry-run
```
