"""
Policy-as-Code configuration loader for AgentArmor.

Supports YAML (.yml / .yaml) and JSON (.json) config files.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


# Default config filenames searched in order
_CONFIG_FILENAMES = [
    ".agentarmor.yml",
    ".agentarmor.yaml",
    ".agentarmor.json",
    "agentarmor.yml",
    "agentarmor.yaml",
    "agentarmor.json",
]


def _find_config_file(start_dir: Optional[str] = None) -> Optional[Path]:
    """
    Search for a config file starting from start_dir, walking up to the
    filesystem root, then checking the user's home directory.
    """
    search_dir = Path(start_dir) if start_dir else Path.cwd()

    # Walk upward from search_dir to root
    current = search_dir.resolve()
    while True:
        for name in _CONFIG_FILENAMES:
            candidate = current / name
            if candidate.is_file():
                return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback: check home directory
    home = Path.home()
    for name in _CONFIG_FILENAMES:
        candidate = home / name
        if candidate.is_file():
            return candidate

    return None


def _parse_yaml(text: str) -> Dict[str, Any]:
    """
    Minimal YAML parser for flat key-value configs.
    Handles strings, booleans, numbers, and inline lists.
    No external dependencies required.
    """
    result: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            continue

        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()

        # Remove inline comments
        if " #" in raw_value:
            raw_value = raw_value[: raw_value.index(" #")].strip()

        result[key] = _coerce_value(raw_value)

    return result


def _coerce_value(raw: str) -> Any:
    """Convert a raw YAML string value to an appropriate Python type."""
    if not raw:
        return None

    # Boolean
    if raw.lower() in ("true", "yes", "on"):
        return True
    if raw.lower() in ("false", "no", "off"):
        return False

    # Inline list: [pii, secrets] or ["pii", "secrets"]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        items = [_coerce_scalar(item.strip().strip("\"'")) for item in inner.split(",") if item.strip()]
        return items

    # Quoted string
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]

    return _coerce_scalar(raw)


def _coerce_scalar(raw: str) -> Any:
    """Try to convert a scalar string to int or float, else return as string."""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load an AgentArmor config file and return a dict of init() kwargs.

    Args:
        path: Explicit path to a config file. If None, auto-discovers
              by searching CWD → parent directories → home directory.

    Returns:
        Dict of kwargs suitable for passing to agentarmor.init().

    Raises:
        FileNotFoundError: If no config file is found.
        ValueError: If the config file format is unsupported.
    """
    if path:
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        config_path = _find_config_file()
        if config_path is None:
            raise FileNotFoundError(
                "No AgentArmor config file found. "
                "Create .agentarmor.yml in your project root."
            )

    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()

    if suffix == ".json":
        config = json.loads(text)
    elif suffix in (".yml", ".yaml"):
        config = _parse_yaml(text)
    else:
        raise ValueError(f"Unsupported config format: {suffix}")

    return config
