"""Validated physical surface definitions; values are user supplied, never presets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from math import isfinite

from ..errors import ValidationError


def number(
    value: object,
    label: str,
    low: float = 0,
    high: float = float("inf"),
    *,
    positive: bool = False,
) -> float:
    """Validate a finite numeric input without clipping."""
    if isinstance(value, (bool, str)):
        raise ValidationError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be a finite number") from exc
    if (
        not isfinite(result)
        or result < low
        or result > high
        or (positive and result == 0)
    ):
        raise ValidationError(
            f"{label} must be finite and in [{low}, {high}]"
            + (" and positive" if positive else "")
        )
    return result


def name_check(name: str) -> None:
    if (
        not isinstance(name, str)
        or not name.strip()
        or name != name.strip()
        or any(c in name for c in '\n\r;"[]')
    ):
        raise ValidationError(
            "Names must be nonempty, trimmed strings without INP delimiters"
        )


def json_check(value: object) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Metadata must be finite JSON-serializable data") from exc


@dataclass
class LandCoverClass:
    """Physical surface properties, independent of native LANDUSES.

    Fractions use 0..1; pct_zero uses 0..100. Storage and infiltration
    lengths/rates use the attached model's native units (mm or inches).
    All hydrological properties are optional until derivation needs them.
    Invalid definitions raise ValidationError. Example:
    ``LandCoverClass('roof', impervious=1, n_imp=.012)``.
    """

    name: str
    impervious: float | None = None
    n_imp: float | None = None
    n_perv: float | None = None
    dstore_imp: float | None = None
    dstore_perv: float | None = None
    pct_zero: float | None = None
    infiltration: dict | None = None
    lids: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)
    description: str | None = None

    def __post_init__(self) -> None:
        name_check(self.name)
        for key in (
            "impervious",
            "n_imp",
            "n_perv",
            "dstore_imp",
            "dstore_perv",
            "pct_zero",
        ):
            value = getattr(self, key)
            if value is not None:
                number(
                    value,
                    key,
                    high=1
                    if key == "impervious"
                    else 100
                    if key == "pct_zero"
                    else float("inf"),
                    positive=key.startswith("n_"),
                )
        for key in ("lids", "attributes"):
            if not isinstance(getattr(self, key), dict):
                raise ValidationError(f"{key} must be a dictionary")
        if self.description is not None and not isinstance(self.description, str):
            raise ValidationError("description must be a string")
        for lid, value in self.lids.items():
            name_check(lid)
            if isinstance(value, dict):
                if (
                    set(value) - {"suitable_fraction", "min_area", "priority"}
                    or "suitable_fraction" not in value
                ):
                    raise ValidationError(
                        "LID metadata supports suitable_fraction, min_area (m2), priority only"
                    )
                number(value["suitable_fraction"], lid, high=1)
                number(value.get("min_area", 0), "min_area")
                number(value.get("priority", 0), "priority", high=1)
            else:
                number(value, lid, high=1)
        if self.infiltration is not None:
            from .infiltration import validate_parameters

            validate_parameters(self.infiltration)
        json_check(asdict(self))


@dataclass
class LandCoverCoverage:
    """Snapshot of one assignment; fractions dimensionless and area_m2 in m².

    Returned snapshots can be changed without mutating their manager.
    Example: ``LandCoverCoverage('S1', {'roof': 1}, 1000)``.
    """

    subcatchment: str
    fractions: dict[str, float]
    area_m2: float | None = None
