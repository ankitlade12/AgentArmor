"""BBQ adapter — Bias Benchmark for QA across 9 social dimensions."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class BBQAdapter(DatasetAdapter):
    name = "bbq"
    description = "BBQ: Bias Benchmark for QA across 9 social dimensions"
    source = "heegyu/bbq"
    target_modules = ["toxicity"]
    default_sample_size = 500

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        ds = load_dataset(self.source, split="test", streaming=True)

        samples = []
        max_scan = 10000

        for i, row in enumerate(ds):
            if i >= max_scan:
                break

            context = row.get("context", "")
            question = row.get("question", "")
            category = row.get("category", row.get("bias_type", "unknown"))

            # Combine context + question as the text
            text = f"{context} {question}".strip()
            if not text:
                continue

            # BBQ labels: stereotyped answers indicate bias
            # We check if the context + question contains biased content
            label_raw = row.get("label", row.get("answer_label", ""))
            # In BBQ, the "target" is the stereotyped answer index
            # For our purposes, ambiguous contexts with stereotyped framing = positive
            target = row.get("target_loc", row.get("stereotyped_groups", ""))

            # Simplified: if the question + context contains stereotyping content,
            # mark as positive; BBQ's structure makes this nuanced
            # For toxicity module testing, we test if the biased framing is detected
            is_biased = row.get("context_condition", "") == "ambig" and str(target) != ""

            samples.append(NormalizedSample(
                text=text,
                label="positive" if is_biased else "negative",
                category=str(category),
                metadata={"source": "bbq", "context_condition": row.get("context_condition", "")},
            ))

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
