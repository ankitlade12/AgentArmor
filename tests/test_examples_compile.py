import py_compile
from pathlib import Path


def test_examples_compile(tmp_path):
    example_dir = Path("examples")
    example_files = sorted(example_dir.glob("*.py"))

    assert example_files, "Expected at least one example script"

    for example in example_files:
        py_compile.compile(
            str(example),
            cfile=str(tmp_path / f"{example.stem}.pyc"),
            doraise=True,
        )
