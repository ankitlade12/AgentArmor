import re

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
    "phone": r"\b(\+1\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b",
    "api_key": r"(sk-|pk_|rk_)[a-zA-Z0-9]{20,}",
    "secrets": r"(password|secret|token|api_key)\s*[:=]\s*\S+",
}

class FilterModule:
    def __init__(self, rules: list, on_detect="redact"):
        self.rules = rules  # e.g. ["pii", "secrets"]
        self.on_detect = on_detect  # "redact" | "block"
        self.redactions = 0
        self._build_patterns()

    def _build_patterns(self):
        self.active_patterns = {}
        for rule in self.rules:
            if rule == "pii":
                for name in ["email", "ssn", "credit_card", "phone"]:
                    self.active_patterns[name] = re.compile(PII_PATTERNS[name])
            elif rule == "secrets":
                for name in ["api_key", "secrets"]:
                    self.active_patterns[name] = re.compile(PII_PATTERNS[name], re.IGNORECASE)
            elif rule in PII_PATTERNS:
                self.active_patterns[rule] = re.compile(PII_PATTERNS[rule])

    def scan(self, text: str) -> str:
        for name, pattern in self.active_patterns.items():
            matches = pattern.findall(text)
            if matches:
                self.redactions += len(matches)
                text = pattern.sub(f"[REDACTED:{name.upper()}]", text)
        return text

    def report(self):
        return {"total_redactions": self.redactions}
