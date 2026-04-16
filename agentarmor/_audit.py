"""Runtime introspection of which agentarmor modules opt into record_decision().

Replaces the dropped-in-SPEC-v4 generated `_uninstrumented_modules.py` file
(per S-25). Walks the live HookRegistry, derives module names from each
registered hook's `__module__`, and inspects source for `record_decision` calls.

Used by:
- runtime: agentarmor.init() consults this to fire the S-11 startup
  ExplainModeWarning listing modules that won't surface detail in traces
- CI: scripts/audit_hook_modules.py wraps this to emit GitHub ::warning::
  annotations per S-34
"""

import inspect
from typing import Optional


def get_uninstrumented_modules(registry) -> tuple:
    """Returns sorted tuple of module names whose registered hooks do NOT call
    record_decision in their source. Skips hooks whose source is unreadable
    (e.g. C-extension or dynamically-generated functions).

    A module counts as "instrumented" if ANY of its registered hooks calls
    record_decision; it's "uninstrumented" only if NONE of them do.
    """
    instrumented = set()
    uninstrumented = set()

    all_hooks = (
        list(registry._before_request)
        + list(registry._after_response)
        + list(registry._on_stream_chunk)
    )

    for hook in all_hooks:
        module_name = _module_name_from_hook(hook)
        if module_name is None:
            continue
        try:
            source = inspect.getsource(hook)
        except (OSError, TypeError):
            continue
        if "record_decision" in source:
            instrumented.add(module_name)
        else:
            uninstrumented.add(module_name)

    return tuple(sorted(uninstrumented - instrumented))


def _module_name_from_hook(hook) -> Optional[str]:
    """'agentarmor.modules.shield' -> 'shield'. None for non-module hooks."""
    func_module = getattr(hook, "__module__", None)
    if func_module is None:
        return None
    parts = func_module.rsplit(".", 1)
    if len(parts) < 2 or parts[0] != "agentarmor.modules":
        return None
    return parts[1]
