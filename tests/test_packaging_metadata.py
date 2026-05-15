from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_dependency_ranges_are_explicit():
    """Keep install-time dependency drift from surprising desktop users."""

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["version"] == "0.0.10"
    assert project["dependencies"] == [
        "numpy>=1.26,<2",
        "pandas>=2.1,<3",
        "matplotlib>=3.8,<3.9",
        "networkx>=3,<3.4",
    ]
