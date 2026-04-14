import re
import base64
import threading
from typing import Optional, List, Dict, Any
from ..exceptions import DataExfiltrationDetected
from ..hooks import RequestContext, ResponseContext


# Zero-width characters used for steganography
ZERO_WIDTH_CHARS = [
    '\u200b',  # zero-width space
    '\u200c',  # zero-width non-joiner
    '\u200d',  # zero-width joiner
    '\u2060',  # word joiner
    '\ufeff',  # zero-width no-break space
    '\u200e',  # left-to-right mark
    '\u200f',  # right-to-left mark
    '\u202a',  # left-to-right embedding
    '\u202b',  # right-to-left embedding
    '\u202c',  # pop directional formatting
    '\u202d',  # left-to-right override
    '\u202e',  # right-to-left override
    '\u2066',  # left-to-right isolate
    '\u2067',  # right-to-left isolate
    '\u2068',  # first strong isolate
    '\u2069',  # pop directional isolate
]

ZERO_WIDTH_PATTERN = re.compile('[' + ''.join(ZERO_WIDTH_CHARS) + ']{3,}')

# Patterns that indicate sensitive data when found inside encoded content
SENSITIVE_DECODED_PATTERNS = [
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),  # email
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),  # SSN
    re.compile(r'\b(?:\d[ -]*?){13,16}\b'),  # credit card
    re.compile(r'(?:sk-|pk-|api[_-]?key|token|secret|password)[a-zA-Z0-9_\-]{10,}', re.IGNORECASE),  # API keys
    re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'),  # private keys
    re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}'),  # JWT tokens
]

# Suspicious URL patterns for data exfiltration
EXFIL_URL_PATTERNS = [
    re.compile(r'https?://[^\s]+\?[^\s]*(?:data|d|q|payload|p)=[A-Za-z0-9+/=]{50,}', re.IGNORECASE),  # long base64 in query
    re.compile(r'data:[^;]+;base64,[A-Za-z0-9+/=]{100,}'),  # data URIs with large payloads
    re.compile(r'!\[(?:[^\]]*)\]\(https?://[^\s)]+[?&][^\s)]*[A-Za-z0-9+/=]{30,}[^\s)]*\)'),  # markdown images with encoded data
]

# Base64 content detection (uses a low regex floor; actual minimum enforced by min_encoded_length)
BASE64_PATTERN = re.compile(r'(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{16,}={0,2})(?![A-Za-z0-9+/])')

# Hex-encoded content detection (uses a low regex floor; actual minimum enforced by min_encoded_length)
HEX_PATTERN = re.compile(r'(?:0x)?([0-9a-fA-F]{16,})')


class ExfiltrationGuardModule:
    """Detects data exfiltration attempts in LLM outputs and tool calls."""

    def __init__(self, on_detect: str = "block", check_base64: bool = True,
                 check_urls: bool = True, check_steganography: bool = True,
                 check_hex: bool = True, min_encoded_length: int = 40,
                 custom_sensitive_patterns: Optional[List[str]] = None):
        self.on_detect = on_detect
        self.check_base64 = check_base64
        self.check_urls = check_urls
        self.check_steganography = check_steganography
        self.check_hex = check_hex
        self.min_encoded_length = min_encoded_length
        self.detections: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        self.sensitive_patterns = list(SENSITIVE_DECODED_PATTERNS)
        if custom_sensitive_patterns:
            self.sensitive_patterns.extend(
                [re.compile(p, re.IGNORECASE) for p in custom_sensitive_patterns]
            )

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Post-response hook: scan output text for exfiltration attempts."""
        findings = self._scan_text(ctx.text)

        # Also scan tool calls if present
        if ctx.raw_response:
            tool_findings = self._scan_tool_calls(ctx.raw_response, ctx.provider)
            findings.extend(tool_findings)

        if findings:
            with self._lock:
                self.detections.extend(findings)
            if self.on_detect == "block":
                raise DataExfiltrationDetected(
                    f"Data exfiltration attempt detected: {findings[0]['type']} - {findings[0]['detail'][:100]}"
                )
        return ctx

    def stream_filter(self, accumulated_text: str) -> str:
        """Stream hook: scan accumulated text for exfiltration patterns."""
        findings = self._scan_text(accumulated_text)
        if findings:
            with self._lock:
                self.detections.extend(findings)
            if self.on_detect == "block":
                raise DataExfiltrationDetected(
                    f"Data exfiltration attempt detected in stream: {findings[0]['type']}"
                )
        return accumulated_text

    def _scan_text(self, text: str) -> List[Dict[str, Any]]:
        """Scan text for all exfiltration patterns."""
        if not text:
            return []
        findings = []

        if self.check_steganography:
            steg_findings = self._check_steganography_patterns(text)
            findings.extend(steg_findings)

        if self.check_urls:
            url_findings = self._check_url_exfiltration(text)
            findings.extend(url_findings)

        if self.check_base64:
            b64_findings = self._check_base64_exfiltration(text)
            findings.extend(b64_findings)

        if self.check_hex:
            hex_findings = self._check_hex_exfiltration(text)
            findings.extend(hex_findings)

        return findings

    def _check_steganography_patterns(self, text: str) -> List[Dict[str, Any]]:
        """Detect zero-width character sequences that may hide data."""
        findings = []
        for match in ZERO_WIDTH_PATTERN.finditer(text):
            findings.append({
                "type": "steganography",
                "detail": f"Zero-width character sequence of length {len(match.group())} at position {match.start()}",
                "position": match.start(),
            })
        return findings

    def _check_url_exfiltration(self, text: str) -> List[Dict[str, Any]]:
        """Detect suspicious URLs that may carry encoded sensitive data."""
        findings = []
        for pattern in EXFIL_URL_PATTERNS:
            for match in pattern.finditer(text):
                findings.append({
                    "type": "url_exfiltration",
                    "detail": match.group()[:200],
                    "position": match.start(),
                })
        return findings

    def _check_base64_exfiltration(self, text: str) -> List[Dict[str, Any]]:
        """Detect base64-encoded sensitive data in text."""
        findings = []
        for match in BASE64_PATTERN.finditer(text):
            encoded = match.group(1)
            if len(encoded) < self.min_encoded_length:
                continue
            try:
                decoded = base64.b64decode(encoded + '==').decode('utf-8', errors='ignore')
                if self._contains_sensitive_data(decoded):
                    findings.append({
                        "type": "base64_exfiltration",
                        "detail": f"Base64-encoded sensitive data detected (decoded preview: {decoded[:80]}...)",
                        "position": match.start(),
                    })
            except Exception:
                pass
        return findings

    def _check_hex_exfiltration(self, text: str) -> List[Dict[str, Any]]:
        """Detect hex-encoded sensitive data in text."""
        findings = []
        for match in HEX_PATTERN.finditer(text):
            hex_str = match.group(1)
            if len(hex_str) < self.min_encoded_length:
                continue
            try:
                decoded = bytes.fromhex(hex_str).decode('utf-8', errors='ignore')
                if self._contains_sensitive_data(decoded):
                    findings.append({
                        "type": "hex_exfiltration",
                        "detail": f"Hex-encoded sensitive data detected (decoded preview: {decoded[:80]}...)",
                        "position": match.start(),
                    })
            except Exception:
                pass
        return findings

    def _contains_sensitive_data(self, text: str) -> bool:
        """Check if decoded text contains sensitive patterns."""
        for pattern in self.sensitive_patterns:
            if pattern.search(text):
                return True
        return False

    def _scan_tool_calls(self, raw_response: Any, provider: str) -> List[Dict[str, Any]]:
        """Scan tool call arguments for exfiltration attempts."""
        findings = []
        tool_args_texts = self._extract_tool_call_args(raw_response, provider)
        for arg_text in tool_args_texts:
            arg_findings = self._scan_text(arg_text)
            for f in arg_findings:
                f["type"] = f"tool_call_{f['type']}"
            findings.extend(arg_findings)
        return findings

    def _extract_tool_call_args(self, raw_response: Any, provider: str) -> List[str]:
        """Extract tool call argument strings from provider-specific responses."""
        texts = []
        try:
            if provider == "openai":
                # Chat Completions format
                for choice in getattr(raw_response, 'choices', []):
                    msg = getattr(choice, 'message', None)
                    if msg:
                        for tc in getattr(msg, 'tool_calls', []) or []:
                            fn = getattr(tc, 'function', None)
                            if fn:
                                texts.append(getattr(fn, 'arguments', '') or '')
                # Responses API format
                for item in getattr(raw_response, 'output', []):
                    if getattr(item, 'type', '') == 'function_call':
                        args = getattr(item, 'arguments', '')
                        if isinstance(args, dict):
                            import json
                            texts.append(json.dumps(args))
                        elif args:
                            texts.append(str(args))
            elif provider == "anthropic":
                for block in getattr(raw_response, 'content', []):
                    if getattr(block, 'type', '') == 'tool_use':
                        import json
                        texts.append(json.dumps(getattr(block, 'input', {})))
            elif provider == "gemini":
                for candidate in getattr(raw_response, 'candidates', []):
                    content = getattr(candidate, 'content', None)
                    if content:
                        for part in getattr(content, 'parts', []):
                            fc = getattr(part, 'function_call', None)
                            if fc:
                                import json
                                texts.append(json.dumps(getattr(fc, 'args', {})))
        except Exception:
            pass
        return texts

    def report(self) -> dict:
        with self._lock:
            return {
                "detections": len(self.detections),
                "by_type": self._count_by_type(),
                "samples": self.detections[:5],
            }

    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for d in self.detections:
            t = d.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts
