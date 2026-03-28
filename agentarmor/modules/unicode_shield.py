import re
import threading
import unicodedata
from typing import Optional, List, Dict, Any
from ..exceptions import UnicodeInjectionDetected
from ..hooks import RequestContext


# Zero-width characters
ZERO_WIDTH_CHARS = set([
    '\u200b',  # zero-width space
    '\u200c',  # zero-width non-joiner
    '\u200d',  # zero-width joiner
    '\u2060',  # word joiner
    '\ufeff',  # zero-width no-break space (BOM)
])

# Directional override/control characters
BIDI_CHARS = set([
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
])

# Tag characters (U+E0001 to U+E007F) - used to embed invisible ASCII
TAG_RANGE = range(0xE0001, 0xE0080)

# Variation selectors
VARIATION_SELECTORS = set(range(0xFE00, 0xFE10))  # VS1-VS16
VARIATION_SELECTORS.update(range(0xE0100, 0xE01F0))  # VS17-VS256

# Common homoglyph mappings (Cyrillic/Greek that look like Latin)
HOMOGLYPH_MAP = {
    '\u0410': 'A',  # Cyrillic А
    '\u0412': 'B',  # Cyrillic В
    '\u0421': 'C',  # Cyrillic С
    '\u0415': 'E',  # Cyrillic Е
    '\u041d': 'H',  # Cyrillic Н
    '\u041a': 'K',  # Cyrillic К
    '\u041c': 'M',  # Cyrillic М
    '\u041e': 'O',  # Cyrillic О
    '\u0420': 'P',  # Cyrillic Р
    '\u0422': 'T',  # Cyrillic Т
    '\u0425': 'X',  # Cyrillic Х
    '\u0430': 'a',  # Cyrillic а
    '\u0435': 'e',  # Cyrillic е
    '\u043e': 'o',  # Cyrillic о
    '\u0440': 'p',  # Cyrillic р
    '\u0441': 'c',  # Cyrillic с
    '\u0443': 'y',  # Cyrillic у
    '\u0445': 'x',  # Cyrillic х
    '\u0456': 'i',  # Cyrillic і
    '\u0458': 'j',  # Cyrillic ј
    '\u0455': 's',  # Cyrillic ѕ
    # Greek
    '\u0391': 'A',  # Greek Α
    '\u0392': 'B',  # Greek Β
    '\u0395': 'E',  # Greek Ε
    '\u0397': 'H',  # Greek Η
    '\u0399': 'I',  # Greek Ι
    '\u039a': 'K',  # Greek Κ
    '\u039c': 'M',  # Greek Μ
    '\u039d': 'N',  # Greek Ν
    '\u039f': 'O',  # Greek Ο
    '\u03a1': 'P',  # Greek Ρ
    '\u03a4': 'T',  # Greek Τ
    '\u03a5': 'Y',  # Greek Υ
    '\u03a7': 'X',  # Greek Χ
    '\u03bf': 'o',  # Greek ο
    '\u03c1': 'p',  # Greek ρ (rho)
}

HOMOGLYPH_SET = set(HOMOGLYPH_MAP.keys())


class UnicodeShieldModule:
    """Detects invisible unicode-based prompt injection attacks in input messages."""

    def __init__(self, on_detect: str = "block",
                 check_zero_width: bool = True,
                 check_bidi: bool = True,
                 check_tags: bool = True,
                 check_homoglyphs: bool = True,
                 check_variation_selectors: bool = True,
                 zero_width_threshold: int = 3,
                 homoglyph_threshold: int = 2,
                 custom_confusables: Optional[Dict[str, str]] = None):
        self.on_detect = on_detect
        self.check_zero_width = check_zero_width
        self.check_bidi = check_bidi
        self.check_tags = check_tags
        self.check_homoglyphs = check_homoglyphs
        self.check_variation_selectors = check_variation_selectors
        self.zero_width_threshold = zero_width_threshold
        self.homoglyph_threshold = homoglyph_threshold
        self.detections: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        self.homoglyph_map = dict(HOMOGLYPH_MAP)
        if custom_confusables:
            self.homoglyph_map.update({k: v for k, v in custom_confusables.items()})
        self.homoglyph_set = set(self.homoglyph_map.keys())

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Pre-request hook: scan all input messages for unicode attacks."""
        for msg in ctx.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                self._scan(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        self._scan(part["text"])
        return ctx

    def _scan(self, text: str) -> None:
        """Run all enabled unicode checks on text."""
        findings = []

        if self.check_zero_width:
            f = self._detect_zero_width(text)
            if f:
                findings.append(f)

        if self.check_bidi:
            f = self._detect_bidi(text)
            if f:
                findings.append(f)

        if self.check_tags:
            f = self._detect_tag_chars(text)
            if f:
                findings.append(f)

        if self.check_homoglyphs:
            f = self._detect_homoglyphs(text)
            if f:
                findings.append(f)

        if self.check_variation_selectors:
            f = self._detect_variation_selectors(text)
            if f:
                findings.append(f)

        if findings:
            with self._lock:
                self.detections.extend(findings)
            if self.on_detect == "block":
                raise UnicodeInjectionDetected(
                    f"Unicode injection detected: {findings[0]['type']} - {findings[0]['detail']}"
                )

    def _detect_zero_width(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect suspicious concentrations of zero-width characters."""
        count = sum(1 for c in text if c in ZERO_WIDTH_CHARS)
        if count >= self.zero_width_threshold:
            return {
                "type": "zero_width",
                "detail": f"Found {count} zero-width characters (threshold: {self.zero_width_threshold})",
                "count": count,
            }
        return None

    def _detect_bidi(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect bidirectional override characters."""
        found = [c for c in text if c in BIDI_CHARS]
        if found:
            char_names = []
            for c in found[:5]:
                try:
                    char_names.append(unicodedata.name(c, f'U+{ord(c):04X}'))
                except ValueError:
                    char_names.append(f'U+{ord(c):04X}')
            return {
                "type": "bidi_override",
                "detail": f"Found {len(found)} bidirectional control character(s): {', '.join(char_names)}",
                "count": len(found),
            }
        return None

    def _detect_tag_chars(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect Unicode tag characters (U+E0001-U+E007F) that embed invisible ASCII."""
        tag_chars = [c for c in text if ord(c) in TAG_RANGE]
        if tag_chars:
            # Decode hidden message
            hidden = ''.join(chr(ord(c) - 0xE0000) for c in tag_chars)
            return {
                "type": "tag_characters",
                "detail": f"Found {len(tag_chars)} tag characters encoding hidden text: '{hidden[:50]}'",
                "hidden_text": hidden,
                "count": len(tag_chars),
            }
        return None

    def _detect_homoglyphs(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect characters from other scripts that look identical to Latin letters."""
        found = []
        for i, c in enumerate(text):
            if c in self.homoglyph_set:
                found.append({
                    "char": c,
                    "looks_like": self.homoglyph_map[c],
                    "position": i,
                    "codepoint": f"U+{ord(c):04X}",
                })
        if len(found) >= self.homoglyph_threshold:
            samples = [f"'{f['char']}' (U+{ord(f['char']):04X}) looks like '{f['looks_like']}'" for f in found[:5]]
            return {
                "type": "homoglyph",
                "detail": f"Found {len(found)} homoglyph(s): {'; '.join(samples)}",
                "confusables": found,
                "count": len(found),
            }
        return None

    def _detect_variation_selectors(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect variation selectors that could hide data."""
        vs_chars = [c for c in text if ord(c) in VARIATION_SELECTORS]
        if len(vs_chars) >= 2:
            return {
                "type": "variation_selectors",
                "detail": f"Found {len(vs_chars)} variation selector(s) that may encode hidden data",
                "count": len(vs_chars),
            }
        return None

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
