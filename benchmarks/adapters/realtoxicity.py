"""RealToxicityPrompts adapter — 100K prompts with toxicity scores."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class RealToxicityAdapter(DatasetAdapter):
    name = "realtoxicity"
    description = "RealToxicityPrompts: 100K prompts scored by Perspective API"
    source = "allenai/real-toxicity-prompts"
    target_modules = ["toxicity"]
    default_sample_size = 500

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        # Stream and collect toxic/non-toxic separately to ensure balance
        ds = load_dataset(self.source, split="train", streaming=True)

        size = sample_size or self.default_sample_size
        target_per_class = size  # Collect enough for stratified sampling
        positives = []
        negatives = []
        max_scan = 100000

        for i, row in enumerate(ds):
            if i >= max_scan:
                break
            if len(positives) >= target_per_class and len(negatives) >= target_per_class:
                break

            prompt_data = row.get("prompt", {})
            if isinstance(prompt_data, dict):
                text = prompt_data.get("text", "")
                toxicity = prompt_data.get("toxicity", 0) or 0
            else:
                text = str(prompt_data)
                toxicity = 0

            if not text or len(text) < 10:
                continue

            is_toxic = toxicity >= 0.5

            if toxicity >= 0.8:
                category = "high_toxicity"
            elif toxicity >= 0.5:
                category = "medium_toxicity"
            elif toxicity >= 0.2:
                category = "low_toxicity"
            else:
                category = "non_toxic"

            sample = NormalizedSample(
                text=text,
                label="positive" if is_toxic else "negative",
                category=category,
                metadata={"source": "realtoxicity", "toxicity_score": toxicity},
            )

            if is_toxic and len(positives) < target_per_class:
                positives.append(sample)
            elif not is_toxic and len(negatives) < target_per_class:
                negatives.append(sample)

        samples = positives + negatives
        return self._stratified_sample(samples, size, seed)
