Benchmark Summary
=================

This page condenses the benchmark story into a maintainer-friendly narrative.
For the full tables and runner details, see ``benchmarks/README.md``.

What Looks Strong
-----------------

The current benchmark set shows especially strong results in:

- harmful-content detection on AdvBench and HarmBench when multiple detection
  modules are combined
- exfiltration detection for base64, hex, steganographic, and URL-oriented
  leak patterns
- unicode-injection detection for zero-width, homoglyph, bidi, and tag abuse

These are useful proof points when positioning AgentArmor as a runtime safety
layer rather than a generic moderation API clone.

Where The Repo Should Stay Honest
---------------------------------

Some benchmark areas are still clearly improvement targets:

- ``JailbreakBench`` combined F1: ``71.6%``
- ``RealToxicityPrompts`` F1: ``52.8%``
- ``HaluEval`` false-positive rate: ``50.0%``
- ``TruthfulQA`` recall: ``56.9%``

Those numbers are good enough to discuss openly, but they should be framed as
current baselines to improve rather than final claims of state-of-the-art
performance.

How To Talk About The Results
-----------------------------

Good framing:

- AgentArmor is strongest today on practical runtime controls such as budget
  limits, exfiltration detection, unicode abuse detection, and provider-level
  interception
- the repo includes transparent benchmark methodology and failure analysis
- some detection areas are still actively being tuned

Avoid:

- implying universal best-in-class detection across every safety benchmark
- hiding weaker areas such as subtle toxicity or grounding false positives
- mixing synthetic differentiators into vendor head-to-head claims

Methodology Notes
-----------------

The benchmark setup in this repo already does a few important things well:

- uses fixed seeds for reproducibility
- reports false-positive rates instead of only precision/recall
- separates head-to-head vendor comparisons from AgentArmor-only coverage
- documents failures and exclusions in ``tasks/head-to-head-report/``

For a blog-style narrative that can be adapted into launch copy, see
``benchmark_methodology_narrative.rst``.

Reproducibility Flow
--------------------

For maintainers or evaluators who want to retrace the benchmark story:

1. start with ``benchmarks/README.md`` for the dataset table and runner entry
   points
2. use ``tasks/head-to-head-report/SPEC.md`` for the comparison methodology
3. check ``tasks/head-to-head-report/FAILURES.md`` for exclusions or cells that
   need extra explanation
4. use ``RUNBOOK.md`` for the operational steps behind the published tables

Recommended Launch Position
---------------------------

The safest public message is:

AgentArmor provides practical, local-first runtime protection across Python
agent stacks, with transparent benchmark evidence and a clear view of where
the detection quality is already strong versus where more tuning is underway.
