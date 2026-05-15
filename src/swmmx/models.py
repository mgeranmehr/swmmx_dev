"""Small data containers returned by the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    """One validator finding with enough context for a user or UI."""

    severity: str
    code: str
    message: str
    section: str | None = None
    object_id: str | None = None


@dataclass
class ValidationResult:
    """A structured validation response that still feels pandas-native."""

    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        """Return ``True`` when no error-severity findings exist."""

        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return only error findings."""

        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return only warning findings."""

        return [issue for issue in self.issues if issue.severity == "warning"]

    def to_frame(self) -> pd.DataFrame:
        """Return findings as a tabular pandas object."""

        # Explicit columns keep an empty result equally easy to consume.
        rows = [issue.__dict__ for issue in self.issues]
        return pd.DataFrame(rows, columns=["severity", "code", "message", "section", "object_id"])

    def __len__(self) -> int:
        """Return the total number of findings."""

        return len(self.issues)


@dataclass(frozen=True)
class RunResult:
    """Summary returned after a full simulation run."""

    success: bool
    error_code: int
    input_path: Path
    report_path: Path
    output_path: Path
    periods: int
    engine_version: str | None
    validation: ValidationResult


@dataclass(frozen=True)
class SimulationStep:
    """One yielded state from stepwise execution."""

    index: int
    time: datetime
    elapsed_days: float

