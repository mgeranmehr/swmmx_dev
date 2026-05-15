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


class DuplicateIDError(SWMMXError):
    """Raised when a newly-added model element reuses an existing ID."""


class UnknownIDError(ObjectNotFoundError):
    """Raised when add/remove APIs receive IDs that do not exist."""


class MissingRequiredParameterError(SWMMXError):
    """Raised when an add operation is missing a required option."""


class InvalidParameterError(SWMMXError):
    """Raised when an add/remove option has an invalid value or shape."""


class DependencyError(SWMMXError):
    """Raised when removal would leave referenced model elements dangling."""


class SaveError(SWMMXError):
    """Raised when a model cannot be written to disk."""


class PlotError(SWMMXError):
    """Base class for plotting-specific failures."""


class PlotDataError(PlotError):
    """Raised when a plot cannot be built from the available model data."""


class UnknownCategoryError(PlotError):
    """Raised when a plotting namespace category does not exist."""


class UnknownParameterError(PlotError):
    """Raised when a plotting namespace parameter does not exist."""


class NoPathError(PlotError):
    """Raised when no hydraulic path exists between requested nodes."""


class InvalidPathError(PlotError):
    """Raised when user-supplied profile links do not form a valid path."""


class ExportError(SWMMXError):
    """Base class for export-specific failures."""


class ExportGeometryError(ExportError):
    """Raised when GIS export cannot construct required geometry."""


class UnknownExportElementError(ExportError):
    """Raised when export selection contains an unsupported element name."""


class OptionalDependencyError(ExportError):
    """Raised when an optional export dependency is not installed."""


class FormatError(ExportError):
    """Raised when an export format or driver is unsupported."""
