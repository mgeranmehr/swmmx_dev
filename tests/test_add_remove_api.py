from pathlib import Path

import pytest

from swmmx import (
    DependencyError,
    DuplicateIDError,
    InvalidParameterError,
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



def test_add_lid_control_bio_retention_cell_with_all_common_layers():
    model = swmm(new="SI")

    created = model.add.hydrology.lid_control(
        "BR1",
        type="bio_retention_cell",
        surface={"storage_depth": 6, "vegetation_fraction": 0.1, "roughness": 0, "slope": 0, "side_slope": 0},
        soil={"thickness": 18, "porosity": 0.45, "field_capacity": 0.2, "wilting_point": 0.1, "conductivity": 1, "conductivity_slope": 10, "suction_head": 3},
        storage={"height": 12, "void_ratio": 0.75, "seepage_rate": 0.5, "clogging_factor": 0},
        drain={"coefficient": 0.5, "exponent": 0.5, "offset_height": 0, "delay": 0},
        removals={"TSS": 80},
    )

    assert created == "BR1"
    assert model.get.lid_control.count() == 1
    assert model.get.lid_control.type("BR1") == "BC"
    assert model.get.lid_surface.storage_depth("BR1") == pytest.approx(6.0)
    assert model.get.lid_soil.porosity("BR1") == pytest.approx(0.45)
    assert model.get.lid_storage.height("BR1") == pytest.approx(12.0)
    assert model.get.lid_drain.coefficient("BR1") == pytest.approx(0.5)
    assert model.section("LID_CONTROLS")[-1] == ["BR1", "REMOVALS", "TSS", "80.0"]


def test_add_lid_control_supports_all_epa_swmm_lid_types():
    model = swmm(new="SI")

    model.add.hydrology.lid_control("BC1", "BC", surface={}, soil={}, storage={})
    model.add.hydrology.lid_control("RG1", "rain_garden", surface={}, soil={})
    model.add.hydrology.lid_control("GR1", "green_roof", surface={}, soil={}, drain_mat={"thickness": 1.0, "void_ratio": 0.5, "roughness": 0.1})
    model.add.hydrology.lid_control("IT1", "infiltration_trench", surface={}, storage={})
    model.add.hydrology.lid_control("PP1", "permeable_pavement", surface={}, pavement={}, storage={})
    model.add.hydrology.lid_control("RB1", "rain_barrel", storage={}, drain={})
    model.add.hydrology.lid_control("RD1", "rooftop_disconnection", surface={})
    model.add.hydrology.lid_control("VS1", "vegetative_swale", surface={})

    assert model.get.lid_control.count() == 8
    assert list(model.get.lid_control.type(["BC1", "RG1", "GR1", "IT1", "PP1", "RB1", "RD1", "VS1"])) == [
        "BC",
        "RG",
        "GR",
        "IT",
        "PP",
        "RB",
        "RD",
        "VS",
    ]
    assert model.get.lid_drain_mat.thickness("GR1") == pytest.approx(1.0)


def test_lid_control_validation_and_duplicate_ids_are_clear():
    model = swmm(new="SI")

    with pytest.raises(MissingRequiredParameterError, match="requires LID layer"):
        model.add.hydrology.lid_control("BAD1", type="green_roof", surface={}, soil={})

    with pytest.raises(InvalidParameterError, match="not valid for rain_barrel"):
        model.add.hydrology.lid_control("BAD2", type="rain_barrel", surface={}, storage={}, drain={})

    model.add.hydrology.lid_control("BR1", type="bio retention cell", surface={}, soil={}, storage={})
    with pytest.raises(DuplicateIDError, match="lid_control ID 'BR1' already exists"):
        model.add.hydrology.lid_control("BR1", type="bio_retention_cell", surface={}, soil={}, storage={})


def test_remove_lid_control_blocks_or_cascades_lid_usage():
    model = swmm(new="SI")
    model.add.hydrology.lid_control("BR1", type="bio_retention_cell", surface={}, soil={}, storage={})
    model._document.append_row("LID_USAGE", ["S1", "BR1", 1, 100, 10, 0, 100, 0])

    with pytest.raises(DependencyError, match="referenced by LID usage"):
        model.remove.hydrology.lid_control("BR1")

    summary = model.remove.hydrology.lid_control("BR1", force=True)
    assert summary["removed"] == ["BR1"]
    assert summary["dependencies_removed"] == ["lid_usage:S1:BR1"]
    assert model.get.lid_control.count() == 0
    assert model.section("LID_USAGE") == []



def _model_with_lid_usage_ready():
    model = _model_with_minimal_network()
    model.add.time.time_series("Rain1", data=[("2026-01-01 00:00", 0.0)])
    model.add.hydrology.rain_gage("RG1", format="INTENSITY", interval="00:05", source_type="TIMESERIES", time_series="Rain1")
    model.add.hydrology.subcatchment("S1", rain_gage="RG1", outlet="J1", x=0.0, y=0.0, area=1.0)
    model.add.hydrology.subcatchment("S2", rain_gage="RG1", outlet="J1", x=10.0, y=0.0, area=1.0)
    model.add.hydrology.lid_control("BR1", type="bio_retention_cell", surface={}, soil={}, storage={})
    model.add.hydrology.lid_control("RG_LID", type="rain_garden", surface={}, soil={})
    return model


def test_subcatchment_lid_controls_add_get_remove_clear():
    model = _model_with_lid_usage_ready()

    record = model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=10)

    assert record["subcatchment"] == "S1"
    assert record["lid_control"] == "BR1"
    assert record["number"] == 1
    assert record["area_percent"] == pytest.approx(10.0)
    assert model.get.subcatchment.lid_controls("S1")[0]["area_percent"] == pytest.approx(10.0)
    assert "add" in dir(model.set.subcatchment.lid_controls)

    removed = model.set.subcatchment.lid_controls.remove("S1", "BR1")
    assert removed["removed"][0]["lid_control"] == "BR1"
    assert model.get.subcatchment.lid_controls("S1") == []

    model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=5)
    model.set.subcatchment.lid_controls.add("S1", "RG_LID", area_percent=5)
    cleared = model.set.subcatchment.lid_controls.clear("S1")
    assert len(cleared["removed"]) == 2
    assert model.section("LID_USAGE") == []


def test_subcatchment_lid_controls_full_editor_options_and_replacement():
    model = _model_with_lid_usage_ready()

    model.set.subcatchment.lid_controls.add(
        "S1",
        "BR1",
        occupies_full_subcatchment=True,
        number=2,
        width=4.5,
        initial_saturation=25,
        from_impervious_percent=40,
        from_pervious_percent=10,
        return_flow_to_pervious=True,
        report_file="lid_report.txt",
        drain_to="S2",
    )
    record = model.get.subcatchment.lid_controls("S1")[0]

    assert record["occupies_full_subcatchment"]
    assert record["number"] == 2
    assert record["width"] == pytest.approx(4.5)
    assert record["return_flow_to_pervious"] is True
    assert record["report_file"] == "lid_report.txt"
    assert record["drain_to"] == "S2"

    replacement = model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=15, replace=True)
    assert replacement["area_percent"] == pytest.approx(15.0)
    assert len(model.get.subcatchment.lid_controls("S1")) == 1


def test_subcatchment_lid_controls_callable_setter_and_dataframe():
    model = _model_with_lid_usage_ready()

    model.set.subcatchment.lid_controls([
        {"lid_control": "BR1", "area_percent": 8},
        {"lid_control": "RG_LID", "area_percent": 12},
    ], ids="S1")

    records = model.get.subcatchment.lid_controls("S1")
    assert [record["lid_control"] for record in records] == ["BR1", "RG_LID"]
    frame = model.get.subcatchment.lid_controls(format="df")
    assert set(frame["lid_control"]) == {"BR1", "RG_LID"}


def test_subcatchment_lid_controls_validation_is_clear():
    model = _model_with_lid_usage_ready()

    with pytest.raises(MissingRequiredParameterError, match="sizing option"):
        model.set.subcatchment.lid_controls.add("S1", "BR1")
    with pytest.raises(InvalidReferenceError, match="drain_to 'BAD'"):
        model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=10, drain_to="BAD")
    model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=60)
    with pytest.raises(InvalidParameterError, match="covers"):
        model.set.subcatchment.lid_controls.add("S1", "RG_LID", area_percent=50)


def test_add_subcatchment_accepts_lid_controls_option():
    model = _model_with_minimal_network()
    model.add.time.time_series("Rain1", data=[("2026-01-01 00:00", 0.0)])
    model.add.hydrology.rain_gage("RG1", format="INTENSITY", interval="00:05", source_type="TIMESERIES", time_series="Rain1")
    model.add.hydrology.lid_control("BR1", type="bio_retention_cell", surface={}, soil={}, storage={})

    model.add.hydrology.subcatchment(
        "S1",
        rain_gage="RG1",
        outlet="J1",
        x=0.0,
        y=0.0,
        area=1.0,
        lid_controls=[{"lid_control": "BR1", "area_percent": 10}],
    )

    assert model.get.subcatchment.lid_controls("S1")[0]["lid_control"] == "BR1"



def test_subcatchment_lid_usage_rows_are_swmm_runnable():
    model = _model_with_minimal_network()
    model.add.link.conduit("C1", from_node="J1", to_node="OUT1", roughness=0.013, shape="CIRCULAR", diameter=1.0)
    model.add.time.time_series("Rain1", data=[("01/01/2000 00:00", 0.0), ("01/01/2000 00:05", 25.0), ("01/01/2000 00:10", 0.0)])
    model.add.hydrology.rain_gage("RG1", format="INTENSITY", interval="00:05", source_type="TIMESERIES", time_series="Rain1")
    model.add.hydrology.subcatchment("S1", rain_gage="RG1", outlet="J1", x=0.0, y=0.0, area=1.0, width=100.0, slope=1.0, impervious_percent=50.0)
    model.add.hydrology.lid_control(
        "BR1",
        type="bio_retention_cell",
        surface={"storage_depth": 100, "vegetation_fraction": 0.2, "roughness": 0.1, "slope": 1, "side_slope": 0},
        soil={"thickness": 450, "porosity": 0.45, "field_capacity": 0.2, "wilting_point": 0.1, "conductivity": 10, "conductivity_slope": 10, "suction_head": 50},
        storage={"height": 300, "void_ratio": 0.75, "seepage_rate": 2, "clogging_factor": 0},
        drain={"coefficient": 0.5, "exponent": 0.5, "offset_height": 0, "delay": 0},
    )
    for key, value in {
        "START_DATE": "01/01/2000",
        "START_TIME": "00:00:00",
        "END_DATE": "01/01/2000",
        "END_TIME": "01:00:00",
        "REPORT_STEP": "00:05:00",
        "WET_STEP": "00:05:00",
        "DRY_STEP": "00:05:00",
        "ROUTING_STEP": "00:01:00",
    }.items():
        model.options[key] = value
    model.set.subcatchment.lid_controls.add("S1", "BR1", area_percent=10)

    lid_row = model.section("LID_USAGE")[0]
    assert lid_row[7] in {"0", "1"}
    assert lid_row[7] != "NO"
    result = model.run()

    assert result.success, model.log()
    assert model.has_run
