"""Annotation helpers for layout plots."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
import warnings
from typing import TYPE_CHECKING, Any

import pandas as pd
from matplotlib.transforms import ScaledTranslation

from ..errors import PlotDataError

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from ..api import SWMMModel


NODE_SECTION_SPECS = {
    "JUNCTIONS": (
        "junction",
        ("id", "invert_elevation", "max_depth", "initial_depth", "surcharge_depth", "ponded_area"),
    ),
    "OUTFALLS": (
        "outfall",
        ("id", "invert_elevation", "type", "stage_data", "tide_gate", "route_to"),
    ),
    "DIVIDERS": (
        "divider",
        (
            "id",
            "invert_elevation",
            "diverted_link",
            "type",
            "parameter_1",
            "parameter_2",
            "parameter_3",
            "max_depth",
            "initial_depth",
            "surcharge_depth",
            "ponded_area",
        ),
    ),
    "STORAGE": (
        "storage_unit",
        (
            "id",
            "invert_elevation",
            "max_depth",
            "initial_depth",
            "storage_curve_type",
            "storage_curve",
            "area_coefficient",
            "area_exponent",
            "area_constant",
            "evaporation_factor",
            "seepage_loss",
        ),
    ),
}

LINK_SECTION_SPECS = {
    "CONDUITS": (
        "conduit",
        ("id", "from_node", "to_node", "length", "roughness", "inlet_offset", "outlet_offset", "initial_flow", "maximum_flow"),
    ),
    "PUMPS": (
        "pump",
        ("id", "from_node", "to_node", "curve", "initial_status", "startup_depth", "shutoff_depth"),
    ),
    "ORIFICES": (
        "orifice",
        ("id", "from_node", "to_node", "type", "offset", "discharge_coefficient", "flap_gate", "open_close_time"),
    ),
    "WEIRS": (
        "weir",
        (
            "id",
            "from_node",
            "to_node",
            "type",
            "crest_height",
            "discharge_coefficient",
            "length",
            "flap_gate",
            "end_contractions",
            "end_coefficient",
            "surcharge",
            "road_width",
            "road_surface",
        ),
    ),
    "OUTLETS": (
        "outlet",
        ("id", "from_node", "to_node", "offset", "rating_type", "curve_or_coefficient", "exponent", "flap_gate"),
    ),
}

SUBCATCHMENT_FIELDS = (
    "id",
    "rain_gage",
    "outlet",
    "area",
    "impervious_percent",
    "width",
    "slope",
    "curb_length",
    "snow_pack",
)

SUBAREA_FIELDS = (
    "id",
    "n_impervious",
    "n_pervious",
    "depression_storage_impervious",
    "depression_storage_pervious",
    "zero_depression_storage_impervious_percent",
    "subarea_routing",
    "percent_routed",
)

RAIN_GAGE_FIELDS = (
    "id",
    "format",
    "interval",
    "snow_catch_factor",
    "source_type",
    "source_data",
    "station",
    "units",
)

LID_USAGE_FIELDS = (
    "subcatchment_id",
    "lid_control",
    "number",
    "area",
    "width",
    "initial_saturation",
    "impervious_treated_percent",
    "out_to_pervious",
    "report_file",
    "drain_to",
    "from_pervious_percent",
)

LAYER_ALIASES = {
    "node": "nodes",
    "nodes": "nodes",
    "junction": "junctions",
    "junctions": "junctions",
    "outfall": "outfalls",
    "outfalls": "outfalls",
    "flowdivider": "dividers",
    "flowdividers": "dividers",
    "flow_divider": "dividers",
    "flow_dividers": "dividers",
    "divider": "dividers",
    "dividers": "dividers",
    "storage": "storage_units",
    "storages": "storage_units",
    "storageunit": "storage_units",
    "storageunits": "storage_units",
    "storage_unit": "storage_units",
    "storage_units": "storage_units",
    "link": "links",
    "links": "links",
    "conduit": "conduits",
    "conduits": "conduits",
    "pump": "pumps",
    "pumps": "pumps",
    "orifice": "orifices",
    "orifices": "orifices",
    "weir": "weirs",
    "weirs": "weirs",
    "outlet": "outlets",
    "outlets": "outlets",
    "subcatchment": "subcatchments",
    "subcatchments": "subcatchments",
    "raingage": "rain_gages",
    "raingages": "rain_gages",
    "rain_gage": "rain_gages",
    "rain_gages": "rain_gages",
    "raingauge": "rain_gages",
    "raingauges": "rain_gages",
    "rain_gauge": "rain_gages",
    "rain_gauges": "rain_gages",
    "lid": "lid_usages",
    "lids": "lid_usages",
    "lidusage": "lid_usages",
    "lidusages": "lid_usages",
    "lid_usage": "lid_usages",
    "lid_usages": "lid_usages",
    "label": "labels",
    "labels": "labels",
}

POINT_LAYERS = {"nodes", "junctions", "outfalls", "dividers", "storage_units", "rain_gages", "lid_usages", "labels"}
LINE_LAYERS = {"links", "conduits", "pumps", "orifices", "weirs", "outlets"}
POLYGON_LAYERS = {"subcatchments"}

TEXT_STYLE_KEYS = {
    "fontsize",
    "color",
    "alpha",
    "fontweight",
    "fontstyle",
    "ha",
    "va",
    "zorder",
    "clip_on",
}

STYLE_KEYS = TEXT_STYLE_KEYS | {
    "offset",
    "rotation",
    "bbox",
    "bbox_alpha",
    "bbox_facecolor",
    "bbox_edgecolor",
}

VALID_ANNOTATION_ERRORS = {"raise", "skip", "warn"}
VALID_MISSING_DATA = {"empty", "skip", "raise", "warn"}
VALID_WHERE_OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "in", "not in"}
TEXTUAL_FIELDS = {
    "id",
    "from_node",
    "to_node",
    "type",
    "element_type",
    "node_type",
    "link_type",
    "rain_gage",
    "outlet",
    "source_type",
    "source_data",
    "station",
    "units",
    "shape",
    "flap_gate",
    "tide_gate",
    "route_to",
    "curve",
    "initial_status",
    "rating_type",
    "subarea_routing",
    "snow_pack",
    "lid_control",
    "subcatchment_id",
    "report_file",
    "drain_to",
    "text",
    "label",
    "anchor_node",
    "font",
}

NODE_RESULT_FIELDS = ("depth", "head", "flooding", "total_inflow", "volume")
LINK_RESULT_FIELDS = ("flow", "depth", "velocity", "capacity", "volume")
SUBCATCHMENT_RESULT_FIELDS = ("runoff", "rainfall", "infiltration", "evaporation")


@dataclass(frozen=True)
class AnnotationData:
    """Normalized external user annotation data."""

    rows: dict[str, dict[str, Any]]
    fields: tuple[str, ...]


def normalize_annotation_layer_key(key: str) -> str:
    """Return a canonical annotation layer key or raise a clear error."""

    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    compact = normalized.replace("_", "")
    canonical = LAYER_ALIASES.get(normalized) or LAYER_ALIASES.get(compact)
    if canonical is None:
        valid = ", ".join(sorted(set(LAYER_ALIASES.values())))
        raise PlotDataError(f"Unknown annotation layer '{key}'. Supported layers include: {valid}.")
    return canonical


def normalize_annotation_config(annotation) -> dict[str, dict[str, Any]]:
    """Normalize all public ``annotation=`` forms into layer dictionaries."""

    if annotation is None:
        return {}
    if isinstance(annotation, str) or callable(annotation) or _is_string_sequence(annotation):
        return {"nodes": _normalize_layer_config("nodes", annotation)}
    if not isinstance(annotation, Mapping):
        raise TypeError("'annotation' must be None, a string, a list of strings, a dictionary, or a callable.")

    normalized: dict[str, dict[str, Any]] = {}
    for raw_layer, raw_config in annotation.items():
        layer = normalize_annotation_layer_key(str(raw_layer))
        normalized[layer] = _normalize_layer_config(layer, raw_config)
    return normalized


def _normalize_layer_config(layer: str, raw_config) -> dict[str, Any]:
    """Normalize one layer's annotation declaration."""

    config = _base_config(layer)
    if isinstance(raw_config, str):
        config["fields"] = [raw_config]
    elif _is_string_sequence(raw_config):
        config["fields"] = list(raw_config)
    elif callable(raw_config):
        config["callable"] = raw_config
    elif isinstance(raw_config, Mapping):
        raw = dict(raw_config)
        if "fields" in raw:
            fields = raw.pop("fields")
            if isinstance(fields, str):
                config["fields"] = [fields]
            elif _is_string_sequence(fields):
                config["fields"] = list(fields)
            else:
                raise TypeError("Annotation 'fields' must be a string or a list of strings.")
        if "field" in raw and not config["fields"]:
            config["fields"] = [str(raw.pop("field"))]
        if "template" in raw:
            config["template"] = raw.pop("template")
        if "callable" in raw:
            callback = raw.pop("callable")
            if not callable(callback):
                raise TypeError("Annotation 'callable' must be callable.")
            config["callable"] = callback
        for option in (
            "prefix",
            "suffix",
            "format",
            "ids",
            "where",
            "max_labels",
            "on_annotation_error",
            "show_field_names",
            "data",
            "data_id",
            "data_field",
            "user_data_priority",
            "on_missing_data",
        ):
            if option in raw:
                config[option] = raw.pop(option)
        for key in STYLE_KEYS:
            if key in raw:
                config["style"][key] = raw.pop(key)
        if raw:
            unknown = ", ".join(sorted(raw))
            raise PlotDataError(f"Unknown annotation option(s) for layer '{layer}': {unknown}.")
    else:
        raise TypeError(f"Annotation layer '{layer}' must be a string, list, dictionary, or callable.")

    if not config["fields"] and config["template"] is None and config["callable"] is None:
        config["fields"] = ["id"]
    if config["template"] is not None and not isinstance(config["template"], str):
        raise TypeError("Annotation 'template' must be a string.")
    if config["on_annotation_error"] not in VALID_ANNOTATION_ERRORS:
        raise ValueError("'on_annotation_error' must be 'raise', 'skip', or 'warn'.")
    if config["on_missing_data"] not in VALID_MISSING_DATA:
        raise ValueError("'on_missing_data' must be 'empty', 'skip', 'raise', or 'warn'.")
    if config["max_labels"] is not None:
        config["max_labels"] = int(config["max_labels"])
        if config["max_labels"] < 0:
            raise ValueError("'max_labels' must be non-negative.")
    config["style"] = _normalize_style(layer, config["style"])
    config["data"] = _normalize_user_data(
        config["data"],
        data_id=config["data_id"],
        data_field=config["data_field"],
    )
    return config


def _base_config(layer: str) -> dict[str, Any]:
    return {
        "fields": [],
        "template": None,
        "callable": None,
        "prefix": {},
        "suffix": {},
        "format": {},
        "ids": None,
        "where": None,
        "max_labels": None,
        "on_annotation_error": "raise",
        "show_field_names": None,
        "data": None,
        "data_id": "id",
        "data_field": None,
        "user_data_priority": False,
        "on_missing_data": "empty",
        "style": _default_style(layer),
    }


def _default_style(layer: str) -> dict[str, Any]:
    is_line = layer in LINE_LAYERS
    is_polygon = layer in POLYGON_LAYERS
    return {
        "fontsize": 8,
        "color": "black",
        "alpha": 1.0,
        "fontweight": "normal",
        "fontstyle": "normal",
        "offset": (0, 5) if is_line else ((0, 0) if is_polygon else (3, 3)),
        "ha": "center" if is_line or is_polygon else "left",
        "va": "center" if is_polygon else "bottom",
        "rotation": 0,
        "zorder": 50,
        "bbox": False,
        "bbox_alpha": 0.65,
        "bbox_facecolor": "white",
        "bbox_edgecolor": "none",
        "clip_on": False,
    }


def _normalize_style(layer: str, style: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {**_default_style(layer), **dict(style)}
    offset = normalized.get("offset", (0, 0))
    if not isinstance(offset, Sequence) or isinstance(offset, str) or len(offset) != 2:
        raise TypeError("Annotation style 'offset' must be a two-item sequence.")
    normalized["offset"] = (float(offset[0]), float(offset[1]))
    return normalized


def _is_string_sequence(value) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value)


def _normalize_user_data(data, *, data_id: str, data_field: str | None) -> AnnotationData | None:
    """Normalize user-supplied annotation data into an ID-indexed mapping."""

    if data is None:
        return None
    if isinstance(data, pd.Series):
        field = data_field or data.name
        if not field:
            raise PlotDataError("Annotation pandas Series data requires 'data_field' when the Series has no name.")
        return AnnotationData(
            rows={str(index): {str(field): _python_value(value)} for index, value in data.items()},
            fields=(str(field),),
        )
    if isinstance(data, pd.DataFrame):
        if data_id not in data.columns:
            raise PlotDataError(f"Annotation DataFrame data is missing the ID column '{data_id}'.")
        fields = tuple(str(column) for column in data.columns if column != data_id)
        rows = {
            str(row[data_id]): {str(field): _python_value(row[field]) for field in fields}
            for _index, row in data.iterrows()
        }
        return AnnotationData(rows=rows, fields=fields)
    if isinstance(data, Mapping):
        rows: dict[str, dict[str, Any]] = {}
        fields: set[str] = set()
        for object_id, value in data.items():
            if isinstance(value, Mapping):
                row = {str(key): _python_value(item) for key, item in value.items()}
            else:
                if not data_field:
                    raise PlotDataError("Simple dictionary annotation data requires 'data_field'.")
                row = {str(data_field): _python_value(value)}
            rows[str(object_id)] = row
            fields.update(row)
        return AnnotationData(rows=rows, fields=tuple(sorted(fields)))
    raise TypeError("Annotation 'data' must be a dictionary, pandas Series, or pandas DataFrame.")


def draw_layout_annotations(
    ax: "Axes",
    model: "SWMMModel",
    annotation,
    *,
    plot_context: Mapping[str, Any] | None = None,
) -> list:
    """Draw layout annotations and return the created text artists."""

    configs = normalize_annotation_config(annotation)
    if not configs:
        return []
    artists = []
    for layer, config in configs.items():
        records = build_annotation_records(model, layer, plot_context=plot_context)
        records = apply_annotation_filters(records, config, layer=layer)
        for record in records:
            text = format_annotation_text(record, config, layer=layer)
            if text in {None, ""}:
                continue
            artist = _draw_annotation_text(ax, record, str(text), config["style"])
            artists.append(artist)
    return artists


def build_annotation_records(
    model: "SWMMModel",
    layer_key: str,
    *,
    plot_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build positioned annotation records for one normalized layer."""

    layer = normalize_annotation_layer_key(layer_key)
    context = dict(plot_context or {})
    node_points = context.get("node_points") or _xy_rows(model, "COORDINATES")
    rain_points = context.get("rain_points") or _xy_rows(model, "SYMBOLS")
    polygons = context.get("polygons") or _grouped_xy_rows(model, "POLYGONS")
    vertices = context.get("vertices") or _grouped_xy_rows(model, "VERTICES")
    link_records = context.get("link_records") or _link_endpoints(model)
    subcatchment_centroids = context.get("subcatchment_centroids") or {
        object_id: _polygon_centroid(points)
        for object_id, points in polygons.items()
        if points
    }

    if layer in POINT_LAYERS and layer not in {"rain_gages", "lid_usages", "labels"}:
        records = _node_records(model, node_points)
        if layer != "nodes":
            target_type = {
                "junctions": "junction",
                "outfalls": "outfall",
                "dividers": "divider",
                "storage_units": "storage_unit",
            }[layer]
            records = [record for record in records if record.get("element_type") == target_type]
        _attach_result_fields(model, records, "node", NODE_RESULT_FIELDS)
        return records

    if layer in LINE_LAYERS:
        records = _link_records(model, node_points, vertices, link_records)
        if layer != "links":
            target_type = {
                "conduits": "conduit",
                "pumps": "pump",
                "orifices": "orifice",
                "weirs": "weir",
                "outlets": "outlet",
            }[layer]
            records = [record for record in records if record.get("element_type") == target_type]
        _attach_result_fields(model, records, "link", LINK_RESULT_FIELDS)
        _attach_conduit_slope(model, records)
        return records

    if layer == "subcatchments":
        records = _subcatchment_records(model, polygons, subcatchment_centroids)
        _attach_result_fields(model, records, "subcatchment", SUBCATCHMENT_RESULT_FIELDS)
        return records

    if layer == "rain_gages":
        return _rain_gage_records(model, rain_points)
    if layer == "lid_usages":
        return _lid_usage_annotation_records(model, subcatchment_centroids, context.get("lid_records"))
    if layer == "labels":
        return _label_records(model)
    return []


def _xy_rows(model: "SWMMModel", section: str) -> dict[str, tuple[float, float]]:
    points: dict[str, tuple[float, float]] = {}
    for row in model._document.rows(section):
        if len(row) >= 3:
            try:
                points[str(row[0])] = (float(row[1]), float(row[2]))
            except (TypeError, ValueError):
                continue
    return points


def _grouped_xy_rows(model: "SWMMModel", section: str) -> dict[str, list[tuple[float, float]]]:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in model._document.rows(section):
        if len(row) >= 3:
            try:
                grouped.setdefault(str(row[0]), []).append((float(row[1]), float(row[2])))
            except (TypeError, ValueError):
                continue
    return grouped


def _link_endpoints(model: "SWMMModel") -> dict[str, tuple[str, str, str]]:
    links: dict[str, tuple[str, str, str]] = {}
    for section, (element_type, _fields) in LINK_SECTION_SPECS.items():
        for row in model._document.rows(section):
            if len(row) >= 3:
                links[str(row[0])] = (str(row[1]), str(row[2]), element_type)
    return links


def _node_records(model: "SWMMModel", node_points: Mapping[str, tuple[float, float]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section, (element_type, fields) in NODE_SECTION_SPECS.items():
        for row in model._document.rows(section):
            if not row:
                continue
            object_id = str(row[0])
            point = node_points.get(object_id)
            if point is None:
                continue
            record = _row_record(fields, row)
            record.update(
                {
                    "id": object_id,
                    "element_type": element_type,
                    "node_type": element_type,
                    "layer": "nodes",
                    "x": point[0],
                    "y": point[1],
                    "annotation_x": point[0],
                    "annotation_y": point[1],
                    "coordinates": point,
                }
            )
            record.setdefault("type", element_type)
            records.append(record)
    return records


def _link_records(
    model: "SWMMModel",
    node_points: Mapping[str, tuple[float, float]],
    vertices: Mapping[str, list[tuple[float, float]]],
    link_records: Mapping[str, tuple[str, str, str]],
) -> list[dict[str, Any]]:
    xsections = _section_records(model, "XSECTIONS", ("id", "shape", "geometry_1", "geometry_2", "geometry_3", "geometry_4", "barrels", "culvert_code"))
    losses = _section_records(model, "LOSSES", ("id", "entry_loss", "exit_loss", "average_loss", "flap_gate", "seepage_rate"))
    records: list[dict[str, Any]] = []
    for section, (element_type, fields) in LINK_SECTION_SPECS.items():
        for row in model._document.rows(section):
            if len(row) < 3:
                continue
            object_id = str(row[0])
            from_node, to_node, _link_type = link_records.get(object_id, (str(row[1]), str(row[2]), element_type))
            if from_node not in node_points or to_node not in node_points:
                continue
            geometry = [node_points[from_node], *vertices.get(object_id, []), node_points[to_node]]
            point = _line_midpoint(geometry)
            record = _row_record(fields, row)
            record.update(
                {
                    "id": object_id,
                    "element_type": element_type,
                    "link_type": element_type,
                    "layer": "links",
                    "from_node": from_node,
                    "to_node": to_node,
                    "annotation_x": point[0],
                    "annotation_y": point[1],
                    "coordinates": geometry,
                    "vertices": vertices.get(object_id, []),
                    "angle": _line_angle(geometry),
                    "type": element_type,
                }
            )
            if object_id in xsections:
                record.update({key: value for key, value in xsections[object_id].items() if key != "id"})
                if "geometry_1" in record:
                    record.setdefault("diameter", record.get("geometry_1"))
                    record.setdefault("height", record.get("geometry_1"))
                if "geometry_2" in record:
                    record.setdefault("width", record.get("geometry_2"))
            if object_id in losses:
                record.update({key: value for key, value in losses[object_id].items() if key != "id"})
            records.append(record)
    return records


def _subcatchment_records(
    model: "SWMMModel",
    polygons: Mapping[str, list[tuple[float, float]]],
    centroids: Mapping[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    subareas = _section_records(model, "SUBAREAS", SUBAREA_FIELDS)
    records: list[dict[str, Any]] = []
    for row in model._document.rows("SUBCATCHMENTS"):
        if not row:
            continue
        object_id = str(row[0])
        point = centroids.get(object_id)
        if point is None:
            continue
        record = _row_record(SUBCATCHMENT_FIELDS, row)
        record.update({key: value for key, value in subareas.get(object_id, {}).items() if key != "id"})
        record.update(
            {
                "id": object_id,
                "element_type": "subcatchment",
                "layer": "subcatchments",
                "x": point[0],
                "y": point[1],
                "annotation_x": point[0],
                "annotation_y": point[1],
                "coordinates": polygons.get(object_id, []),
                "polygon": polygons.get(object_id, []),
            }
        )
        records.append(record)
    return records


def _rain_gage_records(model: "SWMMModel", rain_points: Mapping[str, tuple[float, float]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in model._document.rows("RAINGAGES"):
        if not row:
            continue
        object_id = str(row[0])
        point = rain_points.get(object_id)
        if point is None:
            continue
        record = _row_record(RAIN_GAGE_FIELDS, row)
        record.update(
            {
                "id": object_id,
                "element_type": "rain_gage",
                "layer": "rain_gages",
                "x": point[0],
                "y": point[1],
                "annotation_x": point[0],
                "annotation_y": point[1],
                "coordinates": point,
            }
        )
        records.append(record)
    return records


def _lid_usage_annotation_records(
    model: "SWMMModel",
    centroids: Mapping[str, tuple[float, float]],
    plotted_lid_records=None,
) -> list[dict[str, Any]]:
    plotted_points = {record[0]: record[2] for record in (plotted_lid_records or [])}
    records: list[dict[str, Any]] = []
    for index, row in enumerate(model._document.rows("LID_USAGE")):
        if len(row) < 2:
            continue
        subcatchment_id = str(row[0])
        control_id = str(row[1])
        object_id = f"{subcatchment_id}:{control_id}:{index}"
        point = plotted_points.get(object_id) or centroids.get(subcatchment_id)
        if point is None:
            continue
        record = _row_record(LID_USAGE_FIELDS, row)
        record.update(
            {
                "id": object_id,
                "subcatchment_id": subcatchment_id,
                "lid_control": control_id,
                "element_type": "lid_usage",
                "layer": "lid_usages",
                "x": point[0],
                "y": point[1],
                "annotation_x": point[0],
                "annotation_y": point[1],
                "coordinates": point,
            }
        )
        records.append(record)
    return records


def _label_records(model: "SWMMModel") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(model._document.rows("LABELS")):
        if len(row) < 3:
            continue
        try:
            x, y = float(row[0]), float(row[1])
        except (TypeError, ValueError):
            continue
        text = str(row[2])
        records.append(
            {
                "id": text or str(index),
                "text": text,
                "label": text,
                "anchor_node": row[3] if len(row) > 3 else None,
                "font": row[4] if len(row) > 4 else None,
                "size": row[5] if len(row) > 5 else None,
                "element_type": "label",
                "layer": "labels",
                "x": x,
                "y": y,
                "annotation_x": x,
                "annotation_y": y,
                "coordinates": (x, y),
            }
        )
    return records


def _section_records(model: "SWMMModel", section: str, fields: Sequence[str]) -> dict[str, dict[str, Any]]:
    return {
        str(row[0]): _row_record(fields, row)
        for row in model._document.rows(section)
        if row
    }


def _row_record(fields: Sequence[str], row: Sequence[Any]) -> dict[str, Any]:
    return {
        field: _coerce_record_value(field, row[index])
        for index, field in enumerate(fields)
        if index < len(row) and row[index] not in {None, ""}
    }


def _coerce_record_value(field: str, value: Any) -> Any:
    """Coerce numeric SWMM tokens while preserving IDs and enum strings."""

    value = _python_value(value)
    if field in TEXTUAL_FIELDS or not isinstance(value, str):
        return value
    text = value.strip()
    if text == "":
        return None
    try:
        numeric = float(text)
    except ValueError:
        return value
    if numeric.is_integer() and "." not in text and "e" not in text.lower():
        return int(numeric)
    return numeric


def _attach_result_fields(model: "SWMMModel", records: list[dict[str, Any]], category: str, variables: Sequence[str]) -> None:
    if not records or not getattr(model, "has_run", False):
        return
    ids = [str(record["id"]) for record in records]
    if not hasattr(model.get, category):
        return
    namespace = getattr(model.get, category)
    for variable in variables:
        if not hasattr(namespace, variable):
            continue
        try:
            frame = getattr(namespace, variable)(ids=ids, format="df")
            values = frame.iloc[-1]
        except Exception:
            continue
        for record in records:
            object_id = str(record["id"])
            if object_id in values.index:
                record[variable] = _python_value(values.loc[object_id])


def _attach_conduit_slope(model: "SWMMModel", records: list[dict[str, Any]]) -> None:
    conduit_records = [record for record in records if record.get("element_type") == "conduit"]
    if not conduit_records:
        return
    ids = [str(record["id"]) for record in conduit_records]
    try:
        slopes = model.get.conduit.slope(ids=ids, format="np")
    except Exception:
        return
    for record, slope in zip(conduit_records, slopes):
        record["slope"] = _python_value(slope)


def _polygon_centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 3:
        return _point_mean(points)
    area_twice = 0.0
    cx = 0.0
    cy = 0.0
    for first, second in zip(points, [*points[1:], points[0]]):
        cross = first[0] * second[1] - second[0] * first[1]
        area_twice += cross
        cx += (first[0] + second[0]) * cross
        cy += (first[1] + second[1]) * cross
    if abs(area_twice) < 1e-12:
        return _point_mean(points)
    return cx / (3.0 * area_twice), cy / (3.0 * area_twice)


def _point_mean(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def _line_midpoint(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    lengths = [
        math.hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(points, points[1:])
    ]
    total = sum(lengths)
    if total <= 0:
        return _point_mean(points)
    halfway = total / 2.0
    distance = 0.0
    for first, second, segment_length in zip(points, points[1:], lengths):
        if distance + segment_length >= halfway and segment_length > 0:
            fraction = (halfway - distance) / segment_length
            return (
                first[0] + (second[0] - first[0]) * fraction,
                first[1] + (second[1] - first[1]) * fraction,
            )
        distance += segment_length
    return points[-1]


def _line_angle(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    start = points[0]
    end = points[-1]
    if start == end and len(points) > 2:
        start = points[len(points) // 2 - 1]
        end = points[len(points) // 2]
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    while angle > 90:
        angle -= 180
    while angle < -90:
        angle += 180
    return angle


def apply_annotation_filters(records: list[dict[str, Any]], config: Mapping[str, Any], *, layer: str) -> list[dict[str, Any]]:
    """Apply IDs, user data, where clauses, and max label limits."""

    filtered = list(records)
    requested_ids = config.get("ids")
    if requested_ids is not None:
        if isinstance(requested_ids, str):
            requested = {requested_ids}
        elif isinstance(requested_ids, Sequence) and not isinstance(requested_ids, str):
            requested = {str(value) for value in requested_ids}
        else:
            raise TypeError("Annotation 'ids' must be a string ID or a sequence of IDs.")
        known = {str(record.get("id")) for record in filtered}
        missing = sorted(requested - known)
        if missing:
            raise PlotDataError(f"Annotation layer '{layer}' contains unknown ID(s): {', '.join(missing)}.")
        filtered = [record for record in filtered if str(record.get("id")) in requested]

    filtered = _merge_user_data(filtered, config, layer=layer)

    where = config.get("where")
    if where:
        filtered = [record for record in filtered if _record_matches_where(record, where)]

    max_labels = config.get("max_labels")
    if max_labels is not None and len(filtered) > max_labels:
        warnings.warn(
            f"Annotation layer '{layer}' matched {len(filtered)} objects; only the first {max_labels} labels were drawn.",
            stacklevel=3,
        )
        filtered = filtered[:max_labels]
    return filtered


def _merge_user_data(records: list[dict[str, Any]], config: Mapping[str, Any], *, layer: str) -> list[dict[str, Any]]:
    data: AnnotationData | None = config.get("data")
    if data is None:
        return records
    behavior = str(config.get("on_missing_data", "empty"))
    priority = bool(config.get("user_data_priority", False))
    merged: list[dict[str, Any]] = []
    for record in records:
        object_id = str(record.get("id"))
        user_row = data.rows.get(object_id)
        if user_row is None:
            message = f"Annotation user data for layer '{layer}' is missing ID '{object_id}'."
            if behavior == "raise":
                raise PlotDataError(message)
            if behavior == "skip":
                continue
            if behavior == "warn":
                warnings.warn(message, stacklevel=4)
            user_row = {field: "" for field in data.fields}
        if priority:
            merged.append({**record, **user_row})
        else:
            merged.append({**user_row, **record})
    return merged


def _record_matches_where(record: Mapping[str, Any], where: Mapping[str, Any]) -> bool:
    for field, condition in where.items():
        if not isinstance(condition, Sequence) or isinstance(condition, str) or len(condition) != 2:
            raise PlotDataError("Annotation 'where' values must be two-item sequences such as ['>', 1.0].")
        operator, expected = condition
        operator = str(operator)
        if operator not in VALID_WHERE_OPERATORS:
            allowed = ", ".join(sorted(VALID_WHERE_OPERATORS))
            raise PlotDataError(f"Unsupported annotation where operator '{operator}'. Use one of: {allowed}.")
        if field not in record:
            return False
        if not _compare_values(record[field], operator, expected):
            return False
    return True


def _compare_values(value: Any, operator: str, expected: Any) -> bool:
    value = _python_value(value)
    expected = _python_value(expected)
    if operator in {"in", "not in"}:
        try:
            result = value in expected
        except TypeError:
            result = False
        return result if operator == "in" else not result
    if operator == "==":
        return value == expected
    if operator == "!=":
        return value != expected
    left, right = _maybe_numeric_pair(value, expected)
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    return False


def _maybe_numeric_pair(left: Any, right: Any) -> tuple[Any, Any]:
    try:
        return float(left), float(right)
    except (TypeError, ValueError):
        return left, right


def format_annotation_text(record: Mapping[str, Any], config: Mapping[str, Any], *, layer: str = "") -> str | None:
    """Format annotation text for one record."""

    try:
        if config.get("callable") is not None:
            value = config["callable"](record)
            if value in {None, ""}:
                return None
            return str(value)
        if config.get("template") is not None:
            return _format_template(str(config["template"]), record)
        return _format_fields(record, config)
    except Exception as exc:
        return _handle_annotation_error(exc, record, config, layer=layer)


def _format_template(template: str, record: Mapping[str, Any]) -> str:
    try:
        return template.format_map(_TemplateRecord(record))
    except KeyError as exc:
        missing = exc.args[0]
        raise PlotDataError(f"Annotation template references missing field '{missing}'.") from exc
    except (ValueError, TypeError) as exc:
        raise PlotDataError(f"Annotation template formatting failed: {exc}") from exc


class _TemplateRecord(dict):
    """Mapping that normalizes values before Python template formatting."""

    def __init__(self, record: Mapping[str, Any]) -> None:
        super().__init__({key: _template_value(value) for key, value in record.items()})

    def __missing__(self, key):
        raise KeyError(key)


def _format_fields(record: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    lines: list[str] = []
    fields = config.get("fields") or ["id"]
    prefixes = dict(config.get("prefix") or {})
    suffixes = dict(config.get("suffix") or {})
    formats = dict(config.get("format") or {})
    show_names = config.get("show_field_names")
    for field in fields:
        if field not in record:
            raise PlotDataError(f"Annotation field '{field}' is not available.")
        value = record[field]
        formatted = _format_field_value(value, formats.get(field))
        prefix = str(prefixes.get(field, ""))
        suffix = str(suffixes.get(field, ""))
        if prefix:
            lines.append(f"{prefix}{formatted}{suffix}")
        elif field == "id":
            lines.append(f"{formatted}{suffix}")
        elif show_names is False:
            lines.append(f"{formatted}{suffix}")
        else:
            lines.append(f"{field}: {formatted}{suffix}")
    return "\n".join(lines)


def _format_field_value(value: Any, format_spec: str | None) -> str:
    value = _python_value(value)
    if _is_missing_value(value):
        return ""
    if format_spec:
        try:
            return format(value, format_spec)
        except (ValueError, TypeError) as exc:
            raise PlotDataError(f"Could not format annotation value '{value}' with specifier '{format_spec}'.") from exc
    return str(value)


def _handle_annotation_error(exc: Exception, record: Mapping[str, Any], config: Mapping[str, Any], *, layer: str):
    behavior = str(config.get("on_annotation_error", "raise"))
    object_id = record.get("id", "<unknown>")
    message = f"Could not create annotation for {layer or 'layer'} '{object_id}': {exc}"
    if behavior == "raise":
        if isinstance(exc, PlotDataError):
            raise PlotDataError(message) from exc
        raise PlotDataError(message) from exc
    if behavior == "warn":
        warnings.warn(message, stacklevel=4)
    return None


def _draw_annotation_text(ax: "Axes", record: Mapping[str, Any], text: str, style: Mapping[str, Any]):
    x = float(record["annotation_x"])
    y = float(record["annotation_y"])
    dx, dy = style.get("offset", (0.0, 0.0))
    transform = ax.transData + ScaledTranslation(dx / 72.0, dy / 72.0, ax.figure.dpi_scale_trans)
    rotation = style.get("rotation", 0)
    if rotation == "link":
        rotation = record.get("angle", 0.0)
    bbox = _bbox_kwargs(style)
    text_kwargs = {key: style[key] for key in TEXT_STYLE_KEYS if key in style}
    return ax.text(
        x,
        y,
        text,
        transform=transform,
        rotation=rotation,
        rotation_mode="anchor",
        bbox=bbox,
        label="_swmmx_annotation",
        **text_kwargs,
    )


def _bbox_kwargs(style: Mapping[str, Any]):
    bbox = style.get("bbox", False)
    default = {
        "facecolor": style.get("bbox_facecolor", "white"),
        "edgecolor": style.get("bbox_edgecolor", "none"),
        "alpha": style.get("bbox_alpha", 0.65),
        "boxstyle": "round,pad=0.2",
    }
    if isinstance(bbox, Mapping):
        return {**default, **dict(bbox)}
    if bbox:
        return default
    return None


def _template_value(value: Any) -> Any:
    value = _python_value(value)
    return "" if _is_missing_value(value) else value


def _python_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    return value


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
