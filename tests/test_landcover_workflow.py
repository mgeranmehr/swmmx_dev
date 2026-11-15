"""Frontend contract, bulk editing, revisions, units and GIS cancellation tests."""

import json
from pathlib import Path

import pandas as pd
import pytest

from swmmx import (
    LandCover,
    LandCoverCancelled,
    LandCoverPreview,
    LandCoverValidationError,
    ValidationError,
    landcover,
    swmm,
)

ROOT = Path(__file__).resolve().parents[1]


def test_invalid_preset_does_not_attach_to_model():
    m = swmm(ROOT / "examples/example.inp")
    with pytest.raises(ValidationError, match="preset"):
        landcover(m, preset="unknown")
    assert getattr(m, "_landcover", None) is None


def test_comparison_rejects_different_property_units():
    first = manager(units="SI")
    second = manager(units="US")
    with pytest.raises(ValidationError, match="property units"):
        first.compare(second)


def manager(attached=False, units="SI"):
    m = swmm(ROOT / "examples/example.inp") if attached else None
    lc = landcover(m, units=units)
    lc.define_classes(
        {
            "roof": {"impervious": 1, "n_imp": 0.012, "dstore_imp": 25.4},
            "green": {
                "impervious": 0,
                "n_perv": 0.2,
                "dstore_perv": 50.8,
                "infiltration": {
                    "model": "GREEN_AMPT",
                    "suction_head": 25.4,
                    "hydraulic_conductivity": 50.8,
                    "initial_moisture_deficit": 0.25,
                },
            },
        }
    )
    lc.set_coverage(
        {"CA-1" if attached else "S1": {"roof": 0.4, "green": 0.6}},
        area_m2=None if attached else 10000,
    )
    return lc


def test_bulk_atomic_diagnostics_and_dry_run():
    lc = manager()
    before = lc.to_project().to_json()
    data = [
        {"name": "a", "impervious": 2},
        {"name": "b", "n_imp": 0},
        {"name": "valid", "impervious": 1},
    ]
    report = lc.define_classes(data, validate_only=True)
    assert len(report.issues) == 2 and not report.can_apply
    assert report.issues[0].row == 0
    assert lc.to_project().to_json() == before
    with pytest.raises(LandCoverValidationError) as error:
        lc.define_classes(data)
    assert len(error.value.report.issues) == 2
    assert lc.to_project().to_json() == before
    assert not lc.has_class("valid")


def test_bulk_csv_and_dataframe(tmp_path):
    lc = landcover(units="SI")
    pd.DataFrame(
        [
            {"name": "roof", "impervious": 1, "lids": '{"green_roof":0.7}'},
            {"name": "green", "impervious": 0},
        ]
    ).to_csv(tmp_path / "classes.csv", index=False)
    lc.define_classes(tmp_path / "classes.csv")
    assert lc.classes["roof"].lids == {"green_roof": 0.7}
    pd.DataFrame(
        [{"subcatchment": "S", "roof": 30, "green": 70, "area_m2": 1000}]
    ).to_csv(tmp_path / "cover.csv", index=False)
    lc.set_coverage(tmp_path / "cover.csv", units="percent")
    assert lc.coverage_area("S", "roof") == 300
    lc.set_coverage(
        pd.DataFrame(
            {"roof": [0.5], "green": [0.5]}, index=pd.Index(["S"], name="subcatchment")
        ),
        area_m2=1000,
        overwrite=True,
    )
    assert lc.coverage_fraction("S", "roof") == 0.5


@pytest.mark.parametrize(
    "field,values",
    [
        ("fraction", [0.3, 0.7]),
        ("percent", [30, 70]),
        ("area_m2", [300, 700]),
        ("area_ha", [0.03, 0.07]),
    ],
)
def test_long_coverage_units(field, values):
    lc = manager()
    rows = [
        {
            "subcatchment": "new",
            "class_id": lc.class_id(c),
            field: v,
            "total_area_m2": 1000,
        }
        for c, v in zip(["roof", "green"], values)
    ]
    lc.set_coverage(rows)
    assert lc.coverage_area("new", "roof") == 300


def test_bulk_coverage_failure_is_atomic():
    lc = manager()
    before = lc.to_project().to_json()
    data = {"a": {"roof": 0.1}, "b": {"unknown": 1}, "ok": {"roof": 1}}
    report = lc.set_coverage(data, validate_only=True)
    assert len(report.issues) == 2
    with pytest.raises(LandCoverValidationError):
        lc.set_coverage(data)
    assert lc.to_project().to_json() == before
    duplicates = [
        {"subcatchment": "n", "class": "roof", "fraction": 0.5},
        {"subcatchment": "n", "class": "roof", "fraction": 0.5},
    ]
    with pytest.raises(LandCoverValidationError):
        lc.set_coverage(duplicates)


def test_update_identity_undo_redo_and_atomicity():
    lc = manager()
    uid = lc.class_id("roof")
    initial = lc.revision
    lc.rename_class("roof", "building")
    assert lc.class_name(uid) == "building"
    assert uid in lc.to_project().to_dict()["coverage"][0]["fractions"]
    lc.update_class("building", n_imp=0.02)
    assert lc.class_id("building") == uid
    lc.undo()
    assert lc.classes["building"].n_imp == 0.012
    lc.undo()
    assert lc.class_name(uid) == "roof"
    lc.redo()
    assert lc.class_name(uid) == "building"
    assert lc.revision > initial and lc.history()
    with pytest.raises(ValidationError):
        lc.update_class("building", impervious=4)
    assert lc.classes["building"].impervious == 1


def test_preview_collects_missing_properties_without_model_mutation():
    lc = manager(True)
    lc.update_class("roof", n_imp=None, dstore_imp=None)
    lc.update_class("green", n_perv=None, dstore_perv=None)
    before = lc.model._document.to_text()
    preview = lc.preview()
    assert not preview.can_apply
    assert len([i for i in preview.issues if i.code == "MISSING_PROPERTY"]) == 4
    assert preview.values.loc["CA-1", "percent_impervious"] == 40
    assert before == lc.model._document.to_text()
    assert lc.preview(["imperviousness"]).can_apply


def test_preview_units_adapter_and_json_roundtrip():
    lc = manager(True, units="SI")
    before = lc.model._document.to_text()
    p = lc.preview(
        ["imperviousness", "roughness", "depression_storage", "infiltration"]
    )
    assert p.can_apply and p.values.loc["CA-1", "dstore_imperv"] == pytest.approx(1)
    assert p.values.loc["CA-1", "dstore_perv"] == pytest.approx(2)
    assert p.values.loc["CA-1", "hydraulic_conductivity"] == pytest.approx(2)
    assert lc.classes["roof"].dstore_imp == 25.4
    assert before == lc.model._document.to_text()
    json.dumps(p.to_dict(), allow_nan=False)
    values_copy = p.values
    values_copy.loc["CA-1", "percent_impervious"] = 99
    assert p.values.loc["CA-1", "percent_impervious"] == 40
    lc.model._run_timestamps = [1]
    lc.apply(p.preview_id)
    assert lc.model.get.subcatchment.depression_storage_impervious(
        ids="CA-1"
    ) == pytest.approx(1)
    assert lc.model.get.infiltration_green_ampt.hydraulic_conductivity(
        ids="CA-1"
    ) == pytest.approx(2)
    assert lc.model.modified and lc.model.results_stale
    assert lc.status["model_updated"]
    with pytest.raises(ValidationError):
        lc.apply(p)


@pytest.mark.parametrize(
    "change", ["metadata", "model", "undo", "direct_source", "other_manager"]
)
def test_stale_or_foreign_preview(change):
    lc = manager(True)
    p = lc.preview()
    if change == "metadata":
        lc.update_class("roof", n_imp=0.015)
    elif change == "model":
        lc.model.set.subcatchment.width(900, ids="CA-1")
    elif change == "undo":
        lc.update_class("roof", n_imp=0.015)
        lc.undo()
    elif change == "direct_source":
        lc.source["note"] = "changed"
    else:
        lc = landcover(lc.model.clone())
    before = lc.model._document.to_text()
    with pytest.raises(ValidationError):
        lc.apply(p)
    assert lc.model._document.to_text() == before


def test_tampered_preview_rejected():
    lc = manager(True)
    p = lc.preview()
    data = p.to_dict()
    data["values"][0]["percent_impervious"] = 90
    with pytest.raises(ValidationError):
        lc.apply(LandCoverPreview(json.dumps(data)))


def test_standalone_and_lightweight_scenario():
    lc = manager(True, units="native")
    scenario = lc.scenario("future")
    assert scenario.model is None and scenario.units == "US"
    assert scenario.project_id != lc.project_id
    assert scenario.class_id("roof") == lc.class_id("roof")
    assert scenario.coverage_area("CA-1", "roof") == lc.coverage_area("CA-1", "roof")
    scenario.convert("CA-1", "roof", "green", fraction=0.1)
    assert lc.coverage_fraction("CA-1", "roof") == 0.4
    assert not scenario.preview().can_apply
    assert lc.scenario(clone_model=True).model is not lc.model
    assert lc.copy().model is not None


def test_project_roundtrip_migration_and_invalid_versions(tmp_path):
    lc = manager(units="SI")
    lc.rename_class("roof", "building")
    project = lc.to_project()
    restored = LandCover.from_project(project.to_json())
    assert restored.class_id("building") == lc.class_id("building")
    assert restored.units == "SI"
    pd.testing.assert_frame_equal(lc.coverage_table(), restored.coverage_table())
    path = lc.save(tmp_path / "cover.json")
    assert LandCover.load(path).class_id("building") == lc.class_id("building")
    legacy = {
        "version": 1,
        "classes": [{"name": "roof", "impervious": 1}],
        "coverage": [{"subcatchment": "S", "fractions": {"roof": 1}, "area_m2": 100}],
        "source": {},
    }
    migrated = LandCover.from_project(legacy)
    assert (
        migrated.units == "native" and migrated.to_project().to_dict()["version"] == 2
    )
    for bad in ["{bad", {"version": 99}, {**project.to_dict(), "revision": -1}]:
        with pytest.raises(ValidationError):
            LandCover.from_project(bad)
    data = project.to_dict()
    data["classes"][1]["class_id"] = data["classes"][0]["class_id"]
    with pytest.raises(ValidationError):
        LandCover.from_project(data)


def test_preset_names_only_and_unit_conflict():
    lc = landcover(preset="urban", units="SI")
    assert lc.has_class("roof") and lc.classes["roof"].impervious is None
    lc.set_coverage({"S": {"roof": 1}})
    assert not lc.preview().can_apply
    m = manager(True).model
    with pytest.raises(ValidationError):
        landcover(m, units="US")


def test_noop_preserves_native_state_and_edit_history():
    lc = manager(True)
    lc.apply(lc.preview())
    lc.model._run_timestamps = [1]
    history = lc.history()
    lc.apply(lc.preview())
    assert lc.model.has_run and not lc.model.results_stale
    assert lc.history() == history
    old = lc.revision
    lc.update_class("roof", n_imp=0.012)
    assert lc.revision == old


def test_coverage_only_gis_progress_cancel_and_history():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    lc = landcover(preset="urban", units="SI")
    surfaces = gpd.GeoDataFrame(
        {"surface": ["roof", "green"]},
        geometry=[box(0, 0, 4, 10), box(4, 0, 10, 10)],
        crs=32639,
    )
    subs = gpd.GeoDataFrame(
        {"subcatchment": ["S"]}, geometry=[box(0, 0, 10, 10)], crs=32639
    )
    lc.set_surfaces(surfaces, class_column="surface")
    events = []
    before = lc.to_project().to_json()

    def progress(event):
        events.append(event)

    with pytest.raises(LandCoverCancelled):
        lc.calculate_coverage(
            subs, progress=progress, cancelled=lambda: len(events) >= 3
        )
    assert lc.to_project().to_json() == before and lc.coverage_table().empty
    lc.calculate_coverage(subs, progress=progress)
    frame = lc.coverage_geodataframe()
    assert frame.roof_fraction.iloc[0] == 0.4
    assert "percent_impervious" not in frame
    assert lc.status["spatial_state"] == "ready"
    import matplotlib.pyplot as plt

    lc.plot(class_name="roof")
    plt.close("all")
    lc.convert("S", "roof", "green", fraction=0.1)
    assert lc.status["spatial_state"] == "stale"
    lc.undo()
    assert lc.status["spatial_state"] == "ready"
    assert events[-1]["stage"] == "ready_to_commit"
