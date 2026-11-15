"""Deterministic projected, geographic and invalid polygon fixtures."""

import pandas as pd
import pytest

from swmmx import DuplicateIDError, ValidationError, landcover

gpd = pytest.importorskip("geopandas")
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union


def fixture():
    lc = landcover()
    lc.add_class("roof", impervious=1, n_imp=0.012, dstore_imp=1)
    lc.add_class("green", impervious=0, n_perv=0.2, dstore_perv=5)
    subs = gpd.GeoDataFrame(
        {"subcatchment": ["S1", "S2"]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs=32639,
    )
    cover = gpd.GeoDataFrame(
        {"class": ["roof", "green"]},
        geometry=[box(0, 0, 5, 10), box(5, 0, 20, 10)],
        crs=32639,
    )
    return lc, subs, cover


def test_cross_boundary_outputs_and_file(tmp_path):
    lc, subs, cover = fixture()
    path = tmp_path / "cover.gpkg"
    cover.to_file(path, layer="cover")
    lc.from_gis(path, layer="cover").overlay(subcatchments=subs)
    assert lc.coverage_fraction("S1", "roof") == 0.5
    assert lc.coverage_fraction("S2", "green") == 1
    assert lc.coverage_area("S1", "roof") == 50
    assert lc.intersections_geodataframe().area_m2.sum() == 200
    assert list(lc.to_geodataframe().subcatchment) == ["S1", "S2"]
    assert (lc.coverage_table().sum(axis=1) == 1).all()
    assert lc.source["source_layer"] == "cover"
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lc.plot()
    lc.plot(class_name="roof")
    lc.plot(kind="imperviousness")
    plt.close("all")
    lc.convert("S1", "roof", "green", fraction=0.1)
    with pytest.raises(ValidationError, match="No current"):
        lc.intersections_geodataframe()


def test_multipolygon_repeated_outside_and_sliver():
    lc, subs, _ = fixture()
    cover = gpd.GeoDataFrame(
        {"class": ["roof", "roof", "green", "green"]},
        geometry=[
            MultiPolygon([box(0, 0, 5, 5), box(10, 0, 15, 5)]),
            box(30, 0, 40, 10),
            unary_union(
                [
                    box(0, 5, 10, 10),
                    box(5, 0, 10, 5),
                    box(10, 5, 20, 10),
                    box(15, 0, 20, 5),
                ]
            ),
            box(50, 0, 50.000001, 1),
        ],
        crs=32639,
    )
    lc.overlay(cover, subs)
    assert lc.coverage_fraction("S1", "roof") == 0.25
    assert lc.coverage_fraction("S2", "roof") == 0.25


@pytest.mark.parametrize(
    "problem",
    [
        "overlap",
        "gap",
        "invalid",
        "empty",
        "missing",
        "duplicate_index",
        "duplicate_sub",
        "unknown",
        "zero",
        "crs_missing",
    ],
)
def test_rejects_bad_geometry(problem):
    lc, subs, cover = fixture()
    if problem == "overlap":
        cover.loc[1, "geometry"] = box(4, 0, 20, 10)
    elif problem == "gap":
        cover.loc[1, "geometry"] = box(6, 0, 20, 10)
    elif problem == "invalid":
        cover.loc[0, "geometry"] = Polygon([(0, 0), (5, 10), (5, 0), (0, 10), (0, 0)])
    elif problem == "empty":
        cover.loc[0, "geometry"] = Polygon()
    elif problem == "missing":
        cover.loc[0, "geometry"] = None
    elif problem == "duplicate_index":
        cover.index = [0, 0]
    elif problem == "duplicate_sub":
        subs["subcatchment"] = ["S1", "S1"]
    elif problem == "unknown":
        cover.loc[0, "class"] = "bad"
    elif problem == "zero":
        cover.loc[0, "geometry"] = Polygon([(0, 0), (0, 1), (0, 2), (0, 0)])
    elif problem == "crs_missing":
        cover = cover.set_crs(None, allow_override=True)
    with pytest.raises(ValidationError):
        lc.overlay(cover, subs)
    assert lc.coverage_table().empty


def test_crs():
    lc, subs, cover = fixture()
    with pytest.raises(ValidationError, match="Mismatched"):
        lc.overlay(cover.to_crs(4326), subs)
    with pytest.raises(ValidationError, match="projected"):
        lc.overlay(cover.to_crs(4326), subs.to_crs(4326))
    lc.overlay(cover.to_crs(4326), subs.to_crs(4326), area_crs=32639)
    assert lc.coverage_area("S1", "roof") == pytest.approx(50, abs=1e-6)


def test_feet_crs():
    lc, subs, cover = fixture()
    subs = subs.set_crs(2263, allow_override=True)
    cover = cover.set_crs(2263, allow_override=True)
    lc.overlay(cover, subs)
    assert lc.coverage_area("S1", "roof") == pytest.approx(50 * (1200 / 3937) ** 2)


def test_moderate_overlay():
    lc = landcover()
    lc.add_class("a", impervious=1)
    cells = [box(x, y, x + 1, y + 1) for x in range(20) for y in range(20)]
    cover = gpd.GeoDataFrame({"class": ["a"] * 400}, geometry=cells, crs=32639)
    subs = gpd.GeoDataFrame(
        {"subcatchment": ["S"]}, geometry=[box(0, 0, 20, 20)], crs=32639
    )
    lc.overlay(cover, subs)
    assert len(lc.intersections_geodataframe()) == 400
    assert lc.coverage_fraction("S", "a") == pytest.approx(1)


def test_model_geometry_stale_and_duplicate_overlay():
    from pathlib import Path

    from swmmx import swmm

    m = swmm(Path(__file__).resolve().parents[1] / "examples/example.inp")
    lc = landcover(m)
    lc.add_class("a", impervious=1)
    ids = m._document.section_ids("SUBCATCHMENTS")
    for i, sid in enumerate(ids):
        m.set.subcatchment.polygon(
            [(i * 10, 0), (i * 10 + 10, 0), (i * 10 + 10, 10), (i * 10, 10)], ids=sid
        )
    cover = gpd.GeoDataFrame({"class": ["a"]}, geometry=[box(0, 0, 40, 10)], crs=32639)
    lc.from_geodataframe(cover)
    with pytest.raises(ValidationError, match="model_crs"):
        lc.overlay()
    lc.overlay(model_crs=32639)
    assert lc.coverage_fraction(ids[0], "a") == 1
    with pytest.raises(DuplicateIDError):
        lc.overlay(model_crs=32639)
    m.set.subcatchment.polygon([(0, 0), (9, 0), (9, 10), (0, 10)], ids=ids[0])
    with pytest.raises(ValidationError, match="polygons changed"):
        lc.intersections_geodataframe()


def test_overlay_failure_is_atomic_and_rename():
    lc, subs, cover = fixture()
    lc.overlay(cover, subs)
    before = lc.coverage_table()
    cover.loc[1, "geometry"] = box(6, 0, 20, 10)
    with pytest.raises(ValidationError):
        lc.overlay(cover, subs, overwrite=True)
    pd.testing.assert_frame_equal(lc.coverage_table(), before)
    lc.rename_class("roof", "building")
    assert "building" in set(lc.intersections_geodataframe().landcover)
    assert lc.to_geodataframe().building_fraction.iloc[0] == 0.5
