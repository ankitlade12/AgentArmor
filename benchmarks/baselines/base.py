"""BaselineChecker ABC with score()/check() contract (SPEC v4 D1, D53)."""

import warnings
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
    """ABC for baseline safety/toxicity classifiers.

    Subclasses implement ``score(text) -> float`` (in [0.0, 1.0], higher = more unsafe).
    ``check(text) -> bool`` is a default thresholded view; subclasses may override.

    Legacy subclasses that implement only ``check()`` receive a deprecation warning
    and an auto-bridge ``score()`` returning 0.0/1.0.
    """

    name: str = ""
    description: str = ""
    requires_api_key: Optional[str] = None
    default_threshold: float = 0.5
    score_emitting: bool = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own_score = "score" in cls.__dict__
        own_check = "check" in cls.__dict__
        if own_check and not own_score:
            warnings.warn(
                f"{cls.__name__} implements check() without score(); "
                f"installing bridge score() = 1.0 if check() else 0.0. "
                f"Implement score() explicitly; bridge will be removed in v2.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            cls._legacy_check = cls.check

            def _bridge_score(self, text: str) -> float:
                return 1.0 if self._legacy_check(text) else 0.0

            cls.score = _bridge_score
            cls.score_emitting = False

    @abstractmethod
    def score(self, text: str) -> float:
        """Returns a score in [0.0, 1.0]. Higher = more likely unsafe/toxic."""
        ...

    def check(self, text: str) -> bool:
        """Returns True if text is flagged. Default: score(text) >= default_threshold."""
        return self.score(text) >= self.default_threshold

    def is_available(self) -> bool:
        if self.requires_api_key:
            import os
            return bool(os.environ.get(self.requires_api_key))
        return True
