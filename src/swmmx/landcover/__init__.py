"""Physical surface preprocessing, separate from native SWMM water-quality land uses."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api import SWMMModel

from .classes import LandCoverClass, LandCoverCoverage
from .core import LandCover

__all__ = [
    "LandCover",
    "LandCoverCancelled",
    "LandCoverClass",
    "LandCoverCoverage",
    "LandCoverIssue",
    "LandCoverPreview",
    "LandCoverProject",
    "LandCoverReport",
    "LandCoverValidationError",
    "landcover",
]


def landcover(
    model: SWMMModel | None = None,
    *,
    units: str | None = None,
    preset: str | None = None,
) -> LandCover:
    """Create standalone metadata or recover a model's opt-in JSON sidecar.

    Does not alter simulation inputs. Corrupt sidecars raise ValidationError.
    Example: ``from swmmx import swmm, landcover; lc = landcover(swmm())``.
    """
    if model is not None:
        existing = getattr(model, "_landcover", None)
        if existing is not None:
            if (units is not None and units != existing.units) or preset is not None:
                from ..errors import ValidationError

                raise ValidationError(
                    "Existing manager: units/preset cannot reinterpret saved data"
                )
            return existing
        if model.path is not None:
            sidecar = model.path.with_suffix(".swmmx.json")
            if sidecar.exists():
                from .persistence import read

                if "landcover" in read(sidecar):
                    restored = LandCover.load(sidecar, model)
                    if (
                        units is not None and units != restored.units
                    ) or preset is not None:
                        del model._landcover
                        from ..errors import ValidationError

                        raise ValidationError(
                            "Saved manager units/preset conflict; load without overrides"
                        )
                    return restored
    return LandCover(model, units=units or "native", preset=preset)


from .contracts import (
    LandCoverCancelled,
    LandCoverIssue,
    LandCoverPreview,
    LandCoverProject,
    LandCoverReport,
    LandCoverValidationError,
)
