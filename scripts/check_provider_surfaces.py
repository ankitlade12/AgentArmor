"""Check provider SDK surfaces that AgentArmor patches.

This is a lightweight compatibility drift check. It does not make network
calls; it imports installed SDKs, creates clients with dummy keys where needed,
and verifies the method paths listed in SUPPORT_MATRIX.md still exist.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Surface:
    package: str
    label: str
    path: tuple[str, ...]
    client_factory: str


SURFACES = [
    Surface("openai", "OpenAI chat.completions.create", ("chat", "completions", "create"), "openai"),
    Surface("openai", "OpenAI responses.create", ("responses", "create"), "openai"),
    Surface("anthropic", "Anthropic messages.create", ("messages", "create"), "anthropic"),
    Surface("google.genai", "Google Gemini models.generate_content", ("models", "generate_content"), "google"),
    Surface("google.genai", "Google Gemini models.generate_content_stream", ("models", "generate_content_stream"), "google"),
]


def _getattr_path(obj: Any, path: tuple[str, ...]) -> Any:
    current = obj
    for part in path:
        current = getattr(current, part)
    return current


def _client(surface: Surface) -> Any:
    module = importlib.import_module(surface.package)
    if surface.client_factory == "openai":
        return module.OpenAI(api_key="sk-test")
    if surface.client_factory == "anthropic":
        return module.Anthropic(api_key="sk-ant-test")
    if surface.client_factory == "google":
        return module.Client(api_key="test")
    raise AssertionError(f"unknown client factory: {surface.client_factory}")


def main() -> int:
    failures: list[str] = []
    skipped: list[str] = []

    for surface in SURFACES:
        try:
            client = _client(surface)
            target = _getattr_path(client, surface.path)
        except ModuleNotFoundError:
            skipped.append(f"skip {surface.label}: {surface.package} not installed")
            continue
        except Exception as exc:
            failures.append(f"fail {surface.label}: {exc}")
            continue
        if not callable(target):
            failures.append(f"fail {surface.label}: target exists but is not callable")

    for line in skipped:
        print(line)
    for line in failures:
        print(line, file=sys.stderr)

    if failures:
        return 1
    print("provider surfaces OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

