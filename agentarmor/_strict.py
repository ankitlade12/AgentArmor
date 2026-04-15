"""
Strict-mode kwarg validation for agentarmor.init() / ArmorCore.__init__.

Catches typos at init time so users don't silently misconfigure shields.
Activated via init(strict=True). Default off for backwards compatibility.
"""

import difflib
import inspect
import warnings
from typing import Iterable, Optional, Set

from .exceptions import ConfigurationError


# Common typo aliases — checked BEFORE difflib because difflib otherwise
# returns confusing matches (e.g. "recorder" → "record" where both names
# are plausible but mean different things).
KNOWN_TYPO_ALIASES = {
    "unicode_sheild": "unicode_shield",
    "shields": "shield",
    "filters": "filter",
    "rate_limits": "rate_limit",
    "ratelimit": "rate_limit",
    "tool_firewalls": "tool_firewall",
    "mcp_firewalls": "mcp_firewall",
    "honeytool": "honeytools",
    "ml_sheild": "ml_shield",
    "exfiltration": "exfiltration_guard",
    "exfil_guard": "exfiltration_guard",
    "privilege_escalation_guard": "privilege_escalation",
    "code_security": "code_shield",
    # Short stems users naturally type for module categories
    "redactor": "filter",
    "redact": "filter",
    "pii": "filter",
    "firewall": "tool_firewall",
    "firewalls": "tool_firewall",
    "cot": "cot_auditor",
    "hitl": "hitl_gate",
    "taint": "taint_tracker",
    "echo": "echo_chamber",
    "drift": "semantic_drift",
    "mcp": "mcp_firewall",
    "logs": "record",
    "log": "record",
    "logger": "record",
    "logging": "record",
    "budget_limit": "budget",
}

# Names that are EASILY confused with real kwargs but mean different things.
# We surface both options in the suggestion.
CONFUSING_PAIRS = {
    "recorder": "record",
    "record_logs": "record",
    "logging": "record",
    "log": "record",
}

# Per-process dedup so test suites that loop over typo'd init() don't spam.
_warned_typos: Set[str] = set()


def known_init_kwargs() -> Set[str]:
    """Compute the canonical set of known init kwargs by introspecting
    ArmorCore.__init__. We use ArmorCore (not init()) because that's the
    authoritative parameter list and stays in sync as modules are added."""
    from .core import ArmorCore  # lazy import to avoid cycle

    sig = inspect.signature(ArmorCore.__init__)
    return {
        name for name, param in sig.parameters.items()
        if name != "self"
        and param.kind not in (inspect.Parameter.VAR_KEYWORD,
                                inspect.Parameter.VAR_POSITIONAL)
    }


def suggest(bad_key: str, known: Set[str]) -> Optional[str]:
    """Return a suggested replacement for a bad kwarg, or None if we
    can't confidently suggest one."""
    if bad_key in KNOWN_TYPO_ALIASES:
        return KNOWN_TYPO_ALIASES[bad_key]
    matches = difflib.get_close_matches(bad_key, known, n=1, cutoff=0.7)
    return matches[0] if matches else None


def _format_error(bad_key: str, suggestion: Optional[str]) -> str:
    msg = f"unknown kwarg {bad_key!r} passed to agentarmor.init()"
    if bad_key in CONFUSING_PAIRS:
        real = CONFUSING_PAIRS[bad_key]
        msg += (
            f". {bad_key!r} is not an agentarmor kwarg — "
            f"if you meant the {real!r} module, use {real}=True."
        )
    elif suggestion is not None:
        msg += f". Did you mean {suggestion!r}?"
    return msg


_STRICT_CASE_TYPOS = frozenset({"strict", "STRICT", "Strict"})


def validate_kwargs(received: Iterable[str], strict: bool) -> None:
    """Validate top-level init kwargs.

    Args:
        received: Iterable of kwarg names actually passed by the caller.
        strict: If True, raise ConfigurationError on unknown kwargs.
            If False, emit a UserWarning (visible by default, unlike
            DeprecationWarning) at most once per (process, bad_key) pair.
    """
    known = known_init_kwargs()
    for bad_key in received:
        if bad_key in known:
            continue

        # Special-case: case-typo of the `strict` kwarg itself is uniquely
        # dangerous — silently dropping it means EVERY subsequent typo'd
        # kwarg in the same call goes silent too. Always raise hard,
        # regardless of strict flag.
        if bad_key != "strict" and bad_key in _STRICT_CASE_TYPOS:
            raise ConfigurationError(
                f"unknown kwarg {bad_key!r}. kwarg names are case-sensitive — "
                f"did you mean 'strict' (lowercase)? Note: case typos on "
                f"'strict' are always rejected because silently dropping them "
                f"would defeat strict-mode validation entirely."
            )

        suggestion = suggest(bad_key, known)
        msg = _format_error(bad_key, suggestion)

        if strict:
            raise ConfigurationError(msg)

        # Non-strict: warn once per (process, bad_key)
        if bad_key not in _warned_typos:
            _warned_typos.add(bad_key)
            warnings.warn(msg, UserWarning, stacklevel=4)


def reset_warning_state() -> None:
    """Clear the per-process dedup set. Test-only helper."""
    _warned_typos.clear()
