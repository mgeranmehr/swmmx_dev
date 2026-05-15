"""Schema loading for the parameter-facing public API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = ("main_category", "sub_category", "source", "type", "size")


def _canonicalize_column_name(name: str) -> str:
    """Normalize human-facing CSV headers into stable internal names."""

    # The user's supplied schema is intentionally readable to people, so accept
    # common spacing/punctuation variants rather than making the CSV bend around
    # Python identifiers.
    simplified = (
        name.strip()
        .lower()
        .replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
    )
    simplified = " ".join(simplified.split())

    aliases = {
        "main category": "main_category",
        "subcategory parameter group": "sub_category",
        "sub category": "sub_category",
        "subcategory": "sub_category",
        "source": "source",
        "type": "type",
        "size structure": "size",
        "size": "size",
    }
    return aliases.get(simplified, name)


@dataclass(frozen=True)
class SchemaRegistry:
    """A thin, immutable wrapper around the loaded parameter registry table."""

    frame: pd.DataFrame
    details: pd.DataFrame
    path: Path | None = None
    details_path: Path | None = None

    @classmethod
    def load(cls, explicit_path: str | Path | None = None) -> "SchemaRegistry":
        """Load the first available ``parameters.csv`` candidate.

        The search order favors deliberate configuration first and convenient
        development defaults second.  Every candidate is checked before the
        CSV is read so a missing optional schema never blocks basic package use.
        """

        # Build the ordered list of possible schema locations.
        package_root = Path(__file__).resolve().parent
        candidates: list[Path] = []
        if explicit_path is not None:
            candidates.append(Path(explicit_path).expanduser())

        # Allow callers and CI jobs to point at a schema without changing code.
        env_path = os.environ.get("SWMMX_SCHEMA_PATH")
        if env_path:
            candidates.append(Path(env_path).expanduser())

        # Prefer the distributable package location, then a convenient dev root.
        candidates.append(package_root / "schemas" / "parameters.csv")
        candidates.append(Path.cwd() / "parameters.csv")

        # Return the first valid table we can find.
        for candidate in candidates:
            if candidate.exists():
                frame = pd.read_csv(candidate)
                frame = frame.rename(columns={column: _canonicalize_column_name(column) for column in frame.columns})
                cls._validate_columns(frame, candidate)
                details, details_path = cls._load_details(candidate)
                return cls(
                    frame=frame.copy(),
                    details=details,
                    path=candidate.resolve(),
                    details_path=details_path,
                )

        # A well-formed empty frame keeps downstream code simple and explicit.
        return cls(frame=pd.DataFrame(columns=list(REQUIRED_COLUMNS)), details=pd.DataFrame(), path=None)

    @staticmethod
    def _load_details(schema_path: Path) -> tuple[pd.DataFrame, Path | None]:
        """Load the optional companion ``all.csv`` table when it is available."""

        # Prefer a companion file beside the chosen schema, then the packaged
        # default, then the developer-friendly current working directory.
        package_root = Path(__file__).resolve().parent
        candidates = (
            schema_path.with_name("all.csv"),
            package_root / "schemas" / "all.csv",
            Path.cwd() / "all.csv",
        )
        for candidate in candidates:
            if candidate.exists():
                return pd.read_csv(candidate).copy(), candidate.resolve()
        return pd.DataFrame(), None

    @staticmethod
    def _validate_columns(frame: pd.DataFrame, path: Path) -> None:
        """Ensure the schema contains the contractually required columns."""

        # Normalize through a set so column order remains flexible for the user.
        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Schema file '{path}' is missing required columns: {joined}")

    @property
    def is_loaded(self) -> bool:
        """Return whether a non-empty schema file was discovered."""

        return self.path is not None and not self.frame.empty

    @property
    def main_categories(self) -> tuple[str, ...]:
        """Return distinct top-level category names in deterministic order."""

        # ``dropna`` prevents accidental ``nan`` API names from malformed rows.
        values: Iterable[str] = self.frame["main_category"].dropna().astype(str)
        return tuple(dict.fromkeys(values))

    def describe(self, main_category: str | None = None) -> pd.DataFrame:
        """Return the full schema or the rows for one main category."""

        # Copy before returning so callers can inspect freely without mutating
        # the registry shared by a model clone.
        if main_category is None:
            return self.frame.copy()
        mask = self.frame["main_category"].astype(str) == str(main_category)
        return self.frame.loc[mask].copy()
