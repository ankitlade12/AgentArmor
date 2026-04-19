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
    ("llamaguard", "realtoxicity"): Applicability(
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
    ("openai_moderation", "realtoxicity"): Applicability(
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
    # Perspective API — excluded from v1 head-to-head. Google/Jigsaw announced
    # shutdown: no new access requests after Feb 2026, full API EOL Dec 31 2026.
    # Any published comparison against Perspective would be non-reproducible for
    # readers by the time the doc is live. Entries kept in the rubric (rather
    # than deleted) so the `does_not_apply` appendix transparently explains why.
    ("perspective", "xstest"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API is being sunset by Google/Jigsaw (no new requests after Feb 2026; API EOL 2026-12-31). Excluded from v1 to keep the comparison reproducible beyond the sunset date.",
    ),
    ("perspective", "realtoxicity"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API sunset (see sibling entries). Historical Perspective/RTP numbers are documented in the original Perspective papers; we did not attempt to replicate them against a dying API.",
    ),
    ("perspective", "toxigen"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API sunset (see sibling entries).",
    ),
    ("perspective", "harmbench"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API sunset + taxonomic mismatch (toxicity != harmful-behavior elicitation).",
    ),
    ("perspective", "jailbreakbench"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API sunset + taxonomic mismatch (jailbreak prompts rarely toxic in surface form).",
    ),
    ("perspective", "advbench"): Applicability(
        verdict="does_not_apply",
        rationale="Perspective API sunset + taxonomic mismatch with adversarial jailbreaks.",
    ),
    # AgentArmor modules — the left-hand side of the head-to-head. All three
    # are evaluated across all six main datasets at their ship-default config.
    # Each is applied as `applies` so readers see both wins and losses honestly.
    ("agentarmor_shield", "xstest"): Applicability(
        verdict="applies",
        rationale="Regex shield targets refusal-triggering injection patterns; XSTest's hard cases probe over-refusal.",
    ),
    ("agentarmor_shield", "realtoxicity"): Applicability(
        verdict="applies",
        rationale="Regex shield runs on text surface; reveals recall floor when toxicity isn't injection-styled.",
    ),
    ("agentarmor_shield", "toxigen"): Applicability(
        verdict="applies",
        rationale="Regex shield applied to hate-speech surface for cross-construct recall evidence.",
    ),
    ("agentarmor_shield", "harmbench"): Applicability(
        verdict="applies",
        rationale="Regex shield targets harmful-behavior elicitation prompts.",
    ),
    ("agentarmor_shield", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="Regex shield directly targets jailbreak construct.",
    ),
    ("agentarmor_shield", "advbench"): Applicability(
        verdict="applies",
        rationale="Regex shield targets adversarial jailbreaks.",
    ),
    ("agentarmor_ml_shield", "xstest"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier trained on prompt-injection corpus; XSTest tests over-refusal.",
    ),
    ("agentarmor_ml_shield", "realtoxicity"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier applied to toxicity surface for cross-construct comparison.",
    ),
    ("agentarmor_ml_shield", "toxigen"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier on hate-speech surface.",
    ),
    ("agentarmor_ml_shield", "harmbench"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier on harmful-behavior prompts.",
    ),
    ("agentarmor_ml_shield", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier on jailbreak prompts — core training construct.",
    ),
    ("agentarmor_ml_shield", "advbench"): Applicability(
        verdict="applies",
        rationale="TF-IDF classifier on adversarial jailbreaks.",
    ),
    ("agentarmor_toxicity", "xstest"): Applicability(
        verdict="applies",
        rationale="Toxicity filter applied to XSTest's toxic-trigger subset.",
    ),
    ("agentarmor_toxicity", "realtoxicity"): Applicability(
        verdict="applies",
        rationale="Toxicity filter on RTP — core domain.",
    ),
    ("agentarmor_toxicity", "toxigen"): Applicability(
        verdict="applies",
        rationale="Toxicity filter on hate speech — core domain.",
    ),
    ("agentarmor_toxicity", "harmbench"): Applicability(
        verdict="applies",
        rationale="Toxicity filter applied for cross-construct recall baseline.",
    ),
    ("agentarmor_toxicity", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="Toxicity filter applied across jailbreak surface.",
    ),
    ("agentarmor_toxicity", "advbench"): Applicability(
        verdict="applies",
        rationale="Toxicity filter applied across adversarial jailbreak surface.",
    ),
    # Combined AgentArmor — shipping deployment shape (all modules OR'd).
    # Applies to every dataset: this is THE comparison we actually care about
    # for "is AgentArmor a credible single-product replacement for LlamaGuard?"
    ("agentarmor_combined", "xstest"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape (all modules OR'd). XSTest probes over-refusal.",
    ),
    ("agentarmor_combined", "realtoxicity"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape. RTP toxicity — toxicity module expected to dominate.",
    ),
    ("agentarmor_combined", "toxigen"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape. Hate-speech detection.",
    ),
    ("agentarmor_combined", "harmbench"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape. Harmful-behavior prompts — tests jailbreak + toxicity coverage together.",
    ),
    ("agentarmor_combined", "jailbreakbench"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape. Jailbreak prompts — primary ml_shield construct.",
    ),
    ("agentarmor_combined", "advbench"): Applicability(
        verdict="applies",
        rationale="Shipping deployment shape. Adversarial jailbreaks.",
    ),
    # Mock baseline — present for test coverage of the runner's full matrix.
    ("mock_scored", "xstest"): Applicability(
        verdict="applies",
        rationale="Mock baseline; used for CI smoke + snapshot tests.",
    ),
    ("mock_scored", "realtoxicity"): Applicability(
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
