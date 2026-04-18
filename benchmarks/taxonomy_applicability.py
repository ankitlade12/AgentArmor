"""Head-to-head applicability rubric (SPEC v4 D21, D37, D59).

Declares whether each (baseline, dataset) pair in the head-to-head report is a
methodologically-defensible comparison. Binary verdict (``applies`` |
``does_not_apply``) with prose rationale. For OpenAI Moderation, the
per-dataset category ``projection`` is declared here and consumed by
``OpenAIModerationBaseline.score()`` to form a single scalar.

Adding a new dataset or baseline: append entries to ``APPLIES`` covering every
(baseline, dataset) pair. ``ensure_complete()`` enforces this at CI time.
Reviewers: @rubric-owners (see CODEOWNERS). If blocked >5 business days on
rubric review, break-glass per FAILURES.md D29.

Template
--------
    ("<baseline>", "<dataset>"): Applicability(
        verdict="applies",  # or "does_not_apply"
        rationale="One-sentence justification citing the baseline's taxonomy vs dataset construct.",
        projection=("hate", "violence"),  # OpenAI Moderation only; None elsewhere
    ),
"""

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

RUBRIC_VERSION = "1.0"


@dataclass(frozen=True)
class Applicability:
    """Verdict plus rationale for one (baseline, dataset) pair.

    ``projection`` names the OpenAI Moderation category subset to reduce to a
    scalar (max over projected categories). Must be ``None`` for other
    baselines; they emit a single score already.
    """

    verdict: Literal["applies", "does_not_apply"]
    rationale: str
    projection: Optional[Tuple[str, ...]] = None


# OpenAI Moderation category subsets keyed by dataset construct.
_TOXICITY_CATS: Tuple[str, ...] = ("hate", "harassment", "violence")
_HATE_CATS: Tuple[str, ...] = ("hate", "harassment")
_JAILBREAK_CATS: Tuple[str, ...] = (
    "illicit",
    "self_harm",
    "violence",
    "sexual_minors",
)
_HARMFUL_CATS: Tuple[str, ...] = (
    "illicit",
    "self_harm",
    "violence",
    "sexual_minors",
    "hate",
)
_BROAD_SAFETY_CATS: Tuple[str, ...] = (
    "hate",
    "harassment",
    "violence",
    "sexual",
    "self_harm",
)


APPLIES: Dict[Tuple[str, str], Applicability] = {
    # LlamaGuard — broad safety classifier; applies to all 6.
    ("llamaguard", "xstest"): Applicability(
        verdict="applies",
        rationale="LlamaGuard 3 covers refusal categories relevant to XSTest over-refusal tests.",
    ),
    ("llamaguard", "realtoxicityprompts"): Applicability(
        verdict="applies",
        rationale="LlamaGuard's S10 (Hate) and S2 (Violent Crimes) taxonomy overlaps RTP toxicity labels.",
    ),
    ("llamaguard", "toxigen"): Applicability(
        verdict="applies",
        rationale="LlamaGuard's hate-speech category (S10) matches ToxiGen's construct.",
    ),
    ("llamaguard", "harmbench"): Applicability(
        verdict="applies",
        rationale="LlamaGuard covers HarmBench's harmful-behavior taxonomy via S1-S9.",
    ),
    ("llamaguard", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="LlamaGuard recognizes jailbreak-adjacent unsafe outputs across S1-S13.",
    ),
    ("llamaguard", "advbench"): Applicability(
        verdict="applies",
        rationale="LlamaGuard covers AdvBench's adversarial-jailbreak targets via broad safety taxonomy.",
    ),
    # OpenAI Moderation — per-dataset category projection (D37).
    ("openai_moderation", "xstest"): Applicability(
        verdict="applies",
        rationale="Broad safety projection matches XSTest's mix of over-refusal trigger categories.",
        projection=_BROAD_SAFETY_CATS,
    ),
    ("openai_moderation", "realtoxicityprompts"): Applicability(
        verdict="applies",
        rationale="Toxicity projection (hate+harassment+violence) maps to RTP labels.",
        projection=_TOXICITY_CATS,
    ),
    ("openai_moderation", "toxigen"): Applicability(
        verdict="applies",
        rationale="Hate projection maps directly to ToxiGen's hate-speech construct.",
        projection=_HATE_CATS,
    ),
    ("openai_moderation", "harmbench"): Applicability(
        verdict="applies",
        rationale="Harmful-behavior projection covers HarmBench's illicit/self-harm/violence categories.",
        projection=_HARMFUL_CATS,
    ),
    ("openai_moderation", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="Jailbreak projection targets the unsafe-output categories jailbreaks typically elicit.",
        projection=_JAILBREAK_CATS,
    ),
    ("openai_moderation", "advbench"): Applicability(
        verdict="applies",
        rationale="Jailbreak projection matches AdvBench's adversarial-jailbreak construct.",
        projection=_JAILBREAK_CATS,
    ),
    # Perspective — toxicity-only scorer; does not apply to harmful-behavior / jailbreak datasets.
    ("perspective", "xstest"): Applicability(
        verdict="applies",
        rationale="Perspective TOXICITY covers XSTest's toxic-trigger subset of over-refusal tests.",
    ),
    ("perspective", "realtoxicityprompts"): Applicability(
        verdict="applies",
        rationale="RTP is Perspective's home turf — direct toxicity labeling.",
    ),
    ("perspective", "toxigen"): Applicability(
        verdict="applies",
        rationale="Perspective TOXICITY overlaps ToxiGen's hate-as-toxicity construct.",
    ),
    ("perspective", "harmbench"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective measures toxicity, not harmful-behavior elicitation. Jailbreaks and illicit-behavior requests are typically not toxic in surface form.",
    ),
    ("perspective", "jailbreakbench"): Applicability(
        verdict="does_not_apply",
        rationale="Jailbreak prompts are not inherently toxic; Perspective would systematically under-flag.",
    ),
    ("perspective", "advbench"): Applicability(
        verdict="does_not_apply",
        rationale="AdvBench adversarial jailbreaks are not framed as toxic content; out of Perspective's scope.",
    ),
    # Mock baseline — present for test coverage of the runner's full matrix.
    ("mock_scored", "xstest"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "realtoxicityprompts"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "toxigen"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "harmbench"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "advbench"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
}


def ensure_complete(baselines: List[str], datasets: List[str]) -> None:
    """Raise ``ValueError`` if any (baseline, dataset) pair is missing from APPLIES.

    CI calls this with the runtime list of registered baselines + adapters so
    new datasets or baselines trigger a loud failure until rubric is updated.
    """
    missing = [
        (b, d) for b in baselines for d in datasets if (b, d) not in APPLIES
    ]
    if missing:
        raise ValueError(
            f"Taxonomy rubric missing {len(missing)} pair(s): {missing}.\n"
            f"Add entries to APPLIES in benchmarks/taxonomy_applicability.py "
            f"following the template in the module docstring.\n"
            f"Reviewers: @rubric-owners (see CODEOWNERS).\n"
            f"Break-glass if blocked >5 business days: see "
            f"tasks/head-to-head-report/FAILURES.md D29."
        )


def get_projection(baseline: str, dataset: str) -> Optional[Tuple[str, ...]]:
    """Return the OpenAI Moderation category projection for a cell, or None."""
    entry = APPLIES.get((baseline, dataset))
    return entry.projection if entry else None
