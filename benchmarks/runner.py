"""Core head-to-head runner internals (SPEC v4 D15, D26, D35, D43).

``run_cell`` executes one (baseline, dataset) cell. The CLI entrypoint in
``benchmarks.run_head_to_head`` composes rubric/config/adapters and calls this
per cell.

Responsibilities:
- Consult the sidecar for resume state (skip / redo / resume-from).
- For each sample: compute ``sample_id``, time + call ``baseline.score``,
  build a ``SampleVerdict`` (including ``skipped`` / ``error``), emit run-log
  events, append verdict to JSONL, update the sidecar.
- On ``baseline.score`` exception → record ``error`` and continue (never
  fall back to a paper number per D35).
"""

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Protocol

from .baselines.base import BaselineChecker
from .common import HeadToHeadResult, SampleVerdict, compute_sample_id
from .sidecar import (
    SIDECAR_SCHEMA_VERSION,
    SidecarState,
    append_verdict,
    plan_resume,
    read_sidecar,
    read_verdicts_for_cell,
    write_sidecar,
)


class _SampleLike(Protocol):
    text: str
    label: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class RunLogger:
    """Appends structured events to ``run.jsonl`` (SPEC v4 D26)."""

    def __init__(self, log_path: Path):
        self._path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, **fields) -> None:
        row = {"ts": _now_iso(), **fields}
        with open(self._path, "a") as f:
            f.write(json.dumps(row) + "\n")

    def start(self, baseline: str, dataset: str, sample_id: str) -> None:
        self._emit(
            baseline=baseline,
            dataset=dataset,
            sample_id=sample_id,
            phase="start",
            error_type=None,
            error_msg=None,
        )

    def complete(self, baseline: str, dataset: str, sample_id: str) -> None:
        self._emit(
            baseline=baseline,
            dataset=dataset,
            sample_id=sample_id,
            phase="complete",
            error_type=None,
            error_msg=None,
        )

    def error(
        self,
        baseline: str,
        dataset: str,
        sample_id: Optional[str],
        error_type: str,
        error_msg: str,
    ) -> None:
        self._emit(
            baseline=baseline,
            dataset=dataset,
            sample_id=sample_id,
            phase="error",
            error_type=error_type,
            error_msg=error_msg,
        )

    def red_alert(self, baseline: str, error_type: str, error_msg: str) -> None:
        """For cross-cell events like vendor drift (SPEC v4 D47)."""
        self._emit(
            baseline=baseline,
            dataset=None,
            sample_id=None,
            phase="red_alert",
            error_type=error_type,
            error_msg=error_msg,
        )


def run_cell(
    baseline: BaselineChecker,
    baseline_name: str,
    dataset_name: str,
    samples: List[_SampleLike],
    adapter_name: str,
    adapter_version: str,
    baseline_config_hash: str,
    run_dir: Path,
    run_logger: RunLogger,
    verbose: bool = False,
) -> HeadToHeadResult:
    """Execute one cell; resume from sidecar; return the aggregated result.

    Score-emission errors are recorded as ``SampleVerdict.error`` and the loop
    continues — per D35 a baseline failure yields a blank cell in the doc,
    never a silent fallback.
    """
    cell_id = f"{baseline_name}__{dataset_name}"
    sidecar_path = run_dir / "sidecars" / f"{cell_id}.json"
    jsonl_path = run_dir / "head_to_head_verdicts.jsonl"

    existing = read_sidecar(sidecar_path)
    action, offset = plan_resume(existing, adapter_version, baseline_config_hash)

    verdicts: List[SampleVerdict] = []

    if action == "skip":
        verdicts = read_verdicts_for_cell(jsonl_path, cell_id)
        return HeadToHeadResult(
            baseline=baseline_name,
            dataset=dataset_name,
            samples=verdicts,
            adapter_version=adapter_version,
            baseline_config_hash=baseline_config_hash,
            score_emitting=baseline.score_emitting,
        )

    if action == "resume-from":
        verdicts = read_verdicts_for_cell(jsonl_path, cell_id)
        # Trim to offset to avoid double-processing.
        verdicts = verdicts[:offset]

    start_time = time.time()
    total = len(samples)

    for idx in range(offset, total):
        sample = samples[idx]
        sample_id = compute_sample_id(adapter_name, adapter_version, sample.text)
        run_logger.start(baseline_name, dataset_name, sample_id)

        t0 = time.time()
        pred_score: Optional[float] = None
        pred_bool = False
        error_str: Optional[str] = None
        try:
            pred_score = float(baseline.score(sample.text))
            pred_bool = pred_score >= baseline.default_threshold
        except Exception as exc:  # noqa: BLE001 — D35 blank cell + note
            error_str = f"{type(exc).__name__}: {exc}"
            run_logger.error(
                baseline_name, dataset_name, sample_id, type(exc).__name__, str(exc)
            )
        latency_ms = (time.time() - t0) * 1000.0

        verdict = SampleVerdict(
            sample_id=sample_id,
            adapter_name=adapter_name,
            label=sample.label,
            pred_bool=pred_bool,
            pred_score=pred_score if baseline.score_emitting else None,
            latency_ms=latency_ms,
            error=error_str,
        )
        verdicts.append(verdict)
        append_verdict(jsonl_path, cell_id, verdict)
        write_sidecar(
            sidecar_path,
            SidecarState(
                schema_version=SIDECAR_SCHEMA_VERSION,
                cell_id=cell_id,
                adapter_version=adapter_version,
                baseline_config_hash=baseline_config_hash,
                samples_total=total,
                samples_done=idx + 1,
                completed=False,
                last_verdict_sample_id=sample_id,
            ),
        )
        if error_str is None:
            run_logger.complete(baseline_name, dataset_name, sample_id)

    duration_ms = (time.time() - start_time) * 1000.0

    write_sidecar(
        sidecar_path,
        SidecarState(
            schema_version=SIDECAR_SCHEMA_VERSION,
            cell_id=cell_id,
            adapter_version=adapter_version,
            baseline_config_hash=baseline_config_hash,
            samples_total=total,
            samples_done=total,
            completed=True,
            last_verdict_sample_id=verdicts[-1].sample_id if verdicts else None,
        ),
    )

    return HeadToHeadResult(
        baseline=baseline_name,
        dataset=dataset_name,
        samples=verdicts,
        adapter_version=adapter_version,
        baseline_config_hash=baseline_config_hash,
        score_emitting=baseline.score_emitting,
        duration_ms=duration_ms,
    )


def iter_run_log(run_dir: Path) -> Iterable[dict]:
    """Yield parsed events from a run.jsonl. Skips malformed lines."""
    p = run_dir / "run.jsonl"
    if not p.exists():
        return
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
