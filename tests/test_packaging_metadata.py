from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_package_installation_is_dependency_free():
    """Keep package installation dependency-free by design."""

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert "dependencies" not in project
