from abc import ABC, abstractmethod
from typing import List, Optional

_BASELINES = {}


def register_baseline(cls):
    _BASELINES[cls.name] = cls
    return cls


def get_baseline(name: str) -> "BaselineChecker":
    if name not in _BASELINES:
        raise ValueError(
            f"Unknown baseline: {name}. Available: {list(_BASELINES.keys())}"
        )
    return _BASELINES[name]()


def list_baselines() -> List[str]:
    return list(_BASELINES.keys())


class BaselineChecker(ABC):
    name: str = ""
    description: str = ""
    requires_api_key: Optional[str] = None  # env var name

    @abstractmethod
    def check(self, text: str) -> bool:
        """Returns True if the text is flagged as unsafe/toxic."""
        pass

    def is_available(self) -> bool:
        """Check if required API keys/deps are available."""
        if self.requires_api_key:
            import os

            return bool(os.environ.get(self.requires_api_key))
        return True
