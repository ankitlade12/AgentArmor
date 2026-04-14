import re
from typing import List, Optional
from ..exceptions import InjectionDetected
from ..hooks import RequestContext

# Built-in detection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+your\s+(system\s+)?prompt",
    r"you\s+are\s+now\s+(a\s+)?DAN",
    r"pretend\s+you\s+(have\s+no\s+restrictions|are\s+)",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"act\s+as\s+if\s+you\s+have\s+no\s+(rules|guidelines|restrictions)",
    r"repeat\s+the\s+words\s+above",
    r"what\s+(is|was)\s+your\s+system\s+prompt",
    r"output\s+your\s+(initial|system)\s+instructions",
    # Expanded patterns
    r"translate\s+the\s+following\s+to\s+([a-zA-Z]+):\s*ignore\s+all",
    r"base64\s+decode",
    r"ignore_system_prompt",
    r"system prompt leaked",
    r"bypassing filters",
    r"system=override",
    r"<\s*\|[^|]+\|\s*>",
    # Harmful content request patterns (common in industry benchmarks)
    r"(?:write|create|generate|provide|give)\s+(?:a\s+)?(?:tutorial|guide|instructions?|manual|how.?to)\s+(?:on|for|about)\s+(?:how\s+to\s+)?(?:make|build|create|hack|steal|kill|poison|bomb|attack)",
    r"(?:how\s+(?:to|can\s+I|do\s+you|would\s+I))\s+(?:make|build|create|synthesize|manufacture)\s+(?:a\s+)?(?:bomb|weapon|poison|drug|explosive|meth|cocaine)",
    r"(?:how\s+(?:to|can\s+I|do\s+you))\s+(?:hack|break\s+into|exploit|penetrate|crack)\s+(?:a\s+)?(?:system|network|account|server|website|database|computer)",
    r"(?:how\s+(?:to|can\s+I))\s+(?:kill|murder|poison|assassinate|harm|hurt|attack)\s+(?:someone|a\s+person|my|people)",
    r"(?:write|create|generate|draft)\s+(?:a\s+)?(?:phishing|scam|fraud|malware|ransomware|virus|trojan|keylogger)",
    r"(?:how\s+(?:to|can\s+I))\s+(?:steal|forge|counterfeit|launder|embezzle|shoplift)",
    r"(?:how\s+(?:to|can\s+I))\s+(?:stalk|track|spy\s+on|surveil|dox|harass|bully|threaten)\s+(?:someone|a\s+person|my)",
    r"(?:how\s+(?:to|can\s+I))\s+(?:evade|escape|avoid|flee)\s+(?:police|law\s+enforcement|arrest|prosecution)",
    r"(?:write|create|generate)\s+(?:a\s+)?(?:fake\s+news|propaganda|disinformation|misinformation)\s+(?:article|story|post|campaign)",
    r"(?:how\s+(?:to|can\s+I))\s+(?:make|get|obtain|buy)\s+(?:a\s+)?(?:fake|forged|counterfeit)\s+(?:id|passport|license|identity|document)",
    r"(?:provide|give|share|list)\s+(?:me\s+)?(?:step.by.step|detailed)\s+(?:instructions?|steps?|guide|process)\s+(?:for|to|on)\s+(?:making|building|creating|hacking|stealing|killing)",
    r"(?:design|develop|code|program|write)\s+(?:a\s+)?(?:tool|script|program|software|app)\s+(?:to|for|that)\s+(?:hack|steal|spy|track|surveil|ddos|phish)",
]

DEFAULT_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

class ShieldModule:
    def __init__(self, on_detect: str = "block", custom_patterns: Optional[List[str]] = None):
        """
        Initializes the prompt injection shield.
        
        Args:
            on_detect: Action to take on detection ('block' or 'warn').
            custom_patterns: Additional regex patterns to use for detection.
        """
        self.on_detect = on_detect
        self.detections = []
        self.patterns = list(DEFAULT_COMPILED)
        if custom_patterns:
            self.patterns.extend([re.compile(p, re.IGNORECASE) for p in custom_patterns])

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        for msg in ctx.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                self._scan(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        self._scan(part["text"])
            # Gemini format: messages use "parts" instead of "content"
            parts = msg.get("parts", [])
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and "text" in part:
                        self._scan(part["text"])
        return ctx

    def _scan(self, text: str):
        for pattern in self.patterns:
            if pattern.search(text):
                self.detections.append(text[:100])
                if self.on_detect == "block":
                    raise InjectionDetected(
                        "Prompt injection detected. Call blocked."
                    )
                else:
                    print("[AgentArmor] WARNING: Possible injection detected.")
                return

    def report(self) -> dict:
        return {
            "detections": len(self.detections),
            "samples": self.detections[:3]
        }
