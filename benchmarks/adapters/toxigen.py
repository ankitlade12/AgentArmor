"""ToxiGen adapter — 274K implicit/subtle toxicity statements."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class ToxiGenAdapter(DatasetAdapter):
    name = "toxigen"
    description = "ToxiGen: 274K implicit hate speech targeting 13 minority groups"
    source = "toxigen/toxigen-data"
    target_modules = ["toxicity"]
    default_sample_size = 500

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        # Try different config names
        ds = None
        for config in ["annotated", "train", None]:
            try:
                if config:
                    ds = load_dataset(self.source, config, split="train",
                                     streaming=True)
                else:
                    ds = load_dataset(self.source, split="train",
                                     streaming=True)
                break
            except Exception:
                continue

        if ds is None:
            # Fallback to alternate source
            try:
                ds = load_dataset("skg/toxigen-data", "annotated", split="train",
                                 streaming=True)
            except Exception:
                raise RuntimeError(f"Could not load ToxiGen. Check dataset availability.")

        samples = []
        max_scan = 10000

        for i, row in enumerate(ds):
            if i >= max_scan:
                break

            text = row.get("text", row.get("generation", ""))
            # Label: 1 = toxic, 0 = benign (field may vary)
            label_raw = row.get("toxicity_human", row.get("label", row.get("toxicity_ai", 0)))
            target_group = row.get("target_group", row.get("group", "unknown"))

            if not text:
                continue

            try:
                is_toxic = float(label_raw) >= 0.5
            except (ValueError, TypeError):
                is_toxic = str(label_raw).lower() in ("1", "true", "toxic")

            samples.append(NormalizedSample(
                text=text,
                label="positive" if is_toxic else "negative",
                category=str(target_group),
                metadata={"source": "toxigen", "original_label": str(label_raw)},
            ))

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
