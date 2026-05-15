"""CSV export frontend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import ExportError
from .utils import _collect_export_tables, _csv_file_name, _get_default_export_path

if TYPE_CHECKING:
    from ..api import SWMMModel


def export_csv(
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
    index: bool = False,
    encoding: str = "utf-8",
) -> dict[str, Path]:
    """Export selected SWMM tables as one UTF-8 CSV file per element type."""

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
        raise ExportError(f"Could not create CSV export directory '{target_dir}': {exc}") from exc

    outputs: dict[str, Path] = {}
    for element, frame in tables.items():
        target = target_dir / _csv_file_name(model, element, file_name, len(tables))
        if target.exists() and not overwrite:
            raise ExportError(f"CSV export target already exists: '{target}'. Use overwrite=True to replace it.")
        try:
            frame.to_csv(target, index=index, encoding=encoding)
        except OSError as exc:
            raise ExportError(f"Could not write CSV export '{target}': {exc}") from exc
        outputs[element] = target
    return outputs

