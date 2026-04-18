"""Config loader for benchmarks/config.yaml (SPEC v4 D34, D51).

Validates the loaded dict against a secret allow-list: any key matching
``*_API_KEY`` / ``*_TOKEN`` / ``*_SECRET`` is rejected. Keys must live in
environment variables. Also provides a startup key check that fails loudly
with a structured list of missing env vars + gated baselines.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

_SECRET_PATTERN = re.compile(r"(?:^|_)(API_KEY|TOKEN|SECRET)$", re.IGNORECASE)


class ConfigSecretLeakError(ValueError):
    """Raised when config.yaml contains a field that looks like a secret."""


class MissingKeysError(RuntimeError):
    """Raised at startup when required API keys are absent from the environment."""


def _scan_for_secret_fields(data: Any, path: str = "") -> List[str]:
    """Walk a config tree; return dotted paths of any secret-looking keys."""
    offenders: List[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            full = f"{path}.{k}" if path else str(k)
            if isinstance(k, str) and _SECRET_PATTERN.search(k):
                offenders.append(full)
            offenders.extend(_scan_for_secret_fields(v, full))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            offenders.extend(_scan_for_secret_fields(v, f"{path}[{i}]"))
    return offenders


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate benchmarks/config.yaml.

    Raises ``ConfigSecretLeakError`` if any key matches the secret pattern.
    """
    cfg_path = path or CONFIG_PATH
    with open(cfg_path) as f:
        data = yaml.safe_load(f) or {}
    offenders = _scan_for_secret_fields(data)
    if offenders:
        raise ConfigSecretLeakError(
            f"config.yaml contains secret-looking fields: {offenders}. "
            f"Secrets must live in environment variables only, not in config. "
            f"Remove them from the file; set as env vars per RUNBOOK #0."
        )
    return data


def required_env_vars(config: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return ``(env_var, baseline_name)`` pairs for every baseline that needs a key."""
    pairs: List[Tuple[str, str]] = []
    for name, entry in (config.get("baselines") or {}).items():
        env = (entry or {}).get("requires_api_key_env")
        if env:
            pairs.append((env, name))
    return pairs


def check_required_keys(config: Dict[str, Any]) -> None:
    """Raise ``MissingKeysError`` listing every missing env var + gated baseline."""
    pairs = required_env_vars(config)
    missing = [(env, b) for env, b in pairs if not os.environ.get(env)]
    if missing:
        lines = [f"  {env} (gates {b})" for env, b in missing]
        raise MissingKeysError(
            "Missing required environment variables:\n"
            + "\n".join(lines)
            + "\n\nSet them before running the head-to-head bench. See RUNBOOK #0."
        )
