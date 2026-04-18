"""Per-cell sidecar + JSONL verdict IO for the head-to-head runner
(SPEC v4 D15, D43, D58).

Resume semantics:
- Missing sidecar            → action="redo" (fresh run)
- Truncated / corrupt JSON   → action="redo" (safe default)
- adapter_version mismatch   → raise ResumeAbortError
- baseline_config_hash drift → raise ResumeAbortError
- completed=True             → action="skip" (reload verdicts from JSONL)
- completed=False, matching  → action="resume-from" with last-sample offset

Write ordering (atomicity):
1. Append verdict to JSONL + fsync.
2. Write sidecar to a temp file and ``os.replace`` to target + fsync dir.
This guarantees the JSONL is never ahead of the sidecar's reported progress.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from .common import SampleVerdict

SIDECAR_SCHEMA_VERSION = "1.0"


class ResumeAbortError(RuntimeError):
    """Raised when resume detects adapter- or config-version drift."""


@dataclass(frozen=True)
class SidecarState:
    schema_version: str
    cell_id: str
    adapter_version: str
    baseline_config_hash: str
    samples_total: int
    samples_done: int
    completed: bool
    last_verdict_sample_id: Optional[str]


ResumeAction = Literal["redo", "skip", "resume-from"]


def write_sidecar(sidecar_path: Path, state: SidecarState) -> None:
    """Atomic sidecar write: temp file + os.replace + fsync directory."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    payload = json.dumps(asdict(state), indent=2)
    with open(tmp, "w") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, sidecar_path)
    # fsync the directory so the replace is durable.
    dir_fd = os.open(str(sidecar_path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read_sidecar(sidecar_path: Path) -> Optional[SidecarState]:
    """Return the sidecar state, or None if missing/corrupt."""
    if not sidecar_path.exists():
        return None
    try:
        data = json.loads(sidecar_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    try:
        return SidecarState(
            schema_version=data["schema_version"],
            cell_id=data["cell_id"],
            adapter_version=data["adapter_version"],
            baseline_config_hash=data["baseline_config_hash"],
            samples_total=int(data["samples_total"]),
            samples_done=int(data["samples_done"]),
            completed=bool(data["completed"]),
            last_verdict_sample_id=data.get("last_verdict_sample_id"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def plan_resume(
    sidecar: Optional[SidecarState],
    current_adapter_version: str,
    current_config_hash: str,
) -> Tuple[ResumeAction, int]:
    """Decide what to do given the sidecar state and current code/config.

    Returns ``(action, offset)`` where offset is the number of samples already
    completed (0 for redo/skip).
    """
    if sidecar is None:
        return ("redo", 0)
    if sidecar.adapter_version != current_adapter_version:
        raise ResumeAbortError(
            f"Adapter version changed for cell {sidecar.cell_id}: "
            f"sidecar={sidecar.adapter_version} current={current_adapter_version}. "
            f"Delete sidecars or revert the adapter change."
        )
    if sidecar.baseline_config_hash != current_config_hash:
        raise ResumeAbortError(
            f"Baseline config changed for cell {sidecar.cell_id}: "
            f"sidecar={sidecar.baseline_config_hash} "
            f"current={current_config_hash}. Revert config.yaml or delete sidecars."
        )
    if sidecar.completed:
        return ("skip", sidecar.samples_total)
    return ("resume-from", sidecar.samples_done)


# ---------------------------------------------------------------------------
# JSONL verdict append / read
# ---------------------------------------------------------------------------


def append_verdict(
    jsonl_path: Path, cell_id: str, verdict: SampleVerdict
) -> None:
    """Append one verdict as a JSONL row tagged with the cell_id. Fsyncs.

    The cell_id prefix lets a single JSONL hold verdicts from many cells; each
    row is a self-contained record.
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"cell_id": cell_id, **asdict(verdict)}
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_verdicts_for_cell(
    jsonl_path: Path, cell_id: str
) -> List[SampleVerdict]:
    """Return verdicts in insertion order for a given cell_id."""
    if not jsonl_path.exists():
        return []
    out: List[SampleVerdict] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("cell_id") != cell_id:
                continue
            row.pop("cell_id", None)
            out.append(SampleVerdict(**row))
    return out
