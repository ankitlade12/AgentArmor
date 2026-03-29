# Industry Benchmark Datasets

AgentArmor benchmarks against the following industry-standard datasets.
Datasets are downloaded at runtime via the HuggingFace `datasets` library
and cached in `~/.cache/huggingface/datasets/`.

## Dataset Sources & Licenses

| Dataset | Source | License | Size | Paper |
|---------|--------|---------|------|-------|
| JailbreakBench | `JailbreakBench/JBB-Behaviors` | MIT | 100 behaviors | NeurIPS 2024 |
| XSTest | `walledai/XSTest` | CC-BY-4.0 | 450 prompts | ACL 2024 |
| HarmBench | `centerforaisafety/HarmBench` | MIT | 510 behaviors | ICML 2024 |
| AdvBench | `llm-attacks/llm-attacks` | MIT | 520 strings | NeurIPS 2023 |
| TruthfulQA | `truthfulqa/truthful_qa` | Apache 2.0 | 817 questions | ACL 2022 |
| HaluEval | `pminervini/HaluEval` | CC-BY-SA-4.0 | 35K samples | EMNLP 2023 |
| RealToxicityPrompts | `allenai/real-toxicity-prompts` | Apache 2.0 | 100K prompts | Findings of ACL 2020 |
| ToxiGen | `toxigen/toxigen-data` | Custom (research) | 274K statements | ACL 2022 |
| GuardBench | `AmenRa/GuardBench` | Apache 2.0 | 40 sub-datasets | EMNLP 2024 |
| BBQ | `heegyu/bbq` | CC-BY-4.0 | 58K instances | ACL 2022 |

## Caching

Datasets are cached locally by the HuggingFace `datasets` library:
- Default cache dir: `~/.cache/huggingface/datasets/`
- Set `HF_HOME` env var to customize cache location
- First run downloads datasets; subsequent runs use cache
- Large datasets (RealToxicity, ToxiGen) are streamed and sampled

## Gated Datasets

Some datasets may require a HuggingFace token:
```bash
export HF_TOKEN=hf_your_token_here
```

## No Data Committed

No dataset files are committed to this repository. All data is downloaded
at runtime. This ensures license compliance and keeps the repo lightweight.
