"""
Cost Attribution Tags — tag API calls with custom labels and get
per-tag cost breakdowns for multi-tenant or multi-feature applications.
"""

import contextvars
import threading
from typing import Dict, Optional

from ..hooks import ResponseContext


# Context variable holding the current tag (set via agentarmor.tag())
_current_tag: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_agentarmor_cost_tag", default=None
)


def set_tag(label: str) -> None:
    """Sets the cost attribution tag for subsequent API calls in this context.

    Uses a ContextVar which is safe for asyncio (each task has its own tag).
    Note: ContextVar does NOT propagate across OS threads — if you call set_tag()
    in the main thread, worker threads will NOT inherit it. Each thread must set
    its own tag independently.
    """
    _current_tag.set(label)


def clear_tag() -> None:
    """Clears the current cost attribution tag."""
    _current_tag.set(None)


def get_tag() -> Optional[str]:
    """Returns the current cost attribution tag."""
    return _current_tag.get()


class CostTagsModule:
    """Post-response hook that attributes call costs to the current tag."""

    def __init__(self, default_tag: str = "untagged"):
        self.default_tag = default_tag
        self._by_tag: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.total_tagged = 0

    def post_record(self, ctx: ResponseContext) -> ResponseContext:
        """After-response hook that records cost under the active tag."""
        tag = _current_tag.get() or self.default_tag
        cost = ctx.cost or 0.0

        with self._lock:
            if tag not in self._by_tag:
                self._by_tag[tag] = {"calls": 0, "spent": 0.0, "models": []}

            entry = self._by_tag[tag]
            entry["calls"] += 1
            entry["spent"] += cost
            if ctx.model not in entry["models"]:
                entry["models"].append(ctx.model)

            self.total_tagged += 1

        return ctx

    def get_by_tag(self, tag: str) -> Optional[Dict]:
        """Returns cost data for a specific tag."""
        with self._lock:
            entry = self._by_tag.get(tag)
            if entry:
                return {
                    "calls": entry["calls"],
                    "spent": f"${entry['spent']:.4f}",
                    "models": list(entry["models"]),
                }
        return None

    def report(self) -> dict:
        with self._lock:
            by_tag_formatted = {
                tag: {
                    "calls": data["calls"],
                    "spent": f"${data['spent']:.4f}",
                    "models": list(data["models"]),
                }
                for tag, data in self._by_tag.items()
            }

        return {
            "total_tagged": self.total_tagged,
            "by_tag": by_tag_formatted,
        }
