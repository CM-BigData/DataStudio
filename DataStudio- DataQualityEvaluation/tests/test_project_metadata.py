import tomllib
from pathlib import Path


def test_pyproject_declares_test_extra() -> None:
    """Verify that test dependencies are installable through the test extra."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"

    with pyproject_path.open("rb") as file:
        pyproject = tomllib.load(file)

    optional_dependencies = pyproject["project"]["optional-dependencies"]
    assert optional_dependencies["test"] == ["pytest>=8.0.0"]
