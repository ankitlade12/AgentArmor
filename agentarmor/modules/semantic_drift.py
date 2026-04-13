"""
Semantic Drift Detector — embedding-based conversation trajectory tracking.

Detects when a multi-turn conversation gradually drifts away from its intended
purpose. Uses sentence embeddings to track topic similarity over turns, catching
slow-burn manipulation where each individual message looks safe but the cumulative
trajectory is adversarial.

Requires sentence-transformers:
    pip install agentarmor[semantic_drift]

For tests or custom embedding backends, pass an ``encoder`` callable to bypass
the default sentence-transformers loader.
"""

import threading
import warnings
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from ..exceptions import SemanticDriftDetected
from ..hooks import RequestContext


EncoderFn = Callable[[str], Any]


class SemanticDriftModule:
    """Detects semantic drift in multi-turn conversations.

    Anchors to the system prompt (or first user message) and tracks how
    far each subsequent turn drifts from the anchor in sentence-embedding space.

    Args:
        on_detect: ``"warn"`` emits a :class:`RuntimeWarning` and records the
            alert; ``"block"`` raises :class:`SemanticDriftDetected`.
            Default ``"warn"`` (safer for a new detector).
        drift_threshold: Cosine similarity below this triggers detection.
            Range 0.0–1.0. Lower values require more drift to trigger.
            Default ``0.35`` (tuned for ``all-MiniLM-L6-v2``).
        window_size: Number of recent turns to average when computing drift.
        min_turns: Minimum turns before drift detection activates.
        anchor_to_system: Anchor to the system prompt (and first user message)
            if available. If False or no system prompt exists, the first
            ``window_size`` turns are used as the anchor.
        model_name: sentence-transformers model name. Default
            ``"all-MiniLM-L6-v2"`` (~80MB, 384-dim, fast).
        encoder: Optional callable ``(text) -> np.ndarray`` to use instead of
            loading sentence-transformers. Useful for tests or custom backends.
            When provided, sentence-transformers is not required.
        max_history: Cap on stored turns / drift scores / alerts (FIFO).
            Prevents unbounded memory in long conversations. Default 200.
    """

    def __init__(
        self,
        on_detect: str = "warn",
        drift_threshold: float = 0.35,
        window_size: int = 3,
        min_turns: int = 3,
        anchor_to_system: bool = True,
        model_name: str = "all-MiniLM-L6-v2",
        encoder: Optional[EncoderFn] = None,
        max_history: int = 200,
    ):
        if on_detect not in ("warn", "block"):
            raise ValueError("on_detect must be 'warn' or 'block'")
        if not 0.0 <= drift_threshold <= 1.0:
            raise ValueError("drift_threshold must be between 0 and 1")
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if min_turns < 1:
            raise ValueError("min_turns must be >= 1")
        if max_history < window_size:
            raise ValueError("max_history must be >= window_size")

        self.on_detect = on_detect
        self.drift_threshold = drift_threshold
        self.window_size = window_size
        self.min_turns = min_turns
        self.anchor_to_system = anchor_to_system
        self.model_name = model_name
        self.max_history = max_history

        self._lock = threading.Lock()
        self._turn_count = 0
        self.anchor_embedding: Optional[Any] = None
        self.anchor_text: Optional[str] = None
        self.turn_history: Deque[Dict[str, Any]] = deque(maxlen=max_history)
        self.drift_scores: Deque[float] = deque(maxlen=max_history)
        self.alerts: Deque[Dict[str, Any]] = deque(maxlen=max_history)

        self._custom_encoder = encoder
        self._st_model = None
        self._model_lock = threading.Lock()

        if encoder is None:
            self._check_sentence_transformers()

    @staticmethod
    def _check_sentence_transformers() -> None:
        """Verify sentence-transformers is importable; raise a helpful error if not."""
        try:
            import sentence_transformers  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "SemanticDriftModule requires sentence-transformers. "
                "Install it with: pip install agentarmor[semantic_drift]\n"
                "Alternatively, pass a custom `encoder` callable for testing "
                "or to use a different embedding backend."
            ) from exc

    def _encode(self, text: str) -> Any:
        """Encode text to a vector. Loads the model lazily on first call."""
        if self._custom_encoder is not None:
            return self._custom_encoder(text)

        if self._st_model is None:
            with self._model_lock:
                if self._st_model is None:
                    from sentence_transformers import SentenceTransformer
                    self._st_model = SentenceTransformer(self.model_name)
        return self._st_model.encode(text, convert_to_numpy=True)

    @staticmethod
    def _cosine_similarity(a: Any, b: Any) -> float:
        """Cosine similarity between two vectors."""
        import numpy as np
        va = np.asarray(a, dtype=float)
        vb = np.asarray(b, dtype=float)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Pre-request hook: analyze conversation trajectory."""
        if self.anchor_text is None and self.anchor_to_system:
            self._extract_anchor(ctx.messages)

        user_text = self._extract_user_text(ctx.messages)
        if not user_text:
            return ctx

        with self._lock:
            self._turn_count += 1
            embedding = self._encode(user_text)

            self.turn_history.append({
                "turn": self._turn_count,
                "text_preview": user_text[:100],
                "embedding": embedding,
            })

            if self._turn_count >= self.min_turns:
                drift_score = self._calculate_drift()
                self.drift_scores.append(drift_score)

                if drift_score < self.drift_threshold:
                    alert = {
                        "turn": self._turn_count,
                        "drift_score": round(drift_score, 4),
                        "threshold": self.drift_threshold,
                        "detail": (
                            f"Conversation drift detected at turn {self._turn_count} "
                            f"(similarity: {drift_score:.4f}, threshold: {self.drift_threshold})"
                        ),
                    }
                    self.alerts.append(alert)

                    if self.on_detect == "block":
                        raise SemanticDriftDetected(alert["detail"])
                    warnings.warn(alert["detail"], RuntimeWarning, stacklevel=2)

        return ctx

    def _extract_anchor(self, messages: List[Dict[str, Any]]) -> None:
        """Extract anchor text from system prompt (and first user message if present)."""
        parts = []
        first_user_seen = False
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            text = self._content_to_text(content)
            if not text:
                continue
            if role == "system":
                parts.append(text)
            elif role == "user" and not first_user_seen:
                parts.append(text)
                first_user_seen = True

        anchor_text = " ".join(parts).strip()
        if anchor_text:
            self.anchor_text = anchor_text
            self.anchor_embedding = self._encode(anchor_text)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """Flatten OpenAI/Anthropic-style content (str or list-of-parts) to text."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and "text" in p:
                    parts.append(p["text"])
            return " ".join(parts)
        return ""

    def _extract_user_text(self, messages: List[Dict[str, Any]]) -> str:
        """Extract the latest user message text."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return self._content_to_text(msg.get("content", ""))
        return ""

    def _calculate_drift(self) -> float:
        """Compute similarity of the recent window against the anchor."""
        recent = list(self.turn_history)[-self.window_size:]

        if self.anchor_embedding is not None:
            sims = [
                self._cosine_similarity(self.anchor_embedding, t["embedding"])
                for t in recent
            ]
            return sum(sims) / len(sims) if sims else 1.0

        # Fallback: compare recent window against the earliest window.
        if len(self.turn_history) > self.window_size:
            early = list(self.turn_history)[: self.window_size]
            sims = [
                self._cosine_similarity(e["embedding"], r["embedding"])
                for e in early
                for r in recent
            ]
            return sum(sims) / len(sims) if sims else 1.0

        return 1.0

    def get_drift_score(self) -> Optional[float]:
        """Return the most recent drift score, or None if not yet computed."""
        with self._lock:
            return self.drift_scores[-1] if self.drift_scores else None

    def get_trajectory(self) -> List[float]:
        """Return the bounded history of drift scores."""
        with self._lock:
            return list(self.drift_scores)

    def report(self) -> dict:
        with self._lock:
            scores = list(self.drift_scores)
            alerts = list(self.alerts)
            return {
                "turns_analyzed": self._turn_count,
                "drift_scores": scores[-10:],
                "current_drift": scores[-1] if scores else None,
                "alerts": len(alerts),
                "alert_details": alerts[-5:],
                "anchor_set": self.anchor_text is not None,
                "backend": "custom" if self._custom_encoder else "sentence_transformers",
                "model_name": self.model_name if not self._custom_encoder else None,
            }
