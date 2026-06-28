"""Regression tests: init() must be safe to call more than once.

A second init() previously captured the already-wrapped method as the
"original", so teardown() restored the wrapper instead of the genuine SDK
method (permanent in-process corruption), and the previous core's hooks kept
running underneath the new core (double budget charges, duplicate audit rows).
"""
import pytest
from unittest.mock import MagicMock

import agentarmor

openai = pytest.importorskip("openai")


def _mock_response(text="reply"):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage = None
    return resp


def test_double_init_then_teardown_restores_original_sdk_method():
    """teardown() after two init() calls must restore the genuine SDK method."""
    Completions = openai.resources.chat.completions.Completions
    true_original = Completions.create

    try:
        agentarmor.init(budget="$5")
        agentarmor.init(budget="$5")  # second init — the dangerous case
    finally:
        agentarmor.teardown()

    assert Completions.create is true_original, (
        "teardown() left the SDK patched after a double init() — "
        "the wrapper was captured as the original"
    )


def test_reinit_does_not_leave_previous_core_hooks_running():
    """A re-init must replace the previous core, not stack on top of it."""
    client = openai.OpenAI(api_key="mock")
    Completions = openai.resources.chat.completions.Completions
    original_create = Completions.create
    Completions.create = MagicMock(return_value=_mock_response())

    old_core_ran = {"n": 0}
    new_core_ran = {"n": 0}

    try:
        core1 = agentarmor.init()

        @core1.registry.register_after_response
        def cb_old(ctx):
            old_core_ran["n"] += 1
            return ctx

        core2 = agentarmor.init()  # re-init should retire core1

        @core2.registry.register_after_response
        def cb_new(ctx):
            new_core_ran["n"] += 1
            return ctx

        client.chat.completions.create(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert new_core_ran["n"] == 1, "active core's hook should run exactly once"
        assert old_core_ran["n"] == 0, (
            "retired core's hook still ran — init() double-wrapped the SDK method"
        )
    finally:
        agentarmor.teardown()
        Completions.create = original_create
