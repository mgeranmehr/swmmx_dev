"""Shared data collection and validation helpers for export frontends."""

from __future__ import annotations

from collections import OrderedDict
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING
import json
import re
import warnings

import numpy as np
import pandas as pd

from ..errors import ExportError, ModelNotRunError, UnknownExportElementError

if TYPE_CHECKING:
    from ..api import SWMMModel


EXPORT_ORDER = (
    "rain_gages",
    "subcatchments",
    "aquifers",
    "snow_packs",
    "unit_hydrographs",
    "lid_controls",
    "lid_usage",
    "nodes",
    "junctions",
    "outfalls",
    "dividers",
    "storage_units",
    "links",
    "conduits",
    "pumps",
    "orifices",
    "weirs",
    "outlets",
    "streets",
    "inlets",
    "transects",
    "pollutants",
    "land_uses",
    "coverages",
    "loadings",
    "buildups",
    "washoffs",
    "treatments",
    "curves",
    "time_series",
    "time_patterns",
    "external_inflows",
    "dry_weather_flows",
    "rdii",
    "control_rules",
)

GROUPS = {
    "all": EXPORT_ORDER,
    "hydrology": (
        "rain_gages",
        "subcatchments",
        "aquifers",
        "snow_packs",
        "unit_hydrographs",
        "lid_controls",
        "lid_usage",
    ),
    "quality": (
        "pollutants",
        "land_uses",
        "coverages",
        "loadings",
        "buildups",
        "washoffs",
        "treatments",
    ),
    "curves": ("curves",),
    "time": ("time_series", "time_patterns", "external_inflows", "dry_weather_flows", "rdii"),
    "controls": ("control_rules",),
}

VALID_EXPORT_NAMES = set(EXPORT_ORDER) | set(GROUPS) | {"nodes", "links"}

SIMPLE_SECTIONS = {
    "rain_gages": (
        "RAINGAGES",
        ("id", "format", "interval", "snow_catch_factor", "source_type", "source_data", "station", "units"),
    ),
    "aquifers": (
        "AQUIFERS",
        (
            "id",
            "porosity",
            "wilting_point",
            "field_capacity",
            "conductivity",
            "conductivity_slope",
            "tension_slope",
            "upper_evaporation_fraction",
            "lower_evaporation_depth",
            "lower_groundwater_loss_rate",
            "bottom_elevation",
            "water_table_elevation",
            "unsaturated_moisture",
            "upper_evaporation_pattern",
        ),
    ),
    "snow_packs": ("SNOWPACKS", ("id", "surface", "parameter", "value_1", "value_2", "value_3", "value_4", "value_5", "value_6", "value_7")),
    "unit_hydrographs": ("HYDROGRAPHS", ("id", "rain_gage", "month", "r", "t", "k")),
    "lid_controls": ("LID_CONTROLS", ("id", "layer", "value_1", "value_2", "value_3", "value_4", "value_5", "value_6", "value_7")),
    "lid_usage": ("LID_USAGE", ("subcatchment_id", "lid_control", "number", "area", "width", "initial_saturation", "impervious_treated_percent", "out_to_pervious", "report_file", "drain_to", "from_pervious_percent")),
    "junctions": ("JUNCTIONS", ("id", "invert_elevation", "max_depth", "initial_depth", "surcharge_depth", "ponded_area")),
    "outfalls": ("OUTFALLS", ("id", "invert_elevation", "type", "stage_data", "tide_gate", "route_to")),
    "dividers": ("DIVIDERS", ("id", "invert_elevation", "diverted_link", "type", "parameter_1", "parameter_2", "parameter_3", "max_depth", "initial_depth", "surcharge_depth", "ponded_area")),
    "storage_units": ("STORAGE", ("id", "invert_elevation", "max_depth", "initial_depth", "storage_curve_type", "storage_curve", "area_coefficient", "area_exponent", "area_constant", "evaporation_factor", "seepage_loss")),
    "conduits": ("CONDUITS", ("id", "from_node", "to_node", "length", "roughness", "inlet_offset", "outlet_offset", "initial_flow", "maximum_flow")),
    "pumps": ("PUMPS", ("id", "from_node", "to_node", "curve", "initial_status", "startup_depth", "shutoff_depth")),
    "orifices": ("ORIFICES", ("id", "from_node", "to_node", "type", "offset", "discharge_coefficient", "flap_gate", "open_close_time")),
    "weirs": ("WEIRS", ("id", "from_node", "to_node", "type", "crest_height", "discharge_coefficient", "flap_gate", "end_contractions", "end_coefficient", "surcharge", "road_width", "road_surface")),
    "outlets": ("OUTLETS", ("id", "from_node", "to_node", "offset", "rating_type", "curve_or_coefficient", "exponent", "flap_gate")),
    "streets": ("STREETS", ("id", "crown_width", "curb_height", "cross_slope", "roughness", "depression_storage", "gutter_width", "gutter_slope")),
    "inlets": ("INLETS", ("id", "type", "parameter_1", "parameter_2", "parameter_3", "parameter_4")),
    "transects": ("TRANSECTS", ("id", "record_type", "value_1", "value_2", "value_3", "value_4", "value_5")),
    "pollutants": ("POLLUTANTS", ("id", "units", "rain_concentration", "groundwater_concentration", "rdii_concentration", "decay_coefficient", "snow_only", "co_pollutant", "co_pollutant_fraction", "dry_weather_flow_concentration", "initial_concentration")),
    "land_uses": ("LANDUSES", ("id", "sweeping_interval", "sweeping_availability", "last_swept")),
    "coverages": ("COVERAGES", ("subcatchment_id", "land_use", "percent")),
    "loadings": ("LOADINGS", ("subcatchment_id", "pollutant", "buildup")),
    "buildups": ("BUILDUP", ("land_use", "pollutant", "function", "coefficient_1", "coefficient_2", "coefficient_3", "per_unit")),
    "washoffs": ("WASHOFF", ("land_use", "pollutant", "function", "coefficient_1", "coefficient_2", "sweep_removal", "bmp_removal")),
    "treatments": ("TREATMENT", ("node_id", "pollutant", "expression")),
    "time_patterns": ("PATTERNS", ("id", "type", "multiplier_1", "multiplier_2", "multiplier_3", "multiplier_4", "multiplier_5", "multiplier_6", "multiplier_7", "multiplier_8", "multiplier_9", "multiplier_10", "multiplier_11", "multiplier_12", "multiplier_13", "multiplier_14", "multiplier_15", "multiplier_16", "multiplier_17", "multiplier_18", "multiplier_19", "multiplier_20", "multiplier_21", "multiplier_22", "multiplier_23", "multiplier_24")),
    "external_inflows": ("INFLOWS", ("node_id", "constituent", "time_series", "type", "m_factor", "s_factor", "baseline", "baseline_pattern")),
    "dry_weather_flows": ("DWF", ("node_id", "constituent", "average_value", "time_pattern_1", "time_pattern_2", "time_pattern_3", "time_pattern_4")),
    "rdii": ("RDII", ("node_id", "unit_hydrograph", "sewershed_area")),
}

RESULT_VARIABLES = {
    "nodes": ("node", ("depth", "head", "flooding", "total_inflow", "volume")),
    "junctions": ("node", ("depth", "head", "flooding", "total_inflow", "volume")),
    "outfalls": ("node", ("depth", "head", "flooding", "total_inflow", "volume")),
    "dividers": ("node", ("depth", "head", "flooding", "total_inflow", "volume")),
    "storage_units": ("node", ("depth", "head", "flooding", "total_inflow", "volume")),
    "links": ("link", ("flow", "depth", "velocity", "capacity", "volume")),
    "conduits": ("conduit", ("flow", "depth", "velocity", "capacity")),
    "pumps": ("link", ("flow", "depth", "velocity", "capacity", "volume")),
    "orifices": ("link", ("flow", "depth", "velocity", "capacity", "volume")),
    "weirs": ("link", ("flow", "depth", "velocity", "capacity", "volume")),
    "outlets": ("link", ("flow", "depth", "velocity", "capacity", "volume")),
    "subcatchments": ("subcatchment", ("runoff", "rainfall", "infiltration", "evaporation")),
}

NODE_EXPORT_ELEMENTS = {"nodes", "junctions", "outfalls", "dividers", "storage_units"}
LINK_EXPORT_ELEMENTS = {"links", "conduits", "pumps", "orifices", "weirs", "outlets"}
NODE_ATTACHED_EXPORT_ELEMENTS = {"external_inflows", "dry_weather_flows", "rdii", "treatments"}
RAINGAGE_ATTACHED_EXPORT_ELEMENTS = {"unit_hydrographs"}
SUBCATCHMENT_ATTACHED_EXPORT_ELEMENTS = {"coverages", "loadings", "lid_usage"}
XY_EXPORT_ELEMENTS = (
    NODE_EXPORT_ELEMENTS
    | {"rain_gages", "subcatchments"}
    | NODE_ATTACHED_EXPORT_ELEMENTS
    | RAINGAGE_ATTACHED_EXPORT_ELEMENTS
    | SUBCATCHMENT_ATTACHED_EXPORT_ELEMENTS
)


def _xy_map(model: "SWMMModel", section: str) -> dict[str, tuple[float, float]]:
    """Return ID-indexed XY points from one ordinary map-coordinate section."""

    points: dict[str, tuple[float, float]] = {}
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            points[str(row[0])] = (float(row[1]), float(row[2]))
        except (TypeError, ValueError):
            continue
    return points


def _grouped_xy_map(model: "SWMMModel", section: str) -> dict[str, list[tuple[float, float]]]:
    """Return ID-indexed ordered XY point lists from a map-coordinate section."""

    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            grouped.setdefault(str(row[0]), []).append((float(row[1]), float(row[2])))
        except (TypeError, ValueError):
            continue
    return grouped


def _link_endpoint_rows(model: "SWMMModel") -> dict[str, tuple[str, str]]:
    """Return link endpoint IDs for ordinary routed link sections."""

    endpoints: dict[str, tuple[str, str]] = {}
    for section in ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"):
        for row in model._document.rows(section):
            if len(row) >= 3:
                endpoints[str(row[0])] = (str(row[1]), str(row[2]))
    return endpoints


def _coordinate_maps(model: "SWMMModel") -> dict[str, object]:
    """Collect map-coordinate lookup tables used by all export frontends."""

    return {
        "nodes": _xy_map(model, "COORDINATES"),
        "rain_gages": _xy_map(model, "SYMBOLS"),
        "vertices": _grouped_xy_map(model, "VERTICES"),
        "polygons": _grouped_xy_map(model, "POLYGONS"),
        "endpoints": _link_endpoint_rows(model),
    }


def _json_coordinates(value) -> str | None:
    """Serialize point/list geometry into a stable CSV/Excel/GIS attribute value."""

    if value is None:
        return None
    if isinstance(value, tuple):
        value = list(value)
    elif isinstance(value, list):
        value = [list(point) if isinstance(point, tuple) else point for point in value]
    return json.dumps(value, separators=(",", ":"))


def _polygon_centroid(points: list[tuple[float, float]] | None) -> tuple[float, float] | None:
    """Return the geometric centroid of a polygon point sequence."""

    if not points:
        return None
    if len(points) < 3:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    area_twice = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for point, next_point in zip(points, [*points[1:], points[0]]):
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        area_twice += cross
        cx_sum += (point[0] + next_point[0]) * cross
        cy_sum += (point[1] + next_point[1]) * cross
    if abs(area_twice) < 1e-12:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    return cx_sum / (3.0 * area_twice), cy_sum / (3.0 * area_twice)


def _row_field(row: pd.Series, name: str) -> str | None:
    """Return a non-empty string value from a row field."""

    value = row.get(name)
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value)
    return text if text else None


def _link_coordinates(link_id: str, maps: dict[str, object]):
    """Return the best available full coordinate chain for one link."""

    node_points: dict[str, tuple[float, float]] = maps["nodes"]  # type: ignore[assignment]
    vertices: dict[str, list[tuple[float, float]]] = maps["vertices"]  # type: ignore[assignment]
    endpoints: dict[str, tuple[str, str]] = maps["endpoints"]  # type: ignore[assignment]
    endpoint_pair = endpoints.get(link_id)
    if endpoint_pair and endpoint_pair[0] in node_points and endpoint_pair[1] in node_points:
        return [node_points[endpoint_pair[0]], *vertices.get(link_id, []), node_points[endpoint_pair[1]]]
    return vertices.get(link_id)


def _coordinates_for_row(element: str, row: pd.Series, maps: dict[str, object]):
    """Return the map coordinates associated with one export row, when available."""

    node_points: dict[str, tuple[float, float]] = maps["nodes"]  # type: ignore[assignment]
    rain_points: dict[str, tuple[float, float]] = maps["rain_gages"]  # type: ignore[assignment]
    polygons: dict[str, list[tuple[float, float]]] = maps["polygons"]  # type: ignore[assignment]

    object_id = _row_field(row, "id")
    if element in NODE_EXPORT_ELEMENTS and object_id is not None:
        return node_points.get(object_id)
    if element in LINK_EXPORT_ELEMENTS and object_id is not None:
        return _link_coordinates(object_id, maps)
    if element == "rain_gages" and object_id is not None:
        return rain_points.get(object_id)
    if element == "subcatchments" and object_id is not None:
        return polygons.get(object_id)

    subcatchment_id = _row_field(row, "subcatchment_id")
    if subcatchment_id is not None and subcatchment_id in polygons:
        return polygons[subcatchment_id]
    node_id = _row_field(row, "node_id")
    if node_id is not None and node_id in node_points:
        return node_points[node_id]

    if object_id is not None:
        if object_id in node_points:
            return node_points[object_id]
        if object_id in rain_points:
            return rain_points[object_id]
        if object_id in polygons:
            return polygons[object_id]
        link_coordinates = _link_coordinates(object_id, maps)
        if link_coordinates:
            return link_coordinates
    return None


def _xy_for_row(element: str, row: pd.Series, maps: dict[str, object]) -> tuple[float, float] | None:
    """Return point-style x/y coordinates for node-like export rows."""

    node_points: dict[str, tuple[float, float]] = maps["nodes"]  # type: ignore[assignment]
    rain_points: dict[str, tuple[float, float]] = maps["rain_gages"]  # type: ignore[assignment]
    polygons: dict[str, list[tuple[float, float]]] = maps["polygons"]  # type: ignore[assignment]

    object_id = _row_field(row, "id")
    if element in NODE_EXPORT_ELEMENTS and object_id is not None:
        return node_points.get(object_id)
    if element == "rain_gages" and object_id is not None:
        return rain_points.get(object_id)
    if element == "subcatchments" and object_id is not None:
        return _polygon_centroid(polygons.get(object_id))
    if element in LINK_EXPORT_ELEMENTS:
        return None

    node_id = _row_field(row, "node_id")
    if element in NODE_ATTACHED_EXPORT_ELEMENTS and node_id is not None:
        return node_points.get(node_id)
    rain_gage_id = _row_field(row, "rain_gage")
    if element in RAINGAGE_ATTACHED_EXPORT_ELEMENTS and rain_gage_id is not None:
        return rain_points.get(rain_gage_id)
    subcatchment_id = _row_field(row, "subcatchment_id")
    if element in SUBCATCHMENT_ATTACHED_EXPORT_ELEMENTS and subcatchment_id is not None:
        return _polygon_centroid(polygons.get(subcatchment_id))
    return None


def _attach_spatial_fields(model: "SWMMModel", element: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Add shared serialized coordinates plus node-like ``x``/``y`` columns."""

    result = frame.copy()
    maps = _coordinate_maps(model)
    if result.empty:
        if "coordinates" not in result.columns:
            result["coordinates"] = pd.Series(dtype=object)
        if element in XY_EXPORT_ELEMENTS:
            if "x" not in result.columns:
                result["x"] = pd.Series(dtype=float)
            if "y" not in result.columns:
                result["y"] = pd.Series(dtype=float)
        return result
    rows = list(result.iterrows())
    if "coordinates" not in result.columns:
        result["coordinates"] = [
            _json_coordinates(_coordinates_for_row(element, row, maps))
            for _index, row in rows
        ]
    if element in XY_EXPORT_ELEMENTS and ("x" not in result.columns or "y" not in result.columns):
        xy_values = [_xy_for_row(element, row, maps) for _index, row in rows]
        if "x" not in result.columns:
            result["x"] = [point[0] if point is not None else None for point in xy_values]
        if "y" not in result.columns:
            result["y"] = [point[1] if point is not None else None for point in xy_values]
    return result


def _rows_to_frame(rows: list[list[str]], columns: tuple[str, ...]) -> pd.DataFrame:
    """Convert possibly ragged token rows into a stable DataFrame."""

    width = max(len(columns), max((len(row) for row in rows), default=0))
    full_columns = list(columns) + [f"value_{index}" for index in range(len(columns) + 1, width + 1)]
    normalized = [row + [None] * (width - len(row)) for row in rows]
    return pd.DataFrame(normalized, columns=full_columns)


def _simple_frame(model: "SWMMModel", element: str) -> pd.DataFrame:
    """Return one ordinary direct-section export table."""

    section, columns = SIMPLE_SECTIONS[element]
    return _rows_to_frame(model._document.rows(section), columns)


def _subcatchment_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return subcatchments with associated subarea and infiltration fields."""

    base = _rows_to_frame(
        model._document.rows("SUBCATCHMENTS"),
        ("id", "rain_gage", "outlet", "area", "impervious_percent", "width", "slope", "curb_length", "snow_pack"),
    )
    subareas = _rows_to_frame(
        model._document.rows("SUBAREAS"),
        ("id", "n_impervious", "n_pervious", "depression_storage_impervious", "depression_storage_pervious", "zero_depression_storage_impervious_percent", "subarea_routing", "percent_routed"),
    )
    infiltration = _rows_to_frame(
        model._document.rows("INFILTRATION"),
        ("id", "infiltration_1", "infiltration_2", "infiltration_3", "infiltration_4", "infiltration_5"),
    )
    result = base
    if not subareas.empty:
        result = result.merge(subareas, on="id", how="left")
    if not infiltration.empty:
        result = result.merge(infiltration, on="id", how="left")
    return result


def _node_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return one union table for all modeled node types."""

    frames: list[pd.DataFrame] = []
    for element, element_type in (
        ("junctions", "junction"),
        ("outfalls", "outfall"),
        ("dividers", "divider"),
        ("storage_units", "storage_unit"),
    ):
        frame = _simple_frame(model, element)
        if not frame.empty:
            frame.insert(1, "element_type", element_type)
            frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=["id", "element_type"])


def _link_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return one union table for all modeled link types."""

    frames: list[pd.DataFrame] = []
    for element, element_type in (
        ("conduits", "conduit"),
        ("pumps", "pump"),
        ("orifices", "orifice"),
        ("weirs", "weir"),
        ("outlets", "outlet"),
    ):
        frame = _simple_frame(model, element)
        if not frame.empty:
            frame.insert(1, "element_type", element_type)
            frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=["id", "element_type"])


def _curve_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return curves with explicit, carried-forward curve type values."""

    rows = model._document.rows("CURVES")
    normalized: list[dict[str, object]] = []
    types: dict[str, str] = {}
    for row in rows:
        if len(row) >= 4:
            curve_id, curve_type, x_value, y_value = row[:4]
            if curve_type:
                types[curve_id] = curve_type
        elif len(row) >= 3:
            curve_id, x_value, y_value = row[:3]
            curve_type = types.get(curve_id)
        else:
            continue
        normalized.append({"curve_id": curve_id, "curve_type": curve_type or types.get(curve_id), "x": x_value, "y": y_value})
    return pd.DataFrame(normalized, columns=["curve_id", "curve_type", "x", "y"])


def _time_series_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return time-series rows with a best-effort timestamp column."""

    records: list[dict[str, object]] = []
    last_date_by_id: dict[str, str] = {}
    for row in model._document.rows("TIMESERIES"):
        if len(row) >= 3 and row[1].upper() == "FILE":
            records.append({"series_id": row[0], "source": "FILE", "filename": row[2], "timestamp": None, "value": None})
            continue
        if len(row) >= 4:
            series_id, date_text, time_text, value = row[:4]
            last_date_by_id[series_id] = date_text
        elif len(row) >= 3:
            series_id, time_text, value = row[:3]
            date_text = last_date_by_id.get(series_id)
        else:
            continue
        timestamp = pd.NaT
        if date_text:
            timestamp = pd.to_datetime(f"{date_text} {time_text}", errors="coerce")
        records.append({"series_id": series_id, "source": "INLINE", "timestamp": timestamp, "value": value})
    return pd.DataFrame(records, columns=["series_id", "source", "filename", "timestamp", "value"])


def _control_rules_frame(model: "SWMMModel") -> pd.DataFrame:
    """Return control rules as one text blob per named rule."""

    section = model._document.section("CONTROLS")
    if section is None:
        return pd.DataFrame(columns=["id", "text"])
    records: list[dict[str, str]] = []
    current_id: str | None = None
    current_lines: list[str] = []
    for line in section.lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if stripped.lower().startswith("rule "):
            if current_id is not None:
                records.append({"id": current_id, "text": "\n".join(current_lines)})
            current_id = stripped.split(maxsplit=1)[1]
            current_lines = [stripped]
        elif current_id is not None:
            current_lines.append(stripped)
    if current_id is not None:
        records.append({"id": current_id, "text": "\n".join(current_lines)})
    return pd.DataFrame(records, columns=["id", "text"])


def _base_frame(model: "SWMMModel", element: str) -> pd.DataFrame:
    """Return one parameter table before result or derived joins."""

    if element == "subcatchments":
        return _subcatchment_frame(model)
    if element == "nodes":
        return _node_frame(model)
    if element == "links":
        return _link_frame(model)
    if element == "curves":
        return _curve_frame(model)
    if element == "time_series":
        return _time_series_frame(model)
    if element == "control_rules":
        return _control_rules_frame(model)
    if element in SIMPLE_SECTIONS:
        return _simple_frame(model, element)
    raise UnknownExportElementError(f"Unknown export element '{element}'.")


def _suggestion_message(name: str) -> str:
    """Build a helpful typo suggestion suffix for unknown element errors."""

    suggestions = get_close_matches(name, sorted(VALID_EXPORT_NAMES), n=2, cutoff=0.45)
    if "pipe" in name.lower():
        for fallback in ("links", "conduits"):
            if fallback not in suggestions:
                suggestions.append(fallback)
    if not suggestions:
        return ""
    if len(suggestions) == 1:
        return f" Did you mean '{suggestions[0]}'?"
    return f" Did you mean '{suggestions[0]}' or '{suggestions[1]}'?"


def _resolve_export_elements(elements) -> list[str]:
    """Normalize element/group selection into ordered individual table names."""

    if isinstance(elements, str):
        requested = [elements]
    elif isinstance(elements, (list, tuple)) and all(isinstance(value, str) for value in elements):
        requested = list(elements)
    else:
        raise TypeError("'elements' must be 'all', one element name, or a list of element names.")
    resolved: list[str] = []
    for raw_name in requested:
        name = raw_name.strip().lower()
        if name not in VALID_EXPORT_NAMES:
            raise UnknownExportElementError(
                f"Unknown export element '{raw_name}'.{_suggestion_message(name)}"
            )
        expanded = GROUPS.get(name, (name,))
        for element in expanded:
            if element not in resolved:
                resolved.append(element)
    return [element for element in EXPORT_ORDER if element in resolved]


def _resolve_time_step(model: "SWMMModel", time_step) -> tuple[int, pd.Timestamp]:
    """Resolve an integer or exact timestamp selector against run timestamps."""

    if not model.has_run or model._run_timestamps is None:
        raise ModelNotRunError("Model results are not available. Run the model with m.run() first.")
    timestamps = pd.DatetimeIndex(model._run_timestamps)
    if isinstance(time_step, str):
        timestamp = pd.Timestamp(time_step)
        if timestamp not in timestamps:
            raise ExportError(f"Result timestamp '{timestamp}' is not available.")
        return int(timestamps.get_loc(timestamp)), timestamp
    if not isinstance(time_step, (int, np.integer)):
        raise TypeError("'time_step' must be an integer index or timestamp-like string.")
    index = int(time_step)
    if index < 0:
        index = len(timestamps) + index
    if index < 0 or index >= len(timestamps):
        raise ExportError(f"Result time_step '{time_step}' is outside the available range.")
    return index, pd.Timestamp(timestamps[index])


def _get_result_snapshot(model: "SWMMModel", element: str, ids: list[str], time_step) -> pd.DataFrame:
    """Return one selected result row joined by ID for a supported element."""

    if element not in RESULT_VARIABLES or not ids:
        return pd.DataFrame(columns=["id"])
    category, variables = RESULT_VARIABLES[element]
    index, timestamp = _resolve_time_step(model, time_step)
    data: dict[str, object] = {"id": ids}
    for variable in variables:
        try:
            frame = getattr(getattr(model.get, category), variable)(ids=ids, format="df")
        except Exception:
            continue
        data[variable] = frame.iloc[index].to_numpy()
    result = pd.DataFrame(data)
    result["result_time_step"] = index
    result["result_timestamp"] = timestamp
    return result


def _get_derived_table(model: "SWMMModel", element: str, ids: list[str]) -> pd.DataFrame:
    """Return readily available derived columns for one export element."""

    if element != "conduits" or not ids:
        return pd.DataFrame(columns=["id"])
    try:
        slopes = model.get.conduit.slope(ids=ids, format="np")
    except Exception:
        return pd.DataFrame(columns=["id"])
    return pd.DataFrame({"id": ids, "slope": slopes})


def _collect_export_tables(
    model: "SWMMModel",
    elements,
    *,
    include_parameters: bool = True,
    include_results: bool = True,
    include_derived: bool = True,
    time_step=-1,
    strict_results: bool = False,
) -> "OrderedDict[str, pd.DataFrame]":
    """Collect normalized export tables for all requested elements."""

    if not include_parameters and not include_results:
        raise ExportError("At least one of include_parameters or include_results must be True.")
    selected = _resolve_export_elements(elements)
    tables: "OrderedDict[str, pd.DataFrame]" = OrderedDict()

    results_available = model.has_run
    if include_results and not results_available:
        if strict_results:
            raise ModelNotRunError(
                "Result export requested but model results are unavailable. Run the model with m.run() first."
            )
        warnings.warn(
            "Model results are unavailable; exporting parameters only because strict_results=False.",
            stacklevel=2,
        )
    if include_results and results_available and model.results_stale:
        warnings.warn(
            "Model inputs have changed since the last run. Exported results may not match current inputs.",
            stacklevel=2,
        )

    explicit_all = isinstance(elements, str) and elements.strip().lower() == "all"
    for element in selected:
        frame = _base_frame(model, element)
        if frame.empty and explicit_all:
            continue
        id_column = "id" if "id" in frame.columns else None
        if not include_parameters:
            retained = [column for column in ("id", "element_type") if column in frame.columns]
            frame = frame.loc[:, retained].copy()
        else:
            frame = frame.copy()
        frame = _attach_spatial_fields(model, element, frame)
        if include_derived and include_parameters and id_column == "id" and not frame.empty:
            derived = _get_derived_table(model, element, frame["id"].astype(str).tolist())
            if len(derived.columns) > 1:
                frame = frame.merge(derived, on="id", how="left")
        if include_results and results_available and id_column == "id" and not frame.empty:
            snapshot = _get_result_snapshot(model, element, frame["id"].astype(str).tolist(), time_step)
            if len(snapshot.columns) > 1:
                frame = frame.merge(snapshot, on="id", how="left")
        tables[element] = frame
    return tables


def _get_default_export_path(model: "SWMMModel", path) -> Path:
    """Return a directory target rooted beside the model or current workspace."""

    target = Path(path).expanduser() if path is not None else (model.path.parent if model.path is not None else Path.cwd())
    return target.resolve()


def _default_model_stem(model: "SWMMModel") -> str:
    """Return a stable export stem from the model path when possible."""

    return model.path.stem if model.path is not None else "swmmx_export"


def _sanitize_filename(name: str) -> str:
    """Return a filesystem-friendly filename stem."""

    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return sanitized or "swmmx_export"


def _csv_file_name(model: "SWMMModel", element: str, file_name: str | None, table_count: int) -> str:
    """Return the output CSV filename for one table."""

    if file_name is None:
        prefix = _default_model_stem(model) if model.path is not None else "swmmx"
        return f"{_sanitize_filename(prefix)}_{element}.csv"
    candidate = Path(file_name)
    stem = _sanitize_filename(candidate.stem if candidate.suffix else candidate.name)
    if table_count == 1:
        return f"{stem}.csv"
    return f"{stem}_{element}.csv"


def _excel_file_name(model: "SWMMModel", file_name: str | None) -> str:
    """Return a valid workbook filename or raise a helpful error."""

    if file_name is None:
        return f"{_sanitize_filename(_default_model_stem(model))}_export.xlsx"
    candidate = Path(file_name)
    if candidate.suffix.lower() != ".xlsx":
        raise ExportError("Excel export file name must end with .xlsx.")
    return candidate.name


def _sanitize_excel_sheet_name(name: str, used: set[str]) -> str:
    """Return a unique Excel-safe sheet name capped at 31 characters."""

    base = re.sub(r"[:\\/?*\[\]]+", "_", name)[:31] or "sheet"
    candidate = base
    suffix = 1
    while candidate in used:
        suffix_text = f"_{suffix}"
        candidate = f"{base[:31 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used.add(candidate)
    return candidate
