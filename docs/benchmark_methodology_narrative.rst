Benchmark Methodology Narrative
===============================

AgentArmor's benchmark story is meant to be reproducible, not magical. The
project reports where runtime controls are strong, where specialist detectors
still need tuning, and which comparisons are not valid enough to publish.

The Short Version
-----------------

AgentArmor is a local-first runtime safety layer for Python agents. Benchmarks
therefore measure two different things:

- whether runtime modules block practical risks such as prompt injection,
  hidden unicode payloads, encoded exfiltration, and runaway spend
- how AgentArmor's classifiers compare with external safety baselines on
  datasets where the taxonomies overlap

Those are related but not identical. A tool that protects an agent workflow can
be useful even when one detector is not the best classifier for every public
dataset. The docs should preserve that distinction.

What We Measure
---------------

The industry benchmark suite covers prompt injection, harmful-content
elicitation, toxicity, hallucination-style grounding failures, exfiltration,
and unicode attacks. The head-to-head comparison focuses on six datasets where
AgentArmor can be compared against LlamaGuard 3 and OpenAI Moderation with
per-sample verdicts.

The public tables report per-dataset metrics instead of a single overall
winner. This avoids hiding important shape differences between datasets. For
example, an over-refusal benchmark says something different from a harmful
instruction benchmark, even if both can be squeezed into a binary classifier
table.

Why Some Cells Are Missing
--------------------------

Some baseline/dataset combinations are intentionally excluded. A moderation API
designed around toxicity categories is not always a meaningful baseline for
jailbreak prompts that are benign on the surface. Similarly, Perspective API is
not included in the current v1 head-to-head because the service has a public
end-of-life date, which would make the comparison difficult to reproduce.

Missing cells are not a coverage trick. They are a guardrail against publishing
numbers that look precise but answer the wrong question.

How To Reproduce
----------------

Use these entry points when auditing or rerunning the benchmark story:

1. ``benchmarks/README.md`` for the broad industry benchmark summary
2. ``BENCHMARKS_HEAD_TO_HEAD.md`` for the generated comparison tables
3. ``tasks/head-to-head-report/SPEC.md`` for methodology rules
4. ``tasks/head-to-head-report/FAILURES.md`` for failure and exclusion policy
5. ``RUNBOOK.md`` for operational procedures

The head-to-head runner records sidecars and hashes so resume flows do not
silently mix old adapter behavior with new adapter behavior. Raw model
responses are not committed by default; local debugging can opt into retaining
them.

Current Honest Read
-------------------

The strongest current story is practical runtime protection:

- provider-surface interception without a hosted proxy
- budget controls for multi-step agents
- prompt-injection blocking before provider calls
- encoded exfiltration and unicode-abuse detection
- MCP server, tool, path, and result policy checks

The areas that should stay framed as active tuning targets include subtle
toxicity, grounding false positives, and over-refusal behavior on XSTest-style
prompts. Public claims should make that clear.

Launch-Ready Framing
--------------------

A good public summary is:

AgentArmor gives Python agent builders a local-first runtime safety layer with
transparent benchmark evidence, strong practical controls, and a clear record
of where classifier quality is still improving.

