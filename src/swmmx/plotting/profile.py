"""Longitudinal hydraulic profile plotting and path utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
import warnings

import networkx as nx
import numpy as np

from ..errors import (
    InvalidPathError,
    ModelNotRunError,
    NoPathError,
    PlotDataError,
    UnknownIDError,
)
from .utils import apply_axes_options, create_axes, finalize_plot

if TYPE_CHECKING:
    from ..api import SWMMModel


@dataclass(frozen=True)
class ProfileGeometry:
    """Geometry arrays needed to render one ordered profile path."""

    nodes: list[str]
    links: list[str]
    distances: np.ndarray
    node_inverts: np.ndarray
    node_grounds: np.ndarray
    conduit_inverts_upstream: np.ndarray
    conduit_inverts_downstream: np.ndarray
    conduit_crowns_upstream: np.ndarray
    conduit_crowns_downstream: np.ndarray


class PlotProfileAccessor:
    """Namespace exposed as ``m.plot_profile``."""

    def __init__(self, model: "SWMMModel") -> None:
        """Bind the profile namespace to one model."""

        self._model = model

    def __dir__(self) -> list[str]:
        """Expose public profile helpers for IDE completion."""

        return ["links", "longest", "nodes"]

    def nodes(self, start_node: str, end_node: str, **kwargs):
        """Plot a profile along the directed hydraulic path between two nodes.

        Parameters
        ----------
        start_node, end_node:
            Existing node IDs.  A directed hydraulic path must connect them.
        time_step, aggregation, legend, grid, title, legend_title, axis,
        x_axis_title, y_axis_title, save_format, save_path, figsize, dpi, ax,
        show, unit_length, unit_elevation, show_ground, show_conduits,
        show_invert, show_crown, show_hgl, show_egl, show_water_depth,
        show_node_labels, show_link_labels, show_surcharge, show_flooding,
        fill_conduits, line_styles, colors:
            Shared profile controls; result overlays require a completed run.

        Examples
        --------
        >>> m.plot_profile.nodes("J1", "OUT1", show_hgl=True, aggregation="max")

        Returns
        -------
        tuple
            ``(fig, ax)`` for the matplotlib figure and axes.

        Notes
        -----
        Paths are directed using link ``from_node`` -> ``to_node`` connectivity.
        Geometry-only plots work before a run; HGL/EGL/water-depth overlays do
        not.  With only ``save_format``, files are named
        ``swmm_profile.<format>``.
        """

        links = _find_path_between_nodes(self._model, start_node, end_node)
        return _plot_profile(self._model, links, **kwargs)

    def links(self, ids, **kwargs):
        """Plot a profile along a user-supplied ordered link sequence.

        Parameters
        ----------
        ids:
            Ordered link ID string or list of link ID strings.  Adjacent links
            must connect in sequence.
        time_step, aggregation, legend, grid, title, legend_title, axis,
        x_axis_title, y_axis_title, save_format, save_path, figsize, dpi, ax,
        show, unit_length, unit_elevation, show_ground, show_conduits,
        show_invert, show_crown, show_hgl, show_egl, show_water_depth,
        show_node_labels, show_link_labels, show_surcharge, show_flooding,
        fill_conduits, line_styles, colors:
            Shared profile controls.  Geometry is plotted by default; result
            overlays require a completed run.

        Examples
        --------
        >>> m.plot_profile.links(["C1", "C2", "C3"])

        Returns
        -------
        tuple
            ``(fig, ax)`` for the matplotlib figure and axes.

        Notes
        -----
        Save behavior matches the other plotting APIs.  With only
        ``save_format``, the file name defaults to ``swmm_profile.<format>``.
        Conduit depth and node invert data are required for geometry.
        """

        link_ids = [ids] if isinstance(ids, str) else list(ids)
        _links_to_ordered_nodes(self._model, link_ids)
        return _plot_profile(self._model, link_ids, **kwargs)

    def longest(self, **kwargs):
        """Plot the longest directed conduit path in the model.

        Parameters
        ----------
        time_step, aggregation, legend, grid, title, legend_title, axis,
        x_axis_title, y_axis_title, save_format, save_path, figsize, dpi, ax,
        show, unit_length, unit_elevation, show_ground, show_conduits,
        show_invert, show_crown, show_hgl, show_egl, show_water_depth,
        show_node_labels, show_link_labels, show_surcharge, show_flooding,
        fill_conduits, line_styles, colors:
            Shared profile controls.  Geometry is plotted by default; result
            overlays require a completed run.

        Examples
        --------
        >>> m.plot_profile.longest(show_hgl=True, aggregation="max", title="Longest Path Profile")

        Returns
        -------
        tuple
            ``(fig, ax)`` for the matplotlib figure and axes.

        Notes
        -----
        The longest path is selected from directed conduit connectivity using
        cumulative link length.  With only ``save_format``, files are named
        ``swmm_profile.<format>``.
        """

        return _plot_profile(self._model, _find_longest_path(self._model), **kwargs)


def _link_records(model: "SWMMModel") -> dict[str, dict[str, float | str]]:
    """Return conduit records needed by current profile geometry support."""

    records: dict[str, dict[str, float | str]] = {}
    xsections = {row[0]: row for row in model._document.rows("XSECTIONS") if row}
    for row in model._document.rows("CONDUITS"):
        if len(row) < 7:
            continue
        try:
            records[row[0]] = {
                "from_node": row[1],
                "to_node": row[2],
                "length": float(row[3]),
                "inlet_offset": float(row[5]),
                "outlet_offset": float(row[6]),
                "full_depth": float(xsections[row[0]][2]) if row[0] in xsections and len(xsections[row[0]]) >= 3 else np.nan,
            }
        except ValueError:
            continue
    return records


def _network_graph(model: "SWMMModel") -> nx.DiGraph:
    """Build a directed conduit graph with link IDs and lengths on edges."""

    graph = nx.DiGraph()
    for link_id, record in _link_records(model).items():
        graph.add_edge(
            str(record["from_node"]),
            str(record["to_node"]),
            id=link_id,
            length=float(record["length"]),
        )
    return graph


def _find_path_between_nodes(model: "SWMMModel", start_node: str, end_node: str) -> list[str]:
    """Return directed link IDs along one hydraulic path between two nodes."""

    known_nodes = set(model._ids_for_category("node"))
    for node_id in (start_node, end_node):
        if node_id not in known_nodes:
            raise UnknownIDError(f"Unknown node ID '{node_id}'.")

    graph = _network_graph(model)
    try:
        node_path = nx.shortest_path(graph, start_node, end_node, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise NoPathError(
            f"No path was found from node '{start_node}' to node '{end_node}'."
        ) from exc
    return [graph.edges[first, second]["id"] for first, second in zip(node_path, node_path[1:])]


def _find_longest_path(model: "SWMMModel") -> list[str]:
    """Return link IDs for the longest directed conduit path."""

    graph = _network_graph(model)
    if graph.number_of_edges() == 0:
        raise PlotDataError("Cannot find a longest profile path because the model has no conduits.")

    if nx.is_directed_acyclic_graph(graph):
        node_path = nx.dag_longest_path(graph, weight="length")
    else:
        # Cyclic models have no globally longest simple path without a costly
        # combinatorial search.  For pragmatic drainage-network behavior, test
        # source-to-sink simple paths and choose the longest finite candidate.
        sources = [node for node in graph.nodes if graph.in_degree(node) == 0] or list(graph.nodes)
        sinks = [node for node in graph.nodes if graph.out_degree(node) == 0] or list(graph.nodes)
        candidates: list[list[str]] = []
        for source in sources:
            for sink in sinks:
                if source == sink:
                    continue
                candidates.extend(nx.all_simple_paths(graph, source, sink))
        if not candidates:
            raise PlotDataError("Cannot find a longest simple hydraulic path in this network.")
        node_path = max(
            candidates,
            key=lambda path: sum(graph.edges[first, second]["length"] for first, second in zip(path, path[1:])),
        )
    if len(node_path) < 2:
        raise PlotDataError("Cannot find a longest profile path because no connected conduit path exists.")
    return [graph.edges[first, second]["id"] for first, second in zip(node_path, node_path[1:])]


def _links_to_ordered_nodes(model: "SWMMModel", link_ids: list[str]) -> list[str]:
    """Validate ordered links and return their connected node sequence."""

    records = _link_records(model)
    unknown = [link_id for link_id in link_ids if link_id not in records]
    if unknown:
        raise UnknownIDError(f"Unknown link ID '{unknown[0]}'.")
    if not link_ids:
        raise InvalidPathError("At least one link ID is required for a profile path.")

    nodes = [str(records[link_ids[0]]["from_node"]), str(records[link_ids[0]]["to_node"])]
    for previous, current in zip(link_ids, link_ids[1:]):
        if records[previous]["to_node"] != records[current]["from_node"]:
            raise InvalidPathError(f"Links {link_ids!r} are not connected in sequence.")
        nodes.append(str(records[current]["to_node"]))
    return nodes


def _node_ground_elevation(model: "SWMMModel", node_id: str, invert: float) -> float:
    """Return node ground elevation, approximating it from max depth when needed."""

    for section in ("JUNCTIONS", "DIVIDERS", "STORAGE"):
        for row in model._document.rows(section):
            if row and row[0] == node_id:
                try:
                    return invert + float(row[2]) if len(row) >= 3 else invert
                except ValueError:
                    return invert
    return invert


def _compute_profile_geometry(model: "SWMMModel", link_ids: list[str]) -> ProfileGeometry:
    """Compute cumulative distances, inverts, crowns, and ground elevations."""

    records = _link_records(model)
    nodes = _links_to_ordered_nodes(model, link_ids)
    distances = [0.0]
    for link_id in link_ids:
        distances.append(distances[-1] + float(records[link_id]["length"]))

    node_inverts = np.asarray([model._node_invert_elevation(node_id) for node_id in nodes], dtype=float)
    node_grounds = np.asarray(
        [_node_ground_elevation(model, node_id, invert) for node_id, invert in zip(nodes, node_inverts)],
        dtype=float,
    )
    upstream_inverts: list[float] = []
    downstream_inverts: list[float] = []
    crowns_upstream: list[float] = []
    crowns_downstream: list[float] = []
    for index, link_id in enumerate(link_ids):
        record = records[link_id]
        upstream = node_inverts[index] + float(record["inlet_offset"])
        downstream = node_inverts[index + 1] + float(record["outlet_offset"])
        depth = float(record["full_depth"])
        if np.isnan(depth):
            raise PlotDataError(f"Cannot plot profile for link '{link_id}' because full depth is unavailable.")
        upstream_inverts.append(upstream)
        downstream_inverts.append(downstream)
        crowns_upstream.append(upstream + depth)
        crowns_downstream.append(downstream + depth)
    return ProfileGeometry(
        nodes=nodes,
        links=link_ids,
        distances=np.asarray(distances, dtype=float),
        node_inverts=node_inverts,
        node_grounds=node_grounds,
        conduit_inverts_upstream=np.asarray(upstream_inverts, dtype=float),
        conduit_inverts_downstream=np.asarray(downstream_inverts, dtype=float),
        conduit_crowns_upstream=np.asarray(crowns_upstream, dtype=float),
        conduit_crowns_downstream=np.asarray(crowns_downstream, dtype=float),
    )


def _selected_node_result(model: "SWMMModel", variable: str, nodes: list[str], *, time_step, aggregation):
    """Select or aggregate one node result vector for profile overlays."""

    frame = getattr(model.get.node, variable)(ids=nodes, format="df")
    reducers = {
        "last": lambda value: value.iloc[-1],
        "max": lambda value: value.max(),
        "min": lambda value: value.min(),
        "mean": lambda value: value.mean(),
        "median": lambda value: value.median(),
    }
    if aggregation is not None:
        if aggregation not in reducers:
            allowed = ", ".join(reducers)
            raise PlotDataError(f"Unsupported profile aggregation '{aggregation}'. Use one of: {allowed}.")
        return reducers[aggregation](frame).to_numpy(dtype=float)
    try:
        return frame.iloc[int(time_step)].to_numpy(dtype=float)
    except (IndexError, ValueError) as exc:
        raise PlotDataError(f"Requested profile time_step '{time_step}' is not available.") from exc


def _plot_profile(
    model: "SWMMModel",
    link_ids: list[str],
    *,
    time_step: int = -1,
    aggregation: str | None = None,
    legend: bool = True,
    grid: bool = True,
    title: str | None = None,
    legend_title: str | None = None,
    axis: bool = True,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    save_format: str | None = None,
    save_path: str | Path | None = None,
    figsize: tuple[float, float] = (12, 5),
    dpi: int = 300,
    ax=None,
    show: bool = True,
    unit_length: str | None = None,
    unit_elevation: str | None = None,
    show_ground: bool = True,
    show_conduits: bool = True,
    show_invert: bool = True,
    show_crown: bool = True,
    show_hgl: bool = False,
    show_egl: bool = False,
    show_water_depth: bool = False,
    show_node_labels: bool = True,
    show_link_labels: bool = False,
    show_surcharge: bool = True,
    show_flooding: bool = True,
    fill_conduits: bool = False,
    line_styles: dict[str, str] | None = None,
    colors: dict[str, str] | None = None,
):
    """Render one already-resolved ordered profile path."""

    if any((show_hgl, show_egl, show_water_depth, show_surcharge, show_flooding)) and not model.has_run:
        requested = []
        if show_hgl:
            requested.append("HGL")
        if show_egl:
            requested.append("EGL")
        if show_water_depth:
            requested.append("water depth")
        if show_surcharge:
            requested.append("surcharge")
        if show_flooding:
            requested.append("flooding")
        # Geometry-only defaults keep profile plots usable before simulation,
        # but explicitly asking for overlays should never silently invent them.
        if requested and any(item in requested for item in ("HGL", "EGL", "water depth")):
            raise ModelNotRunError(
                "Profile result overlays require model results. Run the model with m.run() before plotting them."
            )

    geometry = _compute_profile_geometry(model, link_ids)
    fig, ax = create_axes(figsize=figsize, dpi=dpi, ax=ax)
    styles = {
        "ground": "-",
        "invert": "-",
        "crown": "--",
        "hgl": "-",
        "water": ":",
    }
    palette = {
        "ground": "saddlebrown",
        "invert": "black",
        "crown": "dimgray",
        "conduit": "lightgray",
        "hgl": "tab:blue",
        "water": "tab:cyan",
        "flooding": "tab:red",
        "surcharge": "tab:orange",
    }
    if line_styles:
        styles.update(line_styles)
    if colors:
        palette.update(colors)

    if show_ground:
        ax.plot(geometry.distances, geometry.node_grounds, styles["ground"], color=palette["ground"], label="Ground")
    if show_invert:
        ax.plot(geometry.distances, geometry.node_inverts, styles["invert"], color=palette["invert"], label="Node invert")
    if show_conduits:
        for index, link_id in enumerate(geometry.links):
            x_pair = geometry.distances[index : index + 2]
            invert_pair = [geometry.conduit_inverts_upstream[index], geometry.conduit_inverts_downstream[index]]
            crown_pair = [geometry.conduit_crowns_upstream[index], geometry.conduit_crowns_downstream[index]]
            if fill_conduits:
                ax.fill_between(x_pair, invert_pair, crown_pair, color=palette["conduit"], alpha=0.35)
            else:
                ax.plot(x_pair, invert_pair, color=palette["conduit"], linewidth=3, alpha=0.6)
    if show_crown:
        crown_x: list[float] = []
        crown_y: list[float] = []
        for index in range(len(geometry.links)):
            crown_x.extend(geometry.distances[index : index + 2])
            crown_y.extend([geometry.conduit_crowns_upstream[index], geometry.conduit_crowns_downstream[index]])
        ax.plot(crown_x, crown_y, styles["crown"], color=palette["crown"], label="Crown")

    water_surface = None
    if any((show_hgl, show_water_depth, show_surcharge, show_flooding)):
        if model.has_run:
            head = _selected_node_result(model, "head", geometry.nodes, time_step=time_step, aggregation=aggregation)
            depth = _selected_node_result(model, "depth", geometry.nodes, time_step=time_step, aggregation=aggregation)
            water_surface = geometry.node_inverts + depth
            if show_hgl:
                ax.plot(geometry.distances, head, styles["hgl"], color=palette["hgl"], label="HGL")
            if show_water_depth:
                ax.plot(geometry.distances, water_surface, styles["water"], color=palette["water"], label="Water level")
            if show_egl:
                warnings.warn("EGL is not yet available from swmmx result access and was skipped.", stacklevel=2)
            if show_surcharge:
                mask = water_surface > geometry.node_grounds
                if mask.any():
                    ax.scatter(
                        geometry.distances[mask],
                        water_surface[mask],
                        color=palette["surcharge"],
                        marker="o",
                        label="Surcharge",
                        zorder=5,
                    )
            if show_flooding:
                flooding = _selected_node_result(model, "flooding", geometry.nodes, time_step=time_step, aggregation=aggregation)
                mask = flooding > 0
                if mask.any():
                    marker_y = water_surface[mask] if water_surface is not None else geometry.node_grounds[mask]
                    ax.scatter(
                        geometry.distances[mask],
                        marker_y,
                        color=palette["flooding"],
                        marker="v",
                        label="Flooding",
                        zorder=5,
                    )
    elif show_egl:
        warnings.warn("EGL is not yet available from swmmx result access and was skipped.", stacklevel=2)

    if show_node_labels:
        for distance, elevation, node_id in zip(geometry.distances, geometry.node_grounds, geometry.nodes):
            ax.text(distance, elevation, node_id, fontsize=8, ha="center", va="bottom")
    if show_link_labels:
        for index, link_id in enumerate(geometry.links):
            midpoint = float(np.mean(geometry.distances[index : index + 2]))
            midpoint_elevation = float(
                np.mean([geometry.conduit_crowns_upstream[index], geometry.conduit_crowns_downstream[index]])
            )
            ax.text(midpoint, midpoint_elevation, link_id, fontsize=8, ha="center", va="bottom")

    generated_title = title or "SWMM Hydraulic Profile"
    generated_x = x_axis_title or f"Distance{f' ({unit_length})' if unit_length else ''}"
    generated_y = y_axis_title or f"Elevation{f' ({unit_elevation})' if unit_elevation else ''}"
    apply_axes_options(
        ax,
        grid=grid,
        axis=axis,
        title=generated_title,
        x_axis_title=generated_x,
        y_axis_title=generated_y,
    )
    if legend:
        ax.legend(title=legend_title)
    finalize_plot(
        fig,
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem="swmm_profile",
        dpi=dpi,
        show=show,
    )
    return fig, ax
