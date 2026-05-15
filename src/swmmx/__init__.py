"""Public package entry point for :mod:`swmmx`."""

from .api import SWMMModel, swmm
from .errors import (
    EngineLoadError,
    EngineNotFoundError,
    ModelNotRunError,
    NotImplementedYetError,
    SWMMXError,
)

__all__ = [
    "EngineLoadError",
    "EngineNotFoundError",
    "ModelNotRunError",
    "NotImplementedYetError",
    "SWMMModel",
    "SWMMXError",
    "swmm",
]

__version__ = "0.0.1"

