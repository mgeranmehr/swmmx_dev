"""Shared CSV/GIS import execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from ..errors import (
    DuplicateIDError,
    InvalidReferenceError,
    NotImplementedYetError,
    SwmmxImportFieldError,
    SwmmxImportUnsupportedCategoryError,
    SwmmxImportValidationError,
    UnknownIDError,
)
from .fields import match_fields, normalize_field_name
from .results import ImportResult
from .schema import ImportSchema, schema_for

if TYPE_CHECKING:
    from ..api import SWMMModel


VALID_MODES = {"add", "update", "upsert"}
VALID_MISSING = {"error", "skip"}
VALID_UNKNOWN = {"ignore", "warn", "error"}
VALID_ERRORS = {"raise", "skip", "collect"}


@dataclass
class _ModelSnapshot:
    document: Any
    dirty: bool
    results_stale: bool
    run_timestamps: Any
    last_run_result: Any
    last_output_path: Any
    output_file_cache: Any


def _snapshot(model: "SWMMModel") -> _ModelSnapshot:
    return _ModelSnapshot(
        document=model._document.copy(),
        dirty=model._dirty,
        results_stale=model._results_stale,
        run_timestamps=model._run_timestamps,
        last_run_result=model._last_run_result,
        last_output_path=model._last_output_path,
        output_file_cache=model._output_file_cache,
    )


def _restore(model: "SWMMModel", snapshot: _ModelSnapshot) -> None:
    model._document = snapshot.document
    model._dirty = snapshot.dirty
    model._results_stale = snapshot.results_stale
    model._run_timestamps = snapshot.run_timestamps
    model._last_run_result = snapshot.last_run_result
    model._last_output_path = snapshot.last_output_path
    model._output_file_cache = snapshot.output_file_cache


def _validate_options(mode: str, on_missing_required: str, on_unknown_fields: str, on_error: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError("'mode' must be 'add', 'update', or 'upsert'.")
    if on_missing_required not in VALID_MISSING:
        raise ValueError("'on_missing_required' must be 'error' or 'skip'.")
    if on_unknown_fields not in VALID_UNKNOWN:
        raise ValueError("'on_unknown_fields' must be 'ignore', 'warn', or 'error'.")
    if on_error not in VALID_ERRORS:
        raise ValueError("'on_error' must be 'raise', 'skip', or 'collect'.")


def execute_import(
    model: "SWMMModel",
    df: pd.DataFrame,
    *,
    source_path: str | Path,
    source_type: str,
    category: str,
    element_type: str,
    field_map: dict[str, str] | None = None,
    mode: str = "add",
    on_missing_required: str = "error",
    on_unknown_fields: str = "ignore",
    on_error: str = "raise",
    dry_run: bool = False,
    default_type: str | None = None,
    overwrite_geometry: bool = True,
    **_options,
) -> ImportResult:
    """Validate and apply one tabular import."""

    _validate_options(mode, on_missing_required, on_unknown_fields, on_error)
    schema = schema_for(category, element_type)
    result = ImportResult(
        source_path=Path(source_path),
        source_type=source_type,
        category=category,
        element_type=element_type if element_type != "__group__" else category,
        mode=mode,
        dry_run=bool(dry_run),
        rows_total=len(df.index),
    )

    effective_field_map = _group_export_field_map(df.columns, element_type, field_map)

    try:
        matches, ignored = match_fields(
            df.columns,
            schema.fields,
            field_map=effective_field_map,
            required_fields=schema.required_fields if on_missing_required == "error" else (),
        )
    except SwmmxImportFieldError:
        raise
    result.field_matches = dict(matches)
    result.ignored_columns = [column for column in ignored if column != "geometry"]
    if result.ignored_columns and on_unknown_fields == "error":
        raise SwmmxImportFieldError(f"Unknown or unmapped import column(s): {result.ignored_columns}.")
    if result.ignored_columns and on_unknown_fields == "warn":
        result.add_issue(
            "warning",
            f"Ignored unmapped column(s): {', '.join(result.ignored_columns)}.",
            row_number=None,
            field=None,
        )

    if element_type == "__group__":
        return _execute_group_import(
            model,
            df,
            schema=schema,
            result=result,
            matches=matches,
            mode=mode,
            on_missing_required=on_missing_required,
            on_error=on_error,
            dry_run=dry_run,
            default_type=default_type,
            overwrite_geometry=overwrite_geometry,
        )

    if category == "time" and element_type == "time_series":
        return _execute_grouped_points_import(
            model,
            df,
            schema=schema,
            result=result,
            matches=matches,
            mode=mode,
            on_missing_required=on_missing_required,
            on_error=on_error,
            dry_run=dry_run,
        )
    if category == "curve" and element_type == "curve":
        return _execute_grouped_curve_import(
            model,
            df,
            schema=schema,
            result=result,
            matches=matches,
            mode=mode,
            on_missing_required=on_missing_required,
            on_error=on_error,
            dry_run=dry_run,
        )
    if category == "coordinate":
        return _execute_coordinate_import(
            model,
            df,
            schema=schema,
            result=result,
            matches=matches,
            mode=mode,
            on_missing_required=on_missing_required,
            on_error=on_error,
            dry_run=dry_run,
            overwrite_geometry=overwrite_geometry,
        )

    for frame_index, row in df.iterrows():
        row_number = int(frame_index) + 2
        values = _canonical_row(row, matches)
        _process_single_row(
            model,
            schema=schema,
            values=values,
            result=result,
            row_number=row_number,
            mode=mode,
            on_missing_required=on_missing_required,
            on_error=on_error,
            dry_run=dry_run,
            overwrite_geometry=overwrite_geometry,
        )
    return result


def _group_export_field_map(columns, element_type: str, field_map: dict[str, str] | None) -> dict[str, str] | None:
    """Prefer exported ``element_type`` over object-specific ``type`` in group imports."""

    if element_type != "__group__":
        return field_map
    effective = dict(field_map or {})
    if "type" in effective:
        return effective
    for column in columns:
        if normalize_field_name(column) == "elementtype":
            effective["type"] = str(column)
            return effective
    return field_map


def _canonical_row(row, matches: dict[str, str]) -> dict[str, Any]:
    """Return canonical row values from matched columns."""

    values: dict[str, Any] = {}
    for field, column in matches.items():
        value = row[column]
        if _is_missing(value):
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        values[field] = _coerce_scalar(value)
    return values


def _is_missing(value: Any) -> bool:
    """Return whether a dataframe cell should be treated as absent."""

    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _coerce_scalar(value: Any) -> Any:
    """Coerce simple scalar values while preserving IDs and enum strings."""

    if isinstance(value, str):
        text = value.strip()
        upper = text.upper()
        if upper in {"TRUE", "YES"}:
            return "YES"
        if upper in {"FALSE", "NO"}:
            return "NO"
        if text.startswith(("[", "{")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text
    return value.item() if hasattr(value, "item") else value


def _execute_group_import(
    model: "SWMMModel",
    df: pd.DataFrame,
    *,
    schema: ImportSchema,
    result: ImportResult,
    matches: dict[str, str],
    mode: str,
    on_missing_required: str,
    on_error: str,
    dry_run: bool,
    default_type: str | None,
    overwrite_geometry: bool,
) -> ImportResult:
    """Dispatch each row in a group import to a concrete schema."""

    fallback = default_type or ("junction" if schema.category == "node" else "conduit")
    fallback = _normalize_type(fallback, schema)
    for frame_index, row in df.iterrows():
        row_number = int(frame_index) + 2
        values = _canonical_row(row, matches)
        raw_type = values.pop("type", None)
        try:
            element_type = _normalize_type(raw_type or fallback, schema)
            concrete = schema_for(schema.category, element_type)
            filtered = {key: value for key, value in values.items() if key in concrete.fields}
            _process_single_row(
                model,
                schema=concrete,
                values=filtered,
                result=result,
                row_number=row_number,
                mode=mode,
                on_missing_required=on_missing_required,
                on_error=on_error,
                dry_run=dry_run,
                overwrite_geometry=overwrite_geometry,
            )
        except Exception as exc:
            _handle_row_error(result, row_number, "type", exc, on_error)
    return result


def _normalize_type(value: Any, schema: ImportSchema) -> str:
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    normalized = schema.type_aliases.get(text, text)
    if normalized not in schema.group_types:
        raise SwmmxImportValidationError(
            f"Unknown {schema.category} import type '{value}'. Valid values are: {', '.join(schema.group_types)}."
        )
    return normalized


def _process_single_row(
    model: "SWMMModel",
    *,
    schema: ImportSchema,
    values: dict[str, Any],
    result: ImportResult,
    row_number: int,
    mode: str,
    on_missing_required: str,
    on_error: str,
    dry_run: bool,
    overwrite_geometry: bool,
) -> None:
    """Validate and add/update/upsert one ordinary element row."""

    try:
        missing = [field for field in schema.required_fields if field not in values]
        if missing:
            message = f"Missing required field(s): {', '.join(missing)}."
            if on_missing_required == "skip":
                result.rows_skipped += 1
                for field in missing:
                    result.add_issue("error", message, row_number=row_number, field=field)
                return
            raise SwmmxImportValidationError(message)
        object_id = str(values["id"]).strip()
        if not object_id:
            raise SwmmxImportValidationError("ID is empty.")
        exists = _object_exists(model, schema, object_id)
        action = _resolve_action(mode, exists, schema, object_id)
        if dry_run:
            if action == "add":
                result.rows_imported += 1
            else:
                result.rows_updated += 1
            return

        snap = _snapshot(model)
        try:
            if action == "update":
                _remove_existing(model, schema, object_id, overwrite_geometry=overwrite_geometry)
            _add_element(model, schema, object_id, {key: value for key, value in values.items() if key != "id"})
        except Exception:
            _restore(model, snap)
            raise
        if action == "add":
            result.rows_imported += 1
        else:
            result.rows_updated += 1
    except Exception as exc:
        _handle_row_error(result, row_number, None, exc, on_error)


def _resolve_action(mode: str, exists: bool, schema: ImportSchema, object_id: str) -> str:
    if mode == "add":
        if exists:
            raise DuplicateIDError(f"{schema.element_type} ID '{object_id}' already exists.")
        return "add"
    if mode == "update":
        if not exists:
            raise UnknownIDError(f"Unknown {schema.element_type} ID '{object_id}'.")
        return "update"
    return "update" if exists else "add"


def _object_exists(model: "SWMMModel", schema: ImportSchema, object_id: str) -> bool:
    if not schema.id_scope:
        return False
    try:
        return object_id in set(model._editable_service._ids_for_scope(schema.id_scope))
    except Exception:
        return object_id in set(model._ids_for_category(schema.id_scope))


def _handle_row_error(result: ImportResult, row_number: int, field: str | None, exc: Exception, on_error: str) -> None:
    if on_error == "raise":
        raise exc
    result.add_issue("error", str(exc), row_number=row_number, field=field)
    if on_error == "skip":
        result.rows_skipped += 1
    else:
        result.rows_failed += 1


def _add_element(model: "SWMMModel", schema: ImportSchema, object_id: str, options: dict[str, Any]) -> None:
    """Add one element through the best available model path."""

    options = _adapt_exported_options(model, schema, object_id, dict(options))
    tag = options.pop("tag", None)
    if schema.category == "node" and schema.element_type in {"flow_divider", "storage_unit"}:
        _add_direct_node(model, schema, object_id, options)
    elif schema.category == "link" and schema.element_type != "conduit":
        _add_direct_link(model, schema, object_id, options)
    else:
        try:
            add_namespace = getattr(model.add, schema.effective_add_category)
            add_callable = getattr(add_namespace, schema.effective_add_element_type)
            add_callable(object_id, **options)
        except NotImplementedYetError as exc:
            raise SwmmxImportUnsupportedCategoryError(
                f"Import endpoint '{schema.public_path}' is reserved but the matching add API is not implemented yet."
            ) from exc
    if tag not in {None, ""}:
        _set_tag(model, schema, object_id, tag)


def _adapt_exported_options(model: "SWMMModel", schema: ImportSchema, object_id: str, options: dict[str, Any]) -> dict[str, Any]:
    """Translate export-friendly columns back into add-friendly options.

    ``m.export.csv()`` intentionally includes readable, stable columns such as
    ``stage_data``, ``source_data`` and serialized ``coordinates``.  Those are
    ideal for interchange, but the add API expects type-specific names such as
    ``fixed_stage`` or ``time_series``.  This adapter keeps files produced by
    swmmx importable without requiring users to write a custom ``field_map``.
    """

    if schema.category == "node" and schema.element_type == "outfall" and "stage_data" in options:
        stage_data = options.pop("stage_data")
        outfall_type = str(options.get("type", "FREE")).upper()
        if outfall_type == "FIXED":
            options.setdefault("fixed_stage", stage_data)
        elif outfall_type == "TIDAL":
            options.setdefault("tidal_curve", stage_data)
        elif outfall_type == "TIMESERIES":
            options.setdefault("time_series", stage_data)

    if schema.category == "hydrology" and schema.element_type == "rain_gage" and "source_data" in options:
        source_data = options.pop("source_data")
        source_type = str(options.get("source_type", "")).upper()
        if source_type == "TIMESERIES":
            options.setdefault("time_series", source_data)
        elif source_data not in {None, ""}:
            options.setdefault("filename", source_data)

    if schema.category == "link" and "vertices" in options:
        vertices = _strip_exported_link_endpoints(model, options)
        if vertices:
            options["vertices"] = vertices
        else:
            options.pop("vertices", None)

    return options


def _strip_exported_link_endpoints(model: "SWMMModel", options: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Return interior vertices from an exported full link coordinate chain."""

    try:
        vertices = _coerce_points(options.get("vertices"))
    except Exception:
        return options.get("vertices")
    if not isinstance(vertices, list):
        return vertices
    from_node = options.get("from_node")
    to_node = options.get("to_node")
    if from_node not in {None, ""}:
        from_point = model._point_for("COORDINATES", str(from_node))
        if vertices and _points_close(vertices[0], from_point):
            vertices = vertices[1:]
    if to_node not in {None, ""}:
        to_point = model._point_for("COORDINATES", str(to_node))
        if vertices and _points_close(vertices[-1], to_point):
            vertices = vertices[:-1]
    return vertices


def _points_close(first: Any, second: Any, *, tolerance: float = 1e-9) -> bool:
    """Return whether two coordinate pairs represent the same point."""

    if first is None or second is None:
        return False
    try:
        return (
            abs(float(first[0]) - float(second[0])) <= tolerance
            and abs(float(first[1]) - float(second[1])) <= tolerance
        )
    except (TypeError, ValueError, IndexError):
        return False


def _add_direct_node(model: "SWMMModel", schema: ImportSchema, object_id: str, options: dict[str, Any]) -> None:
    """Add currently-reserved node types directly to INP rows."""

    _assert_unique(model, "node", object_id)
    x = options.pop("x")
    y = options.pop("y")
    if schema.element_type == "flow_divider":
        row = [
            object_id,
            options.pop("invert_elevation", 0.0),
            options.pop("max_depth", 0.0),
            options.pop("initial_depth", 0.0),
            options.pop("surcharge_depth", 0.0),
            options.pop("ponded_area", 0.0),
            str(options.pop("type", "CUTOFF")).upper(),
            options.pop("diverted_link", None),
            options.pop("cutoff_flow", None),
            options.pop("diversion_curve", None),
            options.pop("weir_height", None),
            options.pop("weir_coefficient", None),
        ]
        section = "DIVIDERS"
    else:
        area_value = options.pop("area", None)
        if area_value is None:
            area_value = options.pop("area_coefficient", 0.0)
        else:
            options.pop("area_coefficient", None)
        row = [
            object_id,
            options.pop("invert_elevation", 0.0),
            options.pop("max_depth", 0.0),
            options.pop("initial_depth", 0.0),
            str(options.pop("storage_curve_type", "FUNCTIONAL")).upper(),
            options.pop("storage_curve", None),
            area_value,
            options.pop("area_exponent", 0.0),
            options.pop("area_constant", 0.0),
            options.pop("evaporation_factor", 0.0),
            options.pop("seepage_loss", 0.0),
        ]
        section = "STORAGE"
    _reject_unknown(options, schema)
    model._document.append_row(section, row)
    model._document.append_row("COORDINATES", [object_id, x, y])
    model._dirty = True
    model._invalidate_results()


def _add_direct_link(model: "SWMMModel", schema: ImportSchema, object_id: str, options: dict[str, Any]) -> None:
    """Add currently-reserved link types directly to INP rows."""

    _assert_unique(model, "link", object_id)
    from_node = options.pop("from_node")
    to_node = options.pop("to_node")
    _assert_reference(model, "node", from_node, "from_node", schema, object_id)
    _assert_reference(model, "node", to_node, "to_node", schema, object_id)
    vertices = options.pop("vertices", None)
    if schema.element_type == "pump":
        row = [object_id, from_node, to_node, options.pop("curve"), options.pop("initial_status", "ON"), options.pop("startup_depth", None), options.pop("shutoff_depth", None)]
        section = "PUMPS"
    elif schema.element_type == "orifice":
        row = [
            object_id,
            from_node,
            to_node,
            str(options.pop("type")).upper(),
            options.pop("offset", 0.0),
            options.pop("discharge_coefficient"),
            options.pop("flap_gate", "NO"),
            options.pop("open_close_time", 0.0),
        ]
        model._document.append_row("XSECTIONS", [object_id, str(options.pop("shape")).upper(), options.pop("height"), options.pop("width", 0.0), 0, 0, 1])
        section = "ORIFICES"
    elif schema.element_type == "weir":
        row = [
            object_id,
            from_node,
            to_node,
            str(options.pop("type")).upper(),
            options.pop("crest_height"),
            options.pop("discharge_coefficient"),
            options.pop("length", options.pop("side_slope", None)),
            options.pop("flap_gate", "NO"),
            options.pop("end_contractions", 0),
            options.pop("end_coefficient", 0.0),
            options.pop("surcharge", None),
            options.pop("road_width", None),
            options.pop("road_surface", None),
        ]
        section = "WEIRS"
    else:
        row = [
            object_id,
            from_node,
            to_node,
            options.pop("offset", 0.0),
            options.pop("flap_gate", "NO"),
            str(options.pop("rating_type")).upper(),
            options.pop("curve", options.pop("coefficient", None)),
            options.pop("exponent", None),
        ]
        section = "OUTLETS"
    _reject_unknown(options, schema)
    model._document.append_row(section, row)
    if vertices is not None:
        for x, y in _coerce_points(vertices):
            model._document.append_row("VERTICES", [object_id, x, y])
    model._dirty = True
    model._invalidate_results()


def _assert_unique(model: "SWMMModel", scope: str, object_id: str) -> None:
    if object_id in set(model._editable_service._ids_for_scope(scope)):
        raise DuplicateIDError(f"{scope} ID '{object_id}' already exists.")


def _assert_reference(model: "SWMMModel", scope: str, object_id: Any, field: str, schema: ImportSchema, import_id: str) -> None:
    if object_id in {None, "", "*"}:
        return
    if str(object_id) not in set(model._editable_service._ids_for_scope(scope)):
        raise InvalidReferenceError(f"Cannot import {schema.element_type} '{import_id}': {field} '{object_id}' does not exist.")


def _reject_unknown(options: dict[str, Any], schema: ImportSchema) -> None:
    if options:
        raise SwmmxImportValidationError(
            f"Unknown field(s) for {schema.public_path}: {', '.join(sorted(options))}."
        )


def _remove_existing(model: "SWMMModel", schema: ImportSchema, object_id: str, *, overwrite_geometry: bool) -> None:
    """Remove existing rows for an ID before a replacement-style update."""

    if schema.category == "node":
        for section in ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE"):
            model._document.remove_rows(section, [object_id])
        if overwrite_geometry:
            model._document.remove_rows("COORDINATES", [object_id])
    elif schema.category == "link":
        for section in ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS", "XSECTIONS", "LOSSES"):
            model._document.remove_rows(section, [object_id])
        if overwrite_geometry:
            model._document.remove_rows("VERTICES", [object_id])
    elif schema.category == "hydrology" and schema.element_type == "rain_gage":
        model._document.remove_rows("RAINGAGES", [object_id])
        if overwrite_geometry:
            model._document.remove_rows("SYMBOLS", [object_id])
    elif schema.category == "hydrology" and schema.element_type == "subcatchment":
        for section in ("SUBCATCHMENTS", "SUBAREAS", "INFILTRATION"):
            model._document.remove_rows(section, [object_id])
        if overwrite_geometry:
            model._document.remove_rows("POLYGONS", [object_id])
    elif schema.category == "time":
        model._document.remove_rows("TIMESERIES" if schema.element_type == "time_series" else "PATTERNS", [object_id])
    elif schema.category == "curve":
        model._document.remove_rows("CURVES", [object_id])


def _set_tag(model: "SWMMModel", schema: ImportSchema, object_id: str, tag: Any) -> None:
    tag_type = {
        "node": "Node",
        "link": "Link",
        "hydrology": "Subcatch" if schema.element_type == "subcatchment" else "RainGage",
    }.get(schema.category, schema.category)
    model._set_tag(tag_type, object_id, tag)
    model._dirty = True
    model._invalidate_results()


def _execute_grouped_points_import(
    model: "SWMMModel",
    df: pd.DataFrame,
    *,
    schema: ImportSchema,
    result: ImportResult,
    matches: dict[str, str],
    mode: str,
    on_missing_required: str,
    on_error: str,
    dry_run: bool,
) -> ImportResult:
    """Import time series from one or many rows per ID."""

    grouped: dict[str, list[tuple[Any, Any]]] = {}
    descriptions: dict[str, Any] = {}
    filenames: dict[str, Any] = {}
    for frame_index, row in df.iterrows():
        row_number = int(frame_index) + 2
        values = _canonical_row(row, matches)
        missing = [field for field in ("id",) if field not in values]
        if missing:
            if on_missing_required == "skip":
                result.rows_skipped += 1
                result.add_issue("error", "Missing required field: id.", row_number=row_number, field="id")
                continue
            raise SwmmxImportValidationError("Missing required field: id.")
        series_id = str(values["id"])
        if "filename" in values:
            filenames[series_id] = values["filename"]
            continue
        timestamp = values.get("datetime")
        if timestamp is None and "date" in values and "time" in values:
            timestamp = f"{values['date']} {values['time']}"
        elif timestamp is None and "time" in values:
            timestamp = values["time"]
        if timestamp is None or "value" not in values:
            _handle_row_error(result, row_number, "datetime", SwmmxImportValidationError("Time series rows require datetime+value or date+time+value."), on_error)
            continue
        grouped.setdefault(series_id, []).append((timestamp, values["value"]))
        if "description" in values:
            descriptions[series_id] = values["description"]
    for series_id in list(grouped) + [key for key in filenames if key not in grouped]:
        values = {"id": series_id}
        if series_id in filenames:
            values["filename"] = filenames[series_id]
        else:
            values["data"] = grouped[series_id]
            if series_id in descriptions:
                values["description"] = descriptions[series_id]
        _process_single_row(model, schema=schema, values=values, result=result, row_number=None or 0, mode=mode, on_missing_required=on_missing_required, on_error=on_error, dry_run=dry_run, overwrite_geometry=True)
    return result


def _execute_grouped_curve_import(
    model: "SWMMModel",
    df: pd.DataFrame,
    *,
    schema: ImportSchema,
    result: ImportResult,
    matches: dict[str, str],
    mode: str,
    on_missing_required: str,
    on_error: str,
    dry_run: bool,
) -> ImportResult:
    """Import curve rows grouped by ID."""

    curves: dict[str, dict[str, Any]] = {}
    for frame_index, row in df.iterrows():
        row_number = int(frame_index) + 2
        values = _canonical_row(row, matches)
        for field in ("id", "x", "y"):
            if field not in values:
                _handle_row_error(result, row_number, field, SwmmxImportValidationError(f"Missing required field: {field}."), on_error)
                break
        else:
            bucket = curves.setdefault(str(values["id"]), {"id": str(values["id"]), "points": [], "type": values.get("type", "GENERIC")})
            bucket["points"].append((values["x"], values["y"]))
    for values in curves.values():
        curve_id = values["id"]
        try:
            exists = _object_exists(model, schema, curve_id)
            action = _resolve_action(mode, exists, schema, curve_id)
            if dry_run:
                if action == "add":
                    result.rows_imported += 1
                else:
                    result.rows_updated += 1
                continue
            snap = _snapshot(model)
            try:
                if action == "update":
                    _remove_existing(model, schema, curve_id, overwrite_geometry=True)
                getattr(model.add.curve, "generic")(curve_id, type=values.get("type", "GENERIC"), points=values["points"])
            except Exception:
                _restore(model, snap)
                raise
            if action == "add":
                result.rows_imported += 1
            else:
                result.rows_updated += 1
        except Exception as exc:
            _handle_row_error(result, 0, None, exc, on_error)
    return result


def _execute_coordinate_import(
    model: "SWMMModel",
    df: pd.DataFrame,
    *,
    schema: ImportSchema,
    result: ImportResult,
    matches: dict[str, str],
    mode: str,
    on_missing_required: str,
    on_error: str,
    dry_run: bool,
    overwrite_geometry: bool,
) -> ImportResult:
    """Import map geometry helper tables."""

    section = {
        "node_coordinates": "COORDINATES",
        "link_vertices": "VERTICES",
        "polygons": "POLYGONS",
        "labels": "LABELS",
    }[schema.element_type]
    grouped: dict[str, list[tuple[Any, Any]]] = {}
    for frame_index, row in df.iterrows():
        row_number = int(frame_index) + 2
        values = _canonical_row(row, matches)
        missing = [field for field in schema.required_fields if field not in values]
        if missing:
            _handle_row_error(result, row_number, missing[0], SwmmxImportValidationError(f"Missing required field(s): {', '.join(missing)}."), on_error)
            continue
        key = str(values.get("id", values.get("text", "")))
        if dry_run:
            result.rows_imported += 1
            continue
        if schema.element_type == "labels":
            model._document.append_row(section, [values["x"], values["y"], values["text"], values.get("anchor_node"), values.get("font"), values.get("size")])
            result.rows_imported += 1
        elif schema.element_type == "node_coordinates":
            exists = any(row and row[0] == key for row in model._document.rows(section))
            action = _resolve_action(mode, exists, schema, key)
            if action == "update" and overwrite_geometry:
                model._document.remove_rows(section, [key])
            model._document.append_row(section, [key, values["x"], values["y"]])
            result.rows_imported += action == "add"
            result.rows_updated += action == "update"
        else:
            grouped.setdefault(key, []).append((values["x"], values["y"]))
    if not dry_run and schema.element_type in {"link_vertices", "polygons"}:
        for key, points in grouped.items():
            exists = any(row and row[0] == key for row in model._document.rows(section))
            action = _resolve_action(mode, exists, schema, key)
            if action == "update" and overwrite_geometry:
                model._document.remove_rows(section, [key])
            for x, y in points:
                model._document.append_row(section, [key, x, y])
            result.rows_imported += action == "add"
            result.rows_updated += action == "update"
    if not dry_run and (result.rows_imported or result.rows_updated):
        model._dirty = True
        model._invalidate_results()
    return result


def _coerce_points(value: Any) -> list[tuple[Any, Any]]:
    if isinstance(value, str):
        points: list[tuple[Any, Any]] = []
        for pair in value.replace(";", "|").split("|"):
            if not pair.strip():
                continue
            first, second = pair.replace(",", " ").split()[:2]
            points.append((float(first), float(second)))
        return points
    return [tuple(point) for point in value]
