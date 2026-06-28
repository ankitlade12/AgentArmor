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

            # Explicitly enable the built-in ML classifier: this baseline measures
            # AgentArmor's full toxicity capability (regex + ML). The ML is opt-in
            # for end users (off by default — it over-fires on benign text), so we
            # pin it on here to keep the benchmark's behaviour and published
            # numbers stable rather than inheriting the user-facing default.
            self._module = ToxicityModule(on_detect="block", use_builtin_ml=True)
        return self._module

    def score(self, text: str) -> float:
        findings = self._load().scan_text(text)
        return 1.0 if findings else 0.0


@register_baseline
class AgentArmorCombinedBaseline(BaselineChecker):
    """Shipping deployment shape: shield + ml_shield + toxicity run in parallel,
    any one firing = blocked. This is how AgentArmor is typically configured in
    production, so it's the most honest comparison against a single-model
    vendor baseline like LlamaGuard.

    ``score`` returns 1.0 on first-firing module, 0.0 if all pass. Short-circuits
    for efficiency: on toxicity datasets the toxicity module tends to fire
    first and the jailbreak modules are never evaluated.
    """

    name = "agentarmor_combined"
    description = (
        "AgentArmor combined shield stack (shield + ml_shield + toxicity; "
        "any fires → blocked). Matches typical production deployment."
    )
    default_threshold = 0.5
    score_emitting = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._shield = None
        self._ml_shield = None
        self._toxicity = None

    def _load(self):
        if self._shield is None:
            self._shield = AgentArmorShieldBaseline()
            self._ml_shield = AgentArmorMLShieldBaseline()
            self._toxicity = AgentArmorToxicityBaseline()

    def score(self, text: str) -> float:
        self._load()
        for module in (self._shield, self._ml_shield, self._toxicity):
            if module.score(text) >= 0.5:
                return 1.0
        return 0.0
