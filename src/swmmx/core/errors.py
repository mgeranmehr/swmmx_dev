"""Canonical exception hierarchy for :mod:`swmmx`."""

from __future__ import annotations


class SWMMXError(Exception):
    """Base class for all package-level exceptions."""


class UnknownCategoryError(SWMMXError):
    """Raised when a dynamic public API category does not exist."""


class UnknownParameterError(SWMMXError):
    """Raised when a dynamic public API parameter does not exist."""


class UnknownIDError(SWMMXError):
    """Raised when one or more requested object IDs do not exist."""


class ObjectNotFoundError(UnknownIDError):
    """Backward-compatible alias family for older missing-object failures."""


class DimensionMismatchError(SWMMXError):
    """Raised when vector input dimensions do not match selected objects."""


class ReadOnlyParameterError(SWMMXError):
    """Raised when callers attempt to write result or derived parameters."""


class ModelNotRunError(SWMMXError):
    """Raised when run-dependent data is requested before results exist."""


class EngineNotFoundError(SWMMXError):
    """Raised when a suitable SWMM engine file cannot be located."""


class EngineLoadError(SWMMXError):
    """Raised when a native SWMM engine exists but cannot be loaded safely."""


class EngineRunError(SWMMXError):
    """Raised when the native SWMM engine cannot complete a requested run."""


class ValidationError(SWMMXError):
    """Raised when model validation fails in an exception-oriented workflow."""


class NotImplementedYetError(SWMMXError):
    """Raised when a preserved-but-unsupported feature is explicitly accessed."""


class FormatError(SWMMXError):
    """Raised when a public format argument is unsupported."""


class ReferenceError(SWMMXError):
    """Raised when a reference points to a missing model object."""


class InvalidReferenceError(ReferenceError):
    """Backward-compatible concrete reference-validation failure."""


class SaveError(SWMMXError):
    """Raised when a model or artifact cannot be written to disk."""


class ParseError(SWMMXError):
    """Raised when model input cannot be parsed safely."""


class DuplicateIDError(SWMMXError):
    """Raised when a newly-added model element reuses an existing ID."""


class MissingRequiredParameterError(SWMMXError):
    """Raised when an add operation is missing a required option."""


class InvalidParameterError(SWMMXError):
    """Raised when an add/remove option has an invalid value or shape."""


class DependencyError(SWMMXError):
    """Raised when removal would leave referenced model elements dangling."""


class PlotError(SWMMXError):
    """Base class for plotting-specific failures."""


class PlotDataError(PlotError):
    """Raised when a plot cannot be built from the available model data."""


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


class SwmmxImportError(SWMMXError):
    """Base class for import-specific failures."""


class SwmmxImportDependencyError(SwmmxImportError):
    """Raised when an optional import dependency is not installed."""


class SwmmxImportFieldError(SwmmxImportError):
    """Raised when source fields cannot be matched safely."""


class SwmmxImportAmbiguousFieldError(SwmmxImportFieldError):
    """Raised when multiple source columns match the same import field."""


class SwmmxImportMissingFieldError(SwmmxImportFieldError):
    """Raised when required import fields are missing."""


class SwmmxImportValidationError(SwmmxImportError):
    """Raised when import row validation or model mutation fails."""


class SwmmxImportUnsupportedCategoryError(SwmmxImportError):
    """Raised when an import endpoint is reserved but unsupported."""
