#!/usr/bin/env python3
"""Summarize a head-to-head run log (SPEC v4 D56).

Usage:
    python scripts/analyze_run_log.py <run_dir_or_jsonl>
    python scripts/analyze_run_log.py <path> --errors-only
    python scripts/analyze_run_log.py <path> --cell llamaguard/toxigen

Reads ``run.jsonl`` emitted by ``benchmarks.runner.RunLogger`` and prints a
tabular summary. Runs are usually 5000-10000 events; output groups by cell so
an on-call engineer can locate failures without streaming the raw JSONL.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


def _resolve_path(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        return p / "run.jsonl"
    return p


def _iter_events(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize(events: List[dict]) -> Dict[str, Dict[str, int]]:
    """Return ``cell → {phase → count}`` aggregated over all events."""
    agg: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"start": 0, "complete": 0, "error": 0, "red_alert": 0}
    )
    for ev in events:
        baseline = ev.get("baseline") or "?"
        dataset = ev.get("dataset") or "?"
        cell = f"{baseline}/{dataset}"
        phase = ev.get("phase") or "?"
        agg[cell][phase] = agg[cell].get(phase, 0) + 1
    return dict(agg)


def format_summary(agg: Dict[str, Dict[str, int]]) -> str:
    lines = [
        f"{'Cell':<40} {'start':>7} {'complete':>10} {'error':>7} {'red':>5}",
        "-" * 75,
    ]
    for cell in sorted(agg):
        phases = agg[cell]
        marker = "  ← errors" if phases.get("error", 0) else ""
        lines.append(
            f"{cell:<40} "
            f"{phases.get('start', 0):>7} "
            f"{phases.get('complete', 0):>10} "
            f"{phases.get('error', 0):>7} "
            f"{phases.get('red_alert', 0):>5}"
            f"{marker}"
        )
    return "\n".join(lines)


def format_errors(events: List[dict], cell: str = None) -> str:
    lines = []
    for ev in events:
        if ev.get("phase") != "error":
            continue
        if cell and cell != f"{ev.get('baseline','?')}/{ev.get('dataset','?')}":
            continue
        lines.append(
            f"{ev.get('ts','?')} — {ev.get('baseline','?')}/{ev.get('dataset','?')} "
            f"sample={ev.get('sample_id')} {ev.get('error_type','?')}: {ev.get('error_msg','?')}"
        )
    if not lines:
        return "(no error events)"
    return "\n".join(lines)


def format_cell_detail(events: List[dict], cell: str) -> str:
    target_b, _, target_d = cell.partition("/")
    rows = [
        f"[cell] {cell} — drill-down",
        "-" * 75,
    ]
    count = 0
    for ev in events:
        if ev.get("baseline") != target_b or ev.get("dataset") != target_d:
            continue
        count += 1
        rows.append(
            f"{ev.get('ts','?')} {ev.get('phase','?'):<9} "
            f"sample={ev.get('sample_id')} "
            f"{ev.get('error_type','') or ''} {ev.get('error_msg','') or ''}".rstrip()
        )
    if count == 0:
        rows.append("(no events for this cell)")
    return "\n".join(rows)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize a head-to-head run log.")
    parser.add_argument("path", help="run directory or run.jsonl path")
    parser.add_argument("--errors-only", action="store_true")
    parser.add_argument(
        "--cell",
        type=str,
        default=None,
        help="Restrict to a single cell, e.g. 'llamaguard/toxigen'.",
    )
    args = parser.parse_args(argv)

    log_path = _resolve_path(args.path)
    if not log_path.exists():
        print(f"[error] {log_path} not found", file=sys.stderr)
        return 2

    events = list(_iter_events(log_path))
    if args.cell and not args.errors_only:
        print(format_cell_detail(events, args.cell))
        return 0
    if args.errors_only:
        print(format_errors(events, args.cell))
        return 0
    agg = summarize(events)
    print(format_summary(agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
