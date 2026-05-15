"""Public package entry point for :mod:`swmmx`."""

from .api import SWMMModel, swmm
from .errors import (
    DependencyError,
    DimensionMismatchError,
    DuplicateIDError,
    EngineLoadError,
    EngineNotFoundError,
    InvalidPathError,
    InvalidParameterError,
    InvalidReferenceError,
    MissingRequiredParameterError,
    ModelNotRunError,
    NoPathError,
    NotImplementedYetError,
    ObjectNotFoundError,
    PlotDataError,
    PlotError,
    ReadOnlyParameterError,
    SaveError,
    SWMMXError,
    UnknownCategoryError,
    UnknownIDError,
    UnknownParameterError,
)

__all__ = [
    "DependencyError",
    "DimensionMismatchError",
    "DuplicateIDError",
    "EngineLoadError",
    "EngineNotFoundError",
    "InvalidPathError",
    "InvalidParameterError",
    "InvalidReferenceError",
    "MissingRequiredParameterError",
    "ModelNotRunError",
    "NoPathError",
    "NotImplementedYetError",
    "ObjectNotFoundError",
    "PlotDataError",
    "PlotError",
    "ReadOnlyParameterError",
    "SaveError",
    "SWMMModel",
    "SWMMXError",
    "UnknownCategoryError",
    "UnknownIDError",
    "UnknownParameterError",
    "swmm",
]

__version__ = "0.0.5"
