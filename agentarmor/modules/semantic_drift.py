"""
Semantic Drift Detector — embedding-based conversation trajectory tracking.

Detects when a multi-turn conversation gradually drifts away from its intended
purpose. Uses sentence embeddings to track topic similarity over turns, catching
slow-burn manipulation where each individual message looks safe but the cumulative
trajectory is adversarial.

Requires: pip install sentence-transformers
Falls back to TF-IDF (scikit-learn) if sentence-transformers unavailable.
Falls back to keyword overlap if neither is installed.
"""

import math
import threading
from typing import Optional, List, Dict, Any
from ..exceptions import SemanticDriftDetected
from ..hooks import RequestContext


class SemanticDriftModule:
    """Detects semantic drift in multi-turn conversations.

    Anchors to the system prompt (or first user message) and tracks how
    far each subsequent turn drifts from the anchor in embedding space.

    Three backends (auto-selected in priority order):
      1. sentence-transformers — real semantic embeddings (best accuracy)
      2. scikit-learn TF-IDF — document-level similarity (good accuracy)
      3. keyword overlap — bag-of-words fallback (basic)

    Args:
        on_detect: ``"block"`` raises :class:`SemanticDriftDetected`,
            ``"warn"`` prints a warning.
        drift_threshold: Similarity below this triggers detection (0–1).
            Lower = more drift required to trigger. Default 0.35.
        window_size: Number of recent turns to average for drift check.
        min_turns: Minimum turns before drift detection activates.
        anchor_to_system: Anchor to system prompt keywords if available.
        model_name: Sentence-transformers model to use.
            Default ``"all-MiniLM-L6-v2"`` (fast, 384-dim).
    """

    def __init__(
        self,
        on_detect: str = "block",
        drift_threshold: float = 0.35,
        window_size: int = 3,
        min_turns: int = 3,
        anchor_to_system: bool = True,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        self.on_detect = on_detect
        self.drift_threshold = drift_threshold
        self.window_size = window_size
        self.min_turns = min_turns
        self.anchor_to_system = anchor_to_system
        self.model_name = model_name

        self._lock = threading.Lock()
        self._turn_count = 0
        self.anchor_embedding: Optional[Any] = None
        self.anchor_text: Optional[str] = None
        self.turn_history: List[Dict[str, Any]] = []
        self.drift_scores: List[float] = []
        self.alerts: List[Dict[str, Any]] = []

        # Backend selection (lazy init)
        self._backend: Optional[str] = None
        self._st_model = None       # sentence-transformers model
        self._tfidf_vec = None       # TF-IDF vectorizer
        self._init_lock = threading.Lock()

    def _init_backend(self) -> str:
        """Auto-select the best available embedding backend."""
        with self._init_lock:
            if self._backend is not None:
                return self._backend

            # Try sentence-transformers first (best)
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self.model_name)
                self._backend = "sentence_transformers"
                return self._backend
            except ImportError:
                pass

            # Try TF-IDF (good)
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                self._tfidf_vec = TfidfVectorizer(
                    max_features=3000,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                    stop_words="english",
                )
                self._backend = "tfidf"
                return self._backend
            except ImportError:
                pass

            # Keyword fallback (basic)
            self._backend = "keywords"
            return self._backend

    def _embed(self, text: str) -> Any:
        """Compute embedding using the active backend."""
        backend = self._init_backend()

        if backend == "sentence_transformers":
            return self._st_model.encode(text, convert_to_numpy=True)
        elif backend == "tfidf":
            return text  # TF-IDF compares two texts directly, not single embeddings
        else:
            return text  # Keywords compares texts directly

    def _similarity(self, text_a: Any, text_b: Any) -> float:
        """Compute similarity between two texts/embeddings."""
        backend = self._init_backend()

        if backend == "sentence_transformers":
            # Cosine similarity between embedding vectors
            import numpy as np
            a, b = np.array(text_a, dtype=float), np.array(text_b, dtype=float)
            norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))

        elif backend == "tfidf":
            from sklearn.metrics.pairwise import cosine_similarity
            tfidf_matrix = self._tfidf_vec.fit_transform([text_a, text_b])
            return float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])

        else:
            return self._keyword_similarity(text_a, text_b)

    @staticmethod
    def _keyword_similarity(text_a: str, text_b: str) -> float:
        """Simple keyword overlap as last-resort fallback."""
        import re
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
            "at", "by", "from", "as", "into", "it", "its", "this", "that", "and",
            "or", "but", "not", "i", "me", "my", "you", "your", "we", "they",
        }
        words_a = set(re.findall(r"\b[a-z]{3,}\b", text_a.lower())) - stop
        words_b = set(re.findall(r"\b[a-z]{3,}\b", text_b.lower())) - stop
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Pre-request hook: analyze conversation trajectory."""
        # Extract anchor on first call
        if self.anchor_text is None and self.anchor_to_system:
            self._extract_anchor(ctx.messages)

        # Extract current user message
        user_text = self._extract_user_text(ctx.messages)
        if not user_text:
            return ctx

        with self._lock:
            self._turn_count += 1

            # Compute embedding for this turn
            embedding = self._embed(user_text)

            self.turn_history.append({
                "turn": self._turn_count,
                "text_preview": user_text[:100],
                "embedding": embedding,
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
                        "backend": self._backend,
                        "detail": (
                            f"Conversation drift detected at turn {self._turn_count} "
                            f"(similarity: {drift_score:.4f}, threshold: {self.drift_threshold})"
                        ),
                    }
                    self.alerts.append(alert)

                    if self.on_detect == "block":
                        raise SemanticDriftDetected(alert["detail"])

        return ctx

    def _extract_anchor(self, messages: List[Dict[str, Any]]) -> None:
        """Extract anchor text from system prompt or first user message."""
        anchor_text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" and isinstance(content, str):
                anchor_text += " " + content
            elif role == "user" and isinstance(content, str) and not anchor_text:
                anchor_text += " " + content

        if anchor_text.strip():
            self.anchor_text = anchor_text.strip()
            self.anchor_embedding = self._embed(self.anchor_text)

    def _extract_user_text(self, messages: List[Dict[str, Any]]) -> str:
        """Extract the latest user message text."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    parts = [p["text"] for p in content if isinstance(p, dict) and "text" in p]
                    return " ".join(parts)
        return ""

    def _calculate_drift(self) -> float:
        """Calculate drift score between anchor and recent turns."""
        recent = self.turn_history[-self.window_size:]

        if self.anchor_text and self.anchor_embedding is not None:
            # Compare recent window against anchor
            similarities = []
            for turn in recent:
                sim = self._similarity(self.anchor_embedding, turn["embedding"])
                similarities.append(sim)
            return sum(similarities) / len(similarities) if similarities else 1.0

        # Fallback: compare recent against early turns
        if len(self.turn_history) > self.window_size:
            early = self.turn_history[:self.window_size]
            similarities = []
            for r_turn in recent:
                for e_turn in early:
                    sim = self._similarity(e_turn["embedding"], r_turn["embedding"])
                    similarities.append(sim)
            return sum(similarities) / len(similarities) if similarities else 1.0

        return 1.0

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
                "backend": self._backend or "not_initialized",
                "drift_scores": self.drift_scores[-10:],
                "current_drift": self.drift_scores[-1] if self.drift_scores else None,
                "alerts": len(self.alerts),
                "alert_details": self.alerts[-5:],
                "anchor_set": self.anchor_text is not None,
            }
