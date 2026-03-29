"""BBQ adapter — Bias Benchmark for QA across 9 social dimensions."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class BBQAdapter(DatasetAdapter):
    name = "bbq"
    description = "BBQ: Bias Benchmark for QA across 9 social dimensions"
    source = "lighteval/bbq_helm"
    target_modules = ["toxicity"]
    default_sample_size = 500

    # lighteval/bbq_helm configs correspond to social dimensions
    _configs = [
        "Age", "Disability_status", "Gender_identity", "Nationality",
        "Physical_appearance", "Race_ethnicity", "Race_x_SES",
        "Race_x_gender", "Religion", "SES", "Sexual_orientation",
    ]

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []
        max_per_config = 2000

        # Try the 'all' config first, fall back to individual configs
        try:
            ds = load_dataset(self.source, "all", split="test", streaming=True)
            for i, row in enumerate(ds):
                if i >= 10000:
                    break
                sample = self._parse_row(row, "all")
                if sample:
                    samples.append(sample)
        except Exception:
            for config in self._configs:
                try:
                    ds = load_dataset(self.source, config, split="test", streaming=True)
                    for i, row in enumerate(ds):
                        if i >= max_per_config:
                            break
                        sample = self._parse_row(row, config)
                        if sample:
                            samples.append(sample)
                except Exception:
                    continue

        if not samples:
            raise RuntimeError(f"Could not load BBQ from {self.source}. Check dataset availability.")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)

    def _parse_row(self, row: dict, config: str) -> Optional[NormalizedSample]:
        """Parse a row from lighteval/bbq_helm format.

        Fields: context, question, choices (list), gold_index (int),
        references.output (list), references.tags (list of lists).
        """
        context = row.get("context", "")
        question = row.get("question", "")
        text = f"{context} {question}".strip()
        if not text:
            return None

        # In bbq_helm, tags contain labels like 'ambiguous', 'negative', 'non-negative'
        # A question is biased when the gold answer is NOT "Cannot be determined" / similar
        # (i.e. the model can infer stereotyped info from ambiguous context)
        references = row.get("references", {})
        tags_list = references.get("tags", [])
        outputs = references.get("output", [])
        gold_index = row.get("gold_index", -1)

        # Check if the correct answer is the "unknown" / "cannot be determined" option
        gold_answer = ""
        if 0 <= gold_index < len(outputs):
            gold_answer = str(outputs[gold_index]).lower()

        is_ambiguous = any(
            "ambiguous" in tag
            for tags in tags_list
            for tag in tags
        )

        # If gold answer is NOT the uncertain option, it means the question
        # has a determinate (potentially biased) framing
        uncertain_phrases = {"cannot be determined", "can't answer", "not enough info",
                             "not known", "undetermined", "unknown", "can't be determined"}
        gold_is_uncertain = any(p in gold_answer for p in uncertain_phrases)

        # Biased = ambiguous context where the gold answer picks a specific person/group
        is_biased = is_ambiguous and not gold_is_uncertain

        return NormalizedSample(
            text=text,
            label="positive" if is_biased else "negative",
            category=config,
            metadata={"source": "bbq", "gold_answer": gold_answer},
        )
