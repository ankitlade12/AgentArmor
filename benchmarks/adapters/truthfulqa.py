"""
TruthfulQA adapter — 817 questions testing factual grounding.

Strategy: Use TruthfulQA's correct answers as SOURCE CONTEXT, then test
whether the grounding module can distinguish correct vs incorrect answers.
This mirrors real RAG deployments where enterprises have a knowledge base
and want to catch when the LLM deviates from known facts.

- positive (hallucination) = incorrect answers checked against correct source
- negative (grounded) = correct answers checked against correct source
"""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class TruthfulQAAdapter(DatasetAdapter):
    name = "truthfulqa"
    description = "TruthfulQA: 817 questions with correct/incorrect answers for factual grounding"
    source = "truthfulqa/truthful_qa"
    target_modules = ["grounding"]
    default_sample_size = 500

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        ds = load_dataset(self.source, "generation", split="validation", trust_remote_code=True)
        samples = []

        for row in ds:
            question = row.get("question", "")
            best_answer = row.get("best_answer", "")
            correct_answers = row.get("correct_answers", [])
            incorrect_answers = row.get("incorrect_answers", [])
            category = row.get("category", "unknown")

            if not question or not best_answer:
                continue

            # Build source context: question + all correct answers
            # This is the "knowledge base" the grounding module checks against
            source_context = f"Question: {question}\nAnswer: {best_answer}"
            if correct_answers:
                source_context += "\nAlternative correct answers: " + "; ".join(correct_answers)

            # Correct answer = should be grounded (negative = no hallucination)
            samples.append(NormalizedSample(
                text=best_answer,
                label="negative",
                category=category,
                source_context=source_context,
                metadata={
                    "source": "truthfulqa",
                    "question": question,
                    "type": "correct",
                },
            ))

            # Incorrect answers = should be flagged as hallucination (positive)
            for incorrect in incorrect_answers:
                if not incorrect:
                    continue
                samples.append(NormalizedSample(
                    text=incorrect,
                    label="positive",
                    category=category,
                    source_context=source_context,
                    metadata={
                        "source": "truthfulqa",
                        "question": question,
                        "type": "incorrect",
                    },
                ))

        if not samples:
            raise RuntimeError(f"Could not load TruthfulQA from {self.source}")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
