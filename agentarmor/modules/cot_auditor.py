import re
from typing import Dict, List, Optional
from ..hooks import ResponseContext
from ..exceptions import ReasoningViolation

# Red-flag patterns in reasoning traces
MISALIGNMENT_PATTERNS = {
    "deception": [
        (r"(?:I(?:'ll| will| should| need to|'m going to)\s+)?(?:hide|conceal|not (?:tell|mention|reveal|disclose))\s+(?:this|that|it|the\b)", "Agent planning to hide information from user"),
        (r"(?:the user|they)\s+(?:won't|shouldn't|doesn't need to|don't need to)\s+(?:know|notice|see|find out)", "Agent intending to keep user uninformed"),
        (r"(?:I(?:'ll| can| should| will)\s+)?(?:pretend|appear|seem|act as if|make it look)", "Agent planning deceptive appearance"),
    ],
    "goal_deviation": [
        (r"(?:ignore|disregard|override|bypass|skip|circumvent)\s+(?:the|my|these|those|their)?\s*(?:instructions|rules|guidelines|constraints|policies|restrictions)", "Agent considering ignoring instructions"),
        (r"(?:my (?:real|actual|true|own)|I (?:actually|really))\s+(?:goal|objective|purpose|intention|want)", "Agent expressing goals different from stated ones"),
        (r"(?:instead of|rather than)\s+(?:what|doing what)\s+(?:they|the user|I was)\s+(?:asked|told|instructed)", "Agent deviating from user's request"),
    ],
    "manipulation": [
        (r"(?:manipulate|trick|deceive|mislead|fool|exploit)\s+(?:the user|them|into)", "Agent planning to manipulate user"),
        (r"(?:make them|get them to|convince them to)\s+(?:think|believe|feel)\s+(?:that)?", "Agent attempting to influence user beliefs"),
        (r"(?:social engineering|phishing|pretexting)", "Agent considering social engineering"),
    ],
    "safety_bypass": [
        (r"(?:bypass|circumvent|disable|turn off|work around|get around)\s+(?:the\s+)?(?:safety|security|filter|guard|check|shield|firewall)", "Agent trying to bypass safety measures"),
        (r"(?:find a (?:way|loophole|workaround)|exploit)\s+(?:to|in|around)", "Agent looking for exploits"),
    ],
    "data_exfiltration": [
        (r"(?:send|transmit|exfiltrate|leak|share|post|upload)\s+(?:the\s+)?(?:data|information|credentials|keys|tokens|secrets|passwords)", "Agent planning data exfiltration"),
        (r"(?:encode|base64|encrypt|obfuscate)\s+(?:the\s+)?(?:data|output|response)\s+(?:to|so|before)", "Agent encoding data to hide exfiltration"),
    ],
}


class CoTAuditorModule:
    def __init__(self,
                 categories: Optional[List[str]] = None,
                 on_detect: str = "block",
                 custom_patterns: Optional[Dict[str, List[tuple]]] = None,
                 audit_thinking: bool = True,
                 audit_reasoning: bool = True,
                 log_findings: bool = True):
        """
        Audits chain-of-thought / reasoning traces for alignment issues.

        Args:
            categories: Which pattern categories to check (default: all)
            on_detect: "block" raises, "warn" logs, "flag" adds metadata
            custom_patterns: Additional patterns {category: [(pattern, desc), ...]}
            audit_thinking: Inspect Anthropic extended thinking blocks
            audit_reasoning: Inspect OpenAI reasoning_content
            log_findings: Store findings for report
        """
        self.categories = categories
        self.on_detect = on_detect
        self.audit_thinking = audit_thinking
        self.audit_reasoning = audit_reasoning
        self.log_findings = log_findings
        self.findings: List[Dict] = []
        self.audited_count = 0
        self.flagged_count = 0

        # Build active patterns
        self.patterns = {}
        active_cats = categories or list(MISALIGNMENT_PATTERNS.keys())
        for cat in active_cats:
            if cat in MISALIGNMENT_PATTERNS:
                self.patterns[cat] = [
                    (re.compile(p, re.IGNORECASE), desc)
                    for p, desc in MISALIGNMENT_PATTERNS[cat]
                ]
        if custom_patterns:
            for cat, pats in custom_patterns.items():
                self.patterns[cat] = [
                    (re.compile(p, re.IGNORECASE), desc)
                    for p, desc in pats
                ]

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Audit the reasoning trace in the response."""
        reasoning_text = self._extract_reasoning(ctx)
        if not reasoning_text:
            return ctx

        self.audited_count += 1
        findings = self._scan(reasoning_text)

        if findings:
            self.flagged_count += 1
            if self.log_findings:
                self.findings.extend(findings)
            self._handle_findings(ctx, findings)

        return ctx

    def _extract_reasoning(self, ctx: ResponseContext) -> str:
        """Extract chain-of-thought text from the response."""
        parts = []

        # Anthropic: extended thinking blocks
        if self.audit_thinking and ctx.raw_response:
            try:
                if ctx.provider == "anthropic":
                    for block in getattr(ctx.raw_response, 'content', []):
                        if getattr(block, 'type', '') == 'thinking':
                            parts.append(getattr(block, 'thinking', ''))
            except Exception:
                pass

        # OpenAI: reasoning_content in message
        if self.audit_reasoning and ctx.raw_response:
            try:
                if ctx.provider == "openai":
                    msg = ctx.raw_response.choices[0].message
                    reasoning = getattr(msg, 'reasoning_content', None)
                    if reasoning:
                        parts.append(reasoning)
            except Exception:
                pass

        return "\n".join(parts)

    def _scan(self, text: str) -> List[Dict]:
        """Scan text for misalignment patterns."""
        findings = []
        for category, patterns in self.patterns.items():
            for compiled, description in patterns:
                matches = compiled.finditer(text)
                for match in matches:
                    findings.append({
                        "category": category,
                        "description": description,
                        "match": match.group()[:100],
                        "position": match.start(),
                    })
        return findings

    def audit_text(self, text: str) -> List[Dict]:
        """Public method to audit arbitrary reasoning text. For manual use."""
        return self._scan(text)

    def _handle_findings(self, ctx, findings):
        if self.on_detect == "block":
            raise ReasoningViolation(
                f"Chain-of-thought audit failed: {len(findings)} issue(s) detected. "
                f"First: {findings[0]['description']}"
            )
        elif self.on_detect == "warn":
            for f in findings:
                print(f"[AgentArmor] COT WARNING [{f['category']}]: {f['description']}")
        elif self.on_detect == "flag":
            summary = "; ".join(f["description"] for f in findings[:3])
            ctx.text = f"[COT AUDIT WARNING: {summary}]\n{ctx.text}"

    def report(self) -> dict:
        categories = {}
        for f in self.findings:
            cat = f["category"]
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "audited_count": self.audited_count,
            "flagged_count": self.flagged_count,
            "findings_by_category": categories,
            "recent_findings": self.findings[-5:],
        }
