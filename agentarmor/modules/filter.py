import re
from typing import Dict, Optional
from ..hooks import ResponseContext

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
    "phone": r"\b(\+1\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b",
    "api_key": r"(sk-|pk_|rk_)[a-zA-Z0-9]{20,}",
    "generic_secrets": r"(password|secret|token|api_key)\s*[:=]\s*\S+",
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"(ghp_|gho_|ghu_|ghs_|ghr_)[a-zA-Z0-9]{36}",
    "jwt": r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
    "base64_secret": r"(?i)(?:secret|token|key)[\s:=]+(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)",
}

class FilterModule:
    def __init__(self, rules: list, on_detect: str = "redact", custom_patterns: Optional[Dict[str, str]] = None):
        """
        Initializes the output filter for redacting sensitive or PII data.
        
        Args:
            rules: List of active rule categories (e.g. ['pii', 'secrets']).
            on_detect: Action to take on detection (currently supports 'redact').
            custom_patterns: Additional regex patterns mapped by rule name.
        """
        self.rules = rules
        self.on_detect = on_detect
        self.redactions = 0
        self.custom_patterns = custom_patterns or {}
        self._build_patterns()

    def _build_patterns(self):
        self.active_patterns = {}
        for rule in self.rules:
            if rule == "pii":
                for name in ["email", "ssn", "credit_card", "phone"]:
                    self.active_patterns[name] = re.compile(PII_PATTERNS[name])
            elif rule == "secrets":
                for name in ["api_key", "generic_secrets", "aws_key", "github_token", "jwt", "base64_secret"]:
                    self.active_patterns[name] = re.compile(PII_PATTERNS[name], re.IGNORECASE)
            elif rule in PII_PATTERNS:
                self.active_patterns[rule] = re.compile(PII_PATTERNS[rule])
            elif rule in self.custom_patterns:
                self.active_patterns[rule] = re.compile(self.custom_patterns[rule])

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        if isinstance(ctx.text, str) and self.active_patterns:
            ctx.text = self._scan(ctx.text)
        return ctx

    def stream_filter(self, text: str) -> str:
        if isinstance(text, str) and self.active_patterns:
            return self._scan(text)
        return text

    def redact(self, text: str) -> str:
        """Stateless: return a redacted copy of text. Does not touch self.redactions.

        Public API. Used by the trace recorder (Explain Mode) so that what the LLM
        sees and what the trace stores share a single redaction implementation.
        """
        if not isinstance(text, str) or not self.active_patterns:
            return text
        redacted, _ = self._redact_with_count(text)
        return redacted

    def _redact_with_count(self, text: str) -> tuple:
        redacted = text
        count = 0
        for name, pattern in self.active_patterns.items():
            matches = pattern.findall(redacted)
            if matches:
                count += len(matches)
                redacted = pattern.sub(f"[REDACTED:{name.upper()}]", redacted)
        return redacted, count

    def _scan(self, text: str) -> str:
        redacted, count = self._redact_with_count(text)
        self.redactions += count
        return redacted

    def report(self) -> dict:
        return {"total_redactions": self.redactions}
