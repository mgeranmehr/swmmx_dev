"""GIS export frontend using optional GeoPandas/Shapely dependencies."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING
import importlib.util
import json
import warnings
import zipfile

from ..errors import ExportError, ExportGeometryError, FormatError, OptionalDependencyError
from .utils import (
    _collect_export_tables,
    _default_model_stem,
    _get_default_export_path,
    _sanitize_filename,
)

if TYPE_CHECKING:
    from ..api import SWMMModel


SPATIAL_ELEMENTS = {
    "nodes",
    "junctions",
    "outfalls",
    "dividers",
    "storage_units",
    "links",
    "conduits",
    "pumps",
    "orifices",
    "weirs",
    "outlets",
    "subcatchments",
    "rain_gages",
}


def _require_gis_dependencies():
    """Import optional GIS dependencies or raise the documented helper error."""

    if importlib.util.find_spec("geopandas") is None or importlib.util.find_spec("shapely") is None:
        raise OptionalDependencyError(
            "GIS export requires geopandas and shapely. Install with: pip install geopandas shapely"
        )
    try:
        import geopandas as gpd
        from shapely.geometry import LineString, Point, Polygon
    except ImportError as exc:
        raise OptionalDependencyError(
            "GIS export requires geopandas and shapely. Install with: pip install geopandas shapely"
        ) from exc

    return gpd, Point, LineString, Polygon


def _xy_map(model: "SWMMModel", section: str) -> dict[str, tuple[float, float]]:
    """Return ID-indexed XY points from one SWMM coordinate section."""

    points: dict[str, tuple[float, float]] = {}
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            points[row[0]] = (float(row[1]), float(row[2]))
        except ValueError:
            continue
    return points


def _grouped_xy_map(model: "SWMMModel", section: str) -> dict[str, list[tuple[float, float]]]:
    """Return grouped ordered XY points from polygons or vertices."""

    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in model._document.rows(section):
        if len(row) < 3:
            continue
        try:
            grouped[row[0]].append((float(row[1]), float(row[2])))
        except ValueError:
            continue
    return dict(grouped)


def _warn_or_raise_missing_geometry(element: str, missing_count: int, strict_geometry: bool) -> None:
    """Handle geometry gaps according to the caller's strictness policy."""

    if missing_count <= 0:
        return
    if element in {"nodes", "junctions", "outfalls", "dividers", "storage_units"}:
        noun = "node coordinates"
    elif element == "rain_gages":
        noun = "rain gage coordinates"
    else:
        noun = f"{element.rstrip('s')} geometries"
    message = f"Cannot export {element} to GIS because {missing_count} {noun} are missing."
    if strict_geometry:
        raise ExportGeometryError(message)
    warnings.warn(f"{message} Skipping those features.", stacklevel=3)


def _shorten_shapefile_fields(frame):
    """Return a copy with unique <=10-character shapefile field names and mapping."""

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for column in frame.columns:
        if column == "geometry":
            mapping[column] = column
            continue
        base = "".join(character for character in column if character.isalnum() or character == "_")[:10] or "field"
        candidate = base
        suffix = 1
        while candidate.lower() in used:
            suffix_text = str(suffix)
            candidate = f"{base[:10 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        used.add(candidate.lower())
        mapping[column] = candidate
    return frame.rename(columns=mapping), mapping


def _link_endpoint_rows(model: "SWMMModel") -> dict[str, tuple[str, str]]:
    """Return link endpoint IDs for ordinary routed link sections."""

    endpoints: dict[str, tuple[str, str]] = {}
    for section in ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"):
        for row in model._document.rows(section):
            if len(row) >= 3:
                endpoints[row[0]] = (row[1], row[2])
    return endpoints


def _geometry_frame(model: "SWMMModel", element: str, frame, *, strict_geometry: bool, subcatchment_geometry: str):
    """Attach GIS geometry for one supported spatial export table."""

    gpd, Point, LineString, Polygon = _require_gis_dependencies()
    node_points = _xy_map(model, "COORDINATES")
    rain_points = _xy_map(model, "SYMBOLS")
    vertices = _grouped_xy_map(model, "VERTICES")
    polygons = _grouped_xy_map(model, "POLYGONS")
    endpoints = _link_endpoint_rows(model)

    if element in {"nodes", "junctions", "outfalls", "dividers", "storage_units"}:
        geometries = []
        missing = 0
        for object_id in frame.get("id", []):
            point = node_points.get(str(object_id))
            if point is None:
                missing += 1
                geometries.append(None)
            else:
                geometries.append(Point(point))
        _warn_or_raise_missing_geometry(element, missing, strict_geometry)
        result = frame.copy()
        result["geometry"] = geometries
        return {"main": gpd.GeoDataFrame(result.loc[result["geometry"].notna()].copy(), geometry="geometry")}

    if element in {"links", "conduits", "pumps", "orifices", "weirs", "outlets"}:
        geometries = []
        missing = 0
        for object_id in frame.get("id", []):
            endpoint_pair = endpoints.get(str(object_id))
            if endpoint_pair is None or endpoint_pair[0] not in node_points or endpoint_pair[1] not in node_points:
                missing += 1
                geometries.append(None)
                continue
            coordinates = [node_points[endpoint_pair[0]], *vertices.get(str(object_id), []), node_points[endpoint_pair[1]]]
            geometries.append(LineString(coordinates))
        _warn_or_raise_missing_geometry(element, missing, strict_geometry)
        result = frame.copy()
        result["geometry"] = geometries
        return {"main": gpd.GeoDataFrame(result.loc[result["geometry"].notna()].copy(), geometry="geometry")}

    if element == "rain_gages":
        geometries = []
        missing = 0
        for object_id in frame.get("id", []):
            point = rain_points.get(str(object_id))
            if point is None:
                missing += 1
                geometries.append(None)
            else:
                geometries.append(Point(point))
        _warn_or_raise_missing_geometry(element, missing, strict_geometry)
        result = frame.copy()
        result["geometry"] = geometries
        return {"main": gpd.GeoDataFrame(result.loc[result["geometry"].notna()].copy(), geometry="geometry")}

    if element == "subcatchments":
        outputs = {}
        if subcatchment_geometry in {"polygon", "both"}:
            polygon_geometries = []
            missing = 0
            for object_id in frame.get("id", []):
                points = polygons.get(str(object_id))
                if points is None or len(points) < 3:
                    missing += 1
                    polygon_geometries.append(None)
                else:
                    polygon_geometries.append(Polygon(points))
            _warn_or_raise_missing_geometry(element, missing, strict_geometry)
            result = frame.copy()
            result["geometry"] = polygon_geometries
            outputs["main"] = gpd.GeoDataFrame(result.loc[result["geometry"].notna()].copy(), geometry="geometry")
        if subcatchment_geometry in {"centroid", "both"}:
            centroid_geometries = []
            missing = 0
            for object_id in frame.get("id", []):
                points = polygons.get(str(object_id))
                if points is None or len(points) < 3:
                    missing += 1
                    centroid_geometries.append(None)
                else:
                    centroid_geometries.append(Polygon(points).centroid)
            _warn_or_raise_missing_geometry("subcatchment centroids", missing, strict_geometry)
            result = frame.copy()
            result["geometry"] = centroid_geometries
            outputs["centroids"] = gpd.GeoDataFrame(result.loc[result["geometry"].notna()].copy(), geometry="geometry")
        return outputs

    return {}


def _remove_shapefile_family(path: Path) -> None:
    """Delete ordinary shapefile sidecars before an intentional overwrite."""

    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix"):
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()


def _shapefile_base_name(model: "SWMMModel", file_name: str | None) -> str:
    """Return the prefix used for separate shapefile layer files."""

    if file_name is None:
        return _sanitize_filename(_default_model_stem(model))
    candidate = Path(file_name)
    return _sanitize_filename(candidate.stem if candidate.suffix else candidate.name)


def export_gis(
    model: "SWMMModel",
    *,
    path=None,
    file_name: str | None = None,
    elements="all",
    time_step=-1,
    include_results: bool = True,
    include_parameters: bool = True,
    include_derived: bool = True,
    strict_results: bool = False,
    crs=None,
    driver: str = "ESRI Shapefile",
    overwrite: bool = False,
    zip_output: bool = False,
    subcatchment_geometry: str = "polygon",
    strict_geometry: bool = False,
    non_spatial: bool = False,
) -> dict[str, Path]:
    """Export selected spatial SWMM layers to shapefiles or one GeoPackage."""

    gpd, _Point, _LineString, _Polygon = _require_gis_dependencies()
    if driver not in {"ESRI Shapefile", "GPKG"}:
        raise FormatError("GIS driver must be 'ESRI Shapefile' or 'GPKG'.")
    if subcatchment_geometry not in {"polygon", "centroid", "both"}:
        raise ExportError("subcatchment_geometry must be 'polygon', 'centroid', or 'both'.")
    tables = _collect_export_tables(
        model,
        elements,
        include_parameters=include_parameters,
        include_results=include_results,
        include_derived=include_derived,
        time_step=time_step,
        strict_results=strict_results,
    )
    selected_tables = OrderedDict(
        (element, frame)
        for element, frame in tables.items()
        if element in SPATIAL_ELEMENTS or non_spatial
    )
    if driver == "GPKG":
        if path is not None and Path(path).suffix.lower() == ".gpkg":
            target = Path(path).expanduser().resolve()
        else:
            target_dir = _get_default_export_path(model, path)
            gpkg_name = file_name or f"{_sanitize_filename(_default_model_stem(model))}.gpkg"
            if not gpkg_name.lower().endswith(".gpkg"):
                gpkg_name = f"{gpkg_name}.gpkg"
            target = target_dir / gpkg_name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"Could not create GIS export directory '{target.parent}': {exc}") from exc
        if target.exists():
            if not overwrite:
                raise ExportError(f"GIS export target already exists: '{target}'. Use overwrite=True to replace it.")
            target.unlink()
        outputs: dict[str, Path] = {}
        for element, frame in selected_tables.items():
            for suffix, geo_frame in _geometry_frame(
                model,
                element,
                frame,
                strict_geometry=strict_geometry,
                subcatchment_geometry=subcatchment_geometry,
            ).items():
                if geo_frame.empty:
                    continue
                geo_frame = geo_frame.set_crs(crs, allow_override=True) if crs is not None else geo_frame
                layer_name = element if suffix == "main" else f"{element}_{suffix}"
                geo_frame.to_file(target, layer=layer_name, driver="GPKG")
                outputs[layer_name] = target
        if zip_output and target.exists():
            zip_path = target.with_suffix(".zip")
            if zip_path.exists() and not overwrite:
                raise ExportError(f"GIS zip target already exists: '{zip_path}'. Use overwrite=True to replace it.")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(target, arcname=target.name)
            outputs["zip"] = zip_path
        return outputs

    target_dir = _get_default_export_path(model, path)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Could not create GIS export directory '{target_dir}': {exc}") from exc
    prefix = _shapefile_base_name(model, file_name)
    outputs: dict[str, Path] = {}
    field_mappings: dict[str, dict[str, str]] = {}
    for element, frame in selected_tables.items():
        for suffix, geo_frame in _geometry_frame(
            model,
            element,
            frame,
            strict_geometry=strict_geometry,
            subcatchment_geometry=subcatchment_geometry,
        ).items():
            if geo_frame.empty:
                continue
            layer_name = element if suffix == "main" else f"{element}_{suffix}"
            target = target_dir / f"{prefix}_{layer_name}.shp"
            if target.exists() and not overwrite:
                raise ExportError(f"GIS export target already exists: '{target}'. Use overwrite=True to replace it.")
            if overwrite:
                _remove_shapefile_family(target)
            geo_frame = geo_frame.set_crs(crs, allow_override=True) if crs is not None else geo_frame
            shortened, mapping = _shorten_shapefile_fields(geo_frame)
            shortened.to_file(target, driver="ESRI Shapefile")
            outputs[layer_name] = target
            field_mappings[layer_name] = mapping
    if field_mappings:
        mapping_path = target_dir / f"{prefix}_shapefile_fields.json"
        if not mapping_path.exists() or overwrite:
            mapping_path.write_text(json.dumps(field_mappings, indent=2), encoding="utf-8")
    if zip_output and outputs:
        zip_path = target_dir / f"{prefix}_gis.zip"
        if zip_path.exists() and not overwrite:
            raise ExportError(f"GIS zip target already exists: '{zip_path}'. Use overwrite=True to replace it.")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for shapefile in outputs.values():
                for sidecar in shapefile.parent.glob(f"{shapefile.stem}.*"):
                    archive.write(sidecar, arcname=sidecar.name)
        outputs["zip"] = zip_path
    return outputs
