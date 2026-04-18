"""Integration tests for the head-to-head CLI orchestrator (SPEC v4 DoD-1, DoD-7).

Uses mock baseline + a fixture dataset to exercise the runner end-to-end
without any real API calls.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from benchmarks.baselines.mock import MockBaselineScored
from benchmarks.common import compute_adapter_version
from benchmarks.config import compute_config_hash
from benchmarks.run_head_to_head import (
    _collect_applicable_cells,
    build_baseline_for_cell,
    compute_cell_metrics,
    run_main,
    write_summary,
)
from benchmarks.runner import RunLogger, run_cell


# ---------------------------------------------------------------------------
# Simple helpers
# ---------------------------------------------------------------------------


class _FakeSample:
    def __init__(self, text, label):
        self.text = text
        self.label = label


def _fake_samples():
    return [
        _FakeSample("harmful A", "positive"),
        _FakeSample("harmful B", "positive"),
        _FakeSample("benign A", "negative"),
        _FakeSample("benign B", "negative"),
    ]


# ---------------------------------------------------------------------------
# Applicable cell collection
# ---------------------------------------------------------------------------


class TestCollectApplicableCells:
    def test_filters_to_applies_only(self):
        cells = _collect_applicable_cells(None, None)
        # Perspective/harmbench is does_not_apply; must not appear.
        assert ("perspective", "harmbench") not in cells
        # LlamaGuard/xstest is applies.
        assert ("llamaguard", "xstest") in cells

    def test_baseline_filter(self):
        cells = _collect_applicable_cells(["mock_scored"], None)
        assert all(b == "mock_scored" for b, _ in cells)

    def test_dataset_filter(self):
        cells = _collect_applicable_cells(None, ["toxigen"])
        assert all(d == "toxigen" for _, d in cells)


# ---------------------------------------------------------------------------
# Baseline construction — per-cell projection for OpenAI Moderation
# ---------------------------------------------------------------------------


class TestBuildBaselineForCell:
    def test_openai_moderation_gets_projection(self):
        cfg = {"baselines": {"openai_moderation": {"default_threshold": 0.5}}}
        b = build_baseline_for_cell("openai_moderation", "toxigen", cfg)
        assert b._projection is not None
        # Projection for toxigen is the _HATE_CATS tuple.
        assert "hate" in b._projection

    def test_different_datasets_yield_different_projections(self):
        cfg = {"baselines": {"openai_moderation": {}}}
        tox = build_baseline_for_cell("openai_moderation", "toxigen", cfg)
        jb = build_baseline_for_cell("openai_moderation", "jailbreakbench", cfg)
        assert tox._projection != jb._projection

    def test_perspective_uses_config(self):
        cfg = {"baselines": {"perspective": {"default_threshold": 0.7}}}
        b = build_baseline_for_cell("perspective", "toxigen", cfg)
        assert b.default_threshold == 0.7

    def test_mock_scored_uses_registry(self):
        b = build_baseline_for_cell("mock_scored", "toxigen", {})
        assert b.name == "mock_scored"


# ---------------------------------------------------------------------------
# Metric computation per cell
# ---------------------------------------------------------------------------


class TestCellMetrics:
    def test_perfect_classifier_emits_expected_fields(self, tmp_path):
        # Enough samples for bootstrap to stay below the 10% degenerate
        # threshold (N=4 would produce ~12% zero-class resamples).
        scripted = {}
        samples = []
        for i in range(20):
            pt = f"harmful {i}"
            bt = f"benign {i}"
            scripted[pt] = 0.9
            scripted[bt] = 0.1
            samples.append(_FakeSample(pt, "positive"))
            samples.append(_FakeSample(bt, "negative"))
        baseline = MockBaselineScored(scripted_scores=scripted)
        result = run_cell(
            baseline=baseline,
            baseline_name="mock_scored",
            dataset_name="toxigen",
            samples=samples,
            adapter_name="toxigen",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=RunLogger(tmp_path / "run.jsonl"),
        )
        metrics = compute_cell_metrics(result, iters=500)
        assert metrics["baseline"] == "mock_scored"
        assert metrics["dataset"] == "toxigen"
        assert metrics["n_samples"] == 40
        # Perfect classifier: F1 = 1.0
        assert metrics["f1"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["fpr"] == 0.0
        assert metrics["degenerate_flag"] is False
        assert metrics["errors_count"] == 0
        assert metrics["latency_p50_ms"] is not None

    def test_all_errors_degenerate(self, tmp_path):
        from benchmarks.baselines.mock import MockBaselineFailing

        baseline = MockBaselineFailing(failure_mode="timeout")
        result = run_cell(
            baseline=baseline,
            baseline_name="mock_scored",
            dataset_name="toxigen",
            samples=_fake_samples(),
            adapter_name="toxigen",
            adapter_version="v1",
            baseline_config_hash="c1",
            run_dir=tmp_path,
            run_logger=RunLogger(tmp_path / "run.jsonl"),
        )
        metrics = compute_cell_metrics(result, iters=200)
        assert metrics["n_samples"] == 0
        assert metrics["errors_count"] == 4
        assert metrics["f1"] is None
        assert metrics["degenerate_flag"] is True
        assert metrics["latency_p50_ms"] is None


# ---------------------------------------------------------------------------
# Summary JSON shape (for D52 schema consumer later)
# ---------------------------------------------------------------------------


class TestWriteSummary:
    def _cell(self, **overrides) -> dict:
        base = {
            "baseline": "mock_scored",
            "dataset": "toxigen",
            "n_samples": 40,
            "score_emitting": True,
            "operating_point": "mock_scored",
            "degenerate_flag": False,
            "f1": 1.0,
        }
        base.update(overrides)
        return base

    def test_summary_contains_required_fields(self, tmp_path):
        cells = [self._cell()]
        cfg = {"baselines": {"mock_scored": {}}, "calibration": {}}
        path = write_summary(tmp_path, cells, cfg, run_id="test_run")
        data = json.loads(path.read_text())
        assert data["schema_version"] == "1.0"
        assert data["run_id"] == "test_run"
        assert data["rubric_version"] == "1.0"
        assert data["cells"] == cells
        assert "config_echo" in data
        assert data["tolerances"]["same_day_spread_95p"] is None

    def test_summary_is_sorted_stable(self, tmp_path):
        """Stable sorted JSON supports byte-identical regenerate-and-diff (D28)."""
        cells = [self._cell()]
        cfg = {"baselines": {"mock_scored": {}}}
        write_summary(tmp_path, cells, cfg, run_id="r1")
        first = (tmp_path / "head_to_head_summary.json").read_text()
        write_summary(tmp_path, cells, cfg, run_id="r1")
        second = (tmp_path / "head_to_head_summary.json").read_text()
        assert first == second


# ---------------------------------------------------------------------------
# End-to-end run_main with mock baseline and patched adapter
# ---------------------------------------------------------------------------


class TestRunMainMockEndToEnd:
    def _patch_adapter(self):
        """Return patches replacing the adapter and module resolvers."""
        import benchmarks.run_head_to_head as h2h_mod

        class _FakeAdapter:
            def load(self, sample_size=None, seed=42):
                return _fake_samples()

        fake_adapter = _FakeAdapter()
        fake_module = type("FakeMod", (), {"__name__": "fake_toxigen"})()

        patches = [
            mock.patch.object(h2h_mod, "_resolve_adapter", lambda name: fake_adapter),
            mock.patch.object(h2h_mod, "_resolve_adapter_module", lambda name: fake_module),
            mock.patch.object(h2h_mod, "compute_adapter_version", lambda m: "fakev1"),
        ]
        return patches

    def test_dry_run_writes_report(self, tmp_path):
        cfg = {"baselines": {"mock_scored": {}}}
        run_main(
            run_dir=tmp_path,
            config=cfg,
            baselines=["mock_scored"],
            datasets=["toxigen"],
            sample_size=None,
            seed=42,
            bootstrap_iters=200,
            dry_run=True,
        )
        assert (tmp_path / "dry_run.txt").exists()

    def test_end_to_end_with_mock_baseline(self, tmp_path):
        cfg = {"baselines": {"mock_scored": {}}}
        patches = self._patch_adapter()
        for p in patches:
            p.start()
        try:
            run_main(
                run_dir=tmp_path,
                config=cfg,
                baselines=["mock_scored"],
                datasets=["toxigen"],
                sample_size=None,
                seed=42,
                bootstrap_iters=200,
                dry_run=False,
            )
        finally:
            for p in patches:
                p.stop()

        summary_path = tmp_path / "head_to_head_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["schema_version"] == "1.0"
        assert len(summary["cells"]) == 1
        cell = summary["cells"][0]
        assert cell["baseline"] == "mock_scored"
        assert cell["dataset"] == "toxigen"
        assert cell["n_samples"] == 4
        # Mock baseline returns default_score=0.0 for unknown texts → all predict safe.
        # All positives become FN, all negatives TN.
        assert cell["errors_count"] == 0
        # JSONL persisted
        assert (tmp_path / "head_to_head_verdicts.jsonl").exists()
        # Sidecar created
        assert (tmp_path / "sidecars" / "mock_scored__toxigen.json").exists()
        # Run log populated
        assert (tmp_path / "run.jsonl").exists()


# ---------------------------------------------------------------------------
# Config hash drift detection
# ---------------------------------------------------------------------------


class TestConfigHash:
    def test_same_config_same_hash(self):
        cfg = {"baselines": {"perspective": {"default_threshold": 0.5}}}
        a = compute_config_hash(cfg, "perspective")
        b = compute_config_hash(cfg, "perspective")
        assert a == b

    def test_different_config_different_hash(self):
        a = compute_config_hash(
            {"baselines": {"perspective": {"default_threshold": 0.5}}}, "perspective"
        )
        b = compute_config_hash(
            {"baselines": {"perspective": {"default_threshold": 0.7}}}, "perspective"
        )
        assert a != b

    def test_missing_baseline_returns_deterministic_hash(self):
        a = compute_config_hash({}, "llamaguard")
        b = compute_config_hash({}, "llamaguard")
        assert a == b
        assert len(a) == 8

    def test_returns_8_char_hex(self):
        h = compute_config_hash({"baselines": {"m": {"x": 1}}}, "m")
        assert len(h) == 8
        int(h, 16)  # valid hex
