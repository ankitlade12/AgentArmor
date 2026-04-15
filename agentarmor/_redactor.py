"""Built-in PII redactor used by Explain Mode when no user filter is configured.

Conservative regex set covering common unambiguous PII shapes. Custom enterprise
PII (employee IDs, addresses, etc.) is the user's responsibility via
init(filter=["pii"]) or a custom filter.
"""

import re

_DEFAULT_PATTERNS = {
    "EMAIL": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]{20,}", re.IGNORECASE),
    "OPENAI_KEY": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "ANTHROPIC_KEY": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    "JWT": re.compile(r"\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"),
    "AWS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GITHUB_TOKEN": re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[a-zA-Z0-9]{36}\b"),
}


def default_redact(text: str) -> str:
    if not isinstance(text, str):
        return text
    redacted = text
    for name, pattern in _DEFAULT_PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED:{name}]", redacted)
    return redacted
