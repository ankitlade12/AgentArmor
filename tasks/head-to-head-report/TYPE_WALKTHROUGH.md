# Head-to-head Type Walkthrough

This note explains the main data-shape assumptions behind the head-to-head
benchmark runner, especially for LlamaGuard score extraction.

## Goal

When a baseline exposes token-level scores or logprobs, the runner should
convert them into a stable numeric score that can be used for thresholded
evaluation and PR-style analysis.

When that score path is unavailable, the runner should fall back to a simpler
boolean verdict without pretending a real score exists.

## LlamaGuard Path

For local LlamaGuard runs:

1. Inspect the returned token/logprob structure.
2. Extract a usable unsafe-vs-safe score when the output shape supports it.
3. If the expected logprob shape is missing, malformed, or provider behavior
   changes, fall back to a boolean unsafe/safe parse.

That fallback keeps the benchmark runnable, but it also means:

- PR curves may be unavailable for that cell
- the cell should be treated as 0/1 verdict-only
- documentation should note the reduced score fidelity

## Why This Matters

Head-to-head comparisons are easy to overstate. A runner that silently changes
from scored predictions to boolean heuristics can make charts look comparable
when they are not. This walkthrough exists so maintainers can quickly verify
which path a run used.

## Maintainer Check

Before trusting a fresh LlamaGuard run:

1. verify the model loads successfully
2. confirm the score path returns the expected shape
3. confirm the fallback path is logged clearly if used
4. avoid mixing scored and fallback runs in the same published narrative
