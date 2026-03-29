import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NormalizedSample:
    """Universal sample format for all industry benchmarks."""
    text: str                          # Primary input text
    label: str                         # "positive" (threat) or "negative" (safe)
    category: str = "unknown"          # Sub-category for breakdown
    source_context: str = ""           # For grounding: the reference document
    code: str = ""                     # For code benchmarks
    language: str = ""                 # For code benchmarks
    metadata: Dict = field(default_factory=dict)  # Original fields preserved


class DatasetAdapter(ABC):
    """Base class for normalizing industry datasets."""

    name: str = ""
    description: str = ""
    source: str = ""                   # HuggingFace ID or URL
    target_modules: List[str] = []     # Which AgentArmor modules this tests
    default_sample_size: int = 500

    @abstractmethod
    def load(self, sample_size: Optional[int] = None, seed: int = 42) -> List[NormalizedSample]:
        """Load and normalize the dataset. Returns list of NormalizedSample."""
        pass

    def _stratified_sample(self, samples: List[NormalizedSample],
                           sample_size: int, seed: int = 42) -> List[NormalizedSample]:
        """Stratified sampling maintaining label balance."""
        if len(samples) <= sample_size:
            return samples

        rng = random.Random(seed)
        positives = [s for s in samples if s.label == "positive"]
        negatives = [s for s in samples if s.label == "negative"]

        # Maintain ratio or balance 50/50 if one side dominates
        total = sample_size
        pos_ratio = len(positives) / len(samples) if samples else 0.5
        n_pos = max(1, min(len(positives), int(total * pos_ratio)))
        n_neg = min(len(negatives), total - n_pos)
        # Adjust if we don't have enough negatives
        if n_neg < total - n_pos:
            n_pos = total - n_neg

        rng.shuffle(positives)
        rng.shuffle(negatives)
        return positives[:n_pos] + negatives[:n_neg]


# Adapter registry
_ADAPTERS = {}

def register_adapter(cls):
    """Decorator to register an adapter."""
    _ADAPTERS[cls.name] = cls
    return cls

def get_adapter(name: str) -> DatasetAdapter:
    """Get an adapter instance by name."""
    if name not in _ADAPTERS:
        raise ValueError(f"Unknown adapter: {name}. Available: {list(_ADAPTERS.keys())}")
    return _ADAPTERS[name]()

def list_adapters() -> List[str]:
    """List all registered adapter names."""
    return list(_ADAPTERS.keys())
