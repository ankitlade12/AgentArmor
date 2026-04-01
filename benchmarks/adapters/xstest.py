"""XSTest adapter — 250 safe + 200 unsafe prompts for over-refusal testing.

Dataset: Paul/XSTest (split='train')
Fields: id, prompt, type (e.g. 'homonyms'), label ('safe'/'unsafe'), focus, note
"""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class XSTestAdapter(DatasetAdapter):
    name = "xstest"
    description = "XSTest: Safe vs unsafe prompts for measuring over-refusal"
    source = "Paul/XSTest"
    target_modules = ["shield", "ml_shield", "toxicity"]
    default_sample_size = 450  # small dataset, use all

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        # Paul/XSTest only has a 'train' split
        ds = load_dataset(self.source, split="train")
        samples = []

        for row in ds:
            prompt = row.get("prompt", "")
            label_raw = row.get("label", "")
            prompt_type = row.get("type", "")
            focus = row.get("focus", "")
            note = row.get("note", "")

            if not prompt:
                continue

            # XSTest labels: "safe" prompts should NOT be blocked, "unsafe" should
            if str(label_raw).lower() == "safe":
                label = "negative"
            else:
                label = "positive"

            # Use 'type' (e.g. homonyms, figurative_language) as category,
            # fall back to note for context
            category = prompt_type or note or str(label_raw)

            samples.append(NormalizedSample(
                text=prompt,
                label=label,
                category=category,
                metadata={
                    "source": "xstest",
                    "original_label": str(label_raw),
                    "type": prompt_type,
                    "focus": focus,
                    "note": note,
                },
            ))

        if not samples:
            raise RuntimeError(f"Could not load XSTest from {self.source}. Check dataset availability.")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
