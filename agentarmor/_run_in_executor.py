"""Threadpool helper that propagates explain-mode trace context.

Per S-13: ContextVars don't auto-propagate across threadpool workers.
This helper captures current context with copy_context() and runs the function
within it, so record_decision() etc. see the parent trace.

Per S-31: ProcessPoolExecutor cannot propagate contextvars (separate process).
The helper detects this case, emits ExplainModeWarning, and falls back to
direct submit without context.
"""

import contextvars
import warnings
from concurrent.futures import Executor, ProcessPoolExecutor

from .trace import ExplainModeWarning


def run_in_executor(executor: Executor, fn, *args, **kwargs):
    """Run fn in executor with explain-mode trace context propagated.

    For ThreadPoolExecutor: captures current contextvars and runs fn within
    them, so the worker thread sees the parent trace.

    For ProcessPoolExecutor: explain context cannot cross processes. Emits
    ExplainModeWarning and submits fn directly with no context.

    Returns the executor's Future.
    """
    if isinstance(executor, ProcessPoolExecutor):
        warnings.warn(
            (
                "trace context not propagated to ProcessPoolExecutor; explain "
                "mode is thread-pool only. Use ThreadPoolExecutor for explain support."
            ),
            ExplainModeWarning,
            stacklevel=2,
        )
        return executor.submit(fn, *args, **kwargs)

    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)
