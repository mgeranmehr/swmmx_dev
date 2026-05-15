"""Custom exceptions used by :mod:`swmmx`.

Keeping package-specific failures in one module gives callers a stable place to
catch errors without having to know whether the failure originated in the file
parser, the native engine loader, or a higher-level helper.
"""


class SWMMXError(Exception):
    """Base class for all package-level exceptions."""


class EngineNotFoundError(SWMMXError):
    """Raised when a suitable SWMM engine file cannot be located."""


class EngineLoadError(SWMMXError):
    """Raised when a native SWMM engine exists but cannot be loaded safely."""


class ModelNotRunError(SWMMXError):
    """Raised when run-dependent data is requested before results exist."""


class NotImplementedYetError(SWMMXError):
    """Raised when a preserved-but-unsupported section is explicitly accessed."""


class DimensionMismatchError(SWMMXError):
    """Raised when setter values do not match the selected object count."""


class ReadOnlyParameterError(SWMMXError):
    """Raised when a caller attempts to set a derived or result parameter."""


class ObjectNotFoundError(SWMMXError):
    """Raised when one or more requested object IDs do not exist."""


class InvalidReferenceError(SWMMXError):
    """Raised when a reference parameter points at a missing object."""
