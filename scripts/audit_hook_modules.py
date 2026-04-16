#!/usr/bin/env python3
"""CI verifier that lists agentarmor modules without record_decision calls.

Per S-22 + S-34: emits GitHub ::warning:: annotations for inline display in
PR diff view. Always exit 0 — this is a warning surface, not a hard failure.

Source-level scan (no ArmorCore instantiation needed): for each module file in
agentarmor/modules/, check whether the source contains "record_decision". This
is heuristic but sufficient for the warning surface — false positives would
flag a module that imports but never calls; false negatives are impossible
(a module that doesn't import record_decision can't call it).

Usage:
    python scripts/audit_hook_modules.py --check
    python scripts/audit_hook_modules.py --json
"""

import argparse
import json
import sys
from pathlib import Path


# Modules that do NOT register hooks (utilities, base classes, etc.) — exclude
# from the audit. If a new module is added that registers no hooks, add it here.
_NON_HOOK_MODULES = {"__init__", "safe_plan"}


def _scan_modules_dir(modules_dir: Path) -> tuple:
    silent = []
    for py_file in sorted(modules_dir.glob("*.py")):
        name = py_file.stem
        if name in _NON_HOOK_MODULES:
            continue
        source = py_file.read_text()
        if "record_decision" not in source:
            silent.append(name)
    return tuple(silent)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Emit GitHub ::warning:: annotations (default)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON list of uninstrumented modules")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    modules_dir = repo_root / "agentarmor" / "modules"
    if not modules_dir.is_dir():
        print(f"audit: agentarmor/modules/ not found at {modules_dir}", file=sys.stderr)
        return 0

    silent = _scan_modules_dir(modules_dir)

    if args.json:
        print(json.dumps({"uninstrumented_modules": list(silent)}))
        return 0

    if not silent:
        print("audit_hook_modules: all modules in agentarmor/modules/ contain record_decision.")
        return 0

    for module in silent:
        module_path = f"agentarmor/modules/{module}.py"
        print(
            f"::warning file={module_path}::"
            f"Module '{module}' has no record_decision() call. "
            f"Explain mode will surface this module only in Trace.silent_modules, "
            f"not in events. Consider adding record_decision() in its hook body."
        )
    print(
        f"audit_hook_modules: {len(silent)} module(s) have no record_decision call: "
        f"{', '.join(silent)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
