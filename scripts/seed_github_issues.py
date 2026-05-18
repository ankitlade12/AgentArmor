"""Seed the AgentArmor GitHub issue tracker from the local issue list."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass


REPO = "ankitlade12/AgentArmor"


@dataclass(frozen=True)
class IssueSeed:
    title: str
    labels: tuple[str, ...]
    body: str


ISSUES = [
    IssueSeed(
        "Add Google ADK project-style walkthrough",
        ("area:examples", "area:docs"),
        "Expand the ADK example into a copy-paste project layout with `.env` notes and `adk web` instructions.",
    ),
    IssueSeed(
        "Publish benchmark methodology blog draft",
        ("area:docs", "area:benchmarks"),
        "Turn the benchmark methodology and failure notes into a publishable write-up.",
    ),
    IssueSeed(
        "Add MCP result-validation examples",
        ("area:security", "area:examples"),
        "Show how to validate risky MCP tool outputs before they are reused by an agent.",
    ),
    IssueSeed(
        "Add exfiltration case-study example",
        ("area:security", "area:examples"),
        "Demonstrate a blocked leak from model output to a simulated outbound sink.",
    ),
    IssueSeed(
        "Add RAG provenance example",
        ("area:security", "area:examples"),
        "Show source tagging and safer answer construction for retrieved content.",
    ),
    IssueSeed(
        "Add optional framework integration job",
        ("area:testing", "area:ecosystem"),
        "Run framework-specific smoke tests in a scheduled or allow-fail CI job.",
    ),
    IssueSeed(
        "Add provider compatibility drift checks",
        ("area:testing", "area:benchmarks"),
        "Alert when upstream SDK APIs change in ways that affect AgentArmor patching.",
    ),
    IssueSeed(
        "Submit LiteLLM docs/example PR",
        ("area:ecosystem",),
        "Contribute a short integration example or cookbook snippet upstream to LiteLLM.",
    ),
    IssueSeed(
        "Submit LlamaIndex RAG-safety PR or discussion",
        ("area:ecosystem",),
        "Share the RAG poisoning demo with LlamaIndex maintainers and gather feedback.",
    ),
    IssueSeed(
        "Submit Pydantic AI compatibility note",
        ("area:ecosystem",),
        "Document that AgentArmor can protect OpenAI Responses traffic under Pydantic AI.",
    ),
    IssueSeed(
        "Submit Google ADK runtime-safety guide",
        ("area:ecosystem",),
        "Share the ADK example as a minimal runtime-protection pattern.",
    ),
    IssueSeed(
        "Add AgentArmor to awesome-agentic-ai / security lists",
        ("area:ecosystem",),
        "Prepare short blurbs and links for curated ecosystem directories and awesome lists.",
    ),
    IssueSeed(
        "Create launch-week content tracker",
        ("area:ecosystem", "area:docs"),
        "Track blog post, launch clip, social posts, and partner outreach in one place.",
    ),
]

LABEL_COLORS = {
    "area:examples": "1d76db",
    "area:docs": "0e8a16",
    "area:security": "b60205",
    "area:testing": "5319e7",
    "area:benchmarks": "fbca04",
    "area:ecosystem": "0052cc",
    "good first issue": "7057ff",
    "help wanted": "008672",
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def ensure_label(name: str) -> None:
    result = run("gh", "label", "list", "--repo", REPO, "--limit", "200")
    existing = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    if name in existing:
        return
    run(
        "gh",
        "label",
        "create",
        name,
        "--repo",
        REPO,
        "--color",
        LABEL_COLORS[name],
    )


def issue_exists(title: str) -> bool:
    result = run(
        "gh",
        "issue",
        "list",
        "--repo",
        REPO,
        "--search",
        f'"{title}" in:title',
        "--state",
        "all",
        "--limit",
        "50",
        check=False,
    )
    return title in result.stdout


def create_issue(issue: IssueSeed) -> None:
    if issue_exists(issue.title):
        print(f"skip: {issue.title}")
        return

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as temp:
        temp.write(issue.body + "\n")
        body_path = temp.name

    args = [
        "gh",
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        issue.title,
        "--body-file",
        body_path,
    ]
    for label in issue.labels:
        args.extend(["--label", label])
    run(*args)
    print(f"created: {issue.title}")


def main() -> None:
    for label in LABEL_COLORS:
        ensure_label(label)
    for issue in ISSUES:
        create_issue(issue)


if __name__ == "__main__":
    main()
