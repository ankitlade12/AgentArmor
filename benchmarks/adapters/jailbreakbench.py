"""JailbreakBench adapter — 100 misuse behaviors for jailbreak detection."""
from typing import List, Optional
from .base import DatasetAdapter, NormalizedSample, register_adapter


@register_adapter
class JailbreakBenchAdapter(DatasetAdapter):
    name = "jailbreakbench"
    description = "JailbreakBench: 100 misuse behaviors for jailbreak/injection detection"
    source = "JailbreakBench/JBB-Behaviors"
    target_modules = ["shield", "ml_shield"]
    default_sample_size = 200  # small dataset, use all

    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Install datasets: pip install datasets")

        samples = []

        # Load harmful behaviors
        try:
            ds = load_dataset(self.source, "behaviors", split="harmful")
            for row in ds:
                goal = row.get("Goal", row.get("goal", ""))
                category = row.get("Category", row.get("category", "harmful"))
                if goal:
                    samples.append(NormalizedSample(
                        text=goal,
                        label="positive",
                        category=category,
                        metadata={"source": "jailbreakbench", "type": "harmful_behavior"},
                    ))
        except Exception:
            # Fallback: try loading as a simple dataset
            ds = load_dataset(self.source, split="train")
            for row in ds:
                text = row.get("Goal", row.get("goal", row.get("text", "")))
                if text:
                    samples.append(NormalizedSample(
                        text=text,
                        label="positive",
                        category="harmful",
                        metadata={"source": "jailbreakbench"},
                    ))

        # Load benign behaviors for negatives if available
        try:
            ds_benign = load_dataset(self.source, "behaviors", split="benign")
            for row in ds_benign:
                goal = row.get("Goal", row.get("goal", ""))
                if goal:
                    samples.append(NormalizedSample(
                        text=goal,
                        label="negative",
                        category="benign",
                        metadata={"source": "jailbreakbench", "type": "benign"},
                    ))
        except Exception:
            # Add some safe prompts as negatives
            safe_prompts = [
                "What is the capital of France?",
                "Help me write a Python function to sort a list",
                "Explain how photosynthesis works",
                "What are the benefits of regular exercise?",
                "How do I make a peanut butter sandwich?",
                "Tell me about the history of the Roman Empire",
                "What is machine learning?",
                "How do I fix a leaky faucet?",
                "Explain the theory of relativity",
                "What are some good books to read?",
                "How do I start a vegetable garden?",
                "What causes the northern lights?",
                "Explain how a computer processor works",
                "What are the health benefits of green tea?",
                "How do I train for a marathon?",
                "What is the water cycle?",
                "How do I write a cover letter?",
                "What are renewable energy sources?",
                "Explain how vaccines work",
                "What is the Pythagorean theorem?",
            ]
            for p in safe_prompts:
                samples.append(NormalizedSample(
                    text=p, label="negative", category="safe",
                    metadata={"source": "synthetic"},
                ))

        size = sample_size or self.default_sample_size
        return self._stratified_sample(samples, size, seed)
