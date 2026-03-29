"""XSTest adapter — 250 safe + 200 unsafe prompts for over-refusal testing."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class XSTestAdapter(DatasetAdapter):
    name = "xstest"
    description = "XSTest: Safe vs unsafe prompts for measuring over-refusal"
    source = "walledai/XSTest"
    target_modules = ["shield", "ml_shield", "toxicity"]
    default_sample_size = 450  # small dataset, use all

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        ds = load_dataset(self.source, split="test", trust_remote_code=True)
        samples = []

        for row in ds:
            prompt = row.get("prompt", row.get("text", ""))
            label_raw = row.get("label", row.get("type", ""))
            note = row.get("note", row.get("focus", ""))

            if not prompt:
                continue

            # XSTest labels: "safe" prompts should NOT be blocked, "unsafe" should
            if str(label_raw).lower() in ("safe", "0", "benign"):
                label = "negative"
            else:
                label = "positive"

            samples.append(NormalizedSample(
                text=prompt,
                label=label,
                category=str(note or label_raw),
                metadata={"source": "xstest", "original_label": str(label_raw)},
            ))

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
