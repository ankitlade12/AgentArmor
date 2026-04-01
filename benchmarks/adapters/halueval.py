"""HaluEval adapter — 35K hallucination detection samples with source context.

Dataset: pminervini/HaluEval
Configs and their fields:
  - qa_samples (split="data"):  knowledge, question, answer, hallucination (yes/no)
  - dialogue_samples (split="data"):  knowledge, dialogue_history, response, hallucination (yes/no)
  - summarization_samples (split="data"):  document, summary, hallucination (yes/no)
"""
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

        # Config -> (source_context_field, response_field)
        config_fields = {
            "qa_samples": ("knowledge", "answer"),
            "dialogue_samples": ("knowledge", "response"),
            "summarization_samples": ("document", "summary"),
        }

        for config, (context_field, response_field) in config_fields.items():
            try:
                ds = load_dataset(self.source, config, split="data")
                task = config.replace("_samples", "")

                for row in ds:
                    source_context = row.get(context_field, "")
                    response_text = row.get(response_field, "")
                    hallucination = row.get("hallucination", "")

                    if not response_text or not source_context:
                        continue

                    # hallucination field is "yes" or "no"
                    is_hallucinated = str(hallucination).lower().strip() == "yes"

                    samples.append(NormalizedSample(
                        text=response_text,
                        label="positive" if is_hallucinated else "negative",
                        category=task,
                        source_context=source_context,
                        metadata={
                            "source": "halueval",
                            "task": task,
                            "hallucination": str(hallucination),
                        },
                    ))
            except Exception:
                continue

        if not samples:
            raise RuntimeError(f"Could not load HaluEval from {self.source}. Check dataset availability.")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
