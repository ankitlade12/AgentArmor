"""Public-API developer-experience guarantees.

- The exceptions a user actually catches must be importable from the top level
  (the quickstart shows `except agentarmor.BudgetExhausted`).
- A py.typed marker must ship so type checkers/IDEs see the annotations.
- The huge init() kwargs surface must be annotated so it autocompletes.
"""
import inspect
import os

import agentarmor


COMMON_EXCEPTIONS = [
    "BudgetExhausted",
    "InjectionDetected",
    "RateLimitExceeded",
    "FilterViolation",
    "HookError",
    "PatchError",
    "ToolCallBlocked",
]


def test_common_exceptions_are_top_level_importable():
    for name in COMMON_EXCEPTIONS:
        assert hasattr(agentarmor, name), f"agentarmor.{name} is not importable"
        assert isinstance(getattr(agentarmor, name), type)


def test_common_exceptions_are_in_dunder_all():
    for name in COMMON_EXCEPTIONS:
        assert name in agentarmor.__all__, f"{name} missing from __all__"


def test_py_typed_marker_is_shipped():
    pkg_dir = os.path.dirname(agentarmor.__file__)
    assert os.path.exists(os.path.join(pkg_dir, "py.typed")), "py.typed marker missing"


def test_init_public_params_are_annotated():
    sig = inspect.signature(agentarmor.init)
    for param in ["budget", "shield", "filter", "record", "rate_limit", "context_guard"]:
        assert sig.parameters[param].annotation is not inspect.Parameter.empty, (
            f"init() param '{param}' has no type annotation"
        )
