"""Public package entry point for :mod:`swmmx`."""

from .api import SWMMModel, swmm
from .errors import (
    DependencyError,
    DimensionMismatchError,
    DuplicateIDError,
    EngineLoadError,
    EngineNotFoundError,
    InvalidParameterError,
    InvalidReferenceError,
    MissingRequiredParameterError,
    ModelNotRunError,
    NotImplementedYetError,
    ObjectNotFoundError,
    ReadOnlyParameterError,
    SaveError,
    SWMMXError,
    UnknownIDError,
)

__all__ = [
    "DependencyError",
    "DimensionMismatchError",
    "DuplicateIDError",
    "EngineLoadError",
    "EngineNotFoundError",
    "InvalidParameterError",
    "InvalidReferenceError",
    "MissingRequiredParameterError",
    "ModelNotRunError",
    "NotImplementedYetError",
    "ObjectNotFoundError",
    "ReadOnlyParameterError",
    "SaveError",
    "SWMMModel",
    "SWMMXError",
    "UnknownIDError",
    "swmm",
]

__version__ = "0.0.4"
