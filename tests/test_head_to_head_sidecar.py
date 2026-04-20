"""Tests for benchmarks/sidecar.py (SPEC v4 D15, D43, D58)."""

from pathlib import Path

import pytest

from benchmarks.common import SampleVerdict
from benchmarks.sidecar import (
    ResumeAbortError,
    SidecarState,
    append_verdict,
    plan_resume,
    read_sidecar,
    read_verdicts_for_cell,
    write_sidecar,
)


def _state(**overrides) -> SidecarState:
    base = {
        "schema_version": "1.0",
        "cell_id": "llamaguard__xstest",
        "adapter_version": "a3f2b1c8",
        "baseline_config_hash": "7e2d9f4b",
        "samples_total": 200,
        "samples_done": 0,
        "completed": False,
        "last_verdict_sample_id": None,
    }
    base.update(overrides)
    return SidecarState(**base)


class TestWriteReadSidecar:
    def test_roundtrip(self, tmp_path: Path):
        p = tmp_path / "sidecars" / "cell.json"
        state = _state(samples_done=47, last_verdict_sample_id="1a2b3c4d5e6f7890")
        write_sidecar(p, state)
        restored = read_sidecar(p)
        assert restored == state

    def test_missing_returns_none(self, tmp_path: Path):
        assert read_sidecar(tmp_path / "none.json") is None

    def test_corrupted_returns_none(self, tmp_path: Path):
        p = tmp_path / "corrupt.json"
        p.write_text("{not-json,broken")
        assert read_sidecar(p) is None

    def test_partially_structured_returns_none(self, tmp_path: Path):
        """Missing required keys → treat as corrupt → return None → runner redoes."""
        p = tmp_path / "bad.json"
        p.write_text('{"schema_version": "1.0"}')
        assert read_sidecar(p) is None


class TestPlanResume:
    def test_no_sidecar_redoes(self):
        action, offset = plan_resume(None, "v1", "c1")
        assert action == "redo"
        assert offset == 0

    def test_completed_skips(self):
        state = _state(completed=True, samples_done=200)
        action, offset = plan_resume(state, "a3f2b1c8", "7e2d9f4b")
        assert action == "skip"
        assert offset == 200

    def test_partial_resumes_from_offset(self):
        state = _state(samples_done=47)
        action, offset = plan_resume(state, "a3f2b1c8", "7e2d9f4b")
        assert action == "resume-from"
        assert offset == 47

    def test_adapter_drift_raises(self):
        state = _state(samples_done=10)
        with pytest.raises(ResumeAbortError, match="Adapter version changed"):
            plan_resume(state, "NEW_VERSION", "7e2d9f4b")

    def test_config_drift_raises(self):
        state = _state(samples_done=10)
        with pytest.raises(ResumeAbortError, match="Baseline config changed"):
            plan_resume(state, "a3f2b1c8", "NEW_HASH")

    def test_adapter_drift_message_includes_revert_hint(self):
        state = _state()
        with pytest.raises(ResumeAbortError) as exc:
            plan_resume(state, "DIFFERENT", state.baseline_config_hash)
        assert "Delete sidecars" in str(exc.value)


class TestJsonlRoundtrip:
    def _verdict(self, sid: str, label: str = "positive") -> SampleVerdict:
        return SampleVerdict(
            sample_id=sid,
            adapter_name="xstest",
            label=label,
            pred_bool=True,
            pred_score=0.9,
            latency_ms=12.0,
        )

    def test_append_and_read_for_one_cell(self, tmp_path: Path):
        p = tmp_path / "verdicts.jsonl"
        v1 = self._verdict("s1")
        v2 = self._verdict("s2", label="negative")
        append_verdict(p, "llamaguard__xstest", v1)
        append_verdict(p, "llamaguard__xstest", v2)
        verdicts = read_verdicts_for_cell(p, "llamaguard__xstest")
        assert len(verdicts) == 2
        assert verdicts[0].sample_id == "s1"
        assert verdicts[1].sample_id == "s2"

    def test_filters_other_cells(self, tmp_path: Path):
        p = tmp_path / "verdicts.jsonl"
        append_verdict(p, "A__X", self._verdict("a1"))
        append_verdict(p, "B__X", self._verdict("b1"))
        append_verdict(p, "A__X", self._verdict("a2"))
        a = read_verdicts_for_cell(p, "A__X")
        b = read_verdicts_for_cell(p, "B__X")
        assert [v.sample_id for v in a] == ["a1", "a2"]
        assert [v.sample_id for v in b] == ["b1"]

    def test_read_missing_returns_empty(self, tmp_path: Path):
        assert read_verdicts_for_cell(tmp_path / "none.jsonl", "any") == []

    def test_malformed_line_skipped(self, tmp_path: Path):
        p = tmp_path / "verdicts.jsonl"
        append_verdict(p, "A__X", self._verdict("a1"))
        with open(p, "a") as f:
            f.write("{not-json\n")
        append_verdict(p, "A__X", self._verdict("a2"))
        verdicts = read_verdicts_for_cell(p, "A__X")
        assert [v.sample_id for v in verdicts] == ["a1", "a2"]


class TestAtomicityGuarantee:
    """Write ordering: JSONL append+fsync happens before sidecar update.

    A crash between the two leaves JSONL with a verdict the sidecar doesn't
    know about — which is the safer direction (resume replays that sample).
    """

    def test_verdict_visible_without_sidecar_update(self, tmp_path: Path):
        jsonl = tmp_path / "verdicts.jsonl"
        sidecar = tmp_path / "sidecars" / "cell.json"
        v = SampleVerdict(
            sample_id="s1",
            adapter_name="xstest",
            label="positive",
            pred_bool=True,
            pred_score=0.9,
            latency_ms=1.0,
        )
        append_verdict(jsonl, "A__X", v)
        # Simulate crash: no sidecar written yet.
        assert not sidecar.exists()
        # Verdict is still durable.
        assert read_verdicts_for_cell(jsonl, "A__X") == [v]
