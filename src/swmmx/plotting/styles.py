"""Style normalization and data-driven visual encodings for layout plots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

from ..errors import ModelNotRunError, PlotDataError, UnknownCategoryError, UnknownParameterError

if TYPE_CHECKING:
    from ..api import SWMMModel


LAYER_DEFAULTS: dict[str, dict[str, Any]] = {
    "nodes": {
        "visible": True,
        "size": 30,
        "color": "black",
        "edge_color": "white",
        "marker": "o",
        "type_markers": {
            "junction": "o",
            "outfall": "v",
            "divider": "D",
            "storage_unit": "s",
        },
        "linewidth": 0.5,
        "alpha": 1.0,
        "label": "Nodes",
    },
    "links": {
        "visible": True,
        "width": 1.5,
        "color": "gray",
        "linestyle": "-",
        "type_linestyles": {
            "conduit": "-",
            "pump": "-.",
            "orifice": ":",
            "weir": "--",
            "outlet": (0, (5, 1)),
        },
        "alpha": 1.0,
        "label": "Links",
    },
    "subcatchments": {
        "visible": True,
        "color": "lightgreen",
        "edge_color": "green",
        "linewidth": 1.0,
        "alpha": 0.25,
        "label": "Subcatchments",
    },
    "subcatchment_outlets": {
        "visible": True,
        "width": 1.0,
        "color": "0.45",
        "linestyle": "--",
        "alpha": 0.8,
        "label": "Subcatchment outlets",
    },
    "rain_gages": {
        "visible": True,
        "size": 45,
        "color": "tab:blue",
        "marker": "^",
        "alpha": 1.0,
        "label": "Rain gages",
    },
    "lids": {
        "visible": True,
        "size": 55,
        "color": "tab:purple",
        "edge_color": "white",
        "linewidth": 0.5,
        "alpha": 1.0,
        "label": "LID controls",
        "markers": ["P", "X", "*", "h", "8", "d"],
    },
    "labels": {
        "visible": False,
        "fontsize": 8,
        "color": "black",
        "alpha": 1.0,
    },
}

LAYER_DEFAULT_CATEGORY = {
    "nodes": "node",
    "links": "conduit",
    "subcatchments": "subcatchment",
}


@dataclass(frozen=True)
class EncodedStyle:
    """Resolved per-object visual values plus optional legend metadata."""

    values: dict[str, Any]
    mappable: Any | None = None
    legend_title: str | None = None
    discrete_labels: dict[Any, str] | None = None
    discrete_colors: dict[Any, Any] | None = None
    raw_values: dict[str, Any] | None = None
    source: str | None = None


def normalize_layer_config(value, layer: str) -> dict[str, Any]:
    """Merge one optional user layer dictionary with safe defaults."""

    if value is None:
        return dict(LAYER_DEFAULTS[layer])
    if isinstance(value, bool):
        return {**LAYER_DEFAULTS[layer], "visible": value}
    if not isinstance(value, Mapping):
        raise TypeError(f"'{layer}' must be None, a bool, or a dictionary of layer options.")
    return {**LAYER_DEFAULTS[layer], **dict(value)}


def normalize_layout_configs(
    *,
    nodes,
    links,
    subcatchments,
    subcatchment_outlets,
    rain_gages,
    lids,
    labels,
    link_color_by=None,
    link_color_mode=None,
    link_cmap=None,
    node_color_result=None,
    node_result_aggregation=None,
    link_user_data=None,
) -> dict[str, dict[str, Any]]:
    """Normalize rich layer dictionaries plus the documented convenience aliases."""

    configs = {
        "nodes": normalize_layer_config(nodes, "nodes"),
        "links": normalize_layer_config(links, "links"),
        "subcatchments": normalize_layer_config(subcatchments, "subcatchments"),
        "subcatchment_outlets": normalize_layer_config(subcatchment_outlets, "subcatchment_outlets"),
        "rain_gages": normalize_layer_config(rain_gages, "rain_gages"),
        "lids": normalize_layer_config(lids, "lids"),
        "labels": normalize_layer_config(labels, "labels"),
    }

    # Accept the more generic user-facing "size" spelling for link widths
    # while keeping "width" as the canonical matplotlib line parameter.
    if isinstance(links, Mapping) and "size" in links and "width" not in links:
        configs["links"]["width"] = links["size"]

    # The aliases intentionally compile down into the same dictionary grammar as
    # the rich API, so the main renderer only has one path to reason about.
    if link_color_by is not None:
        configs["links"]["color"] = {
            "by": "parameter",
            "category": "conduit",
            "variable": link_color_by,
            "mode": link_color_mode or "continuous",
            "cmap": link_cmap or "viridis",
        }
    if node_color_result is not None:
        configs["nodes"]["color"] = {
            "by": "result",
            "category": "node",
            "variable": node_color_result,
            "aggregation": node_result_aggregation or "last",
            "mode": "continuous",
        }
    if link_user_data is not None:
        configs["links"]["color"] = {
            "by": "user",
            "data": link_user_data,
            "mode": link_color_mode or "discrete",
            "cmap": link_cmap or "tab10",
        }
    return configs


def _getter_for(model: "SWMMModel", category: str, variable: str):
    """Return one dynamic getter or raise plotting-specific lookup errors."""

    if not hasattr(model.get, category):
        raise UnknownCategoryError(f"Unknown plotting category '{category}'.")
    namespace = getattr(model.get, category)
    if not hasattr(namespace, variable):
        raise UnknownParameterError(f"Unknown plotting parameter '{category}.{variable}'.")
    return getattr(namespace, variable)


def _series_from_frame(frame: pd.DataFrame, *, aggregation: str | None, time_step, time) -> pd.Series:
    """Select or aggregate a result frame into one value per object ID."""

    if time is not None:
        timestamp = pd.Timestamp(time)
        if timestamp not in frame.index:
            raise PlotDataError(f"Requested result time '{timestamp}' is not available.")
        return frame.loc[timestamp]
    if time_step is not None:
        try:
            return frame.iloc[int(time_step)]
        except (IndexError, ValueError) as exc:
            raise PlotDataError(f"Requested result time_step '{time_step}' is not available.") from exc
    selected_aggregation = aggregation or "last"
    reducers = {
        "last": lambda value: value.iloc[-1],
        "max": lambda value: value.max(),
        "min": lambda value: value.min(),
        "mean": lambda value: value.mean(),
        "median": lambda value: value.median(),
        "sum": lambda value: value.sum(),
    }
    if selected_aggregation not in reducers:
        allowed = ", ".join(reducers)
        raise PlotDataError(f"Unsupported result aggregation '{selected_aggregation}'. Use one of: {allowed}.")
    return reducers[selected_aggregation](frame)


def resolve_data_values(
    model: "SWMMModel",
    layer: str,
    ids: list[str],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve one static/parameter/result/user style config into raw values."""

    by = str(config.get("by", "static")).lower()
    if by == "static":
        return {object_id: config.get("value") for object_id in ids}
    if by == "user":
        raw = config.get("data")
        if isinstance(raw, pd.Series):
            mapping = raw.to_dict()
        elif isinstance(raw, Mapping):
            mapping = dict(raw)
        else:
            raise PlotDataError("User-driven styling requires a mapping or pandas Series in 'data'.")
        missing = [object_id for object_id in ids if object_id not in mapping]
        if missing:
            raise PlotDataError(
                f"User-driven styling is missing values for: {', '.join(missing)}."
            )
        return {object_id: mapping[object_id] for object_id in ids}

    category = str(config.get("category") or LAYER_DEFAULT_CATEGORY.get(layer, ""))
    variable = config.get("variable")
    if not category or not variable:
        raise PlotDataError(
            f"{by!r} styling for {layer} requires both 'category' and 'variable'."
        )
    getter = _getter_for(model, category, str(variable))
    if by == "parameter":
        raw = getter(ids=ids, format="df")
        if isinstance(raw, pd.DataFrame):
            if raw.shape[0] != 1:
                raise PlotDataError(
                    f"'{category}.{variable}' is time-dependent; use result styling instead."
                )
            return raw.iloc[0].to_dict()
        raise PlotDataError(f"Could not retrieve parameter values for '{category}.{variable}'.")
    if by == "result":
        if not model.has_run:
            raise ModelNotRunError(
                f"'{category}.{variable}' is a result variable. Run the model with m.run() before plotting it."
            )
        raw = getter(ids=ids, format="df")
        if not isinstance(raw, pd.DataFrame) or raw.shape[0] <= 1:
            raise PlotDataError(f"'{category}.{variable}' is not a time-dependent result variable.")
        selected = _series_from_frame(
            raw,
            aggregation=config.get("aggregation"),
            time_step=config.get("time_step"),
            time=config.get("time"),
        )
        return selected.to_dict()
    raise PlotDataError("Style config 'by' must be one of: static, parameter, result, user.")


def _numeric_array(values: dict[str, Any], ids: list[str]) -> np.ndarray:
    """Return values as finite floats or raise a clear plotting error."""

    try:
        numeric = np.asarray([values[object_id] for object_id in ids], dtype=float)
    except (TypeError, ValueError) as exc:
        raise PlotDataError("Continuous styling requires numeric values.") from exc
    if not np.isfinite(numeric).all():
        raise PlotDataError("Continuous styling requires only finite numeric values.")
    return numeric


def encode_color(
    model: "SWMMModel",
    *,
    layer: str,
    ids: list[str],
    value,
) -> EncodedStyle:
    """Return static or data-driven colors for one layout layer."""

    if not isinstance(value, Mapping):
        return EncodedStyle(values={object_id: value for object_id in ids})
    config = dict(value)
    if str(config.get("by", "static")).lower() == "static":
        return EncodedStyle(values={object_id: config.get("value") for object_id in ids})

    raw_values = resolve_data_values(model, layer, ids, config)
    source = str(config.get("by", "static")).lower()
    mode = str(config.get("mode", "continuous")).lower()
    cmap = matplotlib.colormaps.get_cmap(str(config.get("cmap", "viridis")))
    if mode == "continuous":
        numeric = _numeric_array(raw_values, ids)
        vmin = float(config.get("vmin", numeric.min()))
        vmax = float(config.get("vmax", numeric.max()))
        if vmin == vmax:
            vmax = vmin + 1.0
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        scalar_mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
        scalar_mappable.set_array(numeric)
        return EncodedStyle(
            values={object_id: scalar_mappable.to_rgba(raw_values[object_id]) for object_id in ids},
            mappable=scalar_mappable,
            legend_title=config.get("legend_title"),
            raw_values=raw_values,
            source=source,
        )
    if mode == "discrete":
        categories = list(dict.fromkeys(raw_values[object_id] for object_id in ids))
        color_by_category = {
            category: cmap(index / max(1, len(categories) - 1))
            for index, category in enumerate(categories)
        }
        labels = config.get("labels")
        discrete_labels = (
            {category: str(labels[index]) for index, category in enumerate(categories)}
            if isinstance(labels, (list, tuple)) and len(labels) == len(categories)
            else {category: str(category) for category in categories}
        )
        return EncodedStyle(
            values={object_id: color_by_category[raw_values[object_id]] for object_id in ids},
            legend_title=config.get("legend_title"),
            discrete_labels=discrete_labels,
            discrete_colors=color_by_category,
            raw_values=raw_values,
            source=source,
        )
    raise PlotDataError("Color style 'mode' must be 'continuous' or 'discrete'.")


def encode_size(
    model: "SWMMModel",
    *,
    layer: str,
    ids: list[str],
    value,
    default_min: float,
    default_max: float,
    min_key: str,
    max_key: str,
) -> EncodedStyle:
    """Return static or data-driven marker sizes / line widths."""

    if not isinstance(value, Mapping):
        return EncodedStyle(values={object_id: value for object_id in ids})
    config = dict(value)
    if str(config.get("by", "static")).lower() == "static":
        return EncodedStyle(values={object_id: config.get("value") for object_id in ids})

    raw_values = resolve_data_values(model, layer, ids, config)
    source = str(config.get("by", "static")).lower()
    numeric = _numeric_array(raw_values, ids)
    lower = float(config.get(min_key, default_min))
    upper = float(config.get(max_key, default_max))
    if lower < 0 or upper < 0 or upper < lower:
        raise PlotDataError(f"Invalid {layer} size range: {min_key}={lower}, {max_key}={upper}.")
    if numeric.max() == numeric.min():
        scaled = np.full_like(numeric, (lower + upper) / 2.0, dtype=float)
    else:
        scaled = lower + (numeric - numeric.min()) * (upper - lower) / (numeric.max() - numeric.min())
    return EncodedStyle(
        values=dict(zip(ids, scaled.tolist())),
        legend_title=config.get("legend_title"),
        raw_values=raw_values,
        source=source,
    )
