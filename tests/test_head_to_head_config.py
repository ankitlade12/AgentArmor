"""Tests for benchmarks/config.py (SPEC v4 D34, D51)."""

from pathlib import Path

import pytest
import yaml

from benchmarks.config import (
    CONFIG_PATH,
    ConfigSecretLeakError,
    MissingKeysError,
    _scan_for_secret_fields,
    check_required_keys,
    load_config,
    required_env_vars,
)


class TestSecretScan:
    def test_flags_api_key_field(self):
        offenders = _scan_for_secret_fields({"openai": {"OPENAI_API_KEY": "sk-xxx"}})
        assert offenders == ["openai.OPENAI_API_KEY"]

    def test_flags_token_field(self):
        offenders = _scan_for_secret_fields({"auth": {"github_token": "ghp-xxx"}})
        assert offenders == ["auth.github_token"]

    def test_flags_secret_field(self):
        offenders = _scan_for_secret_fields({"client_secret": "x"})
        assert offenders == ["client_secret"]

    def test_ignores_requires_api_key_env_reference(self):
        """`requires_api_key_env: OPENAI_API_KEY` names the env var — not a secret itself."""
        data = {"baselines": {"m": {"requires_api_key_env": "OPENAI_API_KEY"}}}
        assert _scan_for_secret_fields(data) == []

    def test_ignores_normal_fields(self):
        assert _scan_for_secret_fields({"model": "foo", "threshold": 0.5}) == []

    def test_recurses_through_lists(self):
        data = {"list": [{"api_key": "leak"}]}
        offenders = _scan_for_secret_fields(data)
        assert "list[0].api_key" in offenders


class TestLoadConfig:
    def test_loads_committed_config_cleanly(self):
        cfg = load_config()
        assert "baselines" in cfg
        assert "llamaguard" in cfg["baselines"]

    def test_rejects_secret_bearing_config(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            yaml.safe_dump(
                {"baselines": {"m": {"OPENAI_API_KEY": "sk-leak"}}}
            )
        )
        with pytest.raises(ConfigSecretLeakError) as exc:
            load_config(bad)
        assert "OPENAI_API_KEY" in str(exc.value)
        assert "env var" in str(exc.value).lower()


class TestRequiredEnvVars:
    def test_returns_gated_baselines_only(self):
        cfg = {
            "baselines": {
                "llamaguard": {"description": "local, no key"},
                "openai_moderation": {"requires_api_key_env": "OPENAI_API_KEY"},
                "perspective": {"requires_api_key_env": "PERSPECTIVE_API_KEY"},
            }
        }
        pairs = dict(required_env_vars(cfg))
        assert pairs == {
            "OPENAI_API_KEY": "openai_moderation",
            "PERSPECTIVE_API_KEY": "perspective",
        }

    def test_empty_config_returns_empty(self):
        assert required_env_vars({}) == []


class TestCheckRequiredKeys:
    def test_missing_key_raises_with_actionable_message(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PERSPECTIVE_API_KEY", raising=False)
        cfg = {
            "baselines": {
                "openai_moderation": {"requires_api_key_env": "OPENAI_API_KEY"},
                "perspective": {"requires_api_key_env": "PERSPECTIVE_API_KEY"},
            }
        }
        with pytest.raises(MissingKeysError) as exc:
            check_required_keys(cfg)
        msg = str(exc.value)
        assert "OPENAI_API_KEY" in msg
        assert "PERSPECTIVE_API_KEY" in msg
        assert "openai_moderation" in msg
        assert "perspective" in msg
        assert "RUNBOOK" in msg

    def test_no_gated_baselines_passes(self):
        cfg = {"baselines": {"llamaguard": {"description": "local"}}}
        check_required_keys(cfg)  # no raise

    def test_all_keys_present_passes(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cfg = {"baselines": {"openai_moderation": {"requires_api_key_env": "OPENAI_API_KEY"}}}
        check_required_keys(cfg)  # no raise


def test_committed_config_has_no_secrets():
    """Regression gate: the checked-in config.yaml is clean of secret-looking keys."""
    load_config(CONFIG_PATH)
