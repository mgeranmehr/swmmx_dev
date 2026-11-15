"""EPA row formats, editing safety, interchange and native output integration."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from swmmx import (swmm, InvalidParameterError, InvalidReferenceError,
                   MissingRequiredParameterError, DependencyError,
                   NotImplementedYetError, UnknownIDError, DuplicateIDError)
from swmmx.node_fields import node_record


def network(kind="CUTOFF"):
    m = swmm(new="SI")
    m.options["FLOW_ROUTING"] = "KINWAVE"
    m.options["END_DATE"] = m.options["START_DATE"]
    m.options["END_TIME"] = "01:00:00"
    m.add.node.storage_unit("S", x=0, y=0, invert_elevation=4, max_depth=3,
                            initial_depth=1, area=100, tag="Detention pond")
    m.add.curve.diversion("DC", [(0, 0), (1, 0.4), (10, 4)])
    options = {"CUTOFF": {"cutoff_flow": 0.1}, "OVERFLOW": {},
               "TABULAR": {"diversion_curve": "DC"},
               "WEIR": {"cutoff_flow": 0.01, "weir_height": 0.5, "weir_coefficient": 1.8}}[kind]
    m.add.node.divider("D", x=100, y=0, invert_elevation=2, max_depth=3,
                       type=kind, tag="Flow split", **options)
    m.add.node.outfall("O1", x=200, y=50, invert_elevation=0)
    m.add.node.outfall("O2", x=200, y=-50, invert_elevation=0)
    for id, first, last in (("SD", "S", "D"), ("main", "D", "O1"), ("bypass", "D", "O2")):
        m.add.link.conduit(id, from_node=first, to_node=last, length=100, diameter=0.5)
    m.set.flow_divider.diverted_link("bypass", ids="D")
    return m


def test_functional_storage_roundtrip_and_all_fields(tmp_path):
    m = swmm(new="SI")
    m.add.node.storage_unit("S", x=12, y=34, invert_elevation=-2, max_depth=5,
                            initial_depth=1, area_coefficient=2, area_exponent=1.5,
                            area_constant=100, evaporation_factor=0.7, surcharge_depth=0.4,
                            seepage_loss=(3, 0.5, 0.2), tag="Pond A")
    expected = ["S", "-2.0", "5.0", "1.0", "FUNCTIONAL", "2.0", "1.5", "100.0", "0.4", "0.7", "3.0", "0.5", "0.2"]
    assert m.section("STORAGE")[0] == expected
    reopened = swmm(m.save(tmp_path / "storage.inp"))
    assert reopened.section("STORAGE")[0] == expected
    assert reopened.get.storage_unit.area(ids="S") == 100
    assert reopened.get.storage_unit.seepage_loss(ids="S") == 0.5
    assert reopened.get.storage_unit.suction_head(ids="S") == 3
    assert reopened.get.storage_unit.initial_moisture_deficit(ids="S") == 0.2
    assert reopened.get.storage_unit.x(ids="S") == 12
    assert reopened.get.storage_unit.tag(ids="S") == "Pond A"
    assert reopened.get.storage_unit.storage_curve(ids="S") is None
    reopened.set.storage_unit.area(150, ids="S")
    reopened.set.storage_unit.seepage_loss((4, 0.8, 0.3), ids="S")
    reopened.set.storage_unit.y(55, ids="S")
    assert reopened.get.storage_unit.area_constant(ids="S") == 150
    assert reopened.get.storage_unit.hydraulic_conductivity(ids="S") == 0.8
    reopened.set.storage_unit.seepage_loss([5, 0.9, 0.4], ids="S")
    assert reopened.get.storage_unit.suction_head(ids="S") == 5
    assert tuple(reopened.get.node.coordinate(ids="S")) == (12, 55)


def test_tabular_storage_and_reference_guards(tmp_path):
    m = swmm(new="SI")
    m.add.curve.storage("SC", [(0, 10), (3, 50)])
    m.add.node.storage_unit("S", x=0, y=0, storage_curve_type="tabular", storage_curve="SC",
                            max_depth=3, evaporation_factor=0.8, hydraulic_conductivity=2)
    assert m.section("STORAGE")[0][4:] == ["TABULAR", "SC", "0.0", "0.8", "0.0", "2.0", "0.0"]
    reopened = swmm(m.save(tmp_path / "tabular.inp"))
    assert reopened.get.storage_unit.storage_curve(ids="S") == "SC"
    assert reopened.get.storage_unit.area_coefficient(ids="S") is None
    with pytest.raises(DependencyError):
        m.remove.curve.storage("SC")
    with pytest.raises(NotImplementedYetError):
        m.remove.curve.storage("SC", force=True)
    with pytest.raises(InvalidReferenceError):
        m.set.storage_unit.storage_curve("missing", ids="S")
    assert m.get.storage_unit.storage_curve(ids="S") == "SC"


@pytest.mark.parametrize("kind,tail", [
    ("OVERFLOW", []), ("CUTOFF", ["0.1"]), ("TABULAR", ["DC"]),
    ("WEIR", ["0.01", "0.5", "1.8"]),
])
def test_all_divider_rows_getters_roundtrip_and_native_results(tmp_path, kind, tail):
    m = network(kind)
    assert m.section("DIVIDERS")[0] == ["D", "2.0", "bypass", kind, *tail, "3.0", "0.0", "0.0", "0.0"]
    assert m.get.flow_divider.type(ids="D") == kind
    assert m.get.flow_divider.max_depth(ids="D") == 3
    assert m.get.node.max_depth(ids="D") == 3
    m.set.node.max_depth(4, ids="D")
    m.set.flow_divider.ponded_area(12, ids="D")
    m.set.flow_divider.initial_depth(0.05, ids="D")
    assert m.get.flow_divider.max_depth(ids="D") == 4
    reopened = swmm(m.save(tmp_path / f"{kind}.inp"))
    assert reopened.get.flow_divider.ponded_area(ids="D") == 12
    assert reopened.get.flow_divider.initial_depth(ids="D") == 0.05
    assert reopened.get.flow_divider.diverted_link(ids="D") == "bypass"
    result = reopened.run()
    assert result.success, reopened._last_log
    assert np.isfinite(reopened.get.flow_divider.depth(ids="D")).all()
    assert np.allclose(reopened.get.storage_unit.volume(ids="S"), reopened.get.node.volume(ids="S"))
    assert np.allclose(reopened.get.flow_divider.total_inflow(ids="D"), reopened.get.node.total_inflow(ids="D"))
    reopened.set.storage_unit.area(200, ids="S")
    assert reopened.results_stale and reopened.modified and not reopened.has_run


@pytest.mark.parametrize("options,error", [
    ({"storage_curve_type": "bogus"}, InvalidParameterError),
    ({"max_depth": -1}, InvalidParameterError),
    ({"initial_depth": 3, "max_depth": 2}, InvalidParameterError),
    ({"evaporation_factor": 1.1}, InvalidParameterError),
    ({"seepage_loss": (1, 2)}, InvalidParameterError),
    ({"initial_moisture_deficit": 2}, InvalidParameterError),
    ({"area": 2, "area_constant": 3}, InvalidParameterError),
    ({"area": float("nan")}, InvalidParameterError),
    ({"storage_curve_type": "TABULAR"}, MissingRequiredParameterError),
    ({"storage_curve_type": "TABULAR", "storage_curve": "missing"}, InvalidReferenceError),
    ({"storage_curve": "unused"}, InvalidParameterError),
])
def test_storage_invalid_add_is_atomic(options, error):
    m = swmm(new="SI")
    before = m._document.to_text()
    with pytest.raises(error):
        m.add.node.storage_unit("S", x=0, y=0, **options)
    assert m._document.to_text() == before


@pytest.mark.parametrize("options,error", [
    ({"type": "bogus"}, InvalidParameterError),
    ({"type": "CUTOFF"}, MissingRequiredParameterError),
    ({"type": "WEIR", "cutoff_flow": 1, "weir_height": 0, "weir_coefficient": 2}, InvalidParameterError),
    ({"type": "TABULAR", "diversion_curve": "missing"}, InvalidReferenceError),
    ({"diverted_link": "typo"}, InvalidReferenceError),
    ({"type": "OVERFLOW", "cutoff_flow": 2}, InvalidParameterError),
])
def test_divider_invalid_add_is_atomic(options, error):
    m = swmm(new="SI")
    before = m._document.to_text()
    with pytest.raises(error):
        m.add.node.divider("D", x=0, y=0, **options)
    assert m._document.to_text() == before


def test_reference_type_and_bulk_set_validation():
    m = network("TABULAR")
    m.add.curve.storage("SC", [(0, 10), (3, 20)])
    before = m._document.to_text()
    for action in (lambda: m.set.flow_divider.diversion_curve("SC", ids="D"),
                   lambda: m.set.flow_divider.diverted_link("SD", ids="D"),
                   lambda: m.add.node.storage_unit("T", x=0, y=0, storage_curve_type="TABULAR", storage_curve="DC")):
        with pytest.raises(InvalidReferenceError):
            action()
        assert m._document.to_text() == before
    with pytest.raises(InvalidParameterError):
        m.set.node.max_depth([4, -2], ids=["S", "D"])
    assert m._document.to_text() == before
    with pytest.raises(InvalidParameterError):
        m.set.flow_divider.type("WEIR", ids="D")
    with pytest.raises(DuplicateIDError):
        m.add.node.storage_unit("D", x=0, y=0)


@pytest.mark.parametrize("kind", ["storage_unit", "divider"])
def test_removal_metadata_dependencies_and_unsafe_cascades(kind):
    m = swmm(new="SI")
    add, remove = getattr(m.add.node, kind), getattr(m.remove.node, kind)
    add("N", x=0, y=0, tag="test")
    m.add.node.outfall("O", x=10, y=0)
    with pytest.raises(UnknownIDError):
        remove("O")
    m.add.link.conduit("L", from_node="N", to_node="O")
    with pytest.raises(DependencyError):
        remove("N")
    m._document.append_row("SUBCATCHMENTS", ["sub", "rain", "N", 1, 0, 1, 1, 0])
    before = m._document.to_text()
    with pytest.raises(NotImplementedYetError):
        remove("N", force=True)
    assert m._document.to_text() == before
    m._document.remove_rows("SUBCATCHMENTS", ["sub"])
    m._document.append_row("CONTROLS", ["IF", "LINK", "L", "FLOW", ">", 1])
    before = m._document.to_text()
    with pytest.raises(NotImplementedYetError):
        remove("N", force=True)
    assert m._document.to_text() == before
    m._document.remove_rows("CONTROLS", ["IF"])
    assert remove("N", force=True)["dependencies_removed"] == ["conduit:L"]
    assert not m.section("TAGS") and not [r for r in m.section("COORDINATES") if r[0] == "N"]
    add("unused", x=1, y=1)
    assert remove("unused")["removed"] == ["unused"]


def test_protect_diverted_link_and_curve_removal():
    m = network("TABULAR")
    for force, error in ((False, DependencyError), (True, NotImplementedYetError)):
        with pytest.raises(error):
            m.remove.link.conduit("bypass", force=force)
        with pytest.raises(error):
            m.remove.curve.diversion("DC", force=force)
    assert m.remove.node.divider("D", force=True)["dependencies_removed"] == ["conduit:SD", "conduit:main", "conduit:bypass"]
    m.remove.curve.diversion("DC")


def test_validation_and_annotations():
    m = network("WEIR")
    from swmmx.plotting.annotations import _node_records, _xy_rows
    records = {r["id"]: r for r in _node_records(m, _xy_rows(m, "COORDINATES"))}
    assert records["S"]["area_constant"] == 100
    assert records["D"]["weir_height"] == 0.5
    assert records["D"]["max_depth"] == 3
    m.plot_layout(annotation={"storage_units": {"fields": ["id", "area_constant"]},
                               "dividers": {"fields": ["id", "weir_height", "max_depth"]}})
    plt.close("all")
    assert m.validate().ok
    m._document.set_field_values("DIVIDERS", 2, {"D": "missing"})
    assert any(issue.code == "INVALID_NODE_PARAMETERS" for issue in m.validate().issues)


@pytest.mark.parametrize("kind", ["CUTOFF", "TABULAR", "WEIR", "OVERFLOW"])
def test_csv_excel_and_gis_roundtrips(tmp_path, kind):
    m = network(kind)
    m.set.storage_unit.seepage_loss((3, 0.5, 0.2), ids="S")
    outputs = m.export.csv(path=tmp_path / "csv", elements=["storage_units", "dividers"], include_results=False)
    target = swmm(m.save(tmp_path / "source.inp"))
    for element, category in (("storage_units", "storage_unit"), ("dividers", "flow_divider")):
        frame = pd.read_csv(outputs[element])
        assert {"x", "y", "tag"} <= set(frame)
        result = getattr(target.import_csv.node, category)(outputs[element], mode="update")
        assert result.ok
        section = "STORAGE" if category == "storage_unit" else "DIVIDERS"
        assert node_record(category, target.section(section)[0]) == node_record(category, m.section(section)[0])
    xlsx = m.export.excel(path=tmp_path, file_name="nodes.xlsx", elements=["storage_units", "dividers"], include_results=False)
    assert pd.read_excel(xlsx, sheet_name="storage_units").iloc[0]["suction_head"] == 3
    pytest.importorskip("geopandas")
    gpkg = tmp_path / "nodes.gpkg"
    m.export.gis(path=tmp_path, file_name="nodes.gpkg", driver="GPKG", elements=["storage_units", "dividers"], crs="EPSG:27700", include_results=False)
    for element, category in (("storage_units", "storage_unit"), ("dividers", "flow_divider")):
        result = getattr(target.import_gis.node, category)(gpkg, layer=element, mode="update")
        assert result.ok
    assert target.get.storage_unit.suction_head(ids="S") == 3
    assert target.get.flow_divider.type(ids="D") == kind


def test_short_epa_rows_optional_defaults_and_comment_preservation():
    m = swmm(new="SI")
    m._document.append_row("STORAGE", ["S", 0, 3, 0, "FUNCTIONAL", 0, 0, 100, 0, 0, 2])
    m._document.section("STORAGE").lines[-1] += " ; keep this comment"
    assert m.get.storage_unit.seepage_loss(ids="S") == 2
    m.set.storage_unit.evaporation_factor(0.8, ids="S")
    assert "; keep this comment" in m._document.to_text()
    assert m.get.storage_unit.seepage_loss(ids="S") == 2
    m._document.append_row("DIVIDERS", ["D", 0, "*", "OVERFLOW"])
    assert m.get.flow_divider.max_depth(ids="D") == 0
    m.set.flow_divider.max_depth(3, ids="D")
    assert m.section("DIVIDERS")[0][4:] == ["3.0", "0.0", "0.0", "0.0"]


@pytest.mark.parametrize("shape", ["CYLINDRICAL", "CONICAL", "PARABOLIC", "PYRAMIDAL"])
def test_analytical_storage_shapes_native(shape, tmp_path):
    m = swmm(new="SI")
    m.options["END_DATE"] = m.options["START_DATE"]
    m.options["END_TIME"] = "00:30:00"
    m.add.node.storage_unit("S", x=0, y=0, max_depth=3, initial_depth=1,
        storage_curve_type=shape, area_coefficient=10, area_exponent=8, area_constant=2)
    m.add.node.outfall("O", x=100, y=0, invert_elevation=-1)
    m.add.link.conduit("L", from_node="S", to_node="O", length=100, diameter=0.1)
    m.save(tmp_path / f"{shape}.inp")
    assert m.run().success
    assert m.get.storage_unit.volume(ids="S").max() > 0
    assert m.get.node.volume(ids="O").max() == 0
    assert m._output_file_cache.object_ids("node") == ["S", "O"]


def test_fresh_csv_import_and_group_updates(tmp_path):
    m = network("WEIR")
    m.add.curve.storage("SC", [(0, 10), (3, 20)])
    m.add.node.storage_unit("T", x=10, y=20, max_depth=3, storage_curve_type="TABULAR", storage_curve="SC")
    files = m.export.csv(path=tmp_path, elements=["storage_units", "dividers", "nodes"], include_results=False)
    fresh = swmm(new="SI")
    fresh.add.curve.storage("SC", [(0, 10), (3, 20)])
    assert fresh.import_csv.node.storage_unit(files["storage_units"]).ok
    assert fresh.get.storage_unit.storage_curve(ids="T") == "SC"
    # No forward references: bootstrap a standalone divider before its links.
    frame = pd.read_csv(files["dividers"])
    frame["diverted_link"] = "*"
    path = tmp_path / "bootstrap.csv"
    frame.to_csv(path, index=False)
    assert fresh.import_csv.node.flow_divider(path).ok
    assert fresh.get.flow_divider.weir_height(ids="D") == 0.5
    assert any(issue.code == "UNASSIGNED_DIVERTED_LINK" for issue in fresh.validate().issues)
    updated = m.clone()
    assert updated.import_csv.node(files["nodes"], mode="update").ok
    assert updated.get.flow_divider.type(ids="D") == "WEIR"
    assert updated.get.flow_divider.weir_coefficient(ids="D") == 1.8


def test_add_and_remove_stale_and_bulk_failure_preserves_results(tmp_path):
    m = network()
    m.save(tmp_path / "stale.inp")
    assert m.run().success
    before = m._document.to_text()
    with pytest.raises(InvalidParameterError):
        m.set.node.max_depth([4, -1], ids=["S", "D"])
    assert m._document.to_text() == before and m.has_run and not m.results_stale
    m.add.node.storage_unit("extra", x=0, y=5, area=10)
    assert m.results_stale and not m.has_run
    assert m.run().success
    m.remove.node.storage_unit("extra")
    assert m.results_stale and not m.has_run
    assert m.run().success
    m.remove.node.divider("D", force=True)
    assert m.results_stale and not m.has_run


def test_tabular_storage_gis_roundtrip(tmp_path):
    pytest.importorskip("geopandas")
    m = swmm(new="SI")
    m.add.curve.storage("SC", [(0, 10), (3, 20)])
    m.add.node.storage_unit("T", x=1, y=2, max_depth=3, storage_curve_type="TABULAR", storage_curve="SC", seepage_loss=(4, 2, 0.1))
    m.export.gis(path=tmp_path, file_name="tabular.gpkg", driver="GPKG", elements="storage_units", crs="EPSG:27700", include_results=False)
    other = swmm(new="SI")
    other.add.curve.storage("SC", [(0, 10), (3, 20)])
    assert other.import_gis.node.storage_unit(tmp_path / "tabular.gpkg", layer="storage_units").ok
    assert other.section("STORAGE") == m.section("STORAGE")


def test_atomic_relation_transitions_preserve_common_fields():
    m = network("CUTOFF")
    m.set.flow_divider.type({"type": "WEIR", "cutoff_flow": 0.01, "weir_height": 0.5, "weir_coefficient": 1.8}, ids="D")
    assert m.get.flow_divider.weir_height(ids="D") == 0.5
    assert m.get.flow_divider.diverted_link(ids="D") == "bypass"
    m.set.flow_divider.type({"type": "OVERFLOW"}, ids="D")
    assert m.get.flow_divider.cutoff_flow(ids="D") is None
    assert m.get.flow_divider.max_depth(ids="D") == 3
    m.add.curve.storage("SC", [(0, 10), (3, 20)])
    m.set.storage_unit.storage_curve_type({"storage_curve_type": "TABULAR", "storage_curve": "SC"}, ids="S")
    assert m.get.storage_unit.initial_depth(ids="S") == 1
    assert m.get.storage_unit.area(ids="S") is None
    m.set.storage_unit.storage_curve_type({"storage_curve_type": "FUNCTIONAL", "area": 200}, ids="S")
    assert m.get.storage_unit.area(ids="S") == 200
    before = m._document.to_text()
    with pytest.raises(MissingRequiredParameterError):
        m.set.flow_divider.type({"type": "WEIR"}, ids="D")
    assert m._document.to_text() == before
