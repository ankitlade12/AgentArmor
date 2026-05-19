import re
from pathlib import Path


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

    assert package_version == project_version
    assert docs_release == project_version


def test_changelog_contains_current_release():
    project_version = _quoted_assignment("pyproject.toml", "version")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## [{project_version}]" in changelog
