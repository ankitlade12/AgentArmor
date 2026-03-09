import os
import json
import tempfile
import pytest

from agentarmor.config import load_config, _parse_yaml


# --- YAML Parsing Tests ---

def test_parse_yaml_basic():
    text = '''
budget: "$5.00"
shield: true
record: false
'''
    config = _parse_yaml(text)
    assert config["budget"] == "$5.00"
    assert config["shield"] is True
    assert config["record"] is False


def test_parse_yaml_with_list():
    text = '''
filter: [pii, secrets]
shield: true
'''
    config = _parse_yaml(text)
    assert config["filter"] == ["pii", "secrets"]
    assert config["shield"] is True


def test_parse_yaml_with_dash_list():
    """Dash-style lists are standard YAML and must parse correctly."""
    text = '''
filter:
  - pii
  - secrets
shield: true
'''
    config = _parse_yaml(text)
    assert config["filter"] == ["pii", "secrets"]
    assert config["shield"] is True


def test_parse_yaml_dash_list_with_quotes():
    text = '''
filter:
  - "pii"
  - 'secrets'
'''
    config = _parse_yaml(text)
    assert config["filter"] == ["pii", "secrets"]


def test_parse_yaml_with_comments():
    text = '''
# Main config
budget: "$10.00"  # Budget limit
shield: true
# record: false
'''
    config = _parse_yaml(text)
    assert config["budget"] == "$10.00"
    assert config["shield"] is True
    assert "record" not in config


def test_parse_yaml_rate_limit():
    text = '''
budget: "$5.00"
rate_limit: "10/min"
'''
    config = _parse_yaml(text)
    assert config["budget"] == "$5.00"
    assert config["rate_limit"] == "10/min"


# --- load_config Tests ---

def test_load_yaml_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write('budget: "$5.00"\nshield: true\nfilter: [pii, secrets]\nrecord: true\n')
        f.flush()
        config = load_config(f.name)

    os.unlink(f.name)

    assert config["budget"] == "$5.00"
    assert config["shield"] is True
    assert config["filter"] == ["pii", "secrets"]
    assert config["record"] is True


def test_load_json_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"budget": "$3.00", "shield": False, "filter": ["pii"]}, f)
        f.flush()
        config = load_config(f.name)

    os.unlink(f.name)

    assert config["budget"] == "$3.00"
    assert config["shield"] is False
    assert config["filter"] == ["pii"]


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/.agentarmor.yml")


def test_load_config_auto_discovery():
    """Test that auto-discovery finds config in CWD."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, ".agentarmor.yml")
        with open(config_path, "w") as f:
            f.write('budget: "$1.00"\nshield: true\n')

        # Temporarily change CWD
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            config = load_config()
            assert config["budget"] == "$1.00"
            assert config["shield"] is True
        finally:
            os.chdir(original_cwd)


def test_load_config_unsupported_format():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write("[section]\nkey=value\n")
        f.flush()

    try:
        with pytest.raises(ValueError, match="Unsupported config format"):
            load_config(f.name)
    finally:
        os.unlink(f.name)
