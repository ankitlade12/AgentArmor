# Contributing to AgentArmor

First off, thank you for considering contributing to AgentArmor! It's people like you that make AgentArmor such a powerful and secure tool for the community.

## Code of Conduct

This project and everyone participating in it is governed by the [AgentArmor Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

* **Reporting Bugs**: Open an issue using the Bug Report template.
* **Suggesting Enhancements**: Open an issue using the Feature Request template.
* **Pull Requests**: Pull Requests are actively welcomed and reviewed!
* **Breaking a detector**: see the next section — bypasses are contributions here.

## Found a Detector Bypass? That's a Contribution

The heuristic detectors (prompt injection, toxicity, unicode, exfiltration, and friends) are pattern-based and bypassable by design — and every working bypass you find makes the eval suite stronger. We treat confirmed bypasses as first-class contributions:

1. **Reproduce it**: run `agentarmor.demo_attacks()` or the prompt fuzzer (`tools/prompt_fuzzer.py`) to see the current detection surface, then craft the input that should be caught but isn't.
2. **Contribute it**: open an issue with the payload and which shield missed it — or better, submit it as a failing/`xfail` test case so it becomes a permanent regression target.
3. **Get credited**: confirmed bypasses are credited in the CHANGELOG.

Detector bypasses are expected, documented behavior — no responsible-disclosure formality needed. See [SECURITY.md](SECURITY.md) for what *does* qualify as a security vulnerability (a deterministic control failing to enforce: a budget breaker not tripping, a tool allowlist not blocking, redaction not redacting).

## Branching Strategy

To keep the repository clean and manageable, please follow these branch naming conventions:

- `feature/feature-name` - For new features
- `fix/bug-name` - For bug fixes
- `docs/update-name` - For documentation changes
- `test/test-name` - For missing tests
- `chore/task-name` - For maintenance tasks

## Pull Request Process

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite passes (`pytest tests/`).
4. Update the `README.md` if your changes affect the API or user instructions.
5. **If your changes affect the public API, add new modules, or change existing behavior, please update the Sphinx documentation in `docs/`.** This includes updating the relevant `.rst` guide pages and ensuring your docstrings are complete so `autodoc` picks them up. You can build the docs locally with:
   ```bash
   pip install -e ".[docs]"
   cd docs && make html
   ```
6. Create a Pull Request using the provided template.

## Local Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/AgentArmor.git
   cd AgentArmor
   ```

2. Create a virtual environment (**Python 3.10+ required**):
   ```bash
   python3.10 -m venv .venv   # or python3.11, python3.12, etc.
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. Install the package in editable mode with all test dependencies:
   ```bash
   pip install -e ".[all,test]"
   ```
   This installs the SDK providers (openai, anthropic, google-genai),
   ML dependencies (scikit-learn), and the test runner (pytest, pytest-asyncio).

4. Run the tests:
   ```bash
   pytest tests/
   ```

## Adding New Safety Modules
If you have an idea for a new module (e.g., prompt injection detection via LLM-as-a-judge or PII redaction via Presidio), we highly encourage it — though right now, hardening and testing the existing controls is even more valuable than adding new ones.
1. Create a new file in `agentarmor/modules/new_shield.py`.
2. Implement your logic as a Module class with an `__init__()`, `scan()` or `pre_check()`, and `report()` method.
3. Hook it into the monkey-patch pipeline in `agentarmor/core.py`.
4. Include robust deterministic test cases.

Thank you again for your time and contribution!
