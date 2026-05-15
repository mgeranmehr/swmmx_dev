"""Public package entry point for :mod:`swmmx`."""

from .api import SWMMModel, swmm
from .errors import (
    DimensionMismatchError,
    EngineLoadError,
    EngineNotFoundError,
    InvalidReferenceError,
    ModelNotRunError,
    NotImplementedYetError,
    ObjectNotFoundError,
    ReadOnlyParameterError,
    SWMMXError,
)

__all__ = [
    "DimensionMismatchError",
    "EngineLoadError",
    "EngineNotFoundError",
    "InvalidReferenceError",
    "ModelNotRunError",
    "NotImplementedYetError",
    "ObjectNotFoundError",
    "ReadOnlyParameterError",
    "SWMMModel",
    "SWMMXError",
    "swmm",
]

__version__ = "0.0.3"
