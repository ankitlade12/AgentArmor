# Head-to-head Benchmark Specification

This document is the lightweight methodology companion for:

- `BENCHMARKS_HEAD_TO_HEAD.md`
- `benchmarks/run_head_to_head.py`
- `RUNBOOK.md`

It exists so benchmark claims in the repo point to a real, versioned
methodology document rather than an internal-only path.

## Scope

The head-to-head comparison measures AgentArmor against external baselines on
representative safety datasets. The current comparison focuses on:

- prompt-injection and jailbreak-style prompts
- harmful-content and toxicity datasets
- over-refusal / false-positive pressure tests

## Principles

1. Publish per-dataset numbers, not a single universal winner claim.
2. Prefer reproducibility over headline metrics.
3. Keep baseline operating points explicit.
4. Annotate notable losses and ties honestly.
5. Preserve methodology and operations as separate documents.

## Current Baselines

- AgentArmor shipping modules and combined configurations
- LlamaGuard 3 via `llama-cpp-python`
- OpenAI Moderation

Perspective API is excluded from the current v1 comparison because the service
has a public end-of-life date and would make the comparison hard to reproduce
over time.

## Measurement Rules

- Report per-dataset F1 when appropriate for the dataset shape
- Use MCC and balanced accuracy on imbalanced datasets where F1 alone would be
  misleading
- Keep regex-only modules as boolean classifiers; do not fabricate PR curves
- Record latency percentiles alongside quality metrics
- Keep raw-response retention opt-in for local debugging only

## Reproducibility Rules

- Pin benchmark dependencies tightly enough to avoid accidental drift
- Use deterministic seeds for bootstrap confidence intervals
- Treat adapter or config changes as run-invalidating for resume flows
- Keep methodology references stable from README and benchmark docs

## Documents

- Operations: [RUNBOOK.md](/Users/ankithemantlade/Desktop/AgentArmor/RUNBOOK.md)
- Published results: [BENCHMARKS_HEAD_TO_HEAD.md](/Users/ankithemantlade/Desktop/AgentArmor/BENCHMARKS_HEAD_TO_HEAD.md)
- Type/logprob walkthrough: [TYPE_WALKTHROUGH.md](/Users/ankithemantlade/Desktop/AgentArmor/tasks/head-to-head-report/TYPE_WALKTHROUGH.md)
