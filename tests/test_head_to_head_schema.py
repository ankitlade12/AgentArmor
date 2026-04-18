"""Tests for schema_io: versioning + structural validation (SPEC v4 D27, D52)."""

import json
from pathlib import Path

import pytest

from benchmarks.schema_io import (
    SchemaValidationError,
    UnsupportedSchemaError,
    dump_summary,
    load_summary,
    parse_major,
    validate_summary,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_V1_0 = FIXTURES / "head_to_head_summary_v1_0.json"


def _v1_0_data() -> dict:
    return json.loads(FIXTURE_V1_0.read_text())


def _minimal_v1_0() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "r1",
        "agentarmor_version": "1.4.0",
        "run_date": "2026-04-17",
        "rubric_version": "1.0",
        "cells": [],
        "tolerances": {"same_day_spread_95p": None, "one_week_drift_max": None},
    }


# ---------------------------------------------------------------------------
# Version parser
# ---------------------------------------------------------------------------


class TestParseMajor:
    def test_1_0(self):
        assert parse_major("1.0") == "1"

    def test_1_4(self):
        assert parse_major("1.4") == "1"

    def test_2_0(self):
        assert parse_major("2.0") == "2"

    def test_malformed_raises(self):
        with pytest.raises(SchemaValidationError):
            parse_major("v1.0")

    def test_patch_not_allowed(self):
        """Intentional: 1.0.0 is not a minor format; enforce major.minor only."""
        with pytest.raises(SchemaValidationError):
            parse_major("1.0.0")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateSummary:
    def test_fixture_is_valid(self):
        validate_summary(_v1_0_data())

    def test_missing_top_level_field_raises(self):
        data = _minimal_v1_0()
        del data["run_id"]
        with pytest.raises(SchemaValidationError, match="run_id"):
            validate_summary(data)

    def test_cell_missing_required_raises(self):
        data = _minimal_v1_0()
        data["cells"] = [{"baseline": "b"}]  # missing dataset/n_samples/etc.
        with pytest.raises(SchemaValidationError, match="cells\\[0\\]"):
            validate_summary(data)

    def test_malformed_version_raises(self):
        data = _minimal_v1_0()
        data["schema_version"] = "v1"
        with pytest.raises(SchemaValidationError, match="major.minor"):
            validate_summary(data)

    def test_tolerances_missing_required_raises(self):
        data = _minimal_v1_0()
        data["tolerances"] = {}
        with pytest.raises(SchemaValidationError, match="tolerances"):
            validate_summary(data)

    def test_ignores_unknown_fields(self):
        """Forward-compat: extra fields at top level are fine (future minor)."""
        data = _minimal_v1_0()
        data["future_new_field"] = "value"
        validate_summary(data)  # no raise

    def test_ignores_unknown_cell_fields(self):
        data = _minimal_v1_0()
        data["cells"] = [
            {
                "baseline": "b",
                "dataset": "d",
                "n_samples": 0,
                "score_emitting": True,
                "operating_point": "b",
                "degenerate_flag": False,
                "unknown_future_field": 123,
            }
        ]
        validate_summary(data)

    def test_type_mismatch_raises(self):
        data = _minimal_v1_0()
        data["cells"] = [
            {
                "baseline": "b",
                "dataset": "d",
                "n_samples": "not-an-int",
                "score_emitting": True,
                "operating_point": "b",
                "degenerate_flag": False,
            }
        ]
        with pytest.raises(SchemaValidationError, match="n_samples"):
            validate_summary(data)


# ---------------------------------------------------------------------------
# Load/dump
# ---------------------------------------------------------------------------


class TestLoadDumpRoundtrip:
    def test_roundtrip_identity(self, tmp_path: Path):
        data = _v1_0_data()
        out = tmp_path / "summary.json"
        dump_summary(out, data)
        restored = load_summary(out)
        # Field-by-field equality (sort_keys used on dump).
        assert restored == data

    def test_deterministic_dump(self, tmp_path: Path):
        """Same input dumped twice → byte-identical output (supports D28 CI)."""
        data = _v1_0_data()
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        dump_summary(p1, data)
        dump_summary(p2, data)
        assert p1.read_bytes() == p2.read_bytes()


# ---------------------------------------------------------------------------
# Cross-version matrix (D52)
# ---------------------------------------------------------------------------


class TestCrossVersionMatrix:
    def test_1_0_writer_1_0_reader(self, tmp_path: Path):
        data = _minimal_v1_0()
        p = tmp_path / "s.json"
        dump_summary(p, data)
        loaded = load_summary(p)
        assert loaded["schema_version"] == "1.0"

    def test_1_0_writer_1_1_reader_ignores_new_fields(self, tmp_path: Path):
        """A hypothetical 1.1 reader reading 1.0 data — default missing fields to None at consumer."""
        data = _minimal_v1_0()
        p = tmp_path / "s.json"
        dump_summary(p, data)
        loaded = load_summary(p)
        # New-hypothetical 1.1 field not present in 1.0 data → consumer defaults to None.
        assert loaded.get("hypothetical_1_1_field") is None

    def test_1_1_writer_1_0_reader_succeeds(self, tmp_path: Path):
        """A 1.0 reader should accept 1.1 data (additive-minor policy)."""
        data = _minimal_v1_0()
        data["schema_version"] = "1.1"
        data["hypothetical_1_1_field"] = "extra"
        data["cells"] = [
            {
                "baseline": "b",
                "dataset": "d",
                "n_samples": 0,
                "score_emitting": True,
                "operating_point": "b",
                "degenerate_flag": False,
                "hypothetical_cell_1_1_field": 99,
            }
        ]
        p = tmp_path / "s.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
        loaded = load_summary(p)
        assert loaded["schema_version"] == "1.1"

    def test_1_1_writer_1_1_reader(self, tmp_path: Path):
        data = _minimal_v1_0()
        data["schema_version"] = "1.1"
        p = tmp_path / "s.json"
        p.write_text(json.dumps(data))
        loaded = load_summary(p)
        assert loaded["schema_version"] == "1.1"

    def test_2_0_rejected_with_clear_error(self, tmp_path: Path):
        data = _minimal_v1_0()
        data["schema_version"] = "2.0"
        p = tmp_path / "s.json"
        p.write_text(json.dumps(data))
        with pytest.raises(UnsupportedSchemaError, match="unsupported schema major"):
            load_summary(p)

    def test_error_message_actionable(self, tmp_path: Path):
        data = _minimal_v1_0()
        data["schema_version"] = "2.3"
        p = tmp_path / "s.json"
        p.write_text(json.dumps(data))
        with pytest.raises(UnsupportedSchemaError) as exc:
            load_summary(p)
        msg = str(exc.value)
        assert "Upgrade" in msg or "regenerate" in msg


class TestSchemaFilePresent:
    """The machine-readable schema file lives alongside the code."""

    def test_schema_file_exists(self):
        schema = Path("benchmarks/schemas/head_to_head_summary_v1.json")
        assert schema.exists()
        data = json.loads(schema.read_text())
        assert data["title"] == "HeadToHeadSummary"
        assert "Cell" in data["$defs"]
