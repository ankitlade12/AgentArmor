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
        return ctx

    def _scan(self, text: str):
        for pattern in self.patterns:
            if pattern.search(text):
                self.detections.append(text[:100])
                if self.on_detect == "block":
                    raise InjectionDetected(
                        f"Prompt injection detected. Call blocked."
                    )
                else:
                    print(f"[AgentArmor] WARNING: Possible injection detected.")
                return

    def report(self) -> dict:
        return {
            "detections": len(self.detections),
            "samples": self.detections[:3]
        }
