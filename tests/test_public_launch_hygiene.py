import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_public_docs_do_not_contain_local_absolute_paths():
    public_docs = [
        "tasks/head-to-head-report/SPEC.md",
        "tasks/head-to-head-report/FAILURES.md",
        "tasks/head-to-head-report/TYPE_WALKTHROUGH.md",
    ]

    for relative_path in public_docs:
        text = _read(relative_path)
        assert "/Users/" not in text
        assert "/home/" not in text


def test_package_description_avoids_stale_shield_count():
    pyproject = _read("pyproject.toml")
    description_match = re.search(
        r'^description = "([^"]+)"$',
        pyproject,
        flags=re.MULTILINE,
    )

    assert description_match is not None
    description = description_match.group(1)

    assert not re.search(r"\b\d+\s+shields\b", description)


def test_public_examples_avoid_overclaiming_compatibility():
    examples_readme = _read("examples/README.md")

    assert "perfectly patches" not in examples_readme


def test_readme_gif_generator_dependency_is_declared():
    generator = _read("scripts/generate_readme_demo_gif.py")
    pyproject = _read("pyproject.toml")

    assert "from PIL import" in generator
    assert re.search(r'^docs = \[.*"Pillow>=10\.0".*\]$', pyproject, re.MULTILINE)


def test_issue_seed_script_excludes_already_shipped_launch_tasks():
    tree = ast.parse(_read("scripts/seed_github_issues.py"))
    shipped_titles = {
        "Record a 30-second README demo GIF",
        "Add framework setup matrix page",
        "Add Agno multi-tool safety demo",
        "Add LangGraph-specific example",
        "Add OpenTelemetry export example",
        "Add tool-risk presets",
    }
    titles = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "IssueSeed"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }

    assert titles.isdisjoint(shipped_titles)
