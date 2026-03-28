import re
import math
import threading
from collections import Counter
from typing import Optional, List, Dict, Any, Set
from ..exceptions import SemanticDriftDetected
from ..hooks import RequestContext, ResponseContext


# Stop words to exclude from topic extraction
STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
    'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
    'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'both',
    'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
    'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
    'because', 'but', 'and', 'or', 'if', 'while', 'that', 'this', 'what',
    'which', 'who', 'whom', 'these', 'those', 'i', 'me', 'my', 'myself',
    'we', 'our', 'ours', 'you', 'your', 'yours', 'he', 'him', 'his',
    'she', 'her', 'hers', 'it', 'its', 'they', 'them', 'their', 'about',
    'up', 'don', 'didn', 'doesn', 'hadn', 'hasn', 'haven', 'isn', 'let',
    'mustn', 'shan', 'shouldn', 'wasn', 'weren', 'won', 'wouldn', 'please',
    'thank', 'thanks', 'yes', 'no', 'ok', 'okay', 'sure', 'hi', 'hello',
}

WORD_PATTERN = re.compile(r'\b[a-zA-Z]{3,}\b')


def extract_keywords(text: str, top_n: int = 30) -> Counter:
    """Extract meaningful keywords from text, excluding stop words."""
    words = WORD_PATTERN.findall(text.lower())
    filtered = [w for w in words if w not in STOP_WORDS and len(w) >= 3]
    return Counter(filtered).most_common(top_n)


def cosine_similarity(counter1: Counter, counter2: Counter) -> float:
    """Compute cosine similarity between two keyword frequency counters."""
    if not counter1 or not counter2:
        return 0.0

    all_keys = set(dict(counter1).keys()) | set(dict(counter2).keys())
    vec1 = dict(counter1)
    vec2 = dict(counter2)

    dot_product = sum(vec1.get(k, 0) * vec2.get(k, 0) for k in all_keys)
    magnitude1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    magnitude2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


class SemanticDriftModule:
    """Detects semantic drift in multi-turn conversations away from the intended purpose."""

    def __init__(self, on_detect: str = "block",
                 drift_threshold: float = 0.3,
                 window_size: int = 3,
                 min_turns: int = 3,
                 anchor_to_system: bool = True,
                 track_intent_shift: bool = True):
        """
        Args:
            on_detect: 'block' or 'warn'
            drift_threshold: Similarity score below which drift is flagged (0-1, lower = more drift)
            window_size: Number of recent turns to compare against anchor
            min_turns: Minimum turns before drift detection activates
            anchor_to_system: Whether to anchor to system prompt keywords
            track_intent_shift: Whether to track intent category shifts
        """
        self.on_detect = on_detect
        self.drift_threshold = drift_threshold
        self.window_size = window_size
        self.min_turns = min_turns
        self.anchor_to_system = anchor_to_system
        self.track_intent_shift = track_intent_shift

        self._lock = threading.Lock()
        self.anchor_keywords: Optional[Counter] = None
        self.turn_history: List[Dict[str, Any]] = []
        self.drift_scores: List[float] = []
        self.alerts: List[Dict[str, Any]] = []
        self._turn_count = 0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Pre-request hook: analyze conversation trajectory."""
        # Extract system prompt on first call to establish anchor
        if self.anchor_keywords is None and self.anchor_to_system:
            self._extract_anchor(ctx.messages)

        # Extract current turn content
        user_text = self._extract_user_text(ctx.messages)
        if not user_text:
            return ctx

        with self._lock:
            self._turn_count += 1
            turn_keywords = Counter(dict(extract_keywords(user_text)))

            self.turn_history.append({
                "turn": self._turn_count,
                "keywords": turn_keywords,
                "text_preview": user_text[:100],
            })

            # Only check drift after minimum turns
            if self._turn_count >= self.min_turns:
                drift_score = self._calculate_drift()
                self.drift_scores.append(drift_score)

                if drift_score < self.drift_threshold:
                    alert = {
                        "turn": self._turn_count,
                        "drift_score": round(drift_score, 4),
                        "threshold": self.drift_threshold,
                        "detail": f"Conversation drift detected at turn {self._turn_count} "
                                  f"(similarity: {drift_score:.4f}, threshold: {self.drift_threshold})",
                    }
                    self.alerts.append(alert)

                    if self.on_detect == "block":
                        raise SemanticDriftDetected(alert["detail"])

        return ctx

    def _extract_anchor(self, messages: List[Dict[str, Any]]) -> None:
        """Extract anchor keywords from system prompt and initial messages."""
        anchor_text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" and isinstance(content, str):
                anchor_text += " " + content
            elif role == "user" and isinstance(content, str) and not anchor_text:
                # Use first user message as fallback anchor
                anchor_text += " " + content

        if anchor_text.strip():
            self.anchor_keywords = Counter(dict(extract_keywords(anchor_text, top_n=50)))

    def _extract_user_text(self, messages: List[Dict[str, Any]]) -> str:
        """Extract the latest user message text."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            parts.append(part["text"])
                    return " ".join(parts)
        return ""

    def _calculate_drift(self) -> float:
        """Calculate drift score between anchor/early turns and recent turns."""
        # Get recent window keywords
        recent_turns = self.turn_history[-self.window_size:]
        recent_keywords = Counter()
        for turn in recent_turns:
            recent_keywords.update(turn["keywords"])

        # Compare against anchor
        if self.anchor_keywords:
            return cosine_similarity(self.anchor_keywords, recent_keywords)

        # Fallback: compare against early turns
        if len(self.turn_history) > self.window_size:
            early_turns = self.turn_history[:self.window_size]
            early_keywords = Counter()
            for turn in early_turns:
                early_keywords.update(turn["keywords"])
            return cosine_similarity(early_keywords, recent_keywords)

        return 1.0  # No drift detected if not enough history

    def get_drift_score(self) -> Optional[float]:
        """Get the latest drift score."""
        with self._lock:
            return self.drift_scores[-1] if self.drift_scores else None

    def get_trajectory(self) -> List[float]:
        """Get the full trajectory of drift scores."""
        with self._lock:
            return list(self.drift_scores)

    def report(self) -> dict:
        with self._lock:
            return {
                "turns_analyzed": self._turn_count,
                "drift_scores": self.drift_scores[-10:],
                "current_drift": self.drift_scores[-1] if self.drift_scores else None,
                "alerts": len(self.alerts),
                "alert_details": self.alerts[-5:],
                "anchor_set": bool(self.anchor_keywords),
            }
