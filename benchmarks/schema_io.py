"""Summary JSON read/write with schema-version enforcement (SPEC v4 D27, D52).

Design
------
- 1.x readers load all 1.x writers. Additive-minor field changes are
  tolerated in both directions: new fields on read are ignored; missing new
  fields on load default to ``None`` / default values at consumer sites.
- Unknown-major readers (e.g. a 1.x reader encountering 2.0) raise
  ``UnsupportedSchemaError`` loudly.
- Validation is structural: required top-level and per-cell fields are
  enforced; type mismatches raise ``SchemaValidationError``. We deliberately
  avoid a full JSON Schema library — the subset we need is small.

Breaking changes (require major bump):
- Removing a previously-required field.
- Changing a field's meaning (e.g. f1 now 0-100 instead of 0-1).
- Changing a field's type (e.g. scalar → list).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List


class UnsupportedSchemaError(RuntimeError):
    """Reader encountered a schema major version it does not support."""


class SchemaValidationError(ValueError):
    """Required fields missing or type mismatch."""


SUPPORTED_MAJOR = "1"

_TOP_LEVEL_REQUIRED = (
    "schema_version",
    "run_id",
    "agentarmor_version",
    "run_date",
    "rubric_version",
    "cells",
    "tolerances",
)

_CELL_REQUIRED = (
    "baseline",
    "dataset",
    "n_samples",
    "score_emitting",
    "operating_point",
    "degenerate_flag",
)

_TOLERANCES_REQUIRED = (
    "same_day_spread_95p",
    "one_week_drift_max",
)

_SCHEMA_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def _check_type(value: Any, allowed: tuple, field: str) -> None:
    if not isinstance(value, allowed):
        raise SchemaValidationError(
            f"field {field!r} has type {type(value).__name__}, expected {allowed}"
        )


def validate_summary(data: Dict[str, Any]) -> None:
    """Raise ``SchemaValidationError`` if structural constraints fail.

    Ignores unknown additional fields to preserve forward-compat (SPEC v4 D27).
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(f"root must be a dict, got {type(data).__name__}")

    for key in _TOP_LEVEL_REQUIRED:
        if key not in data:
            raise SchemaValidationError(f"missing required field {key!r}")

    version = data["schema_version"]
    if not isinstance(version, str) or not _SCHEMA_VERSION_RE.match(version):
        raise SchemaValidationError(
            f"schema_version {version!r} must match major.minor (e.g. '1.0')"
        )

    cells = data["cells"]
    _check_type(cells, (list,), "cells")
    for i, cell in enumerate(cells):
        _check_type(cell, (dict,), f"cells[{i}]")
        for key in _CELL_REQUIRED:
            if key not in cell:
                raise SchemaValidationError(
                    f"cells[{i}] missing required field {key!r}"
                )
        _check_type(cell["baseline"], (str,), f"cells[{i}].baseline")
        _check_type(cell["dataset"], (str,), f"cells[{i}].dataset")
        _check_type(cell["n_samples"], (int,), f"cells[{i}].n_samples")
        _check_type(cell["score_emitting"], (bool,), f"cells[{i}].score_emitting")
        _check_type(cell["degenerate_flag"], (bool,), f"cells[{i}].degenerate_flag")

    tol = data["tolerances"]
    _check_type(tol, (dict,), "tolerances")
    for key in _TOLERANCES_REQUIRED:
        if key not in tol:
            raise SchemaValidationError(
                f"tolerances missing required field {key!r}"
            )


def parse_major(version: str) -> str:
    m = _SCHEMA_VERSION_RE.match(version)
    if not m:
        raise SchemaValidationError(
            f"schema_version {version!r} must match major.minor"
        )
    return m.group(1)


def load_summary(path: Path) -> Dict[str, Any]:
    """Read + validate a summary JSON; raise on unknown major.

    Additive-minor tolerated: a 1.0 reader succeeds on 1.1 data, ignoring new
    fields.
    """
    raw = Path(path).read_text()
    data = json.loads(raw)
    version = data.get("schema_version", "")
    if isinstance(version, str) and version:
        try:
            major = parse_major(version)
        except SchemaValidationError:
            raise
        if major != SUPPORTED_MAJOR:
            raise UnsupportedSchemaError(
                f"unsupported schema major version {major!r} "
                f"(schema_version={version!r}); this reader supports "
                f"{SUPPORTED_MAJOR}.x only. Upgrade the reader or regenerate "
                f"against an older writer."
            )
    validate_summary(data)
    return data


def dump_summary(path: Path, data: Dict[str, Any]) -> Path:
    """Validate + write summary JSON deterministically (sorted keys)."""
    validate_summary(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return path
