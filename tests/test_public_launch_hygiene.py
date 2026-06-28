import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _github_anchor_ids(relative_path: str) -> set[str]:
    text = _read(relative_path)
    anchors = set()
    seen: dict[str, int] = {}
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE):
        slug = match.group(1).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", slug)
        slug = slug.replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


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


def test_recorder_docs_do_not_overclaim_auditability():
    docs = "\n".join([
        _read("README.md"),
        _read("docs/index.rst"),
        _read("docs/shields.rst"),
    ])

    assert "Total observability and auditability" not in docs
    assert "Full audit trail" not in docs
    assert "tamper-evident" in docs
    assert "unredacted" in docs


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


def test_issue_template_config_does_not_link_disabled_discussions():
    config = _read(".github/ISSUE_TEMPLATE/config.yml")

    assert "/discussions" not in config


def test_readme_and_feature_reference_local_anchors_resolve():
    anchors_by_file = {
        "README.md": _github_anchor_ids("README.md"),
        "FEATURES.md": _github_anchor_ids("FEATURES.md"),
    }
    local_link_pattern = re.compile(r"\[[^\]]+\]\((?:(README|FEATURES)\.md)?#([^)]+)\)")

    for relative_path in anchors_by_file:
        text = _read(relative_path)
        for target_file, anchor in local_link_pattern.findall(text):
            target_path = f"{target_file}.md" if target_file else relative_path
            assert anchor in anchors_by_file[target_path], (
                f"{relative_path} links to missing anchor {target_path}#{anchor}"
            )


def test_feature_docs_do_not_reintroduce_numbered_feature_headings():
    for relative_path in ("README.md", "FEATURES.md"):
        text = _read(relative_path)
        assert not re.search(r"^#{2,4}\s+\d+\.", text, flags=re.MULTILINE)
