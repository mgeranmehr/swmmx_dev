"""GIS import backend with lazy optional dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import SwmmxImportDependencyError
from .importer import execute_import

if TYPE_CHECKING:
    from ..api import SWMMModel


def _optional_gis_dependencies():
    """Import geopandas/shapely lazily and raise a clear package error."""

    try:
        import geopandas as gpd  # type: ignore
        from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon  # type: ignore
    except Exception as exc:  # pragma: no cover - exact missing package varies by env
        raise SwmmxImportDependencyError(
            "GIS import requires geopandas and shapely. Install with:\n"
            "pip install geopandas shapely"
        ) from exc
    return gpd, Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon


def import_gis(
    model: "SWMMModel",
    *,
    category: str,
    element_type: str,
    file_path,
    field_map=None,
    layer=None,
    use_geometry: bool = True,
    geometry_field: str = "geometry",
    compute_length_from_geometry: bool = False,
    polygon_to_centroid: bool = True,
    crs_action: str = "warn",
    **options,
):
    """Read a GIS file and import features into a model."""

    gpd, Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon = _optional_gis_dependencies()
    path = Path(file_path)
    read_kwargs: dict[str, Any] = {}
    if layer is not None:
        read_kwargs["layer"] = layer
    gdf = gpd.read_file(path, **read_kwargs)
    frame = gdf.copy()
    issues = []
    if crs_action == "warn" and getattr(gdf, "crs", None) is not None:
        issues.append(("warning", f"Input CRS '{gdf.crs}' was read, but SWMM .inp files do not have a standard CRS field."))
    elif crs_action not in {"warn", "ignore", "store"}:
        raise ValueError("'crs_action' must be 'warn', 'ignore', or 'store'.")

    if use_geometry and geometry_field in frame:
        for column in ("_swmmx_geom_x", "_swmmx_geom_y", "_swmmx_geom_vertices", "_swmmx_geom_polygon", "_swmmx_geom_length"):
            if column not in frame:
                frame[column] = None
        for index, geometry in frame[geometry_field].items():
            if geometry is None or geometry.is_empty:
                continue
            geometry, warning = _simplify_geometry(geometry, MultiPoint, MultiLineString, MultiPolygon)
            if warning:
                issues.append(("warning", f"Row {index + 2}: {warning}"))
            if isinstance(geometry, Point):
                frame.at[index, "_swmmx_geom_x"] = geometry.x
                frame.at[index, "_swmmx_geom_y"] = geometry.y
            elif isinstance(geometry, LineString):
                coords = [(float(x), float(y)) for x, y, *_rest in geometry.coords]
                frame.at[index, "_swmmx_geom_vertices"] = coords
                if compute_length_from_geometry:
                    frame.at[index, "_swmmx_geom_length"] = float(geometry.length)
            elif isinstance(geometry, Polygon):
                exterior = [(float(x), float(y)) for x, y, *_rest in geometry.exterior.coords]
                frame.at[index, "_swmmx_geom_polygon"] = exterior
                if polygon_to_centroid:
                    centroid = geometry.centroid
                    frame.at[index, "_swmmx_geom_x"] = centroid.x
                    frame.at[index, "_swmmx_geom_y"] = centroid.y

    frame = frame.drop(columns=[geometry_field], errors="ignore")
    auto_map = dict(field_map or {})
    columns = set(frame.columns)
    if "_swmmx_geom_x" in columns and "x" not in auto_map:
        auto_map["x"] = "_swmmx_geom_x"
    if "_swmmx_geom_y" in columns and "y" not in auto_map:
        auto_map["y"] = "_swmmx_geom_y"
    if "_swmmx_geom_vertices" in columns and "vertices" not in auto_map:
        auto_map["vertices"] = "_swmmx_geom_vertices"
    if "_swmmx_geom_polygon" in columns and "polygon" not in auto_map:
        auto_map["polygon"] = "_swmmx_geom_polygon"
    if "_swmmx_geom_length" in columns and "length" not in auto_map:
        auto_map["length"] = "_swmmx_geom_length"

    result = execute_import(
        model,
        frame,
        source_path=path,
        source_type="gis",
        category=category,
        element_type=element_type,
        field_map=auto_map,
        **options,
    )
    for level, message in issues:
        result.add_issue(level, message, row_number=None, field="geometry" if "Row" in message else "crs")
    return result


def _simplify_geometry(geometry, MultiPoint, MultiLineString, MultiPolygon):
    """Return a simple geometry and an optional warning for multipart inputs."""

    if isinstance(geometry, MultiPoint):
        return list(geometry.geoms)[0], "MultiPoint geometry was simplified to its first point."
    if isinstance(geometry, MultiLineString):
        longest = max(geometry.geoms, key=lambda item: item.length)
        return longest, "MultiLineString geometry was simplified to its longest line."
    if isinstance(geometry, MultiPolygon):
        largest = max(geometry.geoms, key=lambda item: item.area)
        return largest, "MultiPolygon geometry was simplified to its largest polygon."
    return geometry, None
