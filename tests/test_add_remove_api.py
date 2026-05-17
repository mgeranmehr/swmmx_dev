from pathlib import Path

import pytest

from swmmx import (
    DependencyError,
    DuplicateIDError,
    InvalidReferenceError,
    MissingRequiredParameterError,
    swmm,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def _model_with_minimal_network():
    """Return a small valid topology useful across add/remove tests."""

    model = swmm(new="SI")
    model.add.node.junction("J1", invert_elevation=10.0, max_depth=3.0, x=0.0, y=0.0)
    model.add.node.outfall("OUT1", invert_elevation=9.0, type="FREE", x=100.0, y=0.0)
    return model


def test_add_namespaces_are_discoverable():
    model = swmm(new="SI")

    assert "node" in dir(model.add)
    assert "junction" in dir(model.add.node)
    assert "conduit" in vars(model.add.link)
    assert "junction" in dir(model.remove.node)


def test_add_junction_and_outfall_update_counts():
    model = swmm(new="SI")

    assert model.add.node.junction("J1", x=0.0, y=0.0, invert_elevation=10.0, max_depth=3.0) == "J1"
    assert model.add.node.outfall("OUT1", x=100.0, y=0.0, invert_elevation=9.0, type="FREE") == "OUT1"

    assert model.get.junction.count() == 1
    assert model.get.outfall.count() == 1
    assert model.modified


def test_add_conduit_between_existing_nodes_and_missing_node_fails():
    model = _model_with_minimal_network()

    created = model.add.link.conduit(
        "C1",
        from_node="J1",
        to_node="OUT1",
        roughness=0.013,
        shape="CIRCULAR",
        diameter=1.0,
    )
    assert created == "C1"
    assert model.get.conduit.count() == 1
    # Length defaults from the two node coordinates.
    assert model.get.conduit.length("C1") == pytest.approx(100.0)

    with pytest.raises(InvalidReferenceError, match="to_node 'J99' does not exist"):
        model.add.link.conduit("C2", from_node="J1", to_node="J99")


def test_add_duplicate_id_fails():
    model = swmm(new="SI")
    model.add.node.junction("J1", x=0.0, y=0.0)

    with pytest.raises(DuplicateIDError, match="junction ID 'J1' already exists"):
        model.add.node.junction("J1", x=0.0, y=0.0)


def test_add_node_and_subcatchment_coordinates_are_required():
    model = swmm(new="SI")

    with pytest.raises(MissingRequiredParameterError, match="required parameter 'x' is missing"):
        model.add.node.junction("J1")

    model.add.node.junction("J1", x=0.0, y=0.0)
    model.add.time.time_series("Rain1", data=[("2026-01-01 00:00", 0.0)])
    model.add.hydrology.rain_gage(
        "RG1",
        format="INTENSITY",
        interval="00:05",
        source_type="TIMESERIES",
        time_series="Rain1",
    )
    with pytest.raises(MissingRequiredParameterError, match="required parameter 'x' is missing"):
        model.add.hydrology.subcatchment("S1", rain_gage="RG1", outlet="J1")


def test_add_rain_gage_default_coordinate_and_subcatchment_explicit_centroid():
    model = _model_with_minimal_network()
    model.add.time.time_series(
        "Rain1",
        data=[
            ("2026-01-01 00:00", 0.0),
            ("2026-01-01 00:05", 5.0),
        ],
    )

    model.add.hydrology.rain_gage(
        "RG1",
        format="INTENSITY",
        interval="00:05",
        source_type="TIMESERIES",
        time_series="Rain1",
    )
    symbol = model.section("SYMBOLS")[-1]
    assert symbol == ["RG1", "100.0", "0.0"]

    model.add.hydrology.subcatchment("S1", rain_gage="RG1", outlet="J1", x=0.0, y=0.0)
    polygon_rows = [row for row in model.section("POLYGONS") if row[0] == "S1"]
    assert len(polygon_rows) == 4
    xs = [float(row[1]) for row in polygon_rows]
    ys = [float(row[2]) for row in polygon_rows]
    # The generated display polygon is centered on the explicit centroid.
    assert sum(xs) / len(xs) == pytest.approx(0.0)
    assert sum(ys) / len(ys) == pytest.approx(0.0)


def test_add_time_series_time_pattern_and_pump_curve():
    model = swmm(new="SI")

    model.add.time.time_series(
        "Rain1",
        data=[
            ("2026-01-01 00:00", 0.0),
            ("2026-01-01 00:05", 5.0),
        ],
    )
    model.add.time.time_pattern("Daily1", "DAILY", [1.0] * 24)
    model.add.curve.pump("PumpCurve1", [(0.0, 0.0), (1.0, 2.0)])

    assert model.get.time_series.count() == 1
    assert model.get.time_pattern.count() == 1
    assert model.get.curve.count() == 1
    assert [row[0] for row in model.section("TIMESERIES")] == ["Rain1", "Rain1"]
    assert model.section("CURVES")[0][:2] == ["PumpCurve1", "PUMP1"]


def test_remove_conduit_and_counts_update():
    model = _model_with_minimal_network()
    model.add.link.conduit("C1", from_node="J1", to_node="OUT1")

    summary = model.remove.link.conduit("C1")

    assert summary == {"removed": ["C1"], "warnings": [], "dependencies_removed": []}
    assert model.get.conduit.count() == 0


def test_remove_node_dependency_blocks_then_force_cascades_conduit():
    model = _model_with_minimal_network()
    model.add.link.conduit("C1", from_node="J1", to_node="OUT1")

    with pytest.raises(DependencyError, match="referenced by conduit 'C1'"):
        model.remove.node.junction("J1")

    summary = model.remove.node.junction("J1", force=True)
    assert summary["removed"] == ["J1"]
    assert summary["dependencies_removed"] == ["conduit:C1"]
    assert model.get.junction.count() == 0
    assert model.get.conduit.count() == 0


def test_generic_fallback_and_save_after_add_remove(tmp_path):
    model = swmm(new="SI")
    model.add_element("node", "junction", "J1", x=0.0, y=0.0, invert_elevation=10.0, max_depth=3.0)
    model.add_element("node", "outfall", "OUT1", x=100.0, y=0.0, invert_elevation=9.0, type="FREE")
    model.add_element("link", "conduit", "C1", from_node="J1", to_node="OUT1")

    first_path = model.save(tmp_path / "with_conduit.inp")
    first_text = first_path.read_text(encoding="utf-8")
    assert "J1 10.0 3.0" in first_text
    assert "C1 J1 OUT1" in first_text

    model.remove_element("link", "conduit", "C1")
    second_path = model.save(tmp_path / "without_conduit.inp")
    second_text = second_path.read_text(encoding="utf-8")
    assert "C1 J1 OUT1" not in second_text


def test_results_are_marked_stale_after_add_and_remove():
    model = swmm(EXAMPLE)
    model.run()
    assert not model.results_stale

    model.add.node.junction("JNEW", x=0.0, y=0.0)
    assert model.modified
    assert model.results_stale
    assert not model.has_run

    # Run again so removal invalidation can be observed independently.
    model.run()
    model.remove.node.junction("JNEW")
    assert model.results_stale
    assert not model.has_run
