"""GuardBench adapter — ToxicChat guardrail evaluation dataset.

Uses lmsys/toxic-chat (toxicchat0124 config) which contains real user-chatbot
conversations with toxicity and jailbreaking labels. This is part of the
GuardBench evaluation suite.
"""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class GuardBenchAdapter(DatasetAdapter):
    name = "guardbench"
    description = "ToxicChat: Real user-chatbot conversations with toxicity labels (from GuardBench suite)"
    source = "lmsys/toxic-chat"
    target_modules = ["shield", "ml_shield", "toxicity"]
    default_sample_size = 1000

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []

        # lmsys/toxic-chat (toxicchat0124) — real user-chatbot conversations
        # Fields: user_input (text), toxicity (0/1), jailbreaking (0/1)
        for split in ["test", "train"]:
            try:
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

                    if toxicity == 1:
                        category = "toxic"
                    elif jailbreaking == 1:
                        category = "jailbreak"
                    else:
                        category = "safe"

                    samples.append(NormalizedSample(
                        text=text,
                        label="positive" if is_unsafe else "negative",
                        category=category,
                        metadata={
                            "source": "toxic-chat",
                            "split": split,
                            "toxicity": toxicity,
                            "jailbreaking": jailbreaking,
                        },
                    ))
            except Exception:
                pass

        if not samples:
            raise RuntimeError(
                "Could not load ToxicChat data from lmsys/toxic-chat. "
                "Install datasets (`pip install datasets`) and check network access."
            )

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
