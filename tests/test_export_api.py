from pathlib import Path
import importlib.util

import pandas as pd
import pytest

from swmmx import (
    ExportError,
    ModelNotRunError,
    OptionalDependencyError,
    UnknownExportElementError,
    swmm,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"
HAS_GIS = bool(importlib.util.find_spec("geopandas") and importlib.util.find_spec("shapely"))


def test_export_csv_creates_selected_files_and_unknown_element_is_helpful(tmp_path):
    model = swmm(EXAMPLE)

    with pytest.warns(UserWarning, match="results are unavailable"):
        outputs = model.export.csv(path=tmp_path, elements=["nodes", "links"])

    assert set(outputs) == {"nodes", "links"}
    assert outputs["nodes"].exists()
    assert outputs["links"].exists()
    nodes = pd.read_csv(outputs["nodes"])
    links = pd.read_csv(outputs["links"])
    assert "coordinates" in nodes.columns
    assert "coordinates" in links.columns
    assert nodes["coordinates"].notna().any()
    assert links["coordinates"].notna().any()
    assert {"x", "y"} <= set(nodes.columns)
    assert {"x", "y"}.isdisjoint(links.columns)
    with pytest.raises(UnknownExportElementError, match="Did you mean 'conduits'"):
        model.export.csv(path=tmp_path, elements="conduitz")


def test_export_csv_all_nonempty_tables_include_coordinates_column(tmp_path):
    model = swmm(EXAMPLE)

    outputs = model.export.csv(path=tmp_path, elements="all", include_results=False)

    assert outputs
    for path in outputs.values():
        frame = pd.read_csv(path)
        assert "coordinates" in frame.columns


def test_export_csv_point_based_tables_include_x_y_and_links_do_not(tmp_path):
    model = swmm(EXAMPLE)

    outputs = model.export.csv(
        path=tmp_path,
        elements=["nodes", "junctions", "outfalls", "rain_gages", "subcatchments", "treatments", "coverages", "links"],
        include_results=False,
    )

    for element in ("nodes", "junctions", "outfalls", "rain_gages", "subcatchments", "treatments", "coverages"):
        frame = pd.read_csv(outputs[element])
        assert {"x", "y"} <= set(frame.columns)
        assert frame["x"].notna().any()
        assert frame["y"].notna().any()
    links = pd.read_csv(outputs["links"])
    assert {"x", "y"}.isdisjoint(links.columns)


def test_export_csv_attaches_last_results_and_strict_mode_controls_missing_results(tmp_path):
    model = swmm(EXAMPLE)

    with pytest.raises(ModelNotRunError, match="Result export requested"):
        model.export.csv(path=tmp_path / "strict", elements=["nodes"], strict_results=True)

    model.run()
    outputs = model.export.csv(path=tmp_path / "with_results", elements=["nodes"], time_step=-1)
    nodes = pd.read_csv(outputs["nodes"])

    assert {"depth", "head", "flooding", "result_time_step", "result_timestamp"} <= set(nodes.columns)
    assert nodes["result_time_step"].iloc[0] == model.time.count_run() - 1


def test_export_csv_existing_target_and_overwrite(tmp_path):
    model = swmm(EXAMPLE)
    first = model.export.csv(path=tmp_path, elements=["nodes"], include_results=False)
    assert first["nodes"].exists()

    with pytest.raises(ExportError, match="already exists"):
        model.export.csv(path=tmp_path, elements=["nodes"], include_results=False)

    second = model.export.csv(path=tmp_path, elements=["nodes"], include_results=False, overwrite=True)
    assert second["nodes"].exists()


def test_export_excel_creates_workbook_and_selected_sheets(tmp_path):
    model = swmm(EXAMPLE)

    with pytest.warns(UserWarning, match="results are unavailable"):
        workbook = model.export.excel(path=tmp_path, elements=["nodes", "links"])
    assert workbook.exists()
    sheets = pd.ExcelFile(workbook).sheet_names
    assert sheets == ["nodes", "links"]
    workbook_data = pd.read_excel(workbook, sheet_name=None)
    assert "coordinates" in workbook_data["nodes"].columns
    assert "coordinates" in workbook_data["links"].columns
    assert {"x", "y"} <= set(workbook_data["nodes"].columns)
    assert {"x", "y"}.isdisjoint(workbook_data["links"].columns)

    only_conduits = model.export.excel(
        path=tmp_path,
        file_name="only_conduits.xlsx",
        elements=["conduits"],
        include_results=False,
    )
    assert pd.ExcelFile(only_conduits).sheet_names == ["conduits"]

    with pytest.raises(ExportError, match="must end with .xlsx"):
        model.export.excel(path=tmp_path, file_name="model.txt", elements=["nodes"], include_results=False)


def test_export_default_path_uses_model_folder_or_current_directory(tmp_path, monkeypatch):
    saved_model = swmm(EXAMPLE)
    model_path = saved_model.save(tmp_path / "saved_model.inp")
    outputs = saved_model.export.csv(elements=["nodes"], include_results=False, overwrite=True)
    assert outputs["nodes"].parent == model_path.parent

    unsaved_model = swmm(new="SI")
    unsaved_model.add.node.junction("J1", x=0.0, y=0.0)
    monkeypatch.chdir(tmp_path)
    unsaved_outputs = unsaved_model.export.csv(elements=["junctions"], include_results=False, overwrite=True)
    assert unsaved_outputs["junctions"].parent == tmp_path


def test_export_gis_missing_optional_dependencies_is_clear(monkeypatch):
    import swmmx.export.gis as gis_module

    monkeypatch.setattr(gis_module.importlib.util, "find_spec", lambda _name: None)
    model = swmm(EXAMPLE)

    with pytest.raises(OptionalDependencyError, match="pip install geopandas shapely"):
        model.export.gis()


@pytest.mark.skipif(not HAS_GIS, reason="GeoPandas/Shapely are not installed in this environment.")
def test_export_gis_writes_spatial_layers(tmp_path):
    import geopandas as gpd

    model = swmm(EXAMPLE)
    with pytest.warns(UserWarning, match="results are unavailable"):
        node_outputs = model.export.gis(path=tmp_path / "nodes", elements=["nodes"])
    link_outputs = model.export.gis(path=tmp_path / "links", elements=["links"], include_results=False)
    sub_outputs = model.export.gis(path=tmp_path / "subcatchments", elements=["subcatchments"], include_results=False)

    assert node_outputs["nodes"].exists()
    assert link_outputs["links"].exists()
    assert sub_outputs["subcatchments"].exists()
    assert set(gpd.read_file(node_outputs["nodes"]).geometry.geom_type) == {"Point"}
    assert set(gpd.read_file(link_outputs["links"]).geometry.geom_type) == {"LineString"}
    assert set(gpd.read_file(sub_outputs["subcatchments"]).geometry.geom_type) == {"Polygon"}
    node_columns = {column.lower() for column in gpd.read_file(node_outputs["nodes"]).columns}
    link_columns = {column.lower() for column in gpd.read_file(link_outputs["links"]).columns}
    sub_columns = {column.lower() for column in gpd.read_file(sub_outputs["subcatchments"]).columns}
    assert any(column.startswith("coordinate") for column in node_columns)
    assert any(column.startswith("coordinate") for column in link_columns)
    assert any(column.startswith("coordinate") for column in sub_columns)
    assert {"x", "y"} <= node_columns
    assert {"x", "y"} <= sub_columns
    assert {"x", "y"}.isdisjoint(link_columns)
