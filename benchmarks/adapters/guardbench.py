"""GuardBench adapter — guardrail evaluation using toxic-chat + jailbreak benchmarks.

Original AmenRa/GuardBench is unavailable on HuggingFace, so we combine
lmsys/toxic-chat (real user-chatbot conversations with toxicity labels) and
JailbreakBench/JBB-Behaviors (harmful + benign prompt pairs) as a robust
substitute for guardrail evaluation.
"""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class GuardBenchAdapter(DatasetAdapter):
    name = "guardbench"
    description = "Guardrail evaluation: toxic-chat + JailbreakBench (EMNLP 2024 inspired)"
    source = "lmsys/toxic-chat"
    target_modules = ["shield", "ml_shield", "toxicity"]
    default_sample_size = 1000

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []

        # Source 1: lmsys/toxic-chat — real user-chatbot conversations
        # Fields: user_input, model_output, toxicity (0/1), jailbreaking (0/1)
        try:
            for split in ["test", "train"]:
                ds = load_dataset("lmsys/toxic-chat", "toxicchat0124",
                                  split=split, streaming=True)
                for i, row in enumerate(ds):
                    if i >= 10000:
                        break
                    text = row.get("user_input", "")
                    if not text:
                        continue
                    toxicity = row.get("toxicity", 0)
                    jailbreaking = row.get("jailbreaking", 0)
                    is_unsafe = toxicity == 1 or jailbreaking == 1
                    samples.append(NormalizedSample(
                        text=text,
                        label="positive" if is_unsafe else "negative",
                        category="toxic" if toxicity else ("jailbreak" if jailbreaking else "safe"),
                        metadata={"source": "toxic-chat", "split": split,
                                  "toxicity": toxicity, "jailbreaking": jailbreaking},
                    ))
        except Exception:
            pass

        # Source 2: JailbreakBench/JBB-Behaviors — curated harmful + benign pairs
        # Fields: Index, Goal, Target, Behavior, Category, Source
        try:
            for split, label in [("harmful", "positive"), ("benign", "negative")]:
                ds = load_dataset("JailbreakBench/JBB-Behaviors", "behaviors",
                                  split=split, streaming=True)
                for i, row in enumerate(ds):
                    if i >= 500:
                        break
                    text = row.get("Goal", "")
                    if not text:
                        continue
                    category = row.get("Category", row.get("Behavior", "unknown"))
                    samples.append(NormalizedSample(
                        text=text,
                        label=label,
                        category=str(category),
                        metadata={"source": "jailbreakbench", "split": split,
                                  "behavior": row.get("Behavior", "")},
                    ))
        except Exception:
            pass

        if not samples:
            raise RuntimeError(
                "Could not load guardrail evaluation data. "
                "Install datasets (`pip install datasets`) and check network access."
            )

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
