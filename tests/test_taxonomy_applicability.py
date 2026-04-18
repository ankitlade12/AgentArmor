"""Tests for benchmarks/taxonomy_applicability.py (SPEC v4 D21, D31, D37, D59)."""

import pytest

from benchmarks.taxonomy_applicability import (
    APPLIES,
    Applicability,
    RUBRIC_VERSION,
    ensure_complete,
    get_projection,
)


MAIN_BASELINES = ["llamaguard", "openai_moderation", "perspective", "mock_scored"]
MAIN_DATASETS = [
    "xstest",
    "realtoxicityprompts",
    "toxigen",
    "harmbench",
    "jailbreakbench",
    "advbench",
]


class TestRubricCompleteness:
    def test_every_main_pair_has_entry(self):
        ensure_complete(MAIN_BASELINES, MAIN_DATASETS)  # raises on missing

    def test_missing_pair_raises_with_actionable_message(self):
        with pytest.raises(ValueError) as exc:
            ensure_complete(MAIN_BASELINES, MAIN_DATASETS + ["unknown_dataset"])
        msg = str(exc.value)
        assert "unknown_dataset" in msg
        assert "APPLIES" in msg
        assert "@rubric-owners" in msg
        assert "D29" in msg

    def test_empty_inputs_pass(self):
        ensure_complete([], [])


class TestApplicabilityShape:
    def test_all_entries_have_verdict_and_rationale(self):
        for (b, d), entry in APPLIES.items():
            assert entry.verdict in ("applies", "does_not_apply"), f"{b},{d}"
            assert entry.rationale, f"{b},{d} missing rationale"
            assert len(entry.rationale) > 20, f"{b},{d} rationale too short"

    def test_projection_only_on_openai_moderation(self):
        for (b, d), entry in APPLIES.items():
            if entry.projection is not None:
                assert b == "openai_moderation", (
                    f"{b},{d} has projection but isn't openai_moderation"
                )

    def test_openai_moderation_applies_entries_have_projection(self):
        for (b, d), entry in APPLIES.items():
            if b == "openai_moderation" and entry.verdict == "applies":
                assert entry.projection is not None, (
                    f"openai_moderation/{d} applies but has no projection"
                )
                assert len(entry.projection) >= 1
                assert isinstance(entry.projection, tuple)  # hashable

    def test_does_not_apply_entries_have_no_projection(self):
        for (b, d), entry in APPLIES.items():
            if entry.verdict == "does_not_apply":
                assert entry.projection is None


class TestGetProjection:
    def test_returns_tuple_for_openai_moderation_applies(self):
        proj = get_projection("openai_moderation", "toxigen")
        assert proj is not None
        assert isinstance(proj, tuple)

    def test_returns_none_for_non_openai(self):
        assert get_projection("llamaguard", "toxigen") is None
        assert get_projection("perspective", "realtoxicityprompts") is None

    def test_returns_none_for_unknown_pair(self):
        assert get_projection("bogus_baseline", "bogus_dataset") is None

    def test_returns_none_for_does_not_apply(self):
        assert get_projection("perspective", "harmbench") is None


class TestApplicabilityImmutability:
    def test_frozen_dataclass(self):
        entry = Applicability(verdict="applies", rationale="X" * 30)
        with pytest.raises(Exception):
            entry.verdict = "does_not_apply"  # type: ignore

    def test_hashable_when_projection_tuple(self):
        entry = Applicability(
            verdict="applies",
            rationale="X" * 30,
            projection=("hate", "violence"),
        )
        hash(entry)  # doesn't raise


def test_rubric_version_present():
    assert RUBRIC_VERSION
    assert isinstance(RUBRIC_VERSION, str)


def test_perspective_does_not_apply_on_harmful_behavior_datasets():
    """Perspective is toxicity-only; not applicable to jailbreak/harmful-behavior datasets."""
    for d in ("harmbench", "jailbreakbench", "advbench"):
        assert APPLIES[("perspective", d)].verdict == "does_not_apply"


def test_llamaguard_applies_across_all_main_datasets():
    for d in MAIN_DATASETS:
        assert APPLIES[("llamaguard", d)].verdict == "applies"
