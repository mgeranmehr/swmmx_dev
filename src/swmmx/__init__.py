"""Public package entry point for :mod:`swmmx`."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from .dependencies import require_runtime_dependencies
from .errors import (
    DependencyError,
    DimensionMismatchError,
    DuplicateIDError,
    EngineLoadError,
    EngineNotFoundError,
    EngineRunError,
    ExportError,
    ExportGeometryError,
    FormatError,
    InvalidPathError,
    InvalidParameterError,
    InvalidReferenceError,
    MissingRequiredParameterError,
    ModelNotRunError,
    NoPathError,
    NotImplementedYetError,
    ObjectNotFoundError,
    OptionalDependencyError,
    ParseError,
    PlotDataError,
    PlotError,
    ReadOnlyParameterError,
    ReferenceError,
    SaveError,
    SWMMXError,
    UnknownCategoryError,
    UnknownExportElementError,
    UnknownIDError,
    UnknownParameterError,
    ValidationError,
)

__all__ = [
    "DependencyError",
    "DimensionMismatchError",
    "DuplicateIDError",
    "EngineLoadError",
    "EngineNotFoundError",
    "EngineRunError",
    "ExportError",
    "ExportGeometryError",
    "FormatError",
    "InvalidPathError",
    "InvalidParameterError",
    "InvalidReferenceError",
    "MissingRequiredParameterError",
    "ModelNotRunError",
    "NoPathError",
    "NotImplementedYetError",
    "ObjectNotFoundError",
    "OptionalDependencyError",
    "ParseError",
    "PlotDataError",
    "PlotError",
    "ReadOnlyParameterError",
    "ReferenceError",
    "SaveError",
    "SWMMModel",
    "SWMMXError",
    "UnknownCategoryError",
    "UnknownExportElementError",
    "UnknownIDError",
    "UnknownParameterError",
    "ValidationError",
    "swmm",
]

try:
    __version__ = version("swmmx")
except PackageNotFoundError:
    __version__ = "0+unknown"


def swmm(
    path: str | Path | None = None,
    new: Literal["SI", "US"] | None = None,
    flow_unit: str | None = None,
    custom_dll_path: str | Path | None = None,
):
    """Create or open an EPA SWMM model.

    Parameters
    ----------
    path:
        Optional path to an existing EPA SWMM ``.inp`` file. When ``path`` is
        supplied, ``new`` and ``flow_unit`` must be omitted because the input
        file already defines the model and its unit system.
    new:
        Optional unit system for a newly-created model. Use ``"SI"`` or
        ``"US"``. If both ``path`` and ``new`` are omitted, ``"SI"`` is used.
    flow_unit:
        Optional flow unit for a new model only. SI models accept ``"LPS"``
        (default), ``"CMS"``, or ``"MLD"``. US models accept ``"CFS"``
        (default), ``"GPM"``, or ``"MGD"``.
    custom_dll_path:
        Optional path to a custom native SWMM engine library. If omitted,
        ``swmmx`` lazily loads the bundled platform engine when a run begins.

    Examples
    --------
    >>> m = swmm("examples/example.inp")
    >>> m = swmm()
    >>> m = swmm(new="SI", flow_unit="CMS")
    >>> m = swmm(new="US", flow_unit="GPM")
    """

    require_runtime_dependencies()
    from .api import swmm as _swmm

    return _swmm(
        path=path,
        new=new,
        flow_unit=flow_unit,
        custom_dll_path=custom_dll_path,
    )


def __getattr__(name: str):
    """Lazily expose heavyweight model types without eager imports."""

    if name == "SWMMModel":
        require_runtime_dependencies()
        from .api import SWMMModel

        return SWMMModel
    raise AttributeError(name)
