"""GuardBench adapter — meta-benchmark with 40 guardrail evaluation datasets."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class GuardBenchAdapter(DatasetAdapter):
    name = "guardbench"
    description = "GuardBench: 40 datasets for unified guardrail evaluation (EMNLP 2024)"
    source = "AmenRa/GuardBench"
    target_modules = ["shield", "ml_shield", "toxicity"]
    default_sample_size = 1000

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []

        # GuardBench has multiple configs/subsets
        # Try loading the main evaluation split
        try:
            ds = load_dataset(self.source, split="test", streaming=True, trust_remote_code=True)
            for i, row in enumerate(ds):
                if i >= 20000:  # Cap scanning
                    break
                text = row.get("prompt", row.get("text", row.get("input", "")))
                label_raw = row.get("label", row.get("is_safe", row.get("safe", "")))
                subset = row.get("subset", row.get("dataset", "unknown"))

                if not text:
                    continue

                # Normalize label: unsafe = positive (threat), safe = negative
                label_str = str(label_raw).lower()
                if label_str in ("unsafe", "1", "true", "harmful", "toxic", "positive"):
                    label = "positive"
                elif label_str in ("safe", "0", "false", "benign", "clean", "negative"):
                    label = "negative"
                else:
                    # Try numeric
                    try:
                        label = "positive" if float(label_raw) >= 0.5 else "negative"
                    except (ValueError, TypeError):
                        continue

                samples.append(NormalizedSample(
                    text=text,
                    label=label,
                    category=str(subset),
                    metadata={"source": "guardbench", "subset": str(subset)},
                ))
        except Exception as e:
            # Try loading individual configs
            for config in ["aegis", "beavertails", "catqa", "do_anything_now",
                          "do_not_answer", "harmful_qa", "hex_phi", "or_bench",
                          "safety_bench", "simple_safety", "sorry_bench",
                          "toxic_chat", "xstest"]:
                try:
                    ds = load_dataset(self.source, config, split="test",
                                    streaming=True, trust_remote_code=True)
                    for i, row in enumerate(ds):
                        if i >= 2000:
                            break
                        text = row.get("prompt", row.get("text", ""))
                        label_raw = row.get("label", "")
                        if text:
                            label_str = str(label_raw).lower()
                            label = "positive" if label_str in ("unsafe", "1", "harmful") else "negative"
                            samples.append(NormalizedSample(
                                text=text, label=label, category=config,
                                metadata={"source": "guardbench", "subset": config},
                            ))
                except Exception:
                    continue

        if not samples:
            raise RuntimeError(f"Could not load GuardBench. Check dataset availability.")

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
