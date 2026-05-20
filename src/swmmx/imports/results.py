"""Result objects returned by public import calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ImportIssue:
    """One import diagnostic message."""

    level: str
    row_number: int | None
    field: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""

        return {
            "level": self.level,
            "row_number": self.row_number,
            "field": self.field,
            "message": self.message,
        }


@dataclass
class ImportResult:
    """Summary and diagnostics for one import operation."""

    source_path: Path
    source_type: str
    category: str
    element_type: str
    mode: str
    dry_run: bool
    rows_total: int = 0
    rows_imported: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    field_matches: dict[str, str] = field(default_factory=dict)
    ignored_columns: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether the import completed without error-level issues."""

        return not self.has_errors

    @property
    def has_warnings(self) -> bool:
        """Return whether any warnings were collected."""

        return any(issue.level == "warning" for issue in self.issues)

    @property
    def has_errors(self) -> bool:
        """Return whether any errors were collected."""

        return any(issue.level == "error" for issue in self.issues)

    def add_issue(self, level: str, message: str, *, row_number: int | None = None, field: str | None = None) -> None:
        """Append one diagnostic issue."""

        self.issues.append(ImportIssue(level=level, row_number=row_number, field=field, message=message))

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable result dictionary."""

        return {
            "source_path": str(self.source_path),
            "source_type": self.source_type,
            "category": self.category,
            "element_type": self.element_type,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "rows_total": self.rows_total,
            "rows_imported": self.rows_imported,
            "rows_updated": self.rows_updated,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
            "field_matches": dict(self.field_matches),
            "ignored_columns": list(self.ignored_columns),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_frame(self) -> pd.DataFrame:
        """Return collected issues as a pandas DataFrame."""

        return pd.DataFrame([issue.to_dict() for issue in self.issues])

    def summary(self) -> str:
        """Return a compact human-readable import summary."""

        status = "ok" if self.ok else "completed with errors"
        warning_text = f", warnings={sum(issue.level == 'warning' for issue in self.issues)}" if self.has_warnings else ""
        return (
            f"{self.source_type.upper()} import {status}: "
            f"{self.category}.{self.element_type}; "
            f"rows={self.rows_total}, added={self.rows_imported}, updated={self.rows_updated}, "
            f"skipped={self.rows_skipped}, failed={self.rows_failed}{warning_text}."
        )

