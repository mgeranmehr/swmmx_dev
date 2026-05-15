"""Excel export frontend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import importlib.util

from ..errors import ExportError, OptionalDependencyError
from .utils import (
    _collect_export_tables,
    _excel_file_name,
    _get_default_export_path,
    _sanitize_excel_sheet_name,
)

if TYPE_CHECKING:
    from ..api import SWMMModel


def export_excel(
    model: "SWMMModel",
    *,
    path=None,
    file_name: str | None = None,
    elements="all",
    time_step=-1,
    include_results: bool = True,
    include_parameters: bool = True,
    include_derived: bool = True,
    strict_results: bool = False,
    overwrite: bool = False,
    engine: str = "openpyxl",
    freeze_panes: bool = True,
    auto_filter: bool = True,
) -> Path:
    """Export selected SWMM tables to one multi-sheet Excel workbook."""

    if engine == "openpyxl" and importlib.util.find_spec("openpyxl") is None:
        raise OptionalDependencyError("Excel export requires openpyxl. Install with: pip install openpyxl")
    tables = _collect_export_tables(
        model,
        elements,
        include_parameters=include_parameters,
        include_results=include_results,
        include_derived=include_derived,
        time_step=time_step,
        strict_results=strict_results,
    )
    target_dir = _get_default_export_path(model, path)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Could not create Excel export directory '{target_dir}': {exc}") from exc
    target = target_dir / _excel_file_name(model, file_name)
    if target.exists() and not overwrite:
        raise ExportError(f"Excel export target already exists: '{target}'. Use overwrite=True to replace it.")

    try:
        import pandas as pd

        used_sheet_names: set[str] = set()
        with pd.ExcelWriter(target, engine=engine) as writer:
            for element, frame in tables.items():
                sheet_name = _sanitize_excel_sheet_name(element, used_sheet_names)
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                if freeze_panes:
                    worksheet.freeze_panes = "A2"
                if auto_filter and worksheet.max_row >= 1 and worksheet.max_column >= 1:
                    worksheet.auto_filter.ref = worksheet.dimensions
    except OSError as exc:
        raise ExportError(f"Could not write Excel export '{target}': {exc}") from exc
    return target

