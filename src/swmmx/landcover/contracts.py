"""JSON-friendly contracts shared by Python clients and future frontends."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..errors import ValidationError


@dataclass(frozen=True)
class LandCoverIssue:
    """One actionable diagnostic; IDs/field identify the affected UI cell."""

    code: str
    severity: str
    object_id: str | None
    field: str | None
    message: str
    remedy: str
    row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class LandCoverReport:
    """All diagnostics from a bulk edit or requested calculation; never mutates inputs."""

    issues: tuple[LandCoverIssue, ...] = ()

    @property
    def can_apply(self) -> bool:
        """Whether no error blocks the proposed operation."""
        return not any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON suitable for a table/form frontend."""
        return {
            "can_apply": self.can_apply,
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_dataframe(self):
        """Return all issues as an independent pandas table."""
        import pandas as pd

        return pd.DataFrame(
            [i.to_dict() for i in self.issues],
            columns=LandCoverIssue.__dataclass_fields__,
        )


class LandCoverValidationError(ValidationError):
    """Atomic edit rejected; report contains every detected row issue."""

    def __init__(self, report: LandCoverReport):
        self.report = report
        super().__init__(
            "; ".join(i.message for i in report.issues if i.severity == "error")
        )


class LandCoverCancelled(ValidationError):
    """Cooperative cancellation; the operation left project data unchanged."""


@dataclass(frozen=True)
class LandCoverProject:
    """Immutable versioned project snapshot, independent of any SWMM model.

    Use manager.to_project() / LandCover.from_project(). Geometry is referenced
    through provenance, not duplicated in JSON. Class references use stable IDs.
    """

    _json: str

    def to_dict(self) -> dict[str, Any]:
        """Return an independent JSON payload."""
        return json.loads(self._json)

    def to_json(self) -> str:
        """Return portable JSON without NaN or Python-only objects."""
        return self._json


@dataclass(frozen=True)
class LandCoverPreview:
    """Immutable review snapshot. DataFrames are copies; apply via originating manager.

    to_dict() is the frontend response; submit preview_id to manager.apply().
    Preview handles are session-local and must be regenerated after loading.
    """

    _json: str

    def to_dict(self) -> dict[str, Any]:
        """Return independent values, changes, issues, assumptions and revision tokens."""
        return json.loads(self._json)

    @property
    def preview_id(self) -> str:
        return self.to_dict()["preview_id"]

    @property
    def can_apply(self) -> bool:
        return self.to_dict()["can_apply"]

    @property
    def issues(self) -> tuple[LandCoverIssue, ...]:
        return tuple(LandCoverIssue(**row) for row in self.to_dict()["issues"])

    @property
    def assumptions(self) -> list[str]:
        return self.to_dict()["assumptions"]

    @property
    def values(self):
        """Return native-target-unit values (declared units when standalone)."""
        import pandas as pd

        rows = self.to_dict()["values"]
        return (
            pd.DataFrame(rows).set_index("subcatchment")
            if rows
            else pd.DataFrame().rename_axis("subcatchment")
        )

    @property
    def changes(self):
        """Return parameter/current/proposed/unit rows; missing values use None."""
        import pandas as pd

        return pd.DataFrame(
            self.to_dict()["changes"],
            columns=["subcatchment", "parameter", "current", "proposed", "unit"],
        )
