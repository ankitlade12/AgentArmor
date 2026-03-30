# AgentArmor Benchmark Results

Evaluated against **10 industry-standard datasets** and 4,600+ samples across prompt injection, toxicity, hallucination detection, and data exfiltration.

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

## Tier B: Industry Benchmarks (Baseline)

Tested against recognized academic and industry datasets using default module configurations. All results use 200 stratified samples per dataset (seed=42).

### Prompt Injection / Harmful Content Detection

| Benchmark | Module | Samples | Precision | Recall | F1 | FP Rate |
|:----------|:-------|--------:|:---------:|:------:|---:|--------:|
| AdvBench | **COMBINED** | 200 | 100.0% | 46.7% | **63.7%** | 0.0% |
| AdvBench | ML Shield | 200 | 100.0% | 31.5% | 47.9% | 0.0% |
| AdvBench | Toxicity | 200 | 100.0% | 16.2% | 27.9% | 0.0% |
| HarmBench | **COMBINED** | 200 | 100.0% | 19.5% | **32.6%** | 0.0% |
| HarmBench | ML Shield | 200 | 100.0% | 15.8% | 27.3% | 0.0% |
| JailbreakBench | **COMBINED** | 200 | 60.0% | 9.0% | **15.7%** | 6.0% |
| JailbreakBench | ML Shield | 200 | 60.0% | 9.0% | 15.7% | 6.0% |

### Toxicity Detection

| Benchmark | Type | Samples | Precision | Recall | F1 | FP Rate |
|:----------|:-----|--------:|:---------:|:------:|---:|--------:|
| RealToxicityPrompts | Subtle toxicity | 200 | 100.0% | 1.0% | **2.0%** | 0.0% |
| ToxiGen | Implicit hate (13 groups) | 200 | 100.0% | 0.5% | **1.0%** | 0.0% |
| XSTest | Over-refusal test | 200 | 50.0% | 2.3% | **4.3%** | 1.8% |

### Hallucination / Grounding Detection

| Benchmark | Type | Samples | Precision | Recall | F1 | FP Rate |
|:----------|:-----|--------:|:---------:|:------:|---:|--------:|
| TruthfulQA | Factual grounding | 200 | 100.0% | 22.5% | **36.7%** | 0.0% |
| HaluEval | QA/dialogue/summarization | 200 | 50.7% | 34.0% | **40.7%** | 33.0% |

### Data Exfiltration Detection

| Benchmark | Type | Samples | Precision | Recall | F1 | FP Rate |
|:----------|:-----|--------:|:---------:|:------:|---:|--------:|
| Exfiltration | Base64/hex/steg/URL | 61 | 100.0% | 100.0% | **100.0%** | 0.0% |

## Datasets

| Dataset | Source | License | What It Tests |
|:--------|:-------|:--------|:-------------|
| [AdvBench](https://github.com/llm-attacks/llm-attacks) | GitHub | MIT | Adversarial harmful strings |
| [HarmBench](https://github.com/centerforaisafety/HarmBench) | GitHub/HuggingFace | MIT | 510 harmful behaviors (7 domains) |
| [JailbreakBench](https://jailbreakbench.github.io/) | HuggingFace | MIT | Jailbreak/injection detection |
| [XSTest](https://huggingface.co/datasets/Paul/XSTest) | HuggingFace | CC-BY-4.0 | Over-refusal / false positives |
| [ToxiGen](https://huggingface.co/datasets/toxigen/toxigen-data) | HuggingFace | Research | Implicit hate speech (13 groups) |
| [RealToxicityPrompts](https://huggingface.co/datasets/allenai/real-toxicity-prompts) | HuggingFace | Apache 2.0 | 100K prompts with toxicity scores |
| [TruthfulQA](https://huggingface.co/datasets/truthfulqa/truthful_qa) | HuggingFace | Apache 2.0 | 817 factual Q&A pairs |
| [HaluEval](https://huggingface.co/datasets/pminervini/HaluEval) | HuggingFace | CC-BY-SA-4.0 | Hallucination detection (35K) |
| [ToxicChat](https://huggingface.co/datasets/lmsys/toxic-chat) | HuggingFace | Various | Real user-chatbot toxic conversations |
| Exfiltration | Synthetic (built-in) | MIT | Base64/hex/steganography/URL exfil |

## Key Takeaways

- **100% precision on most benchmarks** — when AgentArmor flags content, it's almost always correct (zero false positives on AdvBench, HarmBench, TruthfulQA, ToxiGen, RealToxicity)
- **100% F1 on exfiltration** — catches base64/hex-encoded PII, steganographic data, and URL-based exfiltration perfectly
- **Recall is the bottleneck** — baseline regex/TF-IDF modules have high precision but miss subtle attacks. The [module-upgrades](https://github.com/ankitlade12/AgentArmor/tree/feature/module-upgrades) branch adds expanded training data and TF-IDF classifiers for significantly improved recall
- **FP Rate column** — shows exactly how often safe content is incorrectly blocked. Most modules have 0.0% FPR

## Methodology

- **Sampling**: Large datasets stratified-sampled to 200 per benchmark (seed=42)
- **Metrics**: Standard binary classification — Precision, Recall, F1 Score, Accuracy, **False Positive Rate** (FP / (FP + TN))
- **Combined scoring**: Detects if ANY module (shield, ML shield, toxicity) fires — reflects real production behavior
- **Thresholds**: ML Shield=0.85 (default), Toxicity=pattern-matching, Grounding=0.6
- **Module versions**: Baseline (main branch, default configs). No benchmark-specific tuning applied.
- **Reproducibility**: Fixed random seeds. `pip install datasets && python benchmarks/run_industry_benchmarks.py`
- **No LLM API calls needed**: All Tier B benchmarks run locally

## Running Benchmarks

```bash
# Tier A: Smoke tests (no deps, <1s)
python benchmarks/run_benchmarks.py

# Tier B: Industry benchmarks (needs: pip install datasets scikit-learn)
python benchmarks/run_industry_benchmarks.py

# List all available datasets
python benchmarks/run_industry_benchmarks.py --list

# Run a specific dataset with verbose output
python benchmarks/run_industry_benchmarks.py --dataset truthfulqa --verbose

# Tier C: E2E multi-provider (needs API keys in .env)
python benchmarks/run_e2e_benchmarks.py --dry-run
```
