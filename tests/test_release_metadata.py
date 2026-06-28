import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _quoted_assignment(path: str, name: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(rf'^{name}\s*=\s*"([^"]+)"$', text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_release_version_metadata_is_consistent():
    project_version = _quoted_assignment("pyproject.toml", "version")
    package_version = _quoted_assignment("agentarmor/__init__.py", "__version__")
    docs_release = _quoted_assignment("docs/conf.py", "release")
    uv_lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    uv_lock_match = re.search(
        r'\[\[package\]\]\s+name = "agentarmor"\s+version = "([^"]+)"',
        uv_lock,
        flags=re.MULTILINE,
    )

    assert uv_lock_match is not None
    assert package_version == project_version
    assert docs_release == project_version
    assert uv_lock_match.group(1) == project_version


def test_changelog_contains_current_release():
    project_version = _quoted_assignment("pyproject.toml", "version")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## [{project_version}]" in changelog


def test_citation_metadata_matches_current_release():
    project_version = _quoted_assignment("pyproject.toml", "version")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog_match = re.search(
        rf"^## \[{re.escape(project_version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})",
        changelog,
        flags=re.MULTILINE,
    )
    assert changelog_match is not None

    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))

    assert citation["version"] == project_version
    assert citation["date-released"] == changelog_match.group(1)
