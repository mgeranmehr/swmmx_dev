"""Small shared helpers used by the runnable example scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


EXAMPLES_DIR = Path(__file__).resolve().parent


def get_example_path() -> Path:
    """Return the bundled example input path, accepting the legacy typo if needed."""

    for name in ("example.inp", "exampl.inp"):
        candidate = EXAMPLES_DIR / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Expected examples/example.inp (or legacy examples/exampl.inp).")


def get_output_dir() -> Path:
    """Return the safe output folder used by every example."""

    output_dir = EXAMPLES_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def first_id(values: Iterable[str]) -> str | None:
    """Return the first ID from an iterable, or ``None`` when it is empty."""

    return next(iter(values), None)


def first_n_ids(values: Iterable[str], count: int) -> list[str]:
    """Return up to ``count`` IDs from an iterable."""

    return list(values)[:count]


def print_header(title: str) -> None:
    """Print a compact console title for one educational example."""

    border = "=" * len(title)
    print(f"\n{title}\n{border}")


def save_working_copy(model, file_name: str) -> Path:
    """Save a disposable model copy so run artifacts stay under ``examples/output``."""

    target = get_output_dir() / file_name
    return model.save(target)

