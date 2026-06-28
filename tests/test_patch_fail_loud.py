"""Patching must fail LOUD, not silent.

Every patch target sits on a private SDK module path wrapped in
`except ImportError: pass`. If a provider SDK is installed but its patch target
has moved/renamed (version drift), the import fails and is swallowed — leaving
that provider's guardrails silently OFF with no signal. A genuinely-absent SDK
should still be skipped quietly.
"""
import warnings

import agentarmor
from agentarmor.core import ArmorCore


def test_warn_if_installed_warns_for_an_installed_but_unpatchable_sdk():
    core = ArmorCore()
    # openai is installed in the test env; simulate its patch target failing.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core._warn_if_installed("openai", ImportError("cannot import Completions"))
    assert any(
        "INACTIVE" in str(w.message) and "openai" in str(w.message)
        for w in caught
    ), "an installed-but-unpatchable SDK must warn that guardrails are inactive"


def test_warn_if_installed_is_silent_for_an_absent_sdk():
    core = ArmorCore()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core._warn_if_installed(
            "definitely_not_a_real_package_zzz", ImportError("no module")
        )
    assert caught == [], "a genuinely-absent SDK must be skipped silently"


def test_patch_warns_when_installed_sdk_patch_method_is_missing(monkeypatch):
    """If the private class still imports but the method moved, warn instead of
    raising and leaving users without a clear inactive-guardrails signal."""
    from openai.resources.chat.completions import Completions

    monkeypatch.delattr(Completions, "create")

    core = ArmorCore()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core.patch()
        core.unpatch()

    assert any(
        "INACTIVE" in str(w.message) and "openai" in str(w.message)
        for w in caught
    )


def test_patch_does_not_warn_when_sdks_are_patchable():
    """Happy path: with openai/anthropic importable and patchable, patch()
    must not emit the inactive-guardrails warning."""
    core = ArmorCore()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core.patch()
        core.unpatch()
    assert not any("INACTIVE" in str(w.message) for w in caught)
