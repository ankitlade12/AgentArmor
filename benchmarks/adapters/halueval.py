"""HaluEval adapter — 35K hallucination detection samples with source context."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class HaluEvalAdapter(DatasetAdapter):
    name = "halueval"
    description = "HaluEval: Hallucination evaluation across QA, dialogue, and summarization"
    source = "pminervini/HaluEval"
    target_modules = ["grounding"]
    default_sample_size = 500

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []

        # Load QA subset
        for config in ["qa_samples", "dialogue_samples", "summarization_samples"]:
            try:
                ds = load_dataset(self.source, config, split="data", trust_remote_code=True)
                task = config.replace("_samples", "")

                for row in ds:
                    knowledge = row.get("knowledge", row.get("document", row.get("context", "")))

                    # Hallucinated answer
                    hallucinated = row.get("hallucinated_answer", row.get("hallucinated_response", ""))
                    if hallucinated and knowledge:
                        samples.append(NormalizedSample(
                            text=hallucinated,
                            label="positive",
                            category=task,
                            source_context=knowledge,
                            metadata={"source": "halueval", "task": task, "type": "hallucinated"},
                        ))

                    # Correct answer
                    correct = row.get("right_answer", row.get("right_response", row.get("correct_answer", "")))
                    if correct and knowledge:
                        samples.append(NormalizedSample(
                            text=correct,
                            label="negative",
                            category=task,
                            source_context=knowledge,
                            metadata={"source": "halueval", "task": task, "type": "correct"},
                        ))
            except Exception as e:
                # Try alternate loading approaches
                continue

        # If HuggingFace loading fails completely, try general dataset
        if not samples:
            try:
                ds = load_dataset(self.source, split="train", trust_remote_code=True)
                for row in ds:
                    knowledge = row.get("knowledge", row.get("context", ""))
                    for key, lbl in [("hallucinated_answer", "positive"), ("right_answer", "negative")]:
                        answer = row.get(key, "")
                        if answer and knowledge:
                            samples.append(NormalizedSample(
                                text=answer, label=lbl, category="general",
                                source_context=knowledge,
                                metadata={"source": "halueval"},
                            ))
            except Exception:
                pass

        if not samples:
            raise RuntimeError(f"Could not load HaluEval from {self.source}. Check dataset availability.")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
