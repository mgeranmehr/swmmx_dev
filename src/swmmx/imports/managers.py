"""Public import namespaces exposed on ``SWMMModel``."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from ..errors import SwmmxImportUnsupportedCategoryError, UnknownCategoryError, UnknownParameterError
from .csv_importer import import_csv
from .gis_importer import import_gis
from .schema import categories, element_types_for

if TYPE_CHECKING:
    from ..api import SWMMModel


class ImportRoot:
    """Root namespace for ``m.import_csv`` or ``m.import_gis``."""

    def __init__(self, model: "SWMMModel", source_type: str) -> None:
        self._model = model
        self._source_type = source_type
        for category in self.__dir__():
            setattr(self, category, ImportCategory(model, source_type, category))

    def __dir__(self) -> list[str]:
        return categories()

    def __getattr__(self, category: str):
        if category.startswith("_"):
            raise AttributeError(category)
        if category not in categories():
            raise UnknownCategoryError(f"Unknown import category '{category}'.")
        namespace = ImportCategory(self._model, self._source_type, category)
        setattr(self, category, namespace)
        return namespace


class ImportCategory:
    """Callable category namespace such as ``m.import_csv.node``."""

    __signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("file_path", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("field_map", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
            inspect.Parameter("options", inspect.Parameter.VAR_KEYWORD),
        ]
    )

    def __init__(self, model: "SWMMModel", source_type: str, category: str) -> None:
        self._model = model
        self._source_type = source_type
        self._category = category
        for element_type in self.__dir__():
            setattr(self, element_type, ImportCallable(model, source_type, category, element_type))

    def __dir__(self) -> list[str]:
        return element_types_for(self._category)

    def __getattr__(self, element_type: str):
        if element_type.startswith("_"):
            raise AttributeError(element_type)
        if element_type not in self.__dir__():
            raise UnknownParameterError(f"Unknown import endpoint '{self._category}.{element_type}'.")
        endpoint = ImportCallable(self._model, self._source_type, self._category, element_type)
        setattr(self, element_type, endpoint)
        return endpoint

    def __call__(self, file_path, field_map=None, **options):
        """Import a whole category using a type column when supported."""

        if self._category not in {"node", "link"}:
            raise SwmmxImportUnsupportedCategoryError(
                f"Group-level import is not supported for '{self._category}'."
            )
        return _dispatch_import(
            self._model,
            self._source_type,
            self._category,
            "__group__",
            file_path,
            field_map,
            **options,
        )


class ImportCallable:
    """One concrete import endpoint."""

    __signature__ = ImportCategory.__signature__

    def __init__(self, model: "SWMMModel", source_type: str, category: str, element_type: str) -> None:
        self._model = model
        self._source_type = source_type
        self._category = category
        self._element_type = element_type
        self.__name__ = element_type
        self.__doc__ = (
            f"Import {category}.{element_type} objects from a {source_type.upper()} file.\n\n"
            "Call as ``(file_path, field_map=None, **options)``.  Common options include "
            "``mode='add'|'update'|'upsert'``, ``dry_run=True``, ``on_error='raise'|'skip'|'collect'``, "
            "and ``on_unknown_fields='ignore'|'warn'|'error'``."
        )

    def __call__(self, file_path, field_map=None, **options):
        return _dispatch_import(
            self._model,
            self._source_type,
            self._category,
            self._element_type,
            file_path,
            field_map,
            **options,
        )


def _dispatch_import(model: "SWMMModel", source_type: str, category: str, element_type: str, file_path, field_map, **options):
    if source_type == "csv":
        return import_csv(
            model,
            category=category,
            element_type=element_type,
            file_path=file_path,
            field_map=field_map,
            **options,
        )
    return import_gis(
        model,
        category=category,
        element_type=element_type,
        file_path=file_path,
        field_map=field_map,
        **options,
    )
