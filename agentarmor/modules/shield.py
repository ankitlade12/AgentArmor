import re
from ..exceptions import InjectionDetected

# Pattern library — expand this over time
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+your\s+(system\s+)?prompt",
    r"you\s+are\s+now\s+(a\s+)?DAN",
    r"pretend\s+you\s+(have\s+no\s+restrictions|are\s+)",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"act\s+as\s+if\s+you\s+have\s+no\s+(rules|guidelines|restrictions)",
    r"repeat\s+the\s+words\s+above",       # prompt extraction
    r"what\s+(is|was)\s+your\s+system\s+prompt",
    r"output\s+your\s+(initial|system)\s+instructions",
]

COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

class ShieldModule:
    def __init__(self, on_detect="block"):
        self.on_detect = on_detect  # "block" | "warn"
        self.detections = []

    def scan(self, text: str):
        for pattern in COMPILED:
            if pattern.search(text):
                self.detections.append(text[:100])
                if self.on_detect == "block":
                    raise InjectionDetected(
                        f"Prompt injection detected. Call blocked."
                    )
                else:
                    print(f"[AgentArmor] WARNING: Possible injection detected.")
                return

    def report(self):
        return {
            "detections": len(self.detections),
            "samples": self.detections[:3]
        }
