from pathlib import Path
import inspect
import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.figure import Figure
from matplotlib.axis import Axis
from matplotlib.legend_handler import HandlerLine2D
from matplotlib.markers import MarkerStyle

from swmmx import (
    InvalidPathError,
    ModelNotRunError,
    NoPathError,
    PlotDataError,
    UnknownIDError,
    swmm,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def _close(fig):
    """Close figures promptly so plotting tests stay resource-light."""

    plt.close(fig)


def _annotation_texts(ax):
    """Return layout annotation text strings in draw order."""

    return [text.get_text() for text in ax.texts if text.get_label() == "_swmmx_annotation"]


def test_plot_layout_returns_fig_ax_hides_axis_and_can_enable_grid():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(show=False)
    assert fig is ax.figure
    assert not ax.axison
    assert not plt.fignum_exists(fig.number)
    _close(fig)


def test_plot_layout_avoids_show_on_noninteractive_canvas(monkeypatch):
    model = swmm(EXAMPLE)

    def _raise_recursion(_self):
        raise RecursionError("backend recursion")

    monkeypatch.setattr(Figure, "show", _raise_recursion)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = model.plot_layout(show=True)

    assert fig is ax.figure
    assert plt.fignum_exists(fig.number)
    assert not any("active matplotlib backend raised a recursion error" in str(item.message) for item in caught)
    _close(fig)

    fig, ax = model.plot_layout(axis=True, grid=True, title="Model Layout", show=False)
    assert not ax.axison
    assert any(line.get_label() == "_swmmx_grid" for line in ax.lines)
    assert any(line.get_label() == "_swmmx_axis_frame" for line in ax.lines)
    assert any(text.get_label() == "_swmmx_axis_label" and text.get_text() == "X Coordinate" for text in ax.texts)
    assert any(text.get_label() == "_swmmx_axis_label" and text.get_text() == "Y Coordinate" for text in ax.texts)
    _close(fig)

    # `grid=True` is useful even when coordinate labels remain hidden.
    fig, ax = model.plot_layout(grid=True, show=False)
    assert not ax.axison
    assert any(line.get_label() == "_swmmx_grid" for line in ax.lines)
    assert not any(text.get_label() == "_swmmx_axis_label" for text in ax.texts)
    _close(fig)


def test_plot_layout_grid_and_axis_do_not_draw_native_axis_artists(monkeypatch):
    model = swmm(EXAMPLE)

    def _forbid_native_axis_draw(*_args, **_kwargs):
        raise AssertionError("native matplotlib Axis artists should not draw for layout maps")

    monkeypatch.setattr(Axis, "draw", _forbid_native_axis_draw)

    fig, ax = model.plot_layout(grid=True, show=False)
    fig.canvas.draw()
    assert any(line.get_label() == "_swmmx_grid" for line in ax.lines)
    _close(fig)

    fig, ax = model.plot_layout(axis=True, show=False)
    fig.canvas.draw()
    assert any(line.get_label() == "_swmmx_axis_frame" for line in ax.lines)
    _close(fig)


@pytest.mark.parametrize(
    ("plot_kwargs", "needs_run", "expected_title"),
    [
        (
            {
                "links": {
                    "color": {
                        "by": "parameter",
                        "category": "conduit",
                        "variable": "roughness",
                        "mode": "continuous",
                        "cmap": "viridis",
                    }
                }
            },
            False,
            "Links color: conduit.roughness",
        ),
        (
            {
                "nodes": {"size": {"by": "result", "variable": "depth", "aggregation": "max"}},
                "links": {
                    "color": {
                        "by": "result",
                        "category": "link",
                        "variable": "flow",
                        "aggregation": "max",
                    }
                },
            },
            True,
            "Links color: link.flow (max)",
        ),
        (
            {
                "link_color_by": "roughness",
                "link_color_mode": "continuous",
                "link_cmap": "viridis",
            },
            False,
            "Links color: conduit.roughness",
        ),
    ],
)
def test_plot_layout_continuous_color_uses_safe_legend_sections_without_native_colorbars(
    monkeypatch,
    plot_kwargs,
    needs_run,
    expected_title,
):
    model = swmm(EXAMPLE)
    if needs_run:
        model.run()

    def _forbid_native_axis_draw(*_args, **_kwargs):
        raise AssertionError("native matplotlib Axis artists should not draw for layout maps")

    monkeypatch.setattr(Axis, "draw", _forbid_native_axis_draw)

    fig, ax = model.plot_layout(show=False, **plot_kwargs)
    fig.canvas.draw()

    legend_titles = [artist.get_title().get_text() for artist in ax.artists if artist.__class__.__name__ == "Legend"]
    assert len(fig.axes) == 1
    assert expected_title in legend_titles
    _close(fig)


def test_plot_layout_default_show_is_quiet_on_agg_and_remains_renderable():
    model = swmm(EXAMPLE)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = model.plot_layout(title="Model Layout")

    assert fig is ax.figure
    assert any(text.get_text() == "Model Layout" for text in ax.texts)
    assert plt.fignum_exists(fig.number)
    assert not any("non-interactive" in str(item.message) for item in caught)
    _close(fig)


def test_plot_layout_hidden_axis_title_uses_safe_text_artist():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(title="SWMM Model Layout", show=False)
    fig.canvas.draw()

    assert ax.get_title() == ""
    assert any(
        text.get_text() == "SWMM Model Layout" and text.get_label() == "_swmmx_layout_title"
        for text in ax.texts
    )
    _close(fig)


def test_plot_layout_default_legend_draws_without_duplicate_artist_recursion():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(show=False)
    fig.canvas.draw()

    assert ax.get_legend() is not None
    assert not any(artist is ax.get_legend() for artist in ax.artists)
    _close(fig)


def test_plot_layout_saves_to_model_folder_when_only_format_is_given(tmp_path):
    model = swmm(EXAMPLE)
    model.save(tmp_path / "layout_model.inp")

    fig, _ax = model.plot_layout(save_format="png", show=False)

    assert (tmp_path / "swmm_layout.png").exists()
    _close(fig)


def test_plot_layout_requires_coordinates_and_supports_static_user_styles():
    with pytest.raises(PlotDataError, match="no node, link, subcatchment, or rain gage coordinates"):
        swmm(new="SI").plot_layout(show=False)

    model = swmm(EXAMPLE)
    fig, ax = model.plot_layout(
        show=False,
        nodes={"size": 40, "color": "black"},
        links={"width": 2.0, "color": {"by": "user", "data": {"P001": 1, "P005": 2, "P009": 1, "P011": 2}, "mode": "discrete"}},
        subcatchments={"color": "lightgreen", "edge_color": "green"},
    )
    assert fig is ax.figure
    _close(fig)


def test_plot_layout_draws_typed_symbology_and_subcatchment_outlet_connectors():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(show=False)
    legend_labels = [text.get_text() for text in ax.get_legend().get_texts()]

    assert "Junctions" in legend_labels
    assert "Outfalls" in legend_labels
    assert "Conduits" in legend_labels
    assert "Subcatchment outlets" in legend_labels
    assert any(line.get_linestyle() == "--" for line in ax.lines)
    _close(fig)


def test_plot_layout_legend_accepts_markerstyle_inputs_without_recursion():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        show=False,
        nodes={"type_markers": {"junction": MarkerStyle("o"), "outfall": MarkerStyle("v")}},
        rain_gages={"marker": MarkerStyle("^")},
    )

    assert ax.get_legend() is not None
    _close(fig)


def test_plot_layout_legend_avoids_default_line2d_handler(monkeypatch):
    model = swmm(EXAMPLE)

    def _forbid_default_handler(*_args, **_kwargs):
        raise AssertionError("default HandlerLine2D should not be used")

    monkeypatch.setattr(HandlerLine2D, "create_artists", _forbid_default_handler)

    fig, ax = model.plot_layout(show=False)

    assert ax.get_legend() is not None
    _close(fig)


def test_plot_layout_supports_parameter_result_user_color_and_size_encodings():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        show=False,
        nodes={"size": {"by": "parameter", "category": "node", "variable": "invert_elevation"}},
        links={"color": {"by": "parameter", "category": "conduit", "variable": "roughness"}},
        subcatchments={"color": {"by": "parameter", "variable": "area"}},
    )
    assert fig is ax.figure
    _close(fig)

    fig, ax = model.plot_layout(
        show=False,
        nodes={
            "color": {
                "by": "user",
                "data": {
                    "P001": "runoff",
                    "P005": "runoff",
                    "P009": "runoff",
                    "P011": "runoff",
                    "Outlet": "outfall",
                },
                "mode": "discrete",
            }
        },
        links={"size": {"by": "user", "data": {"P001": 1, "P005": 2, "P009": 3, "P011": 4}}},
        subcatchments={
            "color": {
                "by": "user",
                "data": {"CA-1": "low", "CA-7": "high", "CA-8": "low", "CA-11": "high"},
                "mode": "discrete",
            }
        },
    )
    assert fig is ax.figure
    _close(fig)

    model.run()
    fig, ax = model.plot_layout(
        show=False,
        nodes={"color": {"by": "result", "category": "node", "variable": "depth", "aggregation": "max"}},
        links={"width": {"by": "result", "category": "link", "variable": "flow", "aggregation": "max"}},
        subcatchments={"color": {"by": "result", "variable": "runoff", "aggregation": "max"}},
    )
    assert fig is ax.figure
    _close(fig)


@pytest.mark.parametrize(
    ("style_kwargs", "needs_run"),
    [
        ({"nodes": {"color": {"by": "parameter", "category": "node", "variable": "invert_elevation"}}}, False),
        ({"nodes": {"size": {"by": "parameter", "category": "node", "variable": "invert_elevation"}}}, False),
        ({"links": {"color": {"by": "parameter", "category": "conduit", "variable": "roughness"}}}, False),
        ({"links": {"width": {"by": "parameter", "category": "conduit", "variable": "roughness"}}}, False),
        ({"subcatchments": {"color": {"by": "parameter", "variable": "area"}}}, False),
        (
            {
                "nodes": {
                    "color": {
                        "by": "user",
                        "data": {
                            "P001": "junction",
                            "P005": "junction",
                            "P009": "junction",
                            "P011": "junction",
                            "Outlet": "outfall",
                        },
                        "mode": "discrete",
                    }
                }
            },
            False,
        ),
        (
            {
                "nodes": {
                    "size": {
                        "by": "user",
                        "data": {"P001": 1, "P005": 2, "P009": 3, "P011": 4, "Outlet": 5},
                    }
                }
            },
            False,
        ),
        (
            {
                "links": {
                    "color": {
                        "by": "user",
                        "data": {"P001": "A", "P005": "B", "P009": "A", "P011": "B"},
                        "mode": "discrete",
                    }
                }
            },
            False,
        ),
        ({"links": {"width": {"by": "user", "data": {"P001": 1, "P005": 2, "P009": 3, "P011": 4}}}}, False),
        (
            {
                "subcatchments": {
                    "color": {
                        "by": "user",
                        "data": {"CA-1": "low", "CA-7": "high", "CA-8": "low", "CA-11": "high"},
                        "mode": "discrete",
                    }
                }
            },
            False,
        ),
        ({"nodes": {"color": {"by": "result", "category": "node", "variable": "depth", "aggregation": "max"}}}, True),
        ({"nodes": {"size": {"by": "result", "category": "node", "variable": "depth", "aggregation": "max"}}}, True),
        ({"links": {"color": {"by": "result", "category": "link", "variable": "flow", "aggregation": "max"}}}, True),
        ({"links": {"width": {"by": "result", "category": "link", "variable": "flow", "aggregation": "max"}}}, True),
        ({"subcatchments": {"color": {"by": "result", "variable": "runoff", "aggregation": "max"}}}, True),
    ],
)
def test_plot_layout_supports_every_documented_data_driven_style(style_kwargs, needs_run):
    model = swmm(EXAMPLE)
    if needs_run:
        model.run()

    fig, ax = model.plot_layout(show=False, **style_kwargs)

    assert fig is ax.figure
    _close(fig)


def test_plot_layout_adds_custom_style_legend_sections():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        show=False,
        nodes={
            "size": {
                "by": "parameter",
                "category": "node",
                "variable": "invert_elevation",
                "legend_title": "Invert elevation",
            }
        },
        links={
            "color": {
                "by": "user",
                "data": {"P001": "A", "P005": "B", "P009": "A", "P011": "B"},
                "mode": "discrete",
                "legend_title": "Inspection class",
            },
            "width": {
                "by": "parameter",
                "category": "conduit",
                "variable": "roughness",
                "legend_title": "Roughness",
            },
        },
    )

    legend_titles = [artist.get_title().get_text() for artist in ax.artists if artist.__class__.__name__ == "Legend"]
    assert "Nodes size: Invert elevation" in legend_titles
    assert "Links color: Inspection class" in legend_titles
    assert "Links width: Roughness" in legend_titles
    _close(fig)


def test_plot_layout_draws_lid_usage_markers_when_present():
    model = swmm(EXAMPLE)
    model._document.append_row("LID_USAGE", ["CA-1", "LID_A", 1, 10.0, 5.0, 0.0, 0.0, 0.0, "*", "*"])
    model._document.append_row("LID_USAGE", ["CA-7", "LID_B", 1, 10.0, 5.0, 0.0, 0.0, 0.0, "*", "*"])

    fig, ax = model.plot_layout(show=False)
    legend_labels = [text.get_text() for text in ax.get_legend().get_texts()]

    assert "LID LID_A" in legend_labels
    assert "LID LID_B" in legend_labels
    _close(fig)


def test_plot_layout_annotation_simple_and_multiple_fields():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(annotation="id", show=False)
    assert "P001" in _annotation_texts(ax)
    _close(fig)

    fig, ax = model.plot_layout(annotation={"nodes": "id"}, show=False)
    texts = _annotation_texts(ax)
    assert "P001" in texts
    assert "Outlet" in texts
    _close(fig)

    fig, ax = model.plot_layout(annotation={"nodes": ["id", "invert_elevation"]}, show=False)
    assert any("invert_elevation: 1.1" in text for text in _annotation_texts(ax))
    _close(fig)


def test_plot_layout_annotation_templates_prefix_suffix_format_and_callable():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        annotation={
            "nodes": {
                "fields": ["id", "invert_elevation"],
                "prefix": {"invert_elevation": "Inv: "},
                "suffix": {"invert_elevation": " m"},
                "format": {"invert_elevation": ".2f"},
            },
            "conduits": {"template": "{id}\nD={diameter:.2f} m\nL={length:.1f} m"},
        },
        show=False,
    )
    texts = _annotation_texts(ax)
    assert any("Inv: 1.10 m" in text for text in texts)
    assert any("D=4.00 m" in text and "L=220.0 m" in text for text in texts)
    _close(fig)

    fig, ax = model.plot_layout(annotation={"nodes": lambda row: f"Node {row['id']}"}, show=False)
    assert "Node P001" in _annotation_texts(ax)
    _close(fig)


def test_plot_layout_annotation_filters_max_labels_and_link_rotation():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        annotation={
            "nodes": {"template": "{id}", "ids": ["P001"]},
            "conduits": {"template": "{id}", "where": {"diameter": [">", 0.5]}, "max_labels": 1, "rotation": "link"},
        },
        show=False,
    )
    texts = [text for text in ax.texts if text.get_label() == "_swmmx_annotation"]
    assert [text.get_text() for text in texts].count("P001") == 2
    rotated = [text for text in texts if text.get_text() == "P001" and text.get_ha() == "center"]
    assert rotated
    assert rotated[0].get_rotation() != 0
    _close(fig)


def test_plot_layout_annotation_missing_fields_and_invalid_layers_are_clear():
    model = swmm(EXAMPLE)

    with pytest.raises(PlotDataError, match="missing field"):
        model.plot_layout(annotation={"nodes": {"template": "{missing_field}"}}, show=False)

    fig, ax = model.plot_layout(
        annotation={"nodes": {"template": "{missing_field}", "on_annotation_error": "skip"}},
        show=False,
    )
    assert _annotation_texts(ax) == []
    _close(fig)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = model.plot_layout(
            annotation={"nodes": {"template": "{missing_field}", "on_annotation_error": "warn"}},
            show=False,
        )
    assert _annotation_texts(ax) == []
    assert any("missing_field" in str(item.message) for item in caught)
    _close(fig)

    with pytest.raises(PlotDataError, match="Unknown annotation layer"):
        model.plot_layout(annotation={"pipes": "id"}, show=False)


@pytest.mark.parametrize("layer_key", ["node", "nodes", "conduit", "conduits", "rain_gage", "rain_gages"])
def test_plot_layout_annotation_singular_plural_layer_aliases(layer_key):
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(annotation={layer_key: {"template": "{id}", "max_labels": 1}}, show=False)

    assert len(_annotation_texts(ax)) == 1
    _close(fig)


def test_plot_layout_annotation_user_data_dict_series_and_dataframe():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(
        annotation={
            "conduits": {
                "template": "{id}\nRisk={risk}\nAge={age}",
                "data": {"P001": {"risk": "High", "age": 42}},
                "on_missing_data": "skip",
            }
        },
        show=False,
    )
    assert _annotation_texts(ax) == ["P001\nRisk=High\nAge=42"]
    _close(fig)

    series = pd.Series({"P001": "High"}, name="risk")
    fig, ax = model.plot_layout(
        annotation={"conduits": {"template": "{id}: {risk}", "data": series, "on_missing_data": "skip"}},
        show=False,
    )
    assert _annotation_texts(ax) == ["P001: High"]
    _close(fig)

    frame = pd.DataFrame({"id": ["P001"], "risk": ["High"], "age": [42]})
    fig, ax = model.plot_layout(
        annotation={"conduits": {"template": "{id}: {risk}/{age}", "data": frame, "on_missing_data": "skip"}},
        show=False,
    )
    assert _annotation_texts(ax) == ["P001: High/42"]
    _close(fig)


def test_plot_layout_annotation_result_fields_after_run():
    model = swmm(EXAMPLE)
    model.run()

    fig, ax = model.plot_layout(
        annotation={
            "conduits": {"template": "{id}\nQ={flow:.3f}", "max_labels": 1},
            "nodes": {"template": "{id}\nDepth={depth:.2f}", "max_labels": 1},
        },
        show=False,
    )

    texts = _annotation_texts(ax)
    assert any("Q=" in text for text in texts)
    assert any("Depth=" in text for text in texts)
    _close(fig)


def test_plot_layout_result_style_requires_run():
    model = swmm(EXAMPLE)

    with pytest.raises(ModelNotRunError, match="'link.flow' is a result variable"):
        model.plot_layout(
            show=False,
            links={"color": {"by": "result", "category": "link", "variable": "flow", "aggregation": "max"}},
        )


def test_plot_timeseries_requires_results_then_plots_link_and_node_series():
    model = swmm(EXAMPLE)

    with pytest.raises(ModelNotRunError, match="'link.flow' is a result variable"):
        model.plot_timeseries.link.flow("P001", show=False)

    model.run()
    fig, ax = model.plot_timeseries.link.flow(["P001", "P005"], show=False)
    assert len([line for line in ax.lines if not line.get_label().startswith("_")]) == 2
    _close(fig)

    fig, ax = model.plot_timeseries.node.depth("P001", show=False)
    assert len([line for line in ax.lines if not line.get_label().startswith("_")]) == 1
    _close(fig)


def test_plot_timeseries_public_signature_and_time_formats_are_simplified():
    model = swmm(EXAMPLE)
    model.run()

    parameters = inspect.signature(model.plot_timeseries.link.flow).parameters
    assert "unit" not in parameters
    assert "max_series" not in parameters

    fig, ax = model.plot_timeseries.link.flow("P001", time_format="datetime", show=False)
    assert any("-" in text.get_text() for text in ax.texts if text.get_label() == "_swmmx_axis_tick_label")
    assert any(text.get_rotation() == 45 for text in ax.texts if text.get_label() == "_swmmx_axis_tick_label")
    assert any(text.get_text() == "Date and Time" for text in ax.texts if text.get_label() == "_swmmx_axis_label")
    _close(fig)

    fig, ax = model.plot_timeseries.link.flow("P001", time_format="clock", show=False)
    assert any(":" in text.get_text() for text in ax.texts if text.get_label() == "_swmmx_axis_tick_label")
    assert any(text.get_text() == "Time" for text in ax.texts if text.get_label() == "_swmmx_axis_label")
    _close(fig)

    fig, ax = model.plot_timeseries.link.flow("P001", time_format="elapsed", show=False)
    assert any(text.get_text() == "Elapsed Time (hours)" for text in ax.texts if text.get_label() == "_swmmx_axis_label")
    _close(fig)

    with pytest.raises(PlotDataError, match="'time_format' must be 'datetime', 'clock', or 'elapsed'"):
        model.plot_timeseries.link.flow("P001", time_format="timestamp", show=False)


def test_plot_timeseries_legends_avoid_default_line2d_handler(monkeypatch):
    model = swmm(EXAMPLE)
    model.run()

    def _forbid_default_handler(*_args, **_kwargs):
        raise AssertionError("default HandlerLine2D should not be used")

    monkeypatch.setattr(HandlerLine2D, "create_artists", _forbid_default_handler)

    for plot_call in (
        model.plot_timeseries.node.depth,
        model.plot_timeseries.link.flow,
        model.plot_timeseries.system.runoff,
    ):
        fig, ax = plot_call(show=False)
        assert ax.get_legend() is not None
        _close(fig)


def test_plot_timeseries_axes_avoid_native_axis_artists(monkeypatch):
    model = swmm(EXAMPLE)
    model.run()

    def _forbid_native_axis_draw(*_args, **_kwargs):
        raise AssertionError("native matplotlib Axis artists should not draw for time-series plots")

    monkeypatch.setattr(Axis, "draw", _forbid_native_axis_draw)

    for plot_call in (
        model.plot_timeseries.link.flow,
        model.plot_timeseries.node.depth,
        model.plot_timeseries.system.runoff,
    ):
        fig, ax = plot_call(show=False)
        fig.canvas.draw()
        assert not ax.axison
        assert any(text.get_label() == "_swmmx_cartesian_title" for text in ax.texts)
        assert any(line.get_label() == "_swmmx_axis_frame" for line in ax.lines)
        _close(fig)


def test_plot_timeseries_invalid_id_raises_unknown_id():
    model = swmm(EXAMPLE)
    model.run()

    with pytest.raises(UnknownIDError, match="Unknown link ID 'C999'"):
        model.plot_timeseries.link.flow("C999", show=False)


def test_plot_profile_validates_paths_finds_nodes_and_longest(tmp_path):
    model = swmm(EXAMPLE)

    with pytest.raises(InvalidPathError, match="not connected in sequence"):
        model.plot_profile.links(["P001", "P009"], show=False)

    fig, ax = model.plot_profile.links(["P001", "P005"], show=False)
    assert fig is ax.figure
    assert any(
        line.get_label() == "Node locations" and line.get_linestyle() == ":" and line.get_linewidth() >= 2.0
        for line in ax.lines
    )
    assert any(text.get_text() == "P001" for text in ax.texts)
    assert any(text.get_text() == "P005" for text in ax.texts)
    assert any(text.get_text() == "Distance (ft)" for text in ax.texts if text.get_label() == "_swmmx_axis_label")
    assert any(text.get_text() == "Elevation (ft)" for text in ax.texts if text.get_label() == "_swmmx_axis_label")
    assert ax.collections
    _close(fig)

    fig, ax = model.plot_profile.nodes("P011", "Outlet", show=False)
    assert fig is ax.figure
    _close(fig)

    fig, ax = model.plot_profile.longest(show=False)
    assert fig is ax.figure
    _close(fig)

    fig, _ax = model.plot_profile.links(["P011", "P005", "P001"], save_path=tmp_path / "profile.png", show=False)
    assert (tmp_path / "profile.png").exists()
    _close(fig)

    fig, _ax = model.plot_profile.links(["P011", "P005", "P001"], save_path=tmp_path / "profile.pdf", show=False)
    assert (tmp_path / "profile.pdf").exists()
    _close(fig)


def test_plot_profile_no_path_raises():
    model = swmm(EXAMPLE)

    with pytest.raises(NoPathError, match="No path was found from node 'Outlet' to node 'P011'"):
        model.plot_profile.nodes("Outlet", "P011", show=False)
