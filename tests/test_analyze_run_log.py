"""Tests for scripts/analyze_run_log.py (SPEC v4 D56).

The script is importable at ``scripts.analyze_run_log`` via direct path
manipulation because ``scripts/`` is not on sys.path by default.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "analyze_run_log.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_run_log", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ARL = _load_script_module()


def _write_log(tmp_path: Path, events: list) -> Path:
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return log


class TestSummarize:
    def test_aggregates_phases_per_cell(self, tmp_path):
        events = [
            {"baseline": "l", "dataset": "x", "phase": "start", "sample_id": "s1"},
            {"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "s1"},
            {"baseline": "l", "dataset": "x", "phase": "start", "sample_id": "s2"},
            {"baseline": "l", "dataset": "x", "phase": "error", "sample_id": "s2"},
            {"baseline": "p", "dataset": "y", "phase": "start", "sample_id": "s3"},
            {"baseline": "p", "dataset": "y", "phase": "complete", "sample_id": "s3"},
        ]
        agg = ARL.summarize(events)
        assert agg["l/x"] == {"start": 2, "complete": 1, "error": 1, "red_alert": 0}
        assert agg["p/y"]["complete"] == 1

    def test_empty_events(self):
        assert ARL.summarize([]) == {}


class TestFormatting:
    def test_summary_mentions_cell_and_counts(self):
        agg = {
            "llamaguard/toxigen": {"start": 5, "complete": 4, "error": 1, "red_alert": 0}
        }
        out = ARL.format_summary(agg)
        assert "llamaguard/toxigen" in out
        assert "← errors" in out  # flagged because error > 0

    def test_summary_does_not_flag_clean_cells(self):
        agg = {
            "llamaguard/toxigen": {"start": 5, "complete": 5, "error": 0, "red_alert": 0}
        }
        out = ARL.format_summary(agg)
        assert "← errors" not in out


class TestErrorsOnly:
    def test_prints_error_events_only(self):
        events = [
            {"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "a"},
            {
                "baseline": "l",
                "dataset": "x",
                "phase": "error",
                "sample_id": "b",
                "error_type": "TimeoutError",
                "error_msg": "timed out",
                "ts": "2026-04-17T00:00:00Z",
            },
        ]
        out = ARL.format_errors(events)
        assert "timed out" in out
        assert "TimeoutError" in out
        assert "complete" not in out

    def test_filters_to_cell(self):
        events = [
            {"baseline": "l", "dataset": "x", "phase": "error", "sample_id": "a", "error_type": "T", "error_msg": "in x"},
            {"baseline": "p", "dataset": "y", "phase": "error", "sample_id": "b", "error_type": "T", "error_msg": "in y"},
        ]
        out = ARL.format_errors(events, cell="p/y")
        assert "in y" in out
        assert "in x" not in out

    def test_no_errors_prints_placeholder(self):
        events = [{"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "a"}]
        out = ARL.format_errors(events)
        assert "no error events" in out


class TestCellDrillDown:
    def test_restricts_to_cell(self):
        events = [
            {"baseline": "l", "dataset": "x", "phase": "start", "sample_id": "a", "ts": "1"},
            {"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "a", "ts": "2"},
            {"baseline": "p", "dataset": "y", "phase": "start", "sample_id": "b", "ts": "3"},
        ]
        out = ARL.format_cell_detail(events, "l/x")
        assert "sample=a" in out
        assert "sample=b" not in out


class TestMainCLI:
    def test_runs_on_directory_arg(self, tmp_path):
        _write_log(
            tmp_path,
            [{"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "a"}],
        )
        rc = ARL.main([str(tmp_path)])
        assert rc == 0

    def test_runs_on_direct_jsonl_arg(self, tmp_path):
        log = _write_log(
            tmp_path,
            [{"baseline": "l", "dataset": "x", "phase": "complete", "sample_id": "a"}],
        )
        rc = ARL.main([str(log)])
        assert rc == 0

    def test_missing_path_nonzero_exit(self, tmp_path):
        rc = ARL.main([str(tmp_path / "does_not_exist.jsonl")])
        assert rc != 0

    def test_errors_only_flag(self, tmp_path, capsys):
        _write_log(
            tmp_path,
            [
                {
                    "baseline": "l",
                    "dataset": "x",
                    "phase": "error",
                    "sample_id": "a",
                    "error_type": "T",
                    "error_msg": "boom",
                    "ts": "1",
                }
            ],
        )
        ARL.main([str(tmp_path), "--errors-only"])
        captured = capsys.readouterr()
        assert "boom" in captured.out

    def test_cell_drill_down_flag(self, tmp_path, capsys):
        _write_log(
            tmp_path,
            [
                {"baseline": "l", "dataset": "x", "phase": "start", "sample_id": "a", "ts": "1"},
                {"baseline": "p", "dataset": "y", "phase": "start", "sample_id": "b", "ts": "2"},
            ],
        )
        ARL.main([str(tmp_path), "--cell", "l/x"])
        captured = capsys.readouterr()
        assert "sample=a" in captured.out
        assert "sample=b" not in captured.out
