"""Whole-network matplotlib layout plotting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import math
from pathlib import Path
from typing import TYPE_CHECKING
import warnings

from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Patch, Polygon
from matplotlib.legend_handler import HandlerPatch

from ..errors import PlotDataError
from .styles import encode_color, encode_size, normalize_layout_configs
from .utils import apply_axes_options, create_axes, finalize_plot

if TYPE_CHECKING:
    from ..api import SWMMModel


NODE_SECTION_TYPES = {
    "JUNCTIONS": "junction",
    "OUTFALLS": "outfall",
    "DIVIDERS": "divider",
    "STORAGE": "storage_unit",
}

LINK_SECTION_TYPES = {
    "CONDUITS": "conduit",
    "PUMPS": "pump",
    "ORIFICES": "orifice",
    "WEIRS": "weir",
    "OUTLETS": "outlet",
}

NODE_TYPE_LABELS = {
    "junction": "Junctions",
    "outfall": "Outfalls",
    "divider": "Dividers",
    "storage_unit": "Storage units",
    "node": "Nodes",
}

LINK_TYPE_LABELS = {
    "conduit": "Conduits",
    "pump": "Pumps",
    "orifice": "Orifices",
    "weir": "Weirs",
    "outlet": "Outlets",
    "link": "Links",
}


def _xy_rows(model: "SWMMModel", section: str) -> dict[str, tuple[float, float]]:
    """Return ``id -> (x, y)`` coordinates from one ordinary XY section."""

    points: dict[str, tuple[float, float]] = {}
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            points[row[0]] = (float(row[1]), float(row[2]))
        except ValueError:
            warnings.warn(f"Skipping invalid coordinates for '{row[0]}' in [{section}].", stacklevel=3)
    return points


def _grouped_xy_rows(model: "SWMMModel", section: str) -> dict[str, list[tuple[float, float]]]:
    """Return ordered grouped XY rows such as polygons or link vertices."""

    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            points[row[0]].append((float(row[1]), float(row[2])))
        except ValueError:
            warnings.warn(f"Skipping invalid coordinates for '{row[0]}' in [{section}].", stacklevel=3)
    return dict(points)


def _type_map(model: "SWMMModel", section_types: Mapping[str, str]) -> dict[str, str]:
    """Return ``object_id -> public type`` for ordinary typed SWMM sections."""

    types: dict[str, str] = {}
    for section, object_type in section_types.items():
        for row in model._document.rows(section):
            if row:
                types[row[0]] = object_type
    return types


def _link_records(model: "SWMMModel") -> dict[str, tuple[str, str, str]]:
    """Return ordinary link endpoints plus the public link type."""

    links: dict[str, tuple[str, str, str]] = {}
    for section, link_type in LINK_SECTION_TYPES.items():
        for row in model._document.rows(section):
            if len(row) >= 3:
                links[row[0]] = (row[1], row[2], link_type)
    return links


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Return an area-weighted polygon centroid, falling back to a point mean."""

    if len(points) < 3:
        x_mean = sum(point[0] for point in points) / len(points)
        y_mean = sum(point[1] for point in points) / len(points)
        return x_mean, y_mean

    signed_area_twice = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for first, second in zip(points, [*points[1:], points[0]]):
        cross = first[0] * second[1] - second[0] * first[1]
        signed_area_twice += cross
        centroid_x += (first[0] + second[0]) * cross
        centroid_y += (first[1] + second[1]) * cross
    if signed_area_twice == 0:
        x_mean = sum(point[0] for point in points) / len(points)
        y_mean = sum(point[1] for point in points) / len(points)
        return x_mean, y_mean
    return centroid_x / (3 * signed_area_twice), centroid_y / (3 * signed_area_twice)


def _subcatchment_centroids(polygons: Mapping[str, list[tuple[float, float]]]) -> dict[str, tuple[float, float]]:
    """Return subcatchment centroid coordinates from polygon geometry."""

    return {
        subcatchment_id: _polygon_centroid(points)
        for subcatchment_id, points in polygons.items()
        if points
    }


def _subcatchment_outlets(model: "SWMMModel") -> dict[str, str]:
    """Return ``subcatchment_id -> outlet_id`` mappings."""

    return {
        row[0]: row[2]
        for row in model._document.rows("SUBCATCHMENTS")
        if len(row) >= 3
    }


def _lid_usage_records(
    model: "SWMMModel",
    subcatchment_centroids: Mapping[str, tuple[float, float]],
) -> list[tuple[str, str, tuple[float, float]]]:
    """Return one plottable LID marker record per LID usage row."""

    records: list[tuple[str, str, tuple[float, float]]] = []
    for index, row in enumerate(model._document.rows("LID_USAGE")):
        if len(row) < 2:
            continue
        subcatchment_id, control_id = row[0], row[1]
        centroid = subcatchment_centroids.get(subcatchment_id)
        if centroid is None:
            warnings.warn(
                f"Skipping LID usage '{control_id}' in subcatchment '{subcatchment_id}' because polygon geometry is missing.",
                stacklevel=3,
            )
            continue
        records.append((f"{subcatchment_id}:{control_id}:{index}", control_id, centroid))
    return records


def _discrete_color_handles(encoded_style) -> list[Patch]:
    """Return ordinary legend patches for one discrete color encoding."""

    if not encoded_style.discrete_labels or not encoded_style.discrete_colors:
        return []
    return [
        Patch(facecolor=encoded_style.discrete_colors[value], label=label)
        for value, label in encoded_style.discrete_labels.items()
    ]


def _data_style_requested(config) -> bool:
    """Return whether one nested style dictionary should explain itself."""

    return (
        isinstance(config, Mapping)
        and str(config.get("by", "static")).lower() != "static"
        and bool(config.get("legend", True))
    )


def _style_descriptor(layer: str, channel: str, config: Mapping) -> str:
    """Build a concise title for one data-driven legend/colorbar section."""

    explicit_title = config.get("legend_title")
    if explicit_title:
        detail = str(explicit_title)
    else:
        source = str(config.get("by", "static")).lower()
        if source in {"parameter", "result"}:
            category = config.get("category")
            variable = config.get("variable")
            detail = f"{category}.{variable}" if category else str(variable)
            if source == "result" and config.get("aggregation"):
                detail = f"{detail} ({config['aggregation']})"
        elif source == "user":
            detail = "user data"
        else:
            detail = source
    return f"{layer.replace('_', ' ').title()} {channel}: {detail}"


def _format_legend_value(value) -> str:
    """Format one raw style value compactly for legend labels."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:.4g}"


def _representative_style_pairs(encoded_style, ids: list[str]) -> list[tuple[float, float]]:
    """Return min/middle/max raw-to-rendered samples for width/size legends."""

    if not encoded_style.raw_values:
        return []
    pairs = sorted(
        (
            float(encoded_style.raw_values[object_id]),
            float(encoded_style.values[object_id]),
        )
        for object_id in ids
    )
    if not pairs:
        return []
    sampled = [pairs[0], pairs[len(pairs) // 2], pairs[-1]]
    unique: list[tuple[float, float]] = []
    for pair in sampled:
        if pair not in unique:
            unique.append(pair)
    return unique


class MarkerLegendProxy(Patch):
    """Simple patch proxy that carries marker metadata without a `MarkerStyle`."""

    def __init__(self, marker, *, facecolor, edgecolor, label: str, markersize: float | None = None) -> None:
        """Store primitive marker metadata for recursion-safe legend rendering."""

        super().__init__(facecolor=facecolor, edgecolor=edgecolor, label=label)
        self.marker = marker
        self.markersize = markersize


class LineLegendProxy(Patch):
    """Simple patch proxy that carries line metadata without a `Line2D` marker."""

    def __init__(self, *, color, linewidth, linestyle, label: str) -> None:
        """Store primitive line metadata for recursion-safe legend rendering."""

        super().__init__(facecolor="none", edgecolor="none", label=label)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle


class MarkerLegendHandler(HandlerPatch):
    """Draw point legend proxies without deep-copying Matplotlib marker paths."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        """Create a fresh primitive marker artist for one legend entry."""

        artist = Line2D(
            [width / 2 - xdescent],
            [(height - ydescent) / 2],
            linestyle="",
            marker=orig_handle.marker,
            markerfacecolor=orig_handle.get_facecolor(),
            markeredgecolor=orig_handle.get_edgecolor(),
            markersize=orig_handle.markersize or max(fontsize * 0.55, 4.0),
        )
        artist.set_transform(trans)
        return [artist]


class LineLegendHandler(HandlerPatch):
    """Draw line legend proxies without asking Matplotlib to copy a `Line2D`."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        """Create a fresh primitive line artist for one legend entry."""

        artist = Line2D(
            [xdescent, xdescent + width],
            [(height - ydescent) / 2, (height - ydescent) / 2],
            color=orig_handle.color,
            linewidth=orig_handle.linewidth,
            linestyle=orig_handle.linestyle,
        )
        artist.set_transform(trans)
        return [artist]


def _marker_legend_handle(
    marker,
    *,
    color,
    edge_color,
    label: str,
    markersize: float | None = None,
) -> MarkerLegendProxy:
    """Return one recursion-safe point-symbol legend handle."""

    primitive_marker = marker.get_marker() if isinstance(marker, MarkerStyle) else marker
    return MarkerLegendProxy(
        primitive_marker,
        facecolor=color,
        edgecolor=edge_color,
        label=label,
        markersize=markersize,
    )


def _line_legend_handle(*, color, linewidth, linestyle, label: str) -> LineLegendProxy:
    """Return one recursion-safe line-symbol legend handle."""

    return LineLegendProxy(
        color=color,
        linewidth=linewidth,
        linestyle=linestyle,
        label=label,
    )


def _selected_ids(config: Mapping, available: list[str]) -> list[str]:
    """Apply an optional layer-level ID filter in document order."""

    requested = config.get("ids")
    if requested is None:
        return list(available)
    if isinstance(requested, str):
        requested_ids = [requested]
    elif isinstance(requested, (list, tuple)) and all(isinstance(value, str) for value in requested):
        requested_ids = list(requested)
    else:
        raise TypeError("Layer 'ids' must be one string ID or a list of string IDs.")
    unknown = [value for value in requested_ids if value not in available]
    if unknown:
        raise PlotDataError(f"Layer filter contains unknown ID(s): {', '.join(unknown)}.")
    return [value for value in available if value in requested_ids]


def _legend_enabled(global_legend: bool, config: Mapping) -> bool:
    """Return whether one layer should contribute to the ordinary legend."""

    return bool(config.get("legend", global_legend))


def plot_layout(
    model: "SWMMModel",
    *,
    legend: bool = True,
    grid: bool = False,
    title: str | None = None,
    legend_title: str | None = None,
    axis: bool = False,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    save_format: str | None = None,
    save_path: str | Path | None = None,
    figsize: tuple[float, float] = (10, 8),
    dpi: int = 300,
    ax=None,
    show: bool = True,
    nodes=None,
    links=None,
    subcatchments=None,
    subcatchment_outlets=None,
    rain_gages=None,
    lids=None,
    labels=None,
    link_color_by=None,
    link_color_mode=None,
    link_cmap=None,
    node_color_result=None,
    node_result_aggregation=None,
    link_user_data=None,
):
    """Plot the mapped SWMM layout with static or data-driven styling.

    Parameters
    ----------
    legend, grid, title, legend_title, axis, x_axis_title, y_axis_title:
        Common presentation controls.  Layouts hide coordinate axes by default
        and show a legend by default.  ``grid=True`` keeps a visible reference
        grid even when coordinate labels remain hidden.
    save_format, save_path:
        Optional save controls.  If only ``save_format`` is supplied, the file
        is written beside the model path when available, otherwise in the
        current working directory as ``swmm_layout.<format>``.
    figsize, dpi, ax, show:
        Standard matplotlib composition controls.  Supply ``ax`` to draw into
        existing axes; use ``show=False`` for scripted or test workflows.  A
        function-created figure is removed from pyplot's manager when hidden so
        inline notebook backends do not display it automatically; non-
        interactive canvases such as Agg are not sent GUI show requests, but
        remain available for notebook/IDE rendering when ``show=True``.
    nodes, links, subcatchments, subcatchment_outlets, rain_gages, lids, labels:
        Optional layer dictionaries.  They support ``visible``, ``label``,
        ``legend``, ``alpha``, ``zorder``, and layer-specific styling keys.
        ``nodes``, ``links``, and ``subcatchments`` also support data-driven
        ``color`` dictionaries; nodes and links also support data-driven
        size/width dictionaries.  Nodes and links use type-specific symbology
        by default, dashed subcatchment outlet connectors are drawn when
        outlet geometry is available, and LID usages are shown at their
        subcatchment centroids when present.  Data-driven color, size, and
        width styles add dedicated legend sections or labeled colorbars when
        their nested ``legend`` option is enabled.

    Examples
    --------
    >>> m.plot_layout()
    >>> m.plot_layout(
    ...     title="Network Layout",
    ...     nodes={"size": 40, "color": "black"},
    ...     links={"width": 1.5, "color": "gray"},
    ... )
    >>> m.plot_layout(
    ...     links={
    ...         "color": {
    ...             "by": "result",
    ...             "variable": "flow",
    ...             "aggregation": "max",
    ...             "mode": "continuous",
    ...         }
    ...     }
    ... )

    Returns
    -------
    tuple
        ``(fig, ax)`` for the matplotlib figure and axes.

    Notes
    -----
    Coordinates are read from ``[COORDINATES]``, ``[VERTICES]``,
    ``[POLYGONS]``, and ``[SYMBOLS]``.  Elements without usable coordinates are
    skipped with a warning.  If the model has no plottable coordinates at all,
    :class:`~swmmx.PlotDataError` is raised.  Result-driven styling requires a
    completed model run.
    """

    configs = normalize_layout_configs(
        nodes=nodes,
        links=links,
        subcatchments=subcatchments,
        subcatchment_outlets=subcatchment_outlets,
        rain_gages=rain_gages,
        lids=lids,
        labels=labels,
        link_color_by=link_color_by,
        link_color_mode=link_color_mode,
        link_cmap=link_cmap,
        node_color_result=node_color_result,
        node_result_aggregation=node_result_aggregation,
        link_user_data=link_user_data,
    )
    owns_axes = ax is None
    fig, ax = create_axes(figsize=figsize, dpi=dpi, ax=ax)

    node_points = _xy_rows(model, "COORDINATES")
    rain_points = _xy_rows(model, "SYMBOLS")
    polygons = _grouped_xy_rows(model, "POLYGONS")
    vertices = _grouped_xy_rows(model, "VERTICES")
    link_records = _link_records(model)
    node_types = _type_map(model, NODE_SECTION_TYPES)
    subcatchment_centroids = _subcatchment_centroids(polygons)

    if not node_points and not rain_points and not polygons:
        raise PlotDataError(
            "Cannot plot layout because no node, link, subcatchment, or rain gage coordinates are available."
        )

    legend_handles: list = []
    style_legend_sections: list[tuple[str, list]] = []

    # Draw subcatchments first so their polygons sit behind network geometry.
    sub_config = configs["subcatchments"]
    sub_ids = _selected_ids(sub_config, list(polygons))
    if sub_config["visible"]:
        sub_colors = encode_color(model, layer="subcatchments", ids=sub_ids, value=sub_config["color"])
        for subcatchment_id in sub_ids:
            points = polygons[subcatchment_id]
            if len(points) < 3:
                warnings.warn(
                    f"Skipping subcatchment '{subcatchment_id}' because its polygon has fewer than three points.",
                    stacklevel=2,
                )
                continue
            ax.add_patch(
                Polygon(
                    points,
                    closed=True,
                    facecolor=sub_colors.values[subcatchment_id],
                    edgecolor=sub_config["edge_color"],
                    linewidth=sub_config["linewidth"],
                    alpha=sub_config["alpha"],
                    zorder=sub_config.get("zorder", 1),
                )
            )
        if sub_ids and _legend_enabled(legend, sub_config):
            legend_handles.append(
                Patch(
                    facecolor=sub_config["color"] if not isinstance(sub_config["color"], Mapping) else "lightgreen",
                    edgecolor=sub_config["edge_color"],
                    alpha=sub_config["alpha"],
                    label=sub_config["label"],
                )
            )
        if _data_style_requested(sub_config.get("color")):
            color_title = _style_descriptor("subcatchments", "color", sub_config["color"])
            if sub_colors.mappable is not None:
                fig.colorbar(sub_colors.mappable, ax=ax, label=color_title)
            else:
                style_legend_sections.append((color_title, _discrete_color_handles(sub_colors)))

    # Draw explicit drainage routing from each subcatchment centroid to the
    # outlet node or downstream subcatchment centroid.  These are map cues only;
    # they do not alter SWMM routing definitions.
    connector_config = configs["subcatchment_outlets"]
    connector_ids = _selected_ids(connector_config, list(subcatchment_centroids))
    connector_count = 0
    if connector_config["visible"]:
        outlets = _subcatchment_outlets(model)
        for subcatchment_id in connector_ids:
            outlet_id = outlets.get(subcatchment_id)
            start = subcatchment_centroids.get(subcatchment_id)
            end = node_points.get(outlet_id) or subcatchment_centroids.get(outlet_id)
            if start is None or end is None:
                continue
            ax.plot(
                [start[0], end[0]],
                [start[1], end[1]],
                color=connector_config["color"],
                linewidth=connector_config["width"],
                linestyle=connector_config["linestyle"],
                alpha=connector_config["alpha"],
                zorder=connector_config.get("zorder", 1.5),
            )
            connector_count += 1
        if connector_count and _legend_enabled(legend, connector_config):
            legend_handles.append(
                _line_legend_handle(
                    color=connector_config["color"],
                    linewidth=connector_config["width"],
                    linestyle=connector_config["linestyle"],
                    label=connector_config["label"],
                )
            )

    # Draw links as ordered polylines from upstream coordinate through optional
    # SWMM vertices to the downstream coordinate.
    link_config = configs["links"]
    link_ids = _selected_ids(link_config, list(link_records))
    plottable_link_ids = [
        link_id
        for link_id in link_ids
        if link_records[link_id][0] in node_points and link_records[link_id][1] in node_points
    ]
    missing_link_ids = [link_id for link_id in link_ids if link_id not in plottable_link_ids]
    for link_id in missing_link_ids:
        warnings.warn(f"Skipping link '{link_id}' because one or both endpoint coordinates are missing.", stacklevel=2)
    if link_config["visible"] and plottable_link_ids:
        link_colors = encode_color(model, layer="links", ids=plottable_link_ids, value=link_config["color"])
        link_widths = encode_size(
            model,
            layer="links",
            ids=plottable_link_ids,
            value=link_config["width"],
            default_min=0.5,
            default_max=4.0,
            min_key="min_width",
            max_key="max_width",
        )
        link_groups: dict[str, list[str]] = defaultdict(list)
        for link_id in plottable_link_ids:
            link_groups[link_records[link_id][2]].append(link_id)
        for link_type, typed_link_ids in link_groups.items():
            linestyle = link_config["type_linestyles"].get(link_type, link_config["linestyle"])
            for link_id in typed_link_ids:
                from_node, to_node, _link_type = link_records[link_id]
                points = [node_points[from_node], *vertices.get(link_id, []), node_points[to_node]]
                ax.plot(
                    [point[0] for point in points],
                    [point[1] for point in points],
                    color=link_colors.values[link_id],
                    linewidth=link_widths.values[link_id],
                    linestyle=linestyle,
                    alpha=link_config["alpha"],
                    zorder=link_config.get("zorder", 2),
                )
        if _legend_enabled(legend, link_config):
            for link_type in link_groups:
                legend_handles.append(
                    _line_legend_handle(
                        color=link_config["color"] if not isinstance(link_config["color"], Mapping) else "gray",
                        linewidth=link_config["width"] if not isinstance(link_config["width"], Mapping) else 1.5,
                        linestyle=link_config["type_linestyles"].get(link_type, link_config["linestyle"]),
                        label=LINK_TYPE_LABELS.get(link_type, link_type.replace("_", " ").title()),
                    )
                )
        if _data_style_requested(link_config.get("color")):
            color_title = _style_descriptor("links", "color", link_config["color"])
            if link_colors.mappable is not None:
                fig.colorbar(link_colors.mappable, ax=ax, label=color_title)
            else:
                style_legend_sections.append((color_title, _discrete_color_handles(link_colors)))
        if _data_style_requested(link_config.get("width")):
            width_title = _style_descriptor("links", "width", link_config["width"])
            style_legend_sections.append(
                (
                    width_title,
                    [
                        _line_legend_handle(
                            color=link_config["color"] if not isinstance(link_config["color"], Mapping) else "gray",
                            linewidth=rendered_width,
                            linestyle=link_config["linestyle"],
                            label=_format_legend_value(raw_width),
                        )
                        for raw_width, rendered_width in _representative_style_pairs(
                            link_widths,
                            plottable_link_ids,
                        )
                    ],
                )
            )

    # Nodes and rain gages are scatter layers so users can control marker shape,
    # size, edge treatment, and alpha without manipulating matplotlib artists.
    node_config = configs["nodes"]
    node_ids = _selected_ids(node_config, list(node_points))
    if node_config["visible"] and node_ids:
        node_colors = encode_color(model, layer="nodes", ids=node_ids, value=node_config["color"])
        node_sizes = encode_size(
            model,
            layer="nodes",
            ids=node_ids,
            value=node_config["size"],
            default_min=20.0,
            default_max=200.0,
            min_key="min_size",
            max_key="max_size",
        )
        node_groups: dict[str, list[str]] = defaultdict(list)
        for node_id in node_ids:
            node_groups[node_types.get(node_id, "node")].append(node_id)
        for node_type, typed_node_ids in node_groups.items():
            ax.scatter(
                [node_points[node_id][0] for node_id in typed_node_ids],
                [node_points[node_id][1] for node_id in typed_node_ids],
                s=[node_sizes.values[node_id] for node_id in typed_node_ids],
                c=[node_colors.values[node_id] for node_id in typed_node_ids],
                edgecolors=node_config["edge_color"],
                marker=node_config["type_markers"].get(node_type, node_config["marker"]),
                linewidths=node_config["linewidth"],
                alpha=node_config["alpha"],
                zorder=node_config.get("zorder", 3),
            )
        if _legend_enabled(legend, node_config):
            for node_type in node_groups:
                legend_handles.append(
                    _marker_legend_handle(
                        node_config["type_markers"].get(node_type, node_config["marker"]),
                        color=node_config["color"] if not isinstance(node_config["color"], Mapping) else "black",
                        edge_color=node_config["edge_color"],
                        label=NODE_TYPE_LABELS.get(node_type, node_type.replace("_", " ").title()),
                    )
                )
        if _data_style_requested(node_config.get("color")):
            color_title = _style_descriptor("nodes", "color", node_config["color"])
            if node_colors.mappable is not None:
                fig.colorbar(node_colors.mappable, ax=ax, label=color_title)
            else:
                style_legend_sections.append((color_title, _discrete_color_handles(node_colors)))
        if _data_style_requested(node_config.get("size")):
            size_title = _style_descriptor("nodes", "size", node_config["size"])
            style_legend_sections.append(
                (
                    size_title,
                    [
                        _marker_legend_handle(
                            node_config["marker"],
                            color=node_config["color"] if not isinstance(node_config["color"], Mapping) else "black",
                            edge_color=node_config["edge_color"],
                            markersize=max(math.sqrt(rendered_size), 4.0),
                            label=_format_legend_value(raw_size),
                        )
                        for raw_size, rendered_size in _representative_style_pairs(node_sizes, node_ids)
                    ],
                )
            )

    rain_config = configs["rain_gages"]
    rain_ids = _selected_ids(rain_config, list(rain_points))
    if rain_config["visible"] and rain_ids:
        ax.scatter(
            [rain_points[rain_id][0] for rain_id in rain_ids],
            [rain_points[rain_id][1] for rain_id in rain_ids],
            s=rain_config["size"],
            c=rain_config["color"],
            marker=rain_config["marker"],
            alpha=rain_config["alpha"],
            zorder=rain_config.get("zorder", 4),
        )
        if _legend_enabled(legend, rain_config):
            legend_handles.append(
                _marker_legend_handle(
                    rain_config["marker"],
                    color=rain_config["color"],
                    edge_color=rain_config["color"],
                    label=rain_config["label"],
                )
            )

    lid_config = configs["lids"]
    lid_records = _lid_usage_records(model, subcatchment_centroids)
    if lid_config["visible"] and lid_records:
        lid_groups: dict[str, list[tuple[str, str, tuple[float, float]]]] = defaultdict(list)
        for record in lid_records:
            lid_groups[record[1]].append(record)
        markers = list(lid_config["markers"]) or ["P"]
        for index, (control_id, records) in enumerate(lid_groups.items()):
            marker = markers[index % len(markers)]
            ax.scatter(
                [record[2][0] for record in records],
                [record[2][1] for record in records],
                s=lid_config["size"],
                c=lid_config["color"],
                edgecolors=lid_config["edge_color"],
                linewidths=lid_config["linewidth"],
                marker=marker,
                alpha=lid_config["alpha"],
                zorder=lid_config.get("zorder", 4.5),
            )
            if _legend_enabled(legend, lid_config):
                legend_handles.append(
                    _marker_legend_handle(
                        marker,
                        color=lid_config["color"],
                        edge_color=lid_config["edge_color"],
                        label=f"LID {control_id}",
                    )
                )

    label_config = configs["labels"]
    if label_config["visible"]:
        for node_id, (x, y) in node_points.items():
            ax.text(
                x,
                y,
                node_id,
                fontsize=label_config["fontsize"],
                color=label_config["color"],
                alpha=label_config["alpha"],
                zorder=label_config.get("zorder", 5),
            )

    apply_axes_options(
        ax,
        grid=grid,
        axis=axis,
        title=title,
        x_axis_title=x_axis_title or ("X Coordinate" if axis else None),
        y_axis_title=y_axis_title or ("Y Coordinate" if axis else None),
    )
    ax.set_aspect("equal", adjustable="datalim")
    if legend and style_legend_sections:
        # One compact legend section per custom visual channel makes the
        # encoding self-describing: the symbol legend says "what objects are
        # these?", while the data legends say "what does color/size/width mean?"
        legend_y = 1.0
        for section_title, handles in style_legend_sections:
            if not handles:
                continue
            try:
                section_legend = ax.legend(
                    handles=handles,
                    title=section_title,
                    loc="upper left",
                    bbox_to_anchor=(1.02, legend_y),
                    borderaxespad=0.0,
                    handler_map={
                        MarkerLegendProxy: MarkerLegendHandler(),
                        LineLegendProxy: LineLegendHandler(),
                    },
                )
                ax.add_artist(section_legend)
                legend_y -= 0.22
            except RecursionError:
                warnings.warn(
                    f"Matplotlib raised a recursion error while building the '{section_title}' legend section. "
                    "The map was created successfully, but that custom legend section was skipped.",
                    stacklevel=2,
                )
    if legend and legend_handles:
        try:
            ordinary_legend = ax.legend(
                handles=legend_handles,
                title=legend_title,
                loc="upper right",
                handler_map={
                    MarkerLegendProxy: MarkerLegendHandler(),
                    LineLegendProxy: LineLegendHandler(),
                },
            )
        except RecursionError:
            warnings.warn(
                "Matplotlib raised a recursion error while building the layout legend. "
                "The map was created successfully, but the legend was skipped for this backend.",
                stacklevel=2,
            )

    finalize_plot(
        fig,
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem="swmm_layout",
        dpi=dpi,
        show=show,
        close_if_hidden=owns_axes and not show,
    )
    return fig, ax
