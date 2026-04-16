"""Smoke tests for bench.py + audit_hook_modules.py — verify they run without
errors and produce expected output shapes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bench_runs_to_completion():
    """python -m agentarmor.bench --explain runs without raising."""
    from agentarmor.bench import run_explain_bench
    result = run_explain_bench(n=200)  # small N for fast test
    assert "control_us" in result
    assert "explain_off_us" in result
    assert "explain_on_us" in result
    assert result["explain_off_us"] >= result["control_us"]
    assert result["explain_on_us"] >= result["explain_off_us"]


def test_bench_cli_exit_zero():
    """python -m agentarmor.bench --explain returns exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "agentarmor.bench", "--explain", "-n", "200", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "control_us" in parsed


def test_bench_cli_no_args_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "agentarmor.bench"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--explain" in result.stdout


def test_audit_script_exit_zero():
    """audit_hook_modules.py never blocks CI even when modules are silent."""
    result = subprocess.run(
        [sys.executable, "scripts/audit_hook_modules.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0


def test_audit_script_emits_github_warning_format():
    result = subprocess.run(
        [sys.executable, "scripts/audit_hook_modules.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # GitHub annotation format: ::warning file=...::message
    assert "::warning file=agentarmor/modules/" in result.stdout


def test_audit_script_json_output_shape():
    result = subprocess.run(
        [sys.executable, "scripts/audit_hook_modules.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "uninstrumented_modules" in parsed
    assert isinstance(parsed["uninstrumented_modules"], list)
    # At v1.4.0 ship time, all detection modules are still silent
    assert "shield" in parsed["uninstrumented_modules"]
    assert "filter" in parsed["uninstrumented_modules"]
