"""Runtime dependency checks for :mod:`swmmx`."""

from __future__ import annotations

from importlib.util import find_spec

from .errors import OptionalDependencyError


# Keep this list centralized so installation can remain dependency-free while
# model construction still reports a clear runtime requirement set.
RUNTIME_DEPENDENCIES = ("numpy", "pandas", "matplotlib", "networkx")


def require_runtime_dependencies() -> None:
    """Raise a helpful error when required runtime packages are unavailable."""

    missing = [name for name in RUNTIME_DEPENDENCIES if find_spec(name) is None]
    if not missing:
        return

    missing_text = ", ".join(missing)
    install_text = " ".join(RUNTIME_DEPENDENCIES)
    raise OptionalDependencyError(
        "swmmx runtime dependencies are missing: "
        f"{missing_text}. Install them before creating a model, for example: "
        f"pip install {install_text}"
    )
