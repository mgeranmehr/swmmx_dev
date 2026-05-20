"""CSV import backend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .importer import execute_import

if TYPE_CHECKING:
    from ..api import SWMMModel


def import_csv(
    model: "SWMMModel",
    *,
    category: str,
    element_type: str,
    file_path,
    field_map=None,
    encoding: str = "utf-8",
    delimiter: str | None = None,
    **options,
):
    """Read a CSV file and import rows into a model."""

    path = Path(file_path)
    read_kwargs = {"encoding": encoding}
    if delimiter is not None:
        read_kwargs["sep"] = delimiter
    frame = pd.read_csv(path, **read_kwargs)
    return execute_import(
        model,
        frame,
        source_path=path,
        source_type="csv",
        category=category,
        element_type=element_type,
        field_map=field_map,
        **options,
    )

