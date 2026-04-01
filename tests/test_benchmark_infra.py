"""Unit tests for benchmark infrastructure: adapters, metrics, and export."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure benchmarks/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from common import BenchmarkResult, export_results


# ---------------------------------------------------------------------------
# BenchmarkResult metrics
# ---------------------------------------------------------------------------

class TestBenchmarkResult:
    def test_precision_basic(self):
        r = BenchmarkResult(module="test", true_positives=8, false_positives=2)
        assert r.precision == pytest.approx(0.8)

    def test_precision_no_positives(self):
        r = BenchmarkResult(module="test", true_positives=0, false_positives=0)
        assert r.precision == 0.0

    def test_recall_basic(self):
        r = BenchmarkResult(module="test", true_positives=8, false_negatives=2)
        assert r.recall == pytest.approx(0.8)

    def test_recall_no_actual_positives(self):
        r = BenchmarkResult(module="test", true_positives=0, false_negatives=0)
        assert r.recall == 0.0

    def test_f1_basic(self):
        r = BenchmarkResult(module="test", true_positives=8, false_positives=2, false_negatives=2)
        # precision=0.8, recall=0.8, f1 = 2*0.8*0.8/(0.8+0.8) = 0.8
        assert r.f1 == pytest.approx(0.8)

    def test_f1_zero_when_no_tp(self):
        r = BenchmarkResult(module="test", true_positives=0, false_positives=5, false_negatives=5)
        assert r.f1 == 0.0

    def test_accuracy(self):
        r = BenchmarkResult(module="test", total=100, true_positives=40, true_negatives=40,
                            false_positives=10, false_negatives=10)
        assert r.accuracy == pytest.approx(0.8)

    def test_accuracy_zero_total(self):
        r = BenchmarkResult(module="test", total=0)
        assert r.accuracy == 0.0

    def test_false_positive_rate(self):
        r = BenchmarkResult(module="test", false_positives=5, true_negatives=95)
        assert r.false_positive_rate == pytest.approx(0.05)

    def test_false_positive_rate_no_negatives(self):
        r = BenchmarkResult(module="test", false_positives=0, true_negatives=0)
        assert r.false_positive_rate == 0.0

    def test_add_category(self):
        r = BenchmarkResult(module="test")
        r.add_category("cat_a", tp=3, fp=1)
        r.add_category("cat_a", tp=2, fn=1)
        assert r.category_results["cat_a"]["tp"] == 5
        assert r.category_results["cat_a"]["fp"] == 1
        assert r.category_results["cat_a"]["fn"] == 1

    def test_perfect_score(self):
        r = BenchmarkResult(module="test", total=100, true_positives=50, true_negatives=50,
                            false_positives=0, false_negatives=0)
        assert r.precision == 1.0
        assert r.recall == 1.0
        assert r.f1 == 1.0
        assert r.accuracy == 1.0
        assert r.false_positive_rate == 0.0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_creates_json(self, tmp_path):
        r = BenchmarkResult(module="test_mod", total=10, true_positives=8,
                            false_positives=1, true_negatives=0, false_negatives=1)
        output = str(tmp_path / "test_results.json")
        export_results([r], output, version="test", result_type="unit_test")

        with open(output) as f:
            data = json.load(f)

        assert data["version"] == "test"
        assert data["type"] == "unit_test"
        assert "test_mod" in data["modules"]
        mod = data["modules"]["test_mod"]
        assert mod["true_positives"] == 8
        assert mod["false_positives"] == 1
        assert "false_positive_rate" in mod

    def test_export_creates_parent_dirs(self, tmp_path):
        output = str(tmp_path / "deep" / "nested" / "results.json")
        r = BenchmarkResult(module="m", total=1, true_positives=1)
        export_results([r], output)
        assert Path(output).exists()

    def test_export_multiple_modules(self, tmp_path):
        r1 = BenchmarkResult(module="mod_a", total=5, true_positives=3, false_negatives=2)
        r2 = BenchmarkResult(module="mod_b", total=5, true_negatives=5)
        output = str(tmp_path / "multi.json")
        export_results([r1, r2], output)

        with open(output) as f:
            data = json.load(f)
        assert len(data["modules"]) == 2


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    @classmethod
    def setup_class(cls):
        """Import all adapter modules so they register with the registry."""
        import adapters.advbench         # noqa: F401
        import adapters.truthfulqa       # noqa: F401
        import adapters.jailbreakbench   # noqa: F401
        import adapters.xstest           # noqa: F401
        import adapters.harmbench        # noqa: F401
        import adapters.halueval         # noqa: F401
        import adapters.realtoxicity     # noqa: F401
        import adapters.toxigen          # noqa: F401
        import adapters.guardbench       # noqa: F401
        import adapters.exfiltration     # noqa: F401

    def test_list_adapters_returns_names(self):
        from adapters import list_adapters
        names = list_adapters()
        assert isinstance(names, list)
        assert len(names) > 0
        # At least these should exist
        assert "advbench" in names
        assert "truthfulqa" in names

    def test_get_adapter_returns_instance(self):
        from adapters import get_adapter
        adapter = get_adapter("truthfulqa")
        assert hasattr(adapter, "load")
        assert hasattr(adapter, "name")
        assert adapter.name == "truthfulqa"

    def test_get_unknown_adapter_raises(self):
        from adapters import get_adapter
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent_dataset_xyz")

    def test_bbq_not_registered(self):
        """BBQ was removed because it tests model reasoning, not content filtering."""
        from adapters import list_adapters
        assert "bbq" not in list_adapters()


# ---------------------------------------------------------------------------
# NormalizedSample
# ---------------------------------------------------------------------------

class TestNormalizedSample:
    def test_sample_fields(self):
        from adapters.base import NormalizedSample
        s = NormalizedSample(text="hello", label="positive", category="test")
        assert s.text == "hello"
        assert s.label == "positive"
        assert s.category == "test"
        assert s.source_context == ""
        assert s.metadata == {}

    def test_sample_with_source_context(self):
        from adapters.base import NormalizedSample
        s = NormalizedSample(
            text="The answer is 42",
            label="negative",
            category="qa",
            source_context="The meaning of life is 42",
        )
        assert s.source_context == "The meaning of life is 42"


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------

class TestStratifiedSampling:
    def test_maintains_balance(self):
        from adapters.base import DatasetAdapter, NormalizedSample

        class DummyAdapter(DatasetAdapter):
            name = "dummy"
            def load(self, sample_size=None, seed=42):
                return []

        adapter = DummyAdapter()
        samples = (
            [NormalizedSample(text=f"pos_{i}", label="positive") for i in range(100)] +
            [NormalizedSample(text=f"neg_{i}", label="negative") for i in range(100)]
        )
        result = adapter._stratified_sample(samples, 50, seed=42)
        pos = sum(1 for s in result if s.label == "positive")
        neg = sum(1 for s in result if s.label == "negative")
        # Should roughly maintain the 50/50 ratio
        assert 20 <= pos <= 30
        assert 20 <= neg <= 30
        assert len(result) == 50

    def test_returns_all_if_under_limit(self):
        from adapters.base import DatasetAdapter, NormalizedSample

        class DummyAdapter(DatasetAdapter):
            name = "dummy"
            def load(self, sample_size=None, seed=42):
                return []

        adapter = DummyAdapter()
        samples = [NormalizedSample(text=f"s_{i}", label="positive") for i in range(10)]
        result = adapter._stratified_sample(samples, 100, seed=42)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# Exfiltration adapter sample alignment
# ---------------------------------------------------------------------------

class TestExfiltrationSampleAlignment:
    """Verify synthetic exfiltration samples actually trigger the detector."""

    def test_base64_samples_exceed_min_length(self):
        """All base64 positive samples must produce encoded strings >= 40 chars."""
        import base64 as b64
        from adapters.exfiltration import ExfiltrationAdapter

        adapter = ExfiltrationAdapter()
        samples = adapter.load(sample_size=200)

        for s in samples:
            if s.label == "positive" and s.category.startswith("base64"):
                # Extract the base64 string from the sample text
                # The format is "... {base64_encoded} ..."
                # We just need to verify it's long enough
                import re
                matches = re.findall(r'[A-Za-z0-9+/]{16,}={0,2}', s.text)
                assert len(matches) > 0, f"No base64 found in: {s.text[:80]}"
                for m in matches:
                    assert len(m) >= 40, (
                        f"Base64 sample too short ({len(m)} chars, need >=40): {m[:50]}"
                    )
