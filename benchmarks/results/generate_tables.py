#!/usr/bin/env python3
"""Generate markdown tables from benchmark result JSON files."""
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent
BENCHMARKS_DIR = RESULTS_DIR.parent
README_PATH = BENCHMARKS_DIR / "README.md"


def load_json(filename: str) -> dict:
    path = RESULTS_DIR / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def generate_smoke_table(data: dict) -> str:
    if not data or "modules" not in data:
        return ""
    lines = [
        "### Curated Smoke Tests",
        "",
        "| Module | Samples | Accuracy | Precision | Recall | F1 | Time |",
        "|--------|---------|----------|-----------|--------|----|------|",
    ]
    for name, m in data["modules"].items():
        if m.get("errors"):
            continue
        lines.append(
            f"| {name} | {m['total_samples']} | {format_pct(m['accuracy'])} | "
            f"{format_pct(m['precision'])} | {format_pct(m['recall'])} | "
            f"**{format_pct(m['f1'])}** | {m['duration_ms']:.0f}ms |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_industry_table(data: dict) -> str:
    if not data or "modules" not in data:
        return ""

    # Group by dataset (encoded in module name as "Module on Dataset")
    lines = [
        "### Industry Benchmark Results",
        "",
        "| Benchmark | Module | Samples | Accuracy | Precision | Recall | F1 | FP Rate |",
        "|-----------|--------|---------|----------|-----------|--------|----|---------|",
    ]
    for name, m in data["modules"].items():
        if m.get("errors"):
            continue
        fp_rate = m.get("false_positive_rate", 0)
        lines.append(
            f"| {name} | - | {m['total_samples']} | {format_pct(m['accuracy'])} | "
            f"{format_pct(m['precision'])} | {format_pct(m['recall'])} | "
            f"**{format_pct(m['f1'])}** | {format_pct(fp_rate)} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_e2e_table(data: dict) -> str:
    if not data or "scenarios" not in data:
        return ""

    lines = ["### End-to-End Multi-Provider Results", ""]

    for scenario_name, models in data["scenarios"].items():
        title = scenario_name.replace("_", " ").title()
        lines.append(f"#### {title}")
        lines.append("")
        lines.append("| Model | Provider | Samples | Accuracy | Precision | Recall | F1 | FP Rate |")
        lines.append("|-------|----------|---------|----------|-----------|--------|----|---------|")

        for model_name, m in models.items():
            provider = m.get("provider", "unknown")
            fp_rate = m.get("false_positive_rate", 0)
            lines.append(
                f"| {model_name} | {provider} | {m.get('total_samples', 0)} | "
                f"{format_pct(m.get('accuracy', 0))} | {format_pct(m.get('precision', 0))} | "
                f"{format_pct(m.get('recall', 0))} | **{format_pct(m.get('f1', 0))}** | "
                f"{format_pct(fp_rate)} |"
            )
        lines.append("")

    return "\n".join(lines)


def generate_full_readme():
    """Generate the complete benchmarks README from all available results."""
    smoke = load_json("smoke_results.json")
    industry = load_json("industry_results.json")
    e2e = load_json("e2e_results.json")

    sections = [
        "# AgentArmor Benchmark Results",
        "",
        "Auto-generated from benchmark runs. Do not edit manually.",
        "",
        "## Overview",
        "",
        "AgentArmor benchmarks are organized in three tiers:",
        "- **Tier A: Smoke Tests** — 272 curated samples, runs in <1s, zero dependencies",
        "- **Tier B: Industry Benchmarks** — Evaluated against JailbreakBench, XSTest, HarmBench, HaluEval, RealToxicityPrompts, ToxiGen, and more",
        "- **Tier C: E2E Multi-Provider** — End-to-end tests across OpenAI, Anthropic, and Google models",
        "",
    ]

    # Smoke tests
    smoke_table = generate_smoke_table(smoke)
    if smoke_table:
        sections.append("## Tier A: Curated Smoke Tests")
        sections.append("")
        sections.append(smoke_table)

    # Industry
    industry_table = generate_industry_table(industry)
    if industry_table:
        sections.append("## Tier B: Industry Benchmarks")
        sections.append("")
        sections.append("Tested against recognized academic and industry datasets.")
        sections.append("")
        sections.append(industry_table)

    # E2E
    e2e_table = generate_e2e_table(e2e)
    if e2e_table:
        sections.append("## Tier C: End-to-End Multi-Provider")
        sections.append("")
        sections.append("Results vary by model — AgentArmor's pre-request shields block identically across models,")
        sections.append("but post-response filtering depends on what each model generates.")
        sections.append("")
        sections.append(e2e_table)

    # Methodology
    sections.extend([
        "## Methodology",
        "",
        "- **Sampling**: Large datasets (>1K samples) are stratified-sampled to 500 by default (seed=42)",
        "- **Metrics**: Standard binary classification — Precision, Recall, F1 Score, Accuracy",
        "- **Thresholds**: ML Shield threshold=0.5, Grounding threshold=0.6, Toxicity uses pattern matching",
        "- **Reproducibility**: All benchmarks use fixed random seeds. Results may vary with model updates.",
        "",
        "## Running Benchmarks",
        "",
        "```bash",
        "# Tier A: Smoke tests (no deps)",
        "python benchmarks/run_benchmarks.py",
        "",
        "# Tier B: Industry benchmarks (needs: pip install datasets)",
        "python benchmarks/run_industry_benchmarks.py",
        "",
        "# Tier C: E2E (needs API keys in .env)",
        "python benchmarks/run_e2e_benchmarks.py",
        "```",
        "",
    ])

    return "\n".join(sections)


def main():
    readme_content = generate_full_readme()

    with open(README_PATH, "w") as f:
        f.write(readme_content)

    print(f"  Generated {README_PATH}")
    print(f"  Sections: smoke={'yes' if load_json('smoke_results.json') else 'no'}, "
          f"industry={'yes' if load_json('industry_results.json') else 'no'}, "
          f"e2e={'yes' if load_json('e2e_results.json') else 'no'}")


if __name__ == "__main__":
    main()
