"""Conservative indexed polygon overlay using existing optional GIS dependencies."""

from __future__ import annotations

from ..errors import ValidationError
from ..export.gis import _grouped_xy_map, _require_gis_dependencies
from .classes import number


def valid_frame(frame, field):
    gpd, *_ = _require_gis_dependencies()
    if not isinstance(frame, gpd.GeoDataFrame) or field not in frame or len(frame) == 0:
        raise ValidationError(f"Expected nonempty GeoDataFrame with {field}")
    if frame.crs is None:
        raise ValidationError("GIS data requires an explicit CRS")
    if not frame.index.is_unique:
        raise ValidationError("Duplicate GIS index IDs; provide unique IDs")
    if (
        frame[field].isna().any()
        or not frame[field].map(lambda x: isinstance(x, str) and bool(x.strip())).all()
    ):
        raise ValidationError(f"{field} must contain nonempty string IDs")
    if (
        frame.geometry.isna().any()
        or frame.geometry.is_empty.any()
        or not frame.geometry.is_valid.all()
    ):
        raise ValidationError(
            "Invalid, missing or empty geometry; repair it explicitly before import"
        )
    if not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValidationError("Only Polygon and MultiPolygon geometries are supported")
    return (
        frame[[field, frame.geometry.name]].rename_geometry("geometry")
        if frame.geometry.name != "geometry"
        else frame[[field, "geometry"]].copy()
    )


def import_frame(manager, frame, field):
    frame = valid_frame(frame, field).rename(columns={field: "landcover"})
    for name in frame.landcover.unique():
        manager.get_class(name)
    manager._landcover_gdf = frame
    manager._intersections = None
    manager.source = {"class_field": field, "original_crs": str(frame.crs)}
    return manager


def no_overlaps(frame, label, cancelled=None):
    # Spatial index avoids a quadratic all-pairs cross product.
    left, right = frame.sindex.query(frame.geometry, predicate="intersects")
    for i, j in zip(left, right):
        if cancelled is not None and cancelled():
            from .contracts import LandCoverCancelled

            raise LandCoverCancelled("GIS operation cancelled; metadata unchanged")
        if (
            i < j
            and frame.geometry.iloc[i].intersection(frame.geometry.iloc[j]).area > 0
        ):
            raise ValidationError(f"Overlapping {label} polygons at rows {i}, {j}")


def signature(manager):
    return (
        tuple(tuple(r) for r in manager.model.section("POLYGONS"))
        if manager.model is not None
        else None
    )


def check_intersections(manager):
    if manager._intersections is None:
        raise ValidationError(
            "No current intersections; run overlay() after importing or changing coverage"
        )
    if manager._geometry_signature != signature(manager):
        raise ValidationError("Model polygons changed; run overlay again")
    for sid in manager._coverage:
        manager._area(sid)


def overlay(
    manager,
    source,
    subs,
    area_crs,
    model_crs,
    class_field,
    sub_field,
    overlap,
    overwrite,
    progress=None,
    cancelled=None,
):
    from .contracts import LandCoverCancelled

    def checkpoint(stage, completed, total=5):
        if cancelled is not None and cancelled():
            raise LandCoverCancelled("GIS operation cancelled; metadata unchanged")
        if progress is not None:
            progress({"stage": stage, "completed": completed, "total": total})
        if cancelled is not None and cancelled():
            raise LandCoverCancelled("GIS operation cancelled; metadata unchanged")

    checkpoint("validate_inputs", 0)
    gpd, _, _, Polygon = _require_gis_dependencies()
    if overlap != "error":
        raise ValidationError('Only overlap="error" is supported')
    if source is None:
        if manager._landcover_gdf is None:
            raise ValidationError("Import landcover polygons first")
        cover = manager._landcover_gdf.copy()
    else:
        cover = valid_frame(source, class_field).rename(
            columns={class_field: "landcover"}
        )
    for key in cover.landcover.unique():
        manager.get_class(key)
    if subs is None:
        if manager.model is None or model_crs is None:
            raise ValidationError(
                "Model polygon overlay requires attached model and explicit model_crs"
            )
        points = _grouped_xy_map(manager.model, "POLYGONS")
        ids = manager.model._document.section_ids("SUBCATCHMENTS")
        if any(len(points.get(s, [])) < 3 for s in ids):
            raise ValidationError("Missing subcatchment polygons")
        subs = gpd.GeoDataFrame(
            {"subcatchment": ids},
            geometry=[Polygon(points[s]) for s in ids],
            crs=model_crs,
        )
        sub_field = "subcatchment"
    subs = valid_frame(subs, sub_field).rename(columns={sub_field: "subcatchment"})
    if subs.subcatchment.duplicated().any():
        raise ValidationError(
            "Duplicate subcatchment GIS IDs; use MultiPolygon for multipart subcatchments"
        )
    if area_crs is None and cover.crs != subs.crs:
        raise ValidationError("Mismatched CRS; choose explicit area_crs to reproject")
    if area_crs is not None:
        cover, subs = cover.to_crs(area_crs), subs.to_crs(area_crs)
    if not subs.crs.is_projected:
        raise ValidationError("Area requires a projected CRS; provide area_crs")
    axes = subs.crs.axis_info
    if (
        len(axes) < 2
        or axes[0].unit_conversion_factor != axes[1].unit_conversion_factor
    ):
        raise ValidationError("Area CRS must have compatible horizontal linear axes")
    factor = (
        number(axes[0].unit_conversion_factor, "CRS unit conversion", positive=True)
        ** 2
    )
    if (subs.area <= 0).any() or (cover.area <= 0).any():
        raise ValidationError("Zero-area polygons are invalid")
    checkpoint("validate_overlap", 1)
    no_overlaps(cover.reset_index(drop=True), "landcover", cancelled)
    no_overlaps(subs.reset_index(drop=True), "subcatchment", cancelled)
    checkpoint("intersect", 2)
    intersections = gpd.overlay(
        subs, cover, how="intersection", keep_geom_type=True, make_valid=False
    )
    checkpoint("aggregate", 3)
    intersections["area_m2"] = intersections.area * factor
    intersections = intersections[intersections.area_m2 > 0].copy()
    polygon_areas = dict(zip(subs.subcatchment, subs.area * factor))
    intersections["fraction"] = intersections.area_m2 / intersections.subcatchment.map(
        polygon_areas
    )
    table = (
        intersections.groupby(["subcatchment", "landcover"], sort=False)
        .fraction.sum()
        .unstack(fill_value=0)
    )
    # Stage all assignments to avoid partial overlay on error.
    from .core import LandCover

    stage = LandCover()
    stage._editing = True
    stage._classes = manager._classes
    stage._class_ids = manager._class_ids
    stage.model = manager.model
    stage._coverage = manager._coverage.copy()
    for sid in subs.subcatchment:
        checkpoint("assign", 4)
        if sid not in table.index:
            raise ValidationError(f"{sid}: no landcover intersects subcatchment")
        stage.assign(
            sid,
            table.loc[sid].to_dict(),
            area_m2=None if manager.model is not None else polygon_areas[sid],
            overwrite=overwrite,
        )
    checkpoint("ready_to_commit", 5)
    manager._coverage = stage._coverage
    manager._landcover_gdf = cover
    manager._subcatchments_gdf = subs
    manager._intersections = intersections[
        ["subcatchment", "landcover", "area_m2", "fraction", "geometry"]
    ]
    manager._geometry_signature = signature(manager)
    manager.source.update(
        area_crs=str(subs.crs),
        polygon_area_m2=polygon_areas,
        area_basis="polygon fractions; attached model area for coverage and LID areas",
    )
    return manager.coverage_table()
