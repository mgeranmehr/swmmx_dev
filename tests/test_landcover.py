"""Local numerical, integration and adversarial tests for physical landcover."""

import json
import math
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from swmmx import DuplicateIDError, LandCover, ValidationError, landcover, swmm

ROOT = Path(__file__).resolve().parents[1]


def sample(attached=False):
    lc = landcover(swmm(ROOT / "examples/example.inp") if attached else None)
    definitions = [
        ("roof", 1, 0.012, None, 1.5, None),
        ("road", 1, 0.013, None, 2, None),
        ("pedestrian", 0.8, 0.015, 0.15, 2, 4),
        ("green", 0, None, 0.2, None, 5),
        ("other", 0.3, 0.015, 0.18, 2, 5),
    ]
    for name, imp, ni, np, di, dp in definitions:
        lc.add_class(
            name,
            impervious=imp,
            n_imp=ni,
            n_perv=np,
            dstore_imp=di,
            dstore_perv=dp,
            lids={"bio": 0.4}
            if name == "green"
            else {"roof_lid": 0.7}
            if name == "roof"
            else {},
        )
    lc.assign(
        "CA-1" if attached else "S1",
        dict(zip(lc.list_classes(), [0.3, 0.25, 0.1, 0.25, 0.1])),
        area_m2=None if attached else 25000,
    )
    return lc


@pytest.mark.parametrize(
    "kwargs",
    [
        {"impervious": -0.1},
        {"impervious": 1.1},
        {"impervious": float("nan")},
        {"n_imp": 0},
        {"n_perv": -1},
        {"dstore_imp": -1},
        {"dstore_perv": float("inf")},
        {"pct_zero": 101},
        {"lids": {"x": 1.1}},
        {"lids": []},
        {"attributes": []},
        {"description": 1},
        {"impervious": True},
        {"n_imp": "0.1"},
        {"attributes": {"x": float("nan")}},
        {"lids": {"x": {"suitable_fraction": 0.1, "unknown": 2}}},
    ],
)
def test_invalid_class(kwargs):
    with pytest.raises(ValidationError):
        landcover().add_class("bad", **kwargs)


@pytest.mark.parametrize("name", ["", " ", " bad", "bad;", "a\nb", 'a"b'])
def test_invalid_names(name):
    with pytest.raises(ValidationError):
        landcover().add_class(name)


def test_classes():
    lc = sample()
    with pytest.raises(DuplicateIDError):
        lc.add_class("ROOF")
    with pytest.raises(ValidationError):
        lc.remove_class("roof")
    lc.add_class("unused", attributes={"cost": 2})
    assert lc.classes["unused"].attributes["cost"] == 2
    lc.classes["unused"].attributes["cost"] = 5
    assert lc.get_class("unused").attributes["cost"] == 2
    lc.remove_class("unused")
    lc.rename_class("roof", "building")
    assert lc.coverage_fraction("S1", "building") == 0.3
    assert lc.has_class("building")


@pytest.mark.parametrize(
    "units,values",
    [
        ("fraction", [0.4, 0.6]),
        ("percent", [40, 60]),
        ("m2", [400, 600]),
        ("ha", [0.04, 0.06]),
    ],
)
def test_assignment_units(units, values):
    lc = landcover()
    lc.add_class("a")
    lc.add_class("b")
    lc.assign("S", dict(zip(["a", "b"], values)), units=units, area_m2=1000)
    assert lc.coverage_fraction("S", "a") == pytest.approx(0.4)
    assert lc.coverage_area("S", "b") == pytest.approx(600)
    assert lc.dominant_class("S") == "b"


@pytest.mark.parametrize(
    "values,units",
    [
        ({"roof": -0.1}, "fraction"),
        ({"roof": 1.1}, "fraction"),
        ({"roof": 101}, "percent"),
        ({"roof": 0.2}, "fraction"),
        ({"roof": 0.7, "road": 0.7}, "fraction"),
        ({"unknown": 1}, "fraction"),
        ({"roof": float("inf")}, "m2"),
        ({"roof": 0}, "fraction"),
    ],
)
def test_bad_assignments(values, units):
    lc = sample()
    with pytest.raises(ValidationError):
        lc.assign("S2", values, units=units, area_m2=1000)
    assert list(lc.coverage_table().index) == ["S1"]


def test_normalize_and_duplicates():
    lc = sample()
    lc.assign("S2", {"roof": 0.2, "green": 0.3}, normalize=True)
    assert lc.coverage_fraction("S2", "roof") == 0.4
    lc.normalize("S2")
    with pytest.raises(DuplicateIDError):
        lc.assign("S2", {"roof": 1})
    with pytest.raises(ValidationError):
        lc.assign("S3", {"roof": 0}, normalize=True)
    with pytest.raises(ValidationError):
        lc.assign("S3", {"roof": 10}, units="m2")
    with pytest.raises(ValidationError):
        lc.coverage_area("S2", "roof")


def test_model_area_and_attach():
    lc = sample(True)
    assert lc.coverage_area("CA-1", "roof") == pytest.approx(4.999 * 4046.8564224 * 0.3)
    with pytest.raises(ValidationError):
        lc.assign("bad", {"roof": 1})
    lc.model.set.subcatchment.area(9, ids="CA-1")
    with pytest.raises(ValidationError, match="area changed"):
        lc.derive_hydrology()
    m = swmm(ROOT / "examples/example.inp")
    other = landcover()
    other.add_class("x")
    other.assign("CA-1", {"x": 1})
    other.attach(m)
    assert landcover(m) is other


def test_exact_hydrology():
    row = sample().derive_hydrology().loc["S1"]
    assert row.percent_impervious == pytest.approx(66)
    assert row.n_imperv == pytest.approx(
        (0.3 * 0.012 + 0.25 * 0.013 + 0.08 * 0.015 + 0.03 * 0.015) / 0.66
    )
    assert row.n_perv == pytest.approx((0.02 * 0.15 + 0.25 * 0.2 + 0.07 * 0.18) / 0.34)
    assert row.dstore_imperv == pytest.approx(
        (0.3 * 1.5 + 0.25 * 2 + 0.08 * 2 + 0.03 * 2) / 0.66
    )
    assert row.dstore_perv == pytest.approx((0.02 * 4 + 0.25 * 5 + 0.07 * 5) / 0.34)


@pytest.mark.parametrize(
    "name,imp,missing", [("roof", 100, "n_perv"), ("green", 0, "n_imperv")]
)
def test_absent_surface(name, imp, missing):
    lc = sample()
    lc.assign("S1", {name: 1}, overwrite=True, area_m2=25000)
    row = lc.derive_hydrology().loc["S1"]
    assert row.percent_impervious == imp
    assert math.isnan(row[missing])


def test_missing_selective_atomic_and_state(tmp_path):
    lc = sample(True)
    m = lc.model
    m.save(tmp_path / "before.inp")
    m._run_timestamps = [1]
    before = m._document.to_text()
    lc.derive_hydrology()
    lc.convert("CA-1", "road", "green", fraction=0.01)
    assert m._document.to_text() == before and not m.modified and not m.results_stale
    lc.apply_hydrology(roughness=False, depression_storage=False)
    assert m.modified and m.results_stale
    assert m.get.subcatchment.n_impervious(ids="CA-1") == 0.015
    lc.add_class("missing", impervious=1)
    lc.assign("CA-7", {"missing": 1})
    before = m._document.to_text()
    with pytest.raises(ValidationError, match="n_imp"):
        lc.apply_hydrology()
    assert before == m._document.to_text()
    lc.apply_hydrology(roughness=False, depression_storage=False)


def test_pct_zero():
    lc = landcover()
    lc.add_class("a", impervious=0.5, pct_zero=20)
    lc.add_class("b", impervious=1, pct_zero=80)
    lc.assign("s", {"a": 0.5, "b": 0.5})
    assert lc.derive_hydrology(
        roughness=False, depression_storage=False, pct_zero=True
    ).loc["s", "pct_zero"] == pytest.approx(60)


def test_lids():
    lc = sample()
    table = lc.lid_candidates("S1").set_index("lid_type")
    assert table.loc["roof_lid", "candidate_area_m2"] == pytest.approx(5250)
    assert table.loc["bio", "candidate_fraction"] == pytest.approx(0.1)
    lc.add_class(
        "parking",
        impervious=1,
        lids={"bio": {"suitable_fraction": 0.5, "min_area": 10, "priority": 0.8}},
    )
    lc.assign("S2", {"green": 0.5, "parking": 0.5}, area_m2=100)
    assert lc.lid_candidates("S2").iloc[0].candidate_area_m2 == 45
    assert lc.lid_candidates("S2").iloc[1].candidate_area_m2 == 0
    assert (
        lc.lid_candidates(
            filter_function=lambda row: row["candidate_area_m2"] / 2
        ).candidate_area_m2
        <= lc.lid_candidates().candidate_area_m2
    ).all()
    with pytest.raises(ValidationError):
        lc.lid_candidates(filter_function=lambda row: row["candidate_area_m2"] + 1)
    pd.testing.assert_frame_equal(lc.lid_candidates(), lc.lid_candidates())


def test_scenarios():
    lc = sample()
    future = deepcopy(lc)
    future.convert("S1", "road", "green", area=500)
    assert future.coverage_fraction("S1", "road") == 0.23
    assert lc.coverage_fraction("S1", "road") == 0.25
    assert sum(future.coverage("S1").fractions.values()) == pytest.approx(1)
    assert lc.compare(future).loc["S1", "percent_impervious"] == pytest.approx(-2)
    assert lc.compare(future).loc["S1", "green_area_m2"] == pytest.approx(500)
    with pytest.raises(ValidationError):
        future.convert("S1", "road", "green", fraction=0.9)
    with pytest.raises(ValidationError):
        future.convert("S1", "wrong", "green", fraction=0.1)
    with pytest.raises(ValidationError):
        future.convert("S1", "road", "wrong", fraction=0.1)
    attached = sample(True)
    other = attached.copy()
    other.apply_hydrology()
    assert attached.model.get.subcatchment.impervious_percent(ids="CA-1") == 39


def test_persistence_native_and_clone(tmp_path):
    lc = sample(True)
    lc.source = {"source_file": "local.gpkg"}
    lc.add_class("custom", attributes={"cost": 12})
    lc.apply_hydrology()
    lc.apply_swmm_landuses(overwrite=True)
    assert (
        float(
            next(
                r[2] for r in lc.model.section("COVERAGES") if r[:2] == ["CA-1", "roof"]
            )
        )
        == 30
    )
    with pytest.raises(ValidationError):
        lc.apply_swmm_landuses()
    lc.apply_swmm_landuses(overwrite=True)
    target = lc.model.save(tmp_path / "model.inp")
    reopened = swmm(target)
    recovered = landcover(reopened)
    pd.testing.assert_frame_equal(lc.coverage_table(), recovered.coverage_table())
    assert recovered.get_class("custom").attributes == {"cost": 12}
    assert recovered.source == lc.source
    assert recovered.get_class("roof").lids == {"roof_lid": 0.7}
    assert reopened.get.subcatchment.impervious_percent(ids="CA-1") == 66
    assert "LANDCOVER" not in target.read_text().upper()
    assert landcover(lc.model.clone()).coverage_fraction("CA-1", "roof") == 0.3
    plain = swmm(ROOT / "examples/example.inp")
    path = plain.save(tmp_path / "plain.inp")
    assert not path.with_suffix(".swmmx.json").exists()
    assert landcover(swmm(path)).list_classes() == []
    target.with_suffix(".swmmx.json").write_text("{broken")
    with pytest.raises(ValidationError, match="sidecar"):
        landcover(swmm(target))


@pytest.mark.parametrize(
    "model,params",
    [
        (
            "GREEN_AMPT",
            {
                "suction_head": 110,
                "hydraulic_conductivity": 12,
                "initial_moisture_deficit": 0.25,
            },
        ),
        (
            "MODIFIED_GREEN_AMPT",
            {
                "suction_head": 110,
                "hydraulic_conductivity": 12,
                "initial_moisture_deficit": 0.25,
            },
        ),
        (
            "HORTON",
            {
                "maximum_rate": 10,
                "minimum_rate": 1,
                "decay": 2,
                "dry_time": 3,
                "maximum_volume": 0,
            },
        ),
        (
            "MODIFIED_HORTON",
            {
                "maximum_rate": 10,
                "minimum_rate": 1,
                "decay": 2,
                "dry_time": 3,
                "maximum_volume": 0,
            },
        ),
        ("CURVE_NUMBER", {"curve_number": 80, "conductivity": 0, "dry_time": 3}),
    ],
)
def test_infiltration(model, params):
    lc = landcover()
    lc.add_class("a", impervious=0, infiltration={"model": model, **params})
    lc.add_class(
        "b",
        impervious=0.5,
        infiltration={"model": model, **{k: v / 2 for k, v in params.items()}},
    )
    lc.assign("s", {"a": 0.5, "b": 0.5})
    result = lc.derive_infiltration().loc["s"]
    for key, value in params.items():
        assert result[key] == pytest.approx(value * 5 / 6)
    assert lc.derive_infiltration("dominant").loc["s", next(iter(params))] == next(
        iter(params.values())
    )
    assert (
        lc.derive_infiltration("custom", lambda parts: {"model": model, **params}).loc[
            "s", "model"
        ]
        == model
    )


def test_infiltration_mismatch_and_application():
    lc = sample(True)
    lc.add_class(
        "soil",
        impervious=0,
        n_perv=0.2,
        dstore_perv=5,
        infiltration={
            "model": "GREEN_AMPT",
            "suction_head": 4,
            "hydraulic_conductivity": 0.2,
            "initial_moisture_deficit": 0.3,
        },
    )
    lc.assign("CA-1", {"soil": 1}, overwrite=True)
    lc.apply_hydrology(infiltration=True)
    assert (
        lc.model.get.infiltration_green_ampt.hydraulic_conductivity(ids="CA-1") == 0.2
    )
    lc.model.options["INFILTRATION"] = "HORTON"
    with pytest.raises(ValidationError, match="differs"):
        lc.derive_infiltration()


def test_si_area_and_native_default_creation(tmp_path):
    from swmmx.api import SWMMModel
    from swmmx.inp import InpDocument

    m = SWMMModel(
        InpDocument.from_text(
            "[OPTIONS]\nFLOW_UNITS CMS\nINFILTRATION GREEN_AMPT\n[SUBCATCHMENTS]\nS1 G O 2 0 10 1 0\n[SUBAREAS]\nS1 .01 .1 1 2 0 OUTLET\n"
        )
    )
    lc = landcover(m)
    lc.add_class("roof", impervious=1)
    lc.assign("S1", {"roof": 2}, units="ha")
    assert lc.coverage_area("S1", "roof") == 20000
    lc.apply_swmm_landuses()
    assert m.section("LANDUSES") == [["roof", "0", "0", "0"]]
    assert m.section("COVERAGES") == [["S1", "roof", "100.0"]]
    assert swmm(m.save(tmp_path / "si.inp")).section("COVERAGES") == m.section(
        "COVERAGES"
    )


def test_native_engine_accepts_applied_model(tmp_path):
    lc = sample(True)
    lc.apply_hydrology()
    lc.apply_swmm_landuses(overwrite=True)
    # Avoid the sample's optional runoff-interface output outside pytest's sandbox.
    lc.model._document.sections.pop("FILES", None)
    lc.model.save(tmp_path / "engine.inp")
    lc.model.run()
    assert lc.model.has_run
    lc.derive_hydrology()
    assert not lc.model.results_stale
    lc.convert("CA-1", "road", "green", fraction=0.01)
    assert not lc.model.results_stale
    lc.apply_hydrology()
    assert lc.model.results_stale


def test_noop_application_preserves_results():
    lc = sample(True)
    lc.apply_hydrology()
    lc.model._run_timestamps = [1]
    lc.apply_hydrology()
    assert lc.model.has_run and not lc.model.results_stale


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "{}",
        '{"landcover":{"version":99}}',
        '{"landcover":{"version":1,"classes":[],"coverage":[],"source":[]}}',
    ],
)
def test_bad_sidecar_schema(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValidationError):
        LandCover.load(path)


def test_sidecar_other_metadata_preserved(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"other_extension": {"x": 2}}))
    lc = sample()
    lc.save(path)
    assert json.loads(path.read_text())["other_extension"] == {"x": 2}
    assert LandCover.load(path).coverage("S1") == lc.coverage("S1")


def test_infiltration_inconsistent_sources():
    lc = landcover()
    lc.add_class(
        "a",
        impervious=0,
        infiltration={
            "model": "GREEN_AMPT",
            "suction_head": 1,
            "hydraulic_conductivity": 1,
            "initial_moisture_deficit": 0.2,
        },
    )
    lc.add_class(
        "b",
        impervious=0,
        infiltration={
            "model": "CURVE_NUMBER",
            "curve_number": 80,
            "conductivity": 0,
            "dry_time": 2,
        },
    )
    lc.assign("S", {"a": 0.5, "b": 0.5})
    with pytest.raises(ValidationError, match="incompatible"):
        lc.derive_infiltration()
    result = lc.derive_infiltration(
        "custom",
        lambda parts: {
            "model": "GREEN_AMPT",
            "suction_head": 2,
            "hydraulic_conductivity": 1,
            "initial_moisture_deficit": 0.2,
        },
    )
    assert result.loc["S", "suction_head"] == 2


def test_attached_wrong_area_and_summary():
    lc = sample(True)
    with pytest.raises(ValidationError):
        lc.assign("CA-7", {"roof": 1}, area_m2=1)
    report = lc.summary()
    assert report["mean_percent_impervious"] == pytest.approx(66)
    assert len(report["validation"]) == 3  # unassigned model catchments
