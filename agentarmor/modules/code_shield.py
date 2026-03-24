import re
import logging
from typing import Dict, List, Optional
from ..hooks import ResponseContext
from ..exceptions import InsecureCodeDetected

logger = logging.getLogger("agentarmor.code_shield")

DANGEROUS_PATTERNS = {
    "python": {
        "code_injection": [
            (r"\beval\s*\(", "eval() can execute arbitrary code"),
            (r"\bexec\s*\(", "exec() can execute arbitrary code"),
            (r"\bcompile\s*\(", "compile() can prepare code for execution"),
            (r"__import__\s*\(", "__import__() can dynamically import modules"),
        ],
        "command_injection": [
            (r"\bos\.system\s*\(", "os.system() executes shell commands"),
            (r"\bos\.popen\s*\(", "os.popen() executes shell commands"),
            (r"\bsubprocess\.\w+\s*\(", "subprocess calls can execute arbitrary commands"),
            (r"Popen\s*\(.*shell\s*=\s*True", "Popen with shell=True is vulnerable to injection"),
        ],
        "file_system": [
            (r"\bos\.remove\s*\(", "os.remove() deletes files"),
            (r"\bshutil\.rmtree\s*\(", "shutil.rmtree() recursively deletes directories"),
            (r"\bos\.chmod\s*\(", "os.chmod() changes file permissions"),
            (r"open\s*\([^)]*['\"]w['\"]", "Writing to files may be destructive"),
        ],
        "network": [
            (r"\burllib\.request\.\w+\s*\(", "Network requests may exfiltrate data"),
            (r"\brequests\.\w+\s*\(", "HTTP requests may exfiltrate data"),
            (r"\bsocket\.\w+\s*\(", "Raw socket operations"),
        ],
        "deserialization": [
            (r"\bpickle\.loads?\s*\(", "pickle deserialization can execute arbitrary code"),
            (r"\byaml\.load\s*\((?!.*Loader)", "yaml.load without SafeLoader is unsafe"),
            (r"\bjson\.loads?\s*\(.*\beval\b", "JSON with eval is dangerous"),
        ],
    },
    "javascript": {
        "code_injection": [
            (r"\beval\s*\(", "eval() executes arbitrary JavaScript"),
            (r"\bFunction\s*\(", "Function constructor can execute arbitrary code"),
            (r"\bsetTimeout\s*\(\s*['\"]", "setTimeout with string arg executes code"),
            (r"\bsetInterval\s*\(\s*['\"]", "setInterval with string arg executes code"),
        ],
        "xss": [
            (r"\.innerHTML\s*=", "innerHTML assignment can cause XSS"),
            (r"document\.write\s*\(", "document.write can cause XSS"),
            (r"\.outerHTML\s*=", "outerHTML assignment can cause XSS"),
        ],
        "command_injection": [
            (r"\bchild_process\.\w+\s*\(", "child_process can execute system commands"),
            (r"require\s*\(\s*['\"]child_process['\"]", "child_process module import"),
        ],
    },
    "sql": {
        "sql_injection": [
            (r"['\"]?\s*\+\s*\w+\s*\+\s*['\"]?.*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)", "String concatenation in SQL query"),
            (r"f['\"].*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER).*\{", "f-string in SQL query"),
            (r"\.format\s*\(.*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)", ".format() in SQL query"),
            (r"(?:DROP|TRUNCATE|DELETE FROM)\s+\w+\s*;?\s*--", "Destructive SQL without WHERE clause"),
        ],
    },
    "shell": {
        "dangerous_commands": [
            (r"\brm\s+-rf\s+/", "rm -rf / is extremely destructive"),
            (r"\bchmod\s+777\b", "chmod 777 makes files world-writable"),
            (r"\bcurl\s+.*\|\s*(?:bash|sh|zsh)", "Piping curl to shell is dangerous"),
            (r"\bwget\s+.*\|\s*(?:bash|sh|zsh)", "Piping wget to shell is dangerous"),
            (r">\s*/dev/sd[a-z]", "Writing directly to block device"),
            (r"\bdd\s+.*of=/dev/", "dd to device can destroy data"),
            (r":\(\)\s*\{\s*:\|\s*:\s*&\s*\}\s*;", "Fork bomb"),
        ],
    },
}

# Severity mapping by category
SEVERITY_MAP = {
    "code_injection": "high",
    "command_injection": "high",
    "sql_injection": "high",
    "xss": "medium",
    "file_system": "medium",
    "network": "medium",
    "deserialization": "high",
    "dangerous_commands": "high",
}


class CodeShieldModule:
    """Scans LLM output for insecure code patterns before they reach tool execution."""

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        on_detect: str = "block",
        custom_patterns: Optional[Dict[str, List[tuple]]] = None,
        allowlist: Optional[List[str]] = None,
    ):
        """
        Args:
            languages: Which languages to scan for (default: all).
            categories: Which categories to scan (default: all).
            on_detect: "block" raises exception, "warn" logs, "redact" removes the code.
            custom_patterns: Additional patterns {category: [(pattern, description), ...]}.
            allowlist: List of pattern descriptions to ignore (for known safe uses).
        """
        if on_detect not in ("block", "warn", "redact"):
            raise ValueError(f"on_detect must be 'block', 'warn', or 'redact', got {on_detect!r}")
        self.languages = languages
        self.categories = categories
        self.on_detect = on_detect
        self.custom_patterns = custom_patterns or {}
        self.allowlist = set(allowlist or [])

        # Stats
        self.scanned_responses = 0
        self.findings_count = 0
        self.blocked_count = 0
        self.recent_findings: List[Dict] = []

        # Build compiled patterns
        self._compiled_patterns = self._build_patterns()

    def _build_patterns(self) -> List[Dict]:
        """Compile regex patterns based on configured languages and categories."""
        compiled = []
        for lang, categories_dict in DANGEROUS_PATTERNS.items():
            if self.languages and lang not in self.languages:
                continue
            for category, patterns in categories_dict.items():
                if self.categories and category not in self.categories:
                    continue
                for pattern_str, description in patterns:
                    if description in self.allowlist:
                        continue
                    compiled.append({
                        "regex": re.compile(pattern_str),
                        "pattern": pattern_str,
                        "category": category,
                        "language": lang,
                        "description": description,
                        "severity": SEVERITY_MAP.get(category, "medium"),
                    })
        # Add custom patterns
        for category, patterns in self.custom_patterns.items():
            if self.categories and category not in self.categories:
                continue
            for pattern_str, description in patterns:
                if description in self.allowlist:
                    continue
                compiled.append({
                    "regex": re.compile(pattern_str),
                    "pattern": pattern_str,
                    "category": category,
                    "language": "custom",
                    "description": description,
                    "severity": SEVERITY_MAP.get(category, "medium"),
                })
        return compiled

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Scan response text for dangerous code patterns."""
        self.scanned_responses += 1
        findings = self.scan_code(ctx.text)
        if findings:
            self.findings_count += len(findings)
            self.recent_findings.extend(findings)
            # Keep only the most recent 100 findings in memory
            if len(self.recent_findings) > 100:
                self.recent_findings = self.recent_findings[-100:]

            if self.on_detect == "block":
                self.blocked_count += 1
                descriptions = "; ".join(f["description"] for f in findings[:3])
                raise InsecureCodeDetected(
                    f"Dangerous code detected: {descriptions}"
                )
            elif self.on_detect == "warn":
                for f in findings:
                    logger.warning(
                        "CodeShield finding: [%s/%s] %s (line %s)",
                        f["language"], f["category"], f["description"], f.get("line"),
                    )
            elif self.on_detect == "redact":
                ctx.text = self._redact_code_blocks(ctx.text)
        return ctx

    def stream_filter(self, text: str) -> str:
        """Scan streaming text for dangerous code patterns."""
        findings = self.scan_code(text)
        if findings:
            self.findings_count += len(findings)
            if self.on_detect == "block":
                self.blocked_count += 1
                descriptions = "; ".join(f["description"] for f in findings[:3])
                raise InsecureCodeDetected(
                    f"Dangerous code detected: {descriptions}"
                )
            elif self.on_detect == "warn":
                for f in findings:
                    logger.warning(
                        "CodeShield stream finding: [%s/%s] %s",
                        f["language"], f["category"], f["description"],
                    )
            elif self.on_detect == "redact":
                text = self._redact_code_blocks(text)
        return text

    def scan_code(self, code: str, language: Optional[str] = None) -> List[Dict]:
        """
        Standalone scan function. Returns list of findings.

        Each finding is a dict with keys: pattern, category, language,
        description, line, severity.
        """
        findings = []
        detected_lang = language or self._detect_language(code)
        lines = code.split("\n")

        for entry in self._compiled_patterns:
            # If a specific language was requested or detected, only match
            # patterns for that language (unless scanning all).
            if detected_lang and entry["language"] not in (detected_lang, "custom"):
                continue

            for line_num, line_text in enumerate(lines, start=1):
                if entry["regex"].search(line_text):
                    finding = {
                        "pattern": entry["pattern"],
                        "category": entry["category"],
                        "language": entry["language"],
                        "description": entry["description"],
                        "line": line_num,
                        "severity": entry["severity"],
                    }
                    findings.append(finding)

        return findings

    def _detect_language(self, code: str) -> Optional[str]:
        """Simple heuristic to detect code language from content."""
        # Check for markdown code block language hints
        md_match = re.search(r"```(\w+)", code)
        if md_match:
            lang_hint = md_match.group(1).lower()
            lang_map = {
                "python": "python",
                "py": "python",
                "python3": "python",
                "javascript": "javascript",
                "js": "javascript",
                "typescript": "javascript",
                "ts": "javascript",
                "sql": "sql",
                "bash": "shell",
                "sh": "shell",
                "zsh": "shell",
                "shell": "shell",
            }
            if lang_hint in lang_map:
                return lang_map[lang_hint]
        # If no markdown hint, return None to scan all languages
        return None

    def _redact_code_blocks(self, text: str) -> str:
        """Replace code blocks that contain dangerous patterns with a redaction notice."""
        # Redact fenced code blocks containing dangerous patterns
        def _replace_block(match):
            block_content = match.group(0)
            for entry in self._compiled_patterns:
                if entry["regex"].search(block_content):
                    return "[CODE REDACTED: Potentially dangerous code removed by CodeShield]"
            return block_content

        result = re.sub(r"```[\s\S]*?```", _replace_block, text)

        # If there were no fenced blocks but the whole text matched, redact inline
        if result == text:
            for entry in self._compiled_patterns:
                if entry["regex"].search(result):
                    # Redact the specific pattern match inline
                    result = entry["regex"].sub("[REDACTED]", result)

        return result

    def report(self) -> dict:
        """Return a summary of scanning activity."""
        return {
            "scanned_responses": self.scanned_responses,
            "findings_count": self.findings_count,
            "blocked_count": self.blocked_count,
            "recent_findings": self.recent_findings[-10:],
        }
