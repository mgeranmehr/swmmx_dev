from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

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


def test_plot_layout_returns_fig_ax_hides_axis_and_can_enable_grid():
    model = swmm(EXAMPLE)

    fig, ax = model.plot_layout(show=False)
    assert fig is ax.figure
    assert not ax.axison
    _close(fig)

    fig, ax = model.plot_layout(axis=True, grid=True, show=False)
    assert any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines())
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
    assert len(ax.lines) == 2
    _close(fig)

    fig, ax = model.plot_timeseries.node.depth("P001", show=False)
    assert len(ax.lines) == 1
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
