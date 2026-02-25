# Contributing to AgentArmor

First off, thank you for considering contributing to AgentArmor! It's people like you that make AgentArmor such a powerful and secure tool for the community.

## Code of Conduct

This project and everyone participating in it is governed by the [AgentArmor Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

* **Reporting Bugs**: Open an issue using the Bug Report template.
* **Suggesting Enhancements**: Open an issue using the Feature Request template.
* **Pull Requests**: Pull Requests are actively welcomed and reviewed!

## Branching Strategy

To keep the repository clean and manageable, please follow these branch naming conventions:

- `feat/feature-name` - For new features
- `fix/bug-name` - For bug fixes
- `docs/update-name` - For documentation changes
- `test/test-name` - For missing tests
- `chore/task-name` - For maintenance tasks

## Pull Request Process

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite passes (`pytest tests/`).
4. Update the `README.md` if your changes affect the API or user instructions.
5. Create a Pull Request using the provided template.

## Local Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/AgentArmor.git
   cd AgentArmor
   ```

2. Create a virtual environment and load it:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package in editable mode with development dependencies:
   ```bash
   pip install -e .
   pip install pytest pytest-cov mock
   ```

4. Run the tests:
   ```bash
   pytest tests/
   ```

## Adding New Safety Modules
If you have an idea for a 5th shield (e.g., prompt injection detection via LLM-as-a-judge or PII redaction via Presidio), we highly encourage it! 
1. Create a new file in `agentarmor/modules/new_shield.py`.
2. Implement your logic as a Module class with an `__init__()`, `scan()` or `pre_check()`, and `report()` method.
3. Hook it into the monkey-patch pipeline in `agentarmor/core.py`.
4. Include robust deterministic test cases.

Thank you again for your time and contribution!
