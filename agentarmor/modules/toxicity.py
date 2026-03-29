import re
import warnings
from typing import Dict, List, Optional
from ..hooks import ResponseContext
from ..exceptions import ToxicContentDetected

# Toxicity categories with keyword patterns
TOXICITY_PATTERNS = {
    "hate_speech": {
        "patterns": [
            # Patterns that detect hate speech structures (not specific slurs)
            r"\b(?:all|every|those)\s+\w+\s+(?:should|must|need to)\s+(?:die|be killed|be eliminated|go back)",
            r"\b(?:exterminate|genocide|ethnic cleansing)\b",
            r"\b(?:subhuman|untermensch|inferior race)\b",
            r"\b(?:white\s+(?:power|supremacy|nationalist)|aryan\s+(?:race|nation))\b",
        ],
        "severity": "critical",
    },
    "violence": {
        "patterns": [
            r"\b(?:how to|instructions? (?:for|to)|steps? to|guide to)\s+(?:kill|murder|assassinate|poison|bomb|shoot)\b",
            r"\b(?:make|build|create|construct)\s+(?:a\s+)?(?:bomb|explosive|weapon|poison|bioweapon)\b",
            r"\b(?:torture|mutilate|dismember)\s+(?:someone|a person|them|him|her)\b",
            r"\b(?:how to|tell me how|teach me|show me|explain how)\s+(?:to\s+)?(?:kill|murder|harm|hurt|attack|assault|injure)\b",
            r"\b(?:weapon|gun|knife|bomb|explosive|grenade|ammunition|firearm)\s+(?:making|building|creating|assembling|constructing)\b",
            r"\b(?:making|building|creating|assembling)\s+(?:a\s+)?(?:weapon|gun|knife|bomb|explosive)\b",
            r"\b(?:attack|assault|shoot|stab|strangle|suffocate|drown)\s+(?:a\s+)?(?:person|people|someone|group|crowd)\b",
        ],
        "severity": "critical",
    },
    "self_harm": {
        "patterns": [
            r"\b(?:how to|ways to|methods? (?:of|for)|steps? to)\s+(?:kill yourself|commit suicide|end your life|self.harm)\b",
            r"\b(?:encourage|promoting|glorif)\w*\s+(?:suicide|self.harm|cutting|anorexia|bulimia)\b",
        ],
        "severity": "critical",
    },
    "sexual_content": {
        "patterns": [
            r"\b(?:explicit|graphic)\s+(?:sexual|pornographic)\s+(?:content|material|description)\b",
            r"\b(?:child\s+(?:porn|sexual|exploitation)|csam|pedophil)\b",
        ],
        "severity": "critical",
    },
    "harmful_requests": {
        "patterns": [
            r"\b(?:write|create|generate|produce|draft)\s+(?:a\s+)?(?:tutorial|guide|instructions?|manual|how-?to)\s+(?:on|for|about)\s+(?:making|creating|building|synthesizing|manufacturing)\b",
            r"\b(?:provide|give|share|tell)\s+(?:me\s+)?(?:detailed|step.by.step|specific)\s+(?:instructions?|steps?|methods?)\s+(?:for|to|on)\b",
            r"\b(?:synthesize|manufacture|produce|create|make)\s+(?:illegal\s+)?(?:drugs?|narcotics?|meth|cocaine|heroin|fentanyl)\b",
        ],
        "severity": "high",
    },
    "weapons": {
        "patterns": [
            r"\b(?:make|build|create|construct|assemble|manufacture)\s+(?:a\s+)?(?:bomb|explosive|weapon|gun|firearm|poison|toxin|nerve\s+(?:agent|gas))\b",
            r"\b(?:3d\s+print|3d-print)\s+(?:a\s+)?(?:gun|weapon|firearm)\b",
            r"\b(?:dirty\s+bomb|pipe\s+bomb|car\s+bomb|mail\s+bomb|suicide\s+bomb)\b",
        ],
        "severity": "critical",
    },
    "cybercrime": {
        "patterns": [
            r"\b(?:hack|exploit|crack|breach|penetrate)\s+(?:into\s+)?(?:a\s+)?(?:system|network|server|account|database|website)\b",
            r"\b(?:write|create|generate|code)\s+(?:a\s+)?(?:malware|virus|trojan|ransomware|keylogger|rootkit|spyware|worm)\b",
            r"\b(?:phishing|spear.?phishing)\s+(?:email|attack|campaign|template)\b",
            r"\b(?:steal|extract|exfiltrate)\s+(?:passwords?|credentials?|data|information|credit\s+cards?)\b",
            r"\b(?:ddos|denial.of.service)\s+(?:attack|tool|script)\b",
        ],
        "severity": "high",
    },
    "fraud": {
        "patterns": [
            r"\b(?:fake|forge|counterfeit|falsify)\s+(?:identity|passport|document|id|license|diploma|certificate)\b",
            r"\b(?:money\s+laundering|launder\s+money)\b",
            r"\b(?:scam|defraud|swindle|con)\s+(?:people|someone|victims?|elderly)\b",
            r"\b(?:ponzi|pyramid)\s+scheme\b",
        ],
        "severity": "high",
    },
    "privacy_violation": {
        "patterns": [
            r"\b(?:track|stalk|surveil|spy on|monitor)\s+(?:someone|a person|my (?:ex|wife|husband|partner|girlfriend|boyfriend))\b",
            r"\b(?:dox|doxx|find\s+(?:the|someone's)\s+(?:address|home|phone|personal\s+information))\b",
        ],
        "severity": "high",
    },
    "harassment": {
        "patterns": [
            r"\b(?:stalk|harass|bully|intimidate|threaten)\s+(?:them|him|her|someone|this person)\b",
            r"\b(?:dox|doxx|swat)\s+(?:them|him|her|someone|this person)\b",
        ],
        "severity": "high",
    },
    "illegal_activity": {
        "patterns": [
            r"\b(?:how to|instructions? (?:for|to)|guide to)\s+(?:hack|phish|scam|fraud|steal|launder|counterfeit)\b",
            r"\b(?:synthesize|manufacture|cook|produce)\s+(?:meth|cocaine|heroin|fentanyl|drugs)\b",
            r"\b(?:pick|break|bypass)\s+(?:a\s+)?(?:lock|safe|security\s+system)\b",
            r"\b(?:shoplift|steal\s+from|rob)\s+(?:a\s+)?(?:store|bank|person|house)\b",
            r"\b(?:evade|avoid|escape)\s+(?:police|law\s+enforcement|arrest|taxes)\b",
            r"\b(?:forge|counterfeit)\s+(?:money|currency|bills?|checks?)\b",
            r"\b(?:human\s+trafficking|child\s+labor|smuggl)\b",
        ],
        "severity": "high",
    },
    "disinformation": {
        "patterns": [
            r"\b(?:write|create|generate|spread)\s+(?:a\s+)?(?:fake\s+news|disinformation|misinformation|propaganda)\b",
            r"\b(?:convincing|realistic|believable)\s+(?:fake|false|fabricated)\s+(?:article|news|story|report)\b",
        ],
        "severity": "high",
    },
    "profanity": {
        "patterns": [
            # Keep profanity detection light - many legitimate contexts use mild language
            r"\b(?:f+u+c+k+|s+h+i+t+|a+s+s+h+o+l+e+)\b",
        ],
        "severity": "low",
    },
}


class ToxicityModule:
    def __init__(self,
                 categories: Optional[List[str]] = None,
                 min_severity: str = "low",
                 on_detect: str = "block",
                 use_ml: bool = False,
                 ml_threshold: float = 0.7,
                 custom_patterns: Optional[Dict[str, Dict]] = None,
                 allowlist_words: Optional[List[str]] = None):
        """
        Args:
            categories: Which toxicity categories to check (default: all)
            min_severity: Minimum severity to trigger ("low", "high", "critical")
            on_detect: "block" raises, "warn" logs, "redact" replaces toxic content
            use_ml: Use detoxify ML model (requires pip install agentarmor[toxicity])
            ml_threshold: ML model confidence threshold
            custom_patterns: Additional category patterns
            allowlist_words: Words to ignore even if they match patterns
        """
        self.min_severity = min_severity
        self.on_detect = on_detect
        self.use_ml = use_ml
        self.ml_threshold = ml_threshold
        self.allowlist_words = set(w.lower() for w in (allowlist_words or []))
        self.detections: List[Dict] = []
        self.scanned_count = 0
        self.blocked_count = 0
        self._ml_model = None

        severity_levels = {"low": 0, "high": 1, "critical": 2}
        min_level = severity_levels.get(min_severity, 0)

        # Build active patterns
        self.active_patterns = {}
        active_cats = categories or list(TOXICITY_PATTERNS.keys())
        for cat in active_cats:
            cat_info = TOXICITY_PATTERNS.get(cat, {})
            if custom_patterns and cat in custom_patterns:
                cat_info = custom_patterns[cat]
            elif cat not in TOXICITY_PATTERNS:
                continue

            cat_severity = severity_levels.get(cat_info.get("severity", "low"), 0)
            if cat_severity >= min_level:
                self.active_patterns[cat] = {
                    "compiled": [re.compile(p, re.IGNORECASE) for p in cat_info["patterns"]],
                    "severity": cat_info["severity"],
                }

        if custom_patterns:
            for cat, info in custom_patterns.items():
                if cat not in self.active_patterns:
                    cat_severity = severity_levels.get(info.get("severity", "low"), 0)
                    if cat_severity >= min_level:
                        self.active_patterns[cat] = {
                            "compiled": [re.compile(p, re.IGNORECASE) for p in info["patterns"]],
                            "severity": info["severity"],
                        }

        if use_ml:
            self._init_ml()

    def _init_ml(self):
        try:
            from detoxify import Detoxify
            self._ml_model = Detoxify('original')
        except ImportError:
            raise ImportError(
                "ML-based toxicity detection requires the 'detoxify' package. "
                "Install it with: pip install agentarmor[toxicity]"
            )

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Scan response for toxic content."""
        if isinstance(ctx.text, str) and ctx.text.strip():
            findings = self._scan(ctx.text)
            self.scanned_count += 1

            if findings:
                self.detections.extend(findings)
                self._handle_detection(ctx, findings)

        return ctx

    def stream_filter(self, text: str) -> str:
        """Scan streaming text for toxic content."""
        if isinstance(text, str) and text.strip():
            findings = self._scan(text)
            if findings and self.on_detect == "redact":
                for f in findings:
                    text = re.sub(f.get("match", ""), "[REDACTED:TOXIC]", text, flags=re.IGNORECASE)
        return text

    def _scan(self, text: str) -> List[Dict]:
        """Scan text for toxicity using patterns and optionally ML."""
        findings = []

        # Pattern-based scan
        for cat, info in self.active_patterns.items():
            for pattern in info["compiled"]:
                matches = pattern.finditer(text)
                for match in matches:
                    matched_text = match.group()
                    # Check allowlist
                    if any(w in matched_text.lower() for w in self.allowlist_words):
                        continue
                    findings.append({
                        "category": cat,
                        "severity": info["severity"],
                        "match": matched_text[:100],
                        "method": "pattern",
                    })

        # ML-based scan
        if self.use_ml and self._ml_model:
            ml_results = self._ml_model.predict(text)
            for label, score in ml_results.items():
                if score >= self.ml_threshold:
                    findings.append({
                        "category": label,
                        "severity": "high",
                        "score": round(score, 3),
                        "method": "ml",
                    })

        return findings

    def scan_text(self, text: str) -> List[Dict]:
        """Public method for standalone toxicity scanning."""
        return self._scan(text)

    def _handle_detection(self, ctx, findings):
        self.blocked_count += 1
        if self.on_detect == "block":
            categories = list(set(f["category"] for f in findings))
            raise ToxicContentDetected(
                f"Toxic content detected in categories: {', '.join(categories)}"
            )
        elif self.on_detect == "warn":
            for f in findings:
                warnings.warn(
                    f"[AgentArmor] Toxic content detected [{f['severity']}] "
                    f"{f['category']}: {f.get('match', '')[:50]}",
                    stacklevel=4,
                )
        elif self.on_detect == "redact":
            for f in findings:
                if "match" in f:
                    ctx.text = ctx.text.replace(f["match"], "[REDACTED:TOXIC]")

    def report(self) -> dict:
        categories = {}
        for d in self.detections:
            cat = d["category"]
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "scanned_count": self.scanned_count,
            "blocked_count": self.blocked_count,
            "total_detections": len(self.detections),
            "by_category": categories,
            "ml_enabled": self.use_ml,
        }
