"""AgentArmor modules wrapped as ``BaselineChecker`` for the head-to-head runner
(SPEC v4 D3).

Each wrapper constructs the production AgentArmor module and translates its
detection API to the uniform ``score(text) -> float`` interface. v1 wrappers
emit 0.0/1.0 only (``score_emitting = False``) — the modules' native detection
API raises on block, and we surface the raise as the positive signal without
introspecting internal scores. Extracting raw confidence values for PR curves
is a follow-up; documented in the "Why a PR curve is missing" note.

Registered baselines:
- ``agentarmor_shield`` — regex prompt-injection patterns (ShieldModule)
- ``agentarmor_ml_shield`` — TF-IDF prompt-injection classifier (MLShieldModule)
- ``agentarmor_toxicity`` — multi-category toxicity filter (ToxicityModule)
"""

from typing import Any, Dict, Optional

from .base import BaselineChecker, register_baseline


def _mk_request_ctx(text: str):
    from agentarmor.hooks import RequestContext

    return RequestContext(
        messages=[{"role": "user", "content": text}],
        model="test",
    )


@register_baseline
class AgentArmorShieldBaseline(BaselineChecker):
    """Wraps ``agentarmor.modules.shield.ShieldModule`` — regex patterns only."""

    name = "agentarmor_shield"
    description = "AgentArmor regex shield (prompt-injection patterns)"
    default_threshold = 0.5
    score_emitting = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._module = None

    def _load(self):
        if self._module is None:
            from agentarmor.modules.shield import ShieldModule

            self._module = ShieldModule(on_detect="block")
        return self._module

    def score(self, text: str) -> float:
        module = self._load()
        try:
            module.pre_check(_mk_request_ctx(text))
            return 0.0
        except Exception:
            return 1.0


@register_baseline
class AgentArmorMLShieldBaseline(BaselineChecker):
    """Wraps ``agentarmor.modules.ml_shield.MLShieldModule`` — TF-IDF classifier.

    Uses AgentArmor's default threshold (0.65). We're comparing at the
    module's shipping configuration — not tuning to a per-dataset sweet spot
    (SPEC v4 non-goal).
    """

    name = "agentarmor_ml_shield"
    description = "AgentArmor ML shield (TF-IDF prompt-injection classifier)"
    default_threshold = 0.65
    score_emitting = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._module = None

    def _load(self):
        if self._module is None:
            from agentarmor.modules.ml_shield import MLShieldModule

            self._module = MLShieldModule(on_detect="block")
        return self._module

    def score(self, text: str) -> float:
        module = self._load()
        try:
            module.pre_check(_mk_request_ctx(text))
            return 0.0
        except Exception:
            return 1.0


@register_baseline
class AgentArmorToxicityBaseline(BaselineChecker):
    """Wraps ``agentarmor.modules.toxicity.ToxicityModule`` — multi-category scan."""

    name = "agentarmor_toxicity"
    description = "AgentArmor toxicity filter (multi-category)"
    default_threshold = 0.5
    score_emitting = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._module = None

    def _load(self):
        if self._module is None:
            from agentarmor.modules.toxicity import ToxicityModule

            self._module = ToxicityModule(on_detect="block")
        return self._module

    def score(self, text: str) -> float:
        findings = self._load().scan_text(text)
        return 1.0 if findings else 0.0
