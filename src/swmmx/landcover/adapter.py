"""The only adapter translating landcover previews into native SWMM inputs."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from ..errors import ValidationError

PARAMETERS = {
    "percent_impervious": "impervious_percent",
    "n_imperv": "n_impervious",
    "n_perv": "n_pervious",
    "dstore_imperv": "depression_storage_impervious",
    "dstore_perv": "depression_storage_pervious",
    "pct_zero": "zero_depression_storage_impervious_percent",
}
LENGTH_FIELDS = {
    "dstore_imperv",
    "dstore_perv",
    "suction_head",
    "hydraulic_conductivity",
    "maximum_rate",
    "minimum_rate",
    "maximum_volume",
    "conductivity",
}


class SWMMLandCoverAdapter:
    """Model boundary: units, current values, fingerprint and atomic native setters."""

    def __init__(self, model):
        self.model = model

    @property
    def units(self) -> str:
        return (
            "US" if self.model.options["FLOW_UNITS"] in ("CFS", "GPM", "MGD") else "SI"
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model._document.to_text().encode()).hexdigest()

    def convert(self, records: list[dict], source_units: str) -> list[dict]:
        """Convert length/rate parameters to target units; all other values unchanged."""
        factor = (
            1
            if source_units in ("native", self.units)
            else (25.4 if self.units == "SI" else 1 / 25.4)
        )
        rows = deepcopy(records)
        for row in rows:
            for key in LENGTH_FIELDS.intersection(row):
                if row[key] is not None:
                    row[key] *= factor
        return rows

    def current(self, sid: str, field: str, model: str | None = None):
        if field in PARAMETERS:
            return getattr(self.model.get.subcatchment, PARAMETERS[field])(ids=sid)
        if field == "model":
            return self.model.options["INFILTRATION"]
        category = "infiltration_" + str(model).removeprefix("MODIFIED_").lower()
        return getattr(getattr(self.model.get, category), field)(ids=sid)

    def apply(self, records: list[dict]) -> bool:
        """Validate all writes on a clone, then atomically commit the native document."""
        trial = self.model.clone()
        for row in records:
            sid = row["subcatchment"]
            if (
                row.get("model") is not None
                and row["model"] != trial.options["INFILTRATION"]
            ):
                raise ValidationError("Preview infiltration model differs from SWMM")
            for key, value in row.items():
                if key in ("subcatchment", "model") or value is None:
                    continue
                if key in PARAMETERS:
                    getattr(trial.set.subcatchment, PARAMETERS[key])(
                        float(value), ids=sid
                    )
                else:
                    category = (
                        "infiltration_" + row["model"].removeprefix("MODIFIED_").lower()
                    )
                    getattr(getattr(trial.set, category), key)(float(value), ids=sid)
        changed = trial._document.to_text() != self.model._document.to_text()
        if changed:
            self.model._document = trial._document
            self.model._dirty = True
            self.model._invalidate_results()
        return changed
