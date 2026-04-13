"""
Multi-Agent Echo-Chamber Detector

Detects when a hallucinated claim circulates between agents and comes
back as "independent confirmation." In multi-agent systems (CrewAI,
Autogen, LangGraph), Agent A might hallucinate a fact, Agent B cites
Agent A as a source, and Agent A later treats B's citation as
confirmation — creating a circular hallucination loop.

This module hashes claims at agent boundaries and flags when the same
claim returns through a different agent path without an external
grounding source.
"""

import hashlib
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set


class Claim:
    """A factual claim extracted from agent output."""

    __slots__ = ("text", "hash", "origin_agent", "seen_by", "timestamp",
                 "grounded")

    def __init__(self, text: str, origin_agent: str, grounded: bool = False):
        self.text = text
        self.hash = self._compute_hash(text)
        self.origin_agent = origin_agent
        self.seen_by: Set[str] = {origin_agent}
        self.timestamp = time.time()
        self.grounded = grounded

    @staticmethod
    def _compute_hash(text: str) -> str:
        """Normalize and hash a claim for dedup."""
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        # Remove common filler words for fuzzy matching
        for w in ("the", "a", "an", "is", "are", "was", "were", "that",
                   "which", "this"):
            normalized = re.sub(rf'\b{w}\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:16]


class EchoChamberAlert:
    """Alert raised when circular confirmation is detected."""

    def __init__(self, claim: Claim, echo_agent: str, path: List[str]):
        self.claim_text = claim.text
        self.claim_hash = claim.hash
        self.origin_agent = claim.origin_agent
        self.echo_agent = echo_agent
        self.path = path
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "claim_text": self.claim_text[:200],
            "claim_hash": self.claim_hash,
            "origin_agent": self.origin_agent,
            "echo_agent": self.echo_agent,
            "path": self.path,
            "timestamp": self.timestamp,
        }


class EchoChamberDetected(Exception):
    """Raised when a circular hallucination loop is detected."""
    pass


class EchoChamberModule:
    """Detects circular confirmation of ungrounded claims across agents.

    Usage:
        detector = EchoChamberModule()
        # When agent produces output:
        detector.register_claims("agent_a", "The capital of Atlantis is Lemuria.")
        # When another agent cites the same claim:
        detector.register_claims("agent_b", "According to sources, the capital of Atlantis is Lemuria.")
        # Echo detected: same claim, different agent, no external grounding
    """

    def __init__(
        self,
        min_claim_length: int = 30,
        on_echo: str = "warn",
        grounding_sources: Optional[List[str]] = None,
        max_claims: int = 500,
    ):
        """
        Args:
            min_claim_length: Minimum character length for a sentence to be
                tracked as a claim.
            on_echo: "block" raises EchoChamberDetected, "warn" logs.
            grounding_sources: List of trusted source texts. Claims that
                appear in these sources are marked as grounded and exempt.
            max_claims: Max claims to track (oldest evicted when exceeded).
        """
        self.min_claim_length = min_claim_length
        self.on_echo = on_echo
        self.grounding_sources = grounding_sources or []
        self.max_claims = max_claims
        self._lock = threading.Lock()
        self._claims: Dict[str, Claim] = {}  # hash -> Claim
        self.alerts: List[EchoChamberAlert] = []
        self.stats = {
            "claims_tracked": 0,
            "echoes_detected": 0,
            "claims_grounded": 0,
        }

    def register_claims(self, agent_id: str, text: str) -> List[EchoChamberAlert]:
        """Extract claims from agent output and check for echo patterns.

        Returns list of echo alerts (empty if no echoes detected).
        """
        sentences = self._extract_sentences(text)
        new_alerts = []

        for sentence in sentences:
            if len(sentence) < self.min_claim_length:
                continue

            claim = Claim(text=sentence, origin_agent=agent_id)

            # Check if this claim is grounded in trusted sources
            if self._is_grounded(sentence):
                claim.grounded = True
                with self._lock:
                    self.stats["claims_grounded"] += 1

            with self._lock:
                existing = self._claims.get(claim.hash)

                if existing is not None:
                    # Same claim seen before
                    if (agent_id != existing.origin_agent
                            and agent_id not in existing.seen_by
                            and not existing.grounded):
                        # Echo detected: same claim, different agent, ungrounded
                        path = [existing.origin_agent] + \
                               sorted(existing.seen_by - {existing.origin_agent}) + \
                               [agent_id]
                        alert = EchoChamberAlert(existing, agent_id, path)
                        self.alerts.append(alert)
                        self.stats["echoes_detected"] += 1
                        new_alerts.append(alert)

                    existing.seen_by.add(agent_id)
                else:
                    # New claim
                    self._claims[claim.hash] = claim
                    self.stats["claims_tracked"] += 1

                    # Evict oldest if over limit
                    if len(self._claims) > self.max_claims:
                        oldest_hash = min(
                            self._claims,
                            key=lambda h: self._claims[h].timestamp,
                        )
                        del self._claims[oldest_hash]

        # Handle alerts
        for alert in new_alerts:
            if self.on_echo == "block":
                raise EchoChamberDetected(
                    f"Circular confirmation detected: claim from "
                    f"'{alert.origin_agent}' echoed by '{alert.echo_agent}' "
                    f"without external grounding. "
                    f"Claim: {alert.claim_text[:100]}"
                )

        return new_alerts

    def add_grounding_source(self, text: str) -> None:
        """Add a trusted grounding source at runtime."""
        self.grounding_sources.append(text)

    def get_ungrounded_claims(self) -> List[Dict]:
        """Return all tracked ungrounded claims."""
        with self._lock:
            return [
                {"text": c.text[:200], "hash": c.hash,
                 "origin": c.origin_agent, "seen_by": sorted(c.seen_by)}
                for c in self._claims.values()
                if not c.grounded
            ]

    def _is_grounded(self, sentence: str) -> bool:
        """Check if a sentence is grounded in trusted sources."""
        s_lower = sentence.lower()
        for source in self.grounding_sources:
            if s_lower in source.lower():
                return True
            # Also check key phrase overlap
            words = set(re.findall(r'\b\w{4,}\b', s_lower))
            src_words = set(re.findall(r'\b\w{4,}\b', source.lower()))
            if words and len(words & src_words) / len(words) >= 0.7:
                return True
        return False

    @staticmethod
    def _extract_sentences(text: str) -> List[str]:
        """Split text into sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def report(self) -> dict:
        with self._lock:
            return {
                "stats": dict(self.stats),
                "active_claims": len(self._claims),
                "alerts": [a.to_dict() for a in self.alerts[-10:]],
            }
