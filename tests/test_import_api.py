from pathlib import Path

import pandas as pd
import pytest

from swmmx import (
    ImportResult,
    SwmmxImportAmbiguousFieldError,
    SwmmxImportDependencyError,
    SwmmxImportFieldError,
    SwmmxImportValidationError,
    swmm,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_INP = ROOT / "examples" / "example.inp"


def _csv(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def test_import_csv_junction_aliases_and_optional_fields(tmp_path):
    model = swmm(new="SI")
    path = _csv(
        tmp_path,
        "junctions.csv",
        {
            "Node ID": ["J1", "J2"],
            "Easting": [0.0, 10.0],
            "Northing": [1.0, 1.0],
            "Invert Elev.": [2.0, 3.0],
            "Max Depth": [4.0, 5.0],
        },
    )

    result = model.import_csv.node.junction(path)

    assert isinstance(result, ImportResult)
    assert result.ok
    assert result.rows_imported == 2
    assert result.field_matches["id"] == "Node ID"
    assert model.modified
    assert list(model.get.node.id()) == ["J1", "J2"]
    assert list(model.get.junction.invert_elevation()) == [2.0, 3.0]
    assert list(model.get.junction.max_depth()) == [4.0, 5.0]


def test_import_csv_explicit_field_map_for_conduit(tmp_path):
    model = swmm(new="SI")
    model.import_csv.node.junction(_csv(tmp_path, "nodes.csv", {"id": ["J1", "J2"], "x": [0, 10], "y": [0, 0]}))
    path = _csv(
        tmp_path,
        "pipes.csv",
        {
            "PipeID": ["C1"],
            "US_Node": ["J1"],
            "DS_Node": ["J2"],
            "Length_m": [10.0],
            "ManningN": [0.014],
            "Dia_mm": [1.2],
        },
    )

    result = model.import_csv.link.conduit(
        path,
        field_map={
            "id": "PipeID",
            "from_node": "US_Node",
            "to_node": "DS_Node",
            "length": "Length_m",
            "roughness": "ManningN",
            "diameter": "Dia_mm",
        },
    )

    assert result.rows_imported == 1
    assert list(model.get.conduit.length()) == [10.0]
    assert list(model.get.conduit.roughness()) == [0.014]
    assert model.get.conduit.geometry()[0][0] == 1.2


def test_import_csv_conduit_common_aliases_without_field_map(tmp_path):
    model = swmm(new="SI")
    model.import_csv.node.junction(_csv(tmp_path, "nodes.csv", {"id": ["J1"], "x": [0], "y": [0]}))
    model.import_csv.node.outfall(_csv(tmp_path, "outfalls.csv", {"id": ["O1"], "x": [10], "y": [0]}))
    path = _csv(
        tmp_path,
        "pipes_aliases.csv",
        {
            "PipeID": ["C1"],
            "FromNode": ["J1"],
            "ToNode": ["O1"],
            "Length": [10.0],
            "ManningN": [0.013],
            "Diameter": [1.0],
        },
    )

    result = model.import_csv.link.conduit(path)

    assert result.rows_imported == 1
    assert list(model.get.link.id()) == ["C1"]


def test_import_csv_exact_exported_input_fields_win_over_result_aliases(tmp_path):
    model = swmm(new="SI")
    path = _csv(
        tmp_path,
        "exported_junctions.csv",
        {
            "id": ["J1"],
            "x": [0.0],
            "y": [0.0],
            "max_depth": [4.0],
            "depth": [0.123],
            "head": [5.0],
            "result_timestamp": ["2026-01-01 00:00:00"],
        },
    )

    result = model.import_csv.node.junction(path)

    assert result.rows_imported == 1
    assert model.get.junction.max_depth()[0] == 4.0
    assert "depth" in result.ignored_columns


def test_import_csv_missing_and_ambiguous_fields_are_clear(tmp_path):
    model = swmm(new="SI")

    with pytest.raises(SwmmxImportFieldError, match="Missing required"):
        model.import_csv.node.junction(_csv(tmp_path, "missing.csv", {"id": ["J1"], "x": [0.0]}))

    with pytest.raises(SwmmxImportAmbiguousFieldError, match="Multiple columns match"):
        model.import_csv.node.junction(
            _csv(tmp_path, "ambiguous.csv", {"node_id": ["J1"], "name": ["JX"], "x": [0.0], "y": [0.0]})
        )


def test_import_csv_unknown_fields_modes_and_dry_run(tmp_path):
    model = swmm(new="SI")
    path = _csv(tmp_path, "junctions.csv", {"id": ["J1"], "x": [0.0], "y": [0.0], "unused field": [1]})

    warned = model.import_csv.node.junction(path, on_unknown_fields="warn", dry_run=True)
    assert warned.rows_imported == 1
    assert warned.has_warnings
    assert list(model.get.node.id()) == []

    with pytest.raises(SwmmxImportFieldError, match="Unknown or unmapped"):
        model.import_csv.node.junction(path, on_unknown_fields="error", dry_run=True)


def test_import_csv_add_update_upsert_modes(tmp_path):
    model = swmm(new="SI")
    initial = _csv(tmp_path, "initial.csv", {"id": ["J1"], "x": [0.0], "y": [0.0], "invert_elevation": [1.0]})
    model.import_csv.node.junction(initial)

    with pytest.raises(Exception, match="already exists"):
        model.import_csv.node.junction(initial, mode="add")

    with pytest.raises(Exception, match="Unknown"):
        model.import_csv.node.junction(
            _csv(tmp_path, "missing_update.csv", {"id": ["J2"], "x": [2.0], "y": [2.0]}),
            mode="update",
        )

    update = _csv(tmp_path, "update.csv", {"id": ["J1", "J2"], "x": [1.0, 2.0], "y": [1.0, 2.0], "invert_elevation": [5.0, 6.0]})
    result = model.import_csv.node.junction(update, mode="upsert")

    assert result.rows_updated == 1
    assert result.rows_imported == 1
    assert list(model.get.junction.invert_elevation()) == [5.0, 6.0]


def test_import_csv_group_level_node_and_link_dispatch(tmp_path):
    model = swmm(new="SI")
    node_path = _csv(
        tmp_path,
        "nodes.csv",
        {"id": ["J1", "O1"], "type": ["junction", "outfall"], "x": [0.0, 10.0], "y": [0.0, 0.0]},
    )

    node_result = model.import_csv.node(node_path)

    assert node_result.rows_imported == 2
    assert list(model.get.node.id()) == ["J1", "O1"]

    link_path = _csv(
        tmp_path,
        "links.csv",
        {
            "id": ["C1"],
            "type": ["conduit"],
            "from_node": ["J1"],
            "to_node": ["O1"],
            "length": [10.0],
            "roughness": [0.013],
            "diameter": [1.0],
        },
    )

    link_result = model.import_csv.link(link_path)

    assert link_result.rows_imported == 1
    assert list(model.get.link.id()) == ["C1"]


def test_import_csv_integration_nodes_conduits_validate_and_save(tmp_path):
    model = swmm(new="SI")
    model.import_csv.node.junction(_csv(tmp_path, "junctions.csv", {"id": ["J1"], "x": [0.0], "y": [0.0]}))
    model.import_csv.node.outfall(_csv(tmp_path, "outfalls.csv", {"id": ["O1"], "x": [10.0], "y": [0.0]}))
    model.import_csv.link.conduit(
        _csv(
            tmp_path,
            "conduits.csv",
            {"id": ["C1"], "from_node": ["J1"], "to_node": ["O1"], "length": [10.0], "roughness": [0.013]},
        )
    )

    validation = model.validate()
    assert not validation.errors
    out = tmp_path / "imported.inp"
    model.save(out)
    assert out.exists()


def test_import_csv_time_series_groups_rows_and_accepts_time_column(tmp_path):
    model = swmm(new="SI")
    path = _csv(
        tmp_path,
        "timeseries.csv",
        {
            "id": ["TS1", "TS1"],
            "time": ["2026-01-01 00:00", "2026-01-01 00:05"],
            "value": [0.0, 1.2],
        },
    )

    result = model.import_csv.time.time_series(path)

    assert result.rows_imported == 1
    assert list(model.get.time_series.id()) == ["TS1"]


def test_import_csv_exported_individual_tables_round_trip(tmp_path):
    source = swmm(EXAMPLE_INP)
    source.run()
    outputs = source.export.csv(
        path=tmp_path / "csv",
        elements=["time_series", "rain_gages", "junctions", "outfalls", "subcatchments", "conduits"],
        time_step=-1,
        overwrite=True,
    )
    target = swmm()

    assert target.import_csv.time.time_series(outputs["time_series"]).rows_imported == 1
    assert target.import_csv.node.junction(outputs["junctions"]).rows_imported == len(source.get.junction.id())
    assert target.import_csv.node.outfall(outputs["outfalls"]).rows_imported == len(source.get.outfall.id())
    assert target.import_csv.hydrology.rain_gage(outputs["rain_gages"]).rows_imported == len(source.get.rain_gage.id())
    assert target.import_csv.hydrology.subcatchment(outputs["subcatchments"]).rows_imported == len(source.get.subcatchment.id())
    assert target.import_csv.link.conduit(outputs["conduits"]).rows_imported == len(source.get.conduit.id())
    assert not target.validate().errors


def test_import_csv_exported_group_tables_use_element_type_for_dispatch(tmp_path):
    source = swmm(EXAMPLE_INP)
    source.run()
    outputs = source.export.csv(
        path=tmp_path / "csv",
        elements=["time_series", "rain_gages", "nodes", "links"],
        time_step=-1,
        overwrite=True,
    )
    target = swmm()

    target.import_csv.time.time_series(outputs["time_series"])
    nodes = target.import_csv.node(outputs["nodes"])
    target.import_csv.hydrology.rain_gage(outputs["rain_gages"])
    links = target.import_csv.link(outputs["links"])

    assert nodes.rows_imported == len(source.get.node.id())
    assert links.rows_imported == len(source.get.link.id())
    assert not target.validate().errors


def test_import_result_helpers_and_collect_errors(tmp_path):
    model = swmm(new="SI")
    result = model.import_csv.node.junction(
        _csv(tmp_path, "bad.csv", {"id": ["J1"], "x": [0.0]}),
        on_missing_required="skip",
        on_error="collect",
    )

    assert not result.ok
    assert result.rows_skipped == 1
    assert result.to_dict()["rows_total"] == 1
    assert not result.to_frame().empty
    assert "failed" in result.summary() or "skipped=1" in result.summary()


def test_import_gis_missing_dependency_is_clear(tmp_path):
    model = swmm(new="SI")
    with pytest.raises(SwmmxImportDependencyError, match="GIS import requires geopandas and shapely"):
        model.import_gis.node.junction(tmp_path / "junctions.geojson")
