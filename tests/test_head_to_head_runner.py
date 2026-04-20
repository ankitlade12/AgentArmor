"""Tests for benchmarks/runner.py (SPEC v4 D15, D26, D35, D43)."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchmarks.baselines.mock import MockBaselineFailing, MockBaselineScored
from benchmarks.runner import RunLogger, run_cell


@dataclass
class _Sample:
    text: str
    label: str


def _samples():
    return [
        _Sample(text="harmful content", label="positive"),
        _Sample(text="benign content", label="negative"),
        _Sample(text="another harmful", label="positive"),
        _Sample(text="another benign", label="negative"),
    ]


def _logger(tmp: Path) -> RunLogger:
    return RunLogger(tmp / "run.jsonl")


class TestRunCellHappyPath:
    def test_runs_full_cell_from_scratch(self, tmp_path: Path):
        scores = {
            "harmful content": 0.9,
            "benign content": 0.1,
            "another harmful": 0.8,
            "another benign": 0.2,
        }
        baseline = MockBaselineScored(scripted_scores=scores)
        result = run_cell(
            baseline=baseline,
            baseline_name="mock_scored",
            dataset_name="toy",
            samples=_samples(),
            adapter_name="toy",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        assert result.total == 4
        assert result.true_positives == 2
        assert result.true_negatives == 2
        assert result.false_positives == 0
        assert result.false_negatives == 0

    def test_persists_verdicts_to_jsonl(self, tmp_path: Path):
        baseline = MockBaselineScored(scripted_scores={"x": 0.5})
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        jsonl = (tmp_path / "head_to_head_verdicts.jsonl").read_text().strip()
        row = json.loads(jsonl)
        assert row["cell_id"] == "m__d"
        assert row["label"] == "positive"

    def test_sidecar_marked_completed(self, tmp_path: Path):
        baseline = MockBaselineScored(scripted_scores={"x": 0.9})
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        sidecar = json.loads((tmp_path / "sidecars" / "m__d.json").read_text())
        assert sidecar["completed"] is True
        assert sidecar["samples_done"] == 1
        assert sidecar["last_verdict_sample_id"]

    def test_run_log_events(self, tmp_path: Path):
        baseline = MockBaselineScored(scripted_scores={"x": 0.9})
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        events = [
            json.loads(line)
            for line in (tmp_path / "run.jsonl").read_text().splitlines()
        ]
        phases = [e["phase"] for e in events]
        assert "start" in phases
        assert "complete" in phases


class TestRunCellFailureModes:
    def test_baseline_exception_records_error_and_continues(self, tmp_path: Path):
        baseline = MockBaselineFailing(failure_mode="timeout")
        result = run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=_samples(),
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        assert len(result.samples) == 4
        assert all(s.error is not None for s in result.samples)
        # Errored samples excluded from TP/FP/TN/FN counts (D35).
        assert result.total == 0

    def test_error_logged_to_run_jsonl(self, tmp_path: Path):
        baseline = MockBaselineFailing(failure_mode="connection_refused")
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        events = [
            json.loads(line)
            for line in (tmp_path / "run.jsonl").read_text().splitlines()
        ]
        error_events = [e for e in events if e["phase"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["error_type"] == "ConnectionError"


class TestRunCellResume:
    def test_second_run_with_matching_version_skips(self, tmp_path: Path):
        baseline = MockBaselineScored(scripted_scores={"x": 0.9, "y": 0.1, "z": 0.7})
        samples = [
            _Sample("x", "positive"),
            _Sample("y", "negative"),
            _Sample("z", "positive"),
        ]
        common = dict(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=samples,
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        run_cell(**common)
        # Second invocation: all cells done → should skip (no new events).
        before = (tmp_path / "run.jsonl").read_text().splitlines()
        run_cell(**common)
        after = (tmp_path / "run.jsonl").read_text().splitlines()
        assert before == after

    def test_resume_from_partial(self, tmp_path: Path):
        """If a sidecar says 2 of 4 done, a rerun processes only the remaining 2."""
        baseline = MockBaselineScored(
            scripted_scores={
                "a": 0.9,
                "b": 0.1,
                "c": 0.8,
                "d": 0.2,
            }
        )
        # Prime: run once with only first 2 samples, leaving sidecar partial.
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("a", "positive"), _Sample("b", "negative")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        # Fake partial state: overwrite sidecar to pretend samples_done=2 of 4,
        # not completed.
        sidecar_path = tmp_path / "sidecars" / "m__d.json"
        state = json.loads(sidecar_path.read_text())
        state["samples_total"] = 4
        state["completed"] = False
        sidecar_path.write_text(json.dumps(state))

        # Now run with the full 4-sample list.
        result = run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[
                _Sample("a", "positive"),
                _Sample("b", "negative"),
                _Sample("c", "positive"),
                _Sample("d", "negative"),
            ],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        assert result.total == 4
        assert result.true_positives == 2
        assert result.true_negatives == 2


class TestRunCellDriftDetection:
    def test_adapter_version_drift_raises(self, tmp_path: Path):
        from benchmarks.sidecar import ResumeAbortError

        baseline = MockBaselineScored(scripted_scores={"x": 0.9})
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        with pytest.raises(ResumeAbortError, match="Adapter version changed"):
            run_cell(
                baseline=baseline,
                baseline_name="m",
                dataset_name="d",
                samples=[_Sample("x", "positive")],
                adapter_name="d",
                adapter_version="v2",  # drifted
                baseline_config_hash="c1",
                run_dir=tmp_path,
                run_logger=_logger(tmp_path),
            )

    def test_config_hash_drift_raises(self, tmp_path: Path):
        from benchmarks.sidecar import ResumeAbortError

        baseline = MockBaselineScored(scripted_scores={"x": 0.9})
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=[_Sample("x", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        with pytest.raises(ResumeAbortError, match="Baseline config changed"):
            run_cell(
                baseline=baseline,
                baseline_name="m",
                dataset_name="d",
                samples=[_Sample("x", "positive")],
                adapter_name="d",
                adapter_version="v1",
                baseline_config_hash="c2",  # drifted
                run_dir=tmp_path,
                run_logger=_logger(tmp_path),
            )


class TestTruncatedSidecarResumeIntegration:
    """D58: runner-level guarantee that a corrupted sidecar → redo cell."""

    def test_corrupted_sidecar_causes_full_redo(self, tmp_path: Path):
        baseline = MockBaselineScored(
            scripted_scores={"x": 0.9, "y": 0.1, "z": 0.7}
        )
        samples = [
            _Sample("x", "positive"),
            _Sample("y", "negative"),
            _Sample("z", "positive"),
        ]
        # Prime a completed run.
        run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=samples,
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        # Corrupt the sidecar mid-JSON.
        sidecar_path = tmp_path / "sidecars" / "m__d.json"
        sidecar_path.write_text('{"schema_version": "1.0", "cell_id": "m__d"')
        # Re-run. Because read_sidecar returns None on corrupt, plan_resume
        # returns "redo", and the runner re-iterates all samples.
        result2 = run_cell(
            baseline=baseline,
            baseline_name="m",
            dataset_name="d",
            samples=samples,
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        assert result2.total == 3
        # Sidecar should be completed again.
        import json
        final = json.loads((tmp_path / "sidecars" / "m__d.json").read_text())
        assert final["completed"] is True


class TestScoreEmittingFlag:
    def test_regex_style_baseline_records_pred_score_none(self, tmp_path: Path):
        import warnings

        from benchmarks.baselines.base import BaselineChecker

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            class RegexStyleBaseline(BaselineChecker):
                name = "regex_style_runner_test"

                def check(self, text: str) -> bool:
                    return "bad" in text

        baseline = RegexStyleBaseline()
        assert baseline.score_emitting is False

        result = run_cell(
            baseline=baseline,
            baseline_name="rx",
            dataset_name="d",
            samples=[_Sample("bad thing", "positive")],
            adapter_name="d",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=_logger(tmp_path),
        )
        assert result.score_emitting is False
        assert result.samples[0].pred_score is None
        assert result.samples[0].pred_bool is True
