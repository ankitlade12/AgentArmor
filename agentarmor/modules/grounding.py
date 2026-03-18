import re
from typing import Dict, List, Optional, Set
from collections import Counter
from ..hooks import RequestContext, ResponseContext
from ..exceptions import HallucinationDetected


class GroundingGuardModule:
    def __init__(self,
                 sources: Optional[List[str]] = None,
                 threshold: float = 0.3,
                 on_detect: str = "warn",
                 check_claims: bool = True,
                 check_numbers: bool = True,
                 check_names: bool = True,
                 extract_from_messages: bool = True):
        """
        Args:
            sources: List of source/context documents to ground against.
                    If None and extract_from_messages=True, extracts from system/context messages.
            threshold: Minimum grounding score (0-1). Below this = potential hallucination.
            on_detect: "block" raises, "warn" logs, "flag" adds metadata to response
            check_claims: Check factual claims (numbers, dates, proper nouns) against sources
            check_numbers: Specifically verify numeric values appear in sources
            check_names: Specifically verify proper nouns/names appear in sources
            extract_from_messages: Auto-extract source text from system messages and RAG context
        """
        self.sources = sources or []
        self.threshold = threshold
        self.on_detect = on_detect
        self.check_claims = check_claims
        self.check_numbers = check_numbers
        self.check_names = check_names
        self.extract_from_messages = extract_from_messages
        self.checks_run = 0
        self.hallucinations_detected = 0
        self.scores: List[float] = []
        self._session_sources: List[str] = []

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Extract source documents from the request messages for grounding."""
        if self.extract_from_messages:
            self._extract_sources_from_messages(ctx.messages)
        return ctx

    def post_filter(self, ctx: ResponseContext) -> ResponseContext:
        """Check response against source documents for grounding."""
        if not self.sources and not self._session_sources:
            return ctx  # No sources to ground against

        all_sources = self.sources + self._session_sources
        score = self._compute_grounding_score(ctx.text, all_sources)
        self.scores.append(score)
        self.checks_run += 1

        if score < self.threshold:
            self.hallucinations_detected += 1
            self._handle_detection(ctx, score)

        return ctx

    def _extract_sources_from_messages(self, messages: List[Dict]) -> None:
        """Extract context/source text from system messages and RAG-style content."""
        self._session_sources = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str):
                # Extract text between common RAG context markers
                if role == "system" or "context" in content.lower()[:50]:
                    self._session_sources.append(content)
                # Look for document/source markers
                doc_blocks = re.findall(
                    r'(?:Document|Source|Context|Reference)\s*(?:\d+)?[:\n](.*?)'
                    r'(?=(?:Document|Source|Context|Reference)\s*(?:\d+)?[:\n]|\Z)',
                    content, re.DOTALL | re.IGNORECASE
                )
                self._session_sources.extend(doc_blocks)

    def _compute_grounding_score(self, response: str, sources: List[str]) -> float:
        """Compute how well the response is grounded in the source documents."""
        if not sources or not response.strip():
            return 1.0  # No sources = assume grounded

        source_text = " ".join(sources).lower()
        response_lower = response.lower()

        scores = []

        # 1. N-gram overlap score
        ngram_score = self._ngram_overlap(response_lower, source_text, n=3)
        scores.append(ngram_score)

        # 2. Key claim verification
        if self.check_claims:
            claim_score = self._verify_claims(response, sources)
            scores.append(claim_score)

        # 3. Number verification
        if self.check_numbers:
            number_score = self._verify_numbers(response, source_text)
            scores.append(number_score)

        # 4. Named entity / proper noun verification
        if self.check_names:
            name_score = self._verify_names(response, source_text)
            scores.append(name_score)

        return sum(scores) / len(scores) if scores else 1.0

    def _ngram_overlap(self, response: str, source: str, n: int = 3) -> float:
        """Calculate n-gram overlap between response and source."""
        resp_ngrams = self._get_ngrams(response, n)
        src_ngrams = self._get_ngrams(source, n)
        if not resp_ngrams:
            return 1.0
        overlap = resp_ngrams & src_ngrams  # Counter intersection
        return sum(overlap.values()) / sum(resp_ngrams.values())

    def _get_ngrams(self, text: str, n: int) -> Counter:
        """Extract word n-grams from text."""
        words = re.findall(r'\b\w+\b', text.lower())
        return Counter(tuple(words[i:i+n]) for i in range(len(words) - n + 1))

    def _verify_numbers(self, response: str, source_text: str) -> float:
        """Check that numbers in the response appear in the source."""
        resp_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', response))
        if not resp_numbers:
            return 1.0
        source_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', source_text))
        if not source_numbers:
            return 0.5  # Can't verify, neutral score
        matched = resp_numbers & source_numbers
        return len(matched) / len(resp_numbers)

    def _verify_names(self, response: str, source_text: str) -> float:
        """Check that capitalized proper nouns in response appear in source."""
        # Extract likely proper nouns (capitalized words not at sentence start)
        resp_names = set(re.findall(
            r'(?<!\. )(?<!\n)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', response
        ))
        # Filter common words
        common = {
            "The", "This", "That", "These", "Those", "They", "What", "When", "Where",
            "Which", "Who", "How", "Are", "Was", "Were", "Has", "Have", "Had", "Been",
            "Will", "Would", "Could", "Should", "May", "Might", "Can", "But", "And",
            "For", "Not", "You", "All", "Any", "Her", "His", "Its", "Our", "Yes", "No",
            "However", "Also", "Just", "Even", "Still", "Here", "There", "Now", "Then",
            "Some", "Each", "Every", "Both", "Such", "Other", "Many", "Most", "Much",
            "More", "New", "First", "Last", "Great", "High", "Long", "Old", "Small", "Large",
        }
        resp_names = resp_names - common
        if not resp_names:
            return 1.0
        matched = sum(1 for name in resp_names if name.lower() in source_text)
        return matched / len(resp_names)

    def _verify_claims(self, response: str, sources: List[str]) -> float:
        """Extract and verify factual claims from response sentences."""
        # Split response into sentences
        sentences = re.split(r'[.!?]+', response)
        if not sentences:
            return 1.0
        source_text = " ".join(sources).lower()

        grounded = 0
        total = 0
        for sent in sentences:
            sent = sent.strip()
            if len(sent.split()) < 4:  # Skip very short sentences
                continue
            total += 1
            # Check if key words from sentence appear in sources
            words = set(re.findall(r'\b\w+\b', sent.lower()))
            # Remove stop words
            stop = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                "have", "has", "had", "do", "does", "did", "will", "would", "could",
                "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                "on", "with", "at", "by", "from", "as", "into", "it", "its", "this",
                "that", "and", "or", "but", "not",
            }
            key_words = words - stop
            if not key_words:
                grounded += 1
                continue
            overlap = sum(1 for w in key_words if w in source_text)
            if overlap / len(key_words) >= 0.5:
                grounded += 1

        return grounded / total if total > 0 else 1.0

    def _handle_detection(self, ctx, score):
        if self.on_detect == "block":
            raise HallucinationDetected(
                f"Response grounding score {score:.2f} below threshold {self.threshold}. "
                "Response may contain hallucinated content."
            )
        elif self.on_detect == "warn":
            print(f"[AgentArmor] WARNING: Low grounding score ({score:.2f}). Possible hallucination.")
        elif self.on_detect == "flag":
            ctx.text = f"[GROUNDING WARNING: score={score:.2f}]\n{ctx.text}"

    def report(self) -> dict:
        avg_score = sum(self.scores) / len(self.scores) if self.scores else 0.0
        return {
            "checks_run": self.checks_run,
            "hallucinations_detected": self.hallucinations_detected,
            "average_grounding_score": round(avg_score, 3),
            "min_score": round(min(self.scores), 3) if self.scores else None,
            "source_count": len(self.sources),
        }
