"""Whole-network matplotlib layout plotting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING
import warnings

from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon

from ..errors import PlotDataError
from .styles import encode_color, encode_size, normalize_layout_configs
from .utils import apply_axes_options, create_axes, finalize_plot

if TYPE_CHECKING:
    from ..api import SWMMModel


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


def _link_endpoint_map(model: "SWMMModel") -> dict[str, tuple[str, str]]:
    """Return ordinary link endpoints for sections with SWMM from/to columns."""

    links: dict[str, tuple[str, str]] = {}
    for section in ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"):
        for row in model._document.rows(section):
            if len(row) >= 3:
                links[row[0]] = (row[1], row[2])
    return links


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
    rain_gages=None,
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
        and show a legend by default.
    save_format, save_path:
        Optional save controls.  If only ``save_format`` is supplied, the file
        is written beside the model path when available, otherwise in the
        current working directory as ``swmm_layout.<format>``.
    figsize, dpi, ax, show:
        Standard matplotlib composition controls.  Supply ``ax`` to draw into
        existing axes; use ``show=False`` for scripted or test workflows.
    nodes, links, subcatchments, rain_gages, labels:
        Optional layer dictionaries.  They support ``visible``, ``label``,
        ``legend``, ``alpha``, ``zorder``, and layer-specific styling keys.
        ``nodes``, ``links``, and ``subcatchments`` also support data-driven
        ``color`` and size/width dictionaries.

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
        rain_gages=rain_gages,
        labels=labels,
        link_color_by=link_color_by,
        link_color_mode=link_color_mode,
        link_cmap=link_cmap,
        node_color_result=node_color_result,
        node_result_aggregation=node_result_aggregation,
        link_user_data=link_user_data,
    )
    fig, ax = create_axes(figsize=figsize, dpi=dpi, ax=ax)

    node_points = _xy_rows(model, "COORDINATES")
    rain_points = _xy_rows(model, "SYMBOLS")
    polygons = _grouped_xy_rows(model, "POLYGONS")
    vertices = _grouped_xy_rows(model, "VERTICES")
    link_endpoints = _link_endpoint_map(model)

    if not node_points and not rain_points and not polygons:
        raise PlotDataError(
            "Cannot plot layout because no node, link, subcatchment, or rain gage coordinates are available."
        )

    legend_handles: list = []

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
        if (
            sub_colors.mappable is not None
            and isinstance(sub_config.get("color"), Mapping)
            and sub_config["color"].get("legend", True)
        ):
            fig.colorbar(sub_colors.mappable, ax=ax, label=sub_colors.legend_title)

    # Draw links as ordered polylines from upstream coordinate through optional
    # SWMM vertices to the downstream coordinate.
    link_config = configs["links"]
    link_ids = _selected_ids(link_config, list(link_endpoints))
    plottable_link_ids = [
        link_id
        for link_id in link_ids
        if link_endpoints[link_id][0] in node_points and link_endpoints[link_id][1] in node_points
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
        for link_id in plottable_link_ids:
            from_node, to_node = link_endpoints[link_id]
            points = [node_points[from_node], *vertices.get(link_id, []), node_points[to_node]]
            ax.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                color=link_colors.values[link_id],
                linewidth=link_widths.values[link_id],
                linestyle=link_config["linestyle"],
                alpha=link_config["alpha"],
                zorder=link_config.get("zorder", 2),
            )
        if _legend_enabled(legend, link_config):
            legend_handles.append(
                Line2D(
                    [],
                    [],
                    color=link_config["color"] if not isinstance(link_config["color"], Mapping) else "gray",
                    linewidth=link_config["width"] if not isinstance(link_config["width"], Mapping) else 1.5,
                    linestyle=link_config["linestyle"],
                    label=link_config["label"],
                )
            )
        if (
            link_colors.mappable is not None
            and isinstance(link_config.get("color"), Mapping)
            and link_config["color"].get("legend", True)
        ):
            fig.colorbar(link_colors.mappable, ax=ax, label=link_colors.legend_title)

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
        ax.scatter(
            [node_points[node_id][0] for node_id in node_ids],
            [node_points[node_id][1] for node_id in node_ids],
            s=[node_sizes.values[node_id] for node_id in node_ids],
            c=[node_colors.values[node_id] for node_id in node_ids],
            edgecolors=node_config["edge_color"],
            marker=node_config["marker"],
            linewidths=node_config["linewidth"],
            alpha=node_config["alpha"],
            zorder=node_config.get("zorder", 3),
        )
        if _legend_enabled(legend, node_config):
            legend_handles.append(
                Line2D(
                    [],
                    [],
                    marker=node_config["marker"],
                    linestyle="",
                    color=node_config["color"] if not isinstance(node_config["color"], Mapping) else "black",
                    markeredgecolor=node_config["edge_color"],
                    markersize=6,
                    label=node_config["label"],
                )
            )
        if (
            node_colors.mappable is not None
            and isinstance(node_config.get("color"), Mapping)
            and node_config["color"].get("legend", True)
        ):
            fig.colorbar(node_colors.mappable, ax=ax, label=node_colors.legend_title)

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
                Line2D(
                    [],
                    [],
                    marker=rain_config["marker"],
                    linestyle="",
                    color=rain_config["color"],
                    markersize=6,
                    label=rain_config["label"],
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
    if legend and legend_handles:
        ax.legend(handles=legend_handles, title=legend_title)

    finalize_plot(
        fig,
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem="swmm_layout",
        dpi=dpi,
        show=show,
    )
    return fig, ax
