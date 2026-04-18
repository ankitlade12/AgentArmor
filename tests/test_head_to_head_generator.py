"""Tests for benchmarks/generate_head_to_head_doc.py (SPEC v4 D24, D28, D48, D57)."""

import json
from pathlib import Path

import pytest

from benchmarks.generate_head_to_head_doc import (
    GENERATED_MARKER,
    generate_markdown,
    main,
)


def _cell(**overrides) -> dict:
    base = {
        "baseline": "llamaguard",
        "dataset": "toxigen",
        "n_samples": 200,
        "score_emitting": True,
        "operating_point": "llamaguard",
        "degenerate_flag": False,
        "f1": 0.82,
        "f1_ci_low": 0.78,
        "f1_ci_high": 0.86,
        "precision": 0.85,
        "recall": 0.79,
        "fpr": 0.12,
        "mcc": 0.65,
        "mcc_ci_low": 0.60,
        "mcc_ci_high": 0.70,
        "balanced_accuracy": 0.83,
        "balanced_accuracy_ci_low": 0.80,
        "balanced_accuracy_ci_high": 0.86,
        "latency_p50_ms": 1200.0,
        "latency_p95_ms": 1800.0,
        "errors_count": 0,
        "skipped_count": 0,
    }
    base.update(overrides)
    return base


def _summary(cells: list) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "test_run",
        "agentarmor_version": "1.4.0",
        "run_date": "2026-04-17",
        "rubric_version": "1.0",
        "config_echo": {},
        "cells": cells,
        "tolerances": {"same_day_spread_95p": None, "one_week_drift_max": None},
    }


class TestGeneratedOutputShape:
    def test_contains_generated_marker(self):
        md = generate_markdown(_summary([_cell()]))
        assert GENERATED_MARKER in md
        # Marker must be on the first line for D28 CI diff message.
        assert md.startswith(GENERATED_MARKER)

    def test_banner_shows_version_and_date(self):
        md = generate_markdown(_summary([_cell()]))
        assert "AgentArmor v1.4.0" in md
        assert "2026-04-17" in md

    def test_headline_is_present(self):
        md = generate_markdown(_summary([_cell()]))
        assert "AgentArmor" in md
        assert "LlamaGuard" in md
        assert "reproduc" in md.lower()  # reproduction instructions

    def test_delta_strip_shows_best_baseline(self):
        md = generate_markdown(_summary([_cell()]))
        assert "Per-dataset summary" in md
        assert "llamaguard" in md  # best baseline for this single-cell fixture
        assert "0.8200" in md

    def test_per_dataset_table_has_cell(self):
        md = generate_markdown(_summary([_cell()]))
        assert "### toxigen" in md

    def test_advbench_notes_f1_omitted(self):
        cell = _cell(dataset="advbench", baseline="llamaguard", f1=None, mcc=0.7)
        md = generate_markdown(_summary([cell]))
        assert "F1 omitted" in md or "F1 not meaningful" in md or "omitted" in md

    def test_operating_point_legend_rendered(self):
        md = generate_markdown(_summary([_cell()]))
        assert "Operating-point legend" in md
        assert "P(\"unsafe\")" in md

    def test_does_not_apply_appendix_includes_perspective_harmbench(self):
        md = generate_markdown(_summary([_cell()]))
        assert "does_not_apply" in md.lower() or "does not apply" in md.lower()
        assert "perspective" in md
        assert "harmbench" in md

    def test_pr_curves_missing_note_enumerates(self):
        md = generate_markdown(_summary([_cell()]))
        assert "PR curve" in md
        assert "regex" in md.lower()
        assert "text-parse" in md.lower()

    def test_historical_versions_block_present(self):
        md = generate_markdown(_summary([_cell()]))
        assert "Historical versions" in md
        assert "git tag" in md.lower()


class TestDeterminism:
    def test_byte_identical_regeneration(self):
        """Same input → byte-identical markdown (supports D28 CI drift-check)."""
        summary = _summary([_cell(baseline="llamaguard"), _cell(baseline="perspective")])
        a = generate_markdown(summary)
        b = generate_markdown(summary)
        assert a == b

    def test_order_insensitive_to_cell_insertion_order(self):
        """Cells dumped in different insertion order must produce identical markdown."""
        summary_a = _summary([_cell(baseline="perspective"), _cell(baseline="llamaguard")])
        summary_b = _summary([_cell(baseline="llamaguard"), _cell(baseline="perspective")])
        a = generate_markdown(summary_a)
        b = generate_markdown(summary_b)
        assert a == b

    def test_float_formatting_uses_four_decimals(self):
        summary = _summary([_cell(f1=0.8)])
        md = generate_markdown(summary)
        assert "0.8000" in md  # not "0.8" (D45 pin)


class TestMultipleCells:
    def test_delta_strip_picks_highest_f1(self):
        summary = _summary(
            [
                _cell(baseline="llamaguard", f1=0.72),
                _cell(baseline="perspective", f1=0.81),
                _cell(baseline="openai_moderation", f1=0.65),
            ]
        )
        md = generate_markdown(summary)
        # Best baseline F1 = 0.81 (perspective)
        assert "0.8100" in md
        # Best-baseline column should name perspective.
        strip_lines = [l for l in md.splitlines() if "toxigen" in l and "|" in l]
        assert any("perspective" in l for l in strip_lines)

    def test_mock_scored_excluded_from_delta(self):
        """Mock baseline exists for CI fixtures but shouldn't dominate the delta strip."""
        summary = _summary(
            [
                _cell(baseline="llamaguard", f1=0.70),
                _cell(baseline="mock_scored", f1=0.99),
            ]
        )
        md = generate_markdown(summary)
        strip = [l for l in md.splitlines() if "toxigen" in l and "|" in l]
        assert any("llamaguard" in l for l in strip)
        assert not any("mock_scored" in l for l in strip)


class TestMainCLI:
    def test_main_reads_summary_and_writes_markdown(self, tmp_path: Path):
        summary_path = tmp_path / "summary.json"
        summary_path.write_text(json.dumps(_summary([_cell()])))
        output = tmp_path / "HEAD_TO_HEAD.md"
        rc = main(["--summary", str(summary_path), "--output", str(output)])
        assert rc == 0
        md = output.read_text()
        assert GENERATED_MARKER in md
        assert "AgentArmor v1.4.0" in md

    def test_main_rejects_unsupported_schema_major(self, tmp_path: Path):
        bad_summary = _summary([_cell()])
        bad_summary["schema_version"] = "2.0"
        summary_path = tmp_path / "bad.json"
        summary_path.write_text(json.dumps(bad_summary))
        output = tmp_path / "HEAD_TO_HEAD.md"
        from benchmarks.schema_io import UnsupportedSchemaError

        with pytest.raises(UnsupportedSchemaError):
            main(["--summary", str(summary_path), "--output", str(output)])


class TestMissingFieldHandling:
    def test_missing_optional_fields_render_as_dash(self):
        cell = _cell(f1=None, f1_ci_low=None, f1_ci_high=None, mcc=None, latency_p50_ms=None)
        md = generate_markdown(_summary([cell]))
        assert "—" in md

    def test_empty_cells_list_does_not_crash(self):
        md = generate_markdown(_summary([]))
        assert GENERATED_MARKER in md
