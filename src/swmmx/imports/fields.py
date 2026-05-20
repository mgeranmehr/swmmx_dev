"""Column-name normalization and import field matching."""

from __future__ import annotations

import re
from collections import defaultdict

from ..errors import SwmmxImportAmbiguousFieldError, SwmmxImportMissingFieldError


def normalize_field_name(name: str) -> str:
    """Normalize a source or canonical field name for conservative matching."""

    text = str(name).strip().lower().replace("%", "percent")
    text = re.sub(r"[\s_\-.\[\]\(\)/\\]+", "", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def build_alias_catalog() -> dict[str, set[str]]:
    """Return canonical import fields and their accepted aliases."""

    aliases = {
        "id": [
            "id",
            "name",
            "label",
            "objectid",
            "object_id",
            "element_id",
            "asset_id",
            "node_id",
            "nodeid",
            "link_id",
            "linkid",
            "pipe_id",
            "pipeid",
            "conduit_id",
            "conduitid",
            "series_id",
            "seriesid",
            "curve_id",
            "curveid",
            "subcatchment_id",
            "subcatchmentid",
        ],
        "type": ["type", "kind", "object_type", "element_type", "curve_type"],
        "tag": ["tag", "group", "class"],
        "x": ["x", "xcoord", "x_coord", "x_coordinate", "xcoordinate", "coord_x", "coordx", "easting", "lon", "longitude"],
        "y": ["y", "ycoord", "y_coord", "y_coordinate", "ycoordinate", "coord_y", "coordy", "northing", "lat", "latitude"],
        "invert_elevation": ["invert", "invert_elev", "invert_elevation", "invert_level", "invertlevel", "elevation"],
        "max_depth": ["max_depth", "maxdepth", "depth", "full_depth"],
        "initial_depth": ["initial_depth", "init_depth", "initial"],
        "surcharge_depth": ["surcharge_depth", "sur_depth", "surcharge"],
        "ponded_area": ["ponded_area", "pondedarea"],
        "fixed_stage": ["fixed_stage", "fixedstage", "stage"],
        "stage_data": ["stage_data", "stagedata"],
        "tidal_curve": ["tidal_curve", "tidalcurve"],
        "time_series": ["time_series", "timeseries", "ts"],
        "tide_gate": ["tide_gate", "tidegate", "flap_gate", "flapgate"],
        "route_to": ["route_to", "routeto"],
        "from_node": ["from_node", "fromnode", "inlet_node", "upstream_node", "us_node", "upstream", "node1", "start_node"],
        "to_node": ["to_node", "tonode", "outlet_node", "downstream_node", "ds_node", "downstream", "node2", "end_node"],
        "length": ["length", "len", "pipe_length"],
        "roughness": ["roughness", "mannings_n", "manning_n", "manning", "n"],
        "inlet_offset": ["inlet_offset", "upstream_offset", "us_offset"],
        "outlet_offset": ["outlet_offset", "downstream_offset", "ds_offset"],
        "initial_flow": ["initial_flow", "init_flow"],
        "maximum_flow": ["maximum_flow", "max_flow"],
        "flap_gate": ["flap_gate", "flapgate", "tide_gate", "tidegate"],
        "shape": ["shape", "xsection_shape", "cross_section", "crosssection"],
        "diameter": ["diameter", "diam", "dia"],
        "geometry": ["geometry", "geom"],
        "geometry_1": ["geometry_1", "geom1", "height", "diameter", "diam", "dia"],
        "geometry_2": ["geometry_2", "geom2", "width"],
        "geometry_3": ["geometry_3", "geom3"],
        "geometry_4": ["geometry_4", "geom4"],
        "barrels": ["barrels", "barrel_count", "number_of_barrels"],
        "culvert_code": ["culvert_code", "culvert"],
        "entry_loss": ["entry_loss", "entrance_loss"],
        "exit_loss": ["exit_loss"],
        "average_loss": ["average_loss", "avg_loss"],
        "seepage_rate": ["seepage_rate", "seepage"],
        "rain_gage": ["rain_gage", "raingage", "rain_gauge", "gauge", "gage"],
        "outlet": ["outlet", "outlet_node", "downstream", "out_node"],
        "area": ["area", "catchment_area", "subcatchment_area"],
        "width": ["width"],
        "slope": ["slope", "percent_slope"],
        "impervious_percent": ["impervious_percent", "imperv_percent", "pct_imperv", "imperv", "percent_impervious", "percentimperv"],
        "curb_length": ["curb_length", "curb"],
        "snow_pack": ["snow_pack", "snowpack"],
        "n_impervious": ["n_impervious", "n_imperv"],
        "n_pervious": ["n_pervious", "n_perv"],
        "depression_storage_impervious": ["depression_storage_impervious", "dstore_imperv"],
        "depression_storage_pervious": ["depression_storage_pervious", "dstore_perv"],
        "zero_depression_storage_impervious_percent": ["zero_depression_storage_impervious_percent", "zero_imperv"],
        "subarea_routing": ["subarea_routing", "routing"],
        "percent_routed": ["percent_routed", "pct_routed"],
        "format": ["format", "rainfall_format"],
        "interval": ["interval", "timestep", "time_step"],
        "snow_catch_factor": ["snow_catch_factor", "snow_factor"],
        "source_type": ["source_type", "source"],
        "source_data": ["source_data", "sourcedata"],
        "filename": ["filename", "file", "path"],
        "station": ["station"],
        "units": ["units"],
        "curve": ["curve", "pump_curve"],
        "initial_status": ["initial_status", "status"],
        "startup_depth": ["startup_depth", "startup"],
        "shutoff_depth": ["shutoff_depth", "shutoff"],
        "offset": ["offset"],
        "discharge_coefficient": ["discharge_coefficient", "coeff", "coefficient"],
        "crest_height": ["crest_height", "crest"],
        "side_slope": ["side_slope"],
        "end_contractions": ["end_contractions"],
        "end_coefficient": ["end_coefficient"],
        "rating_type": ["rating_type"],
        "road_width": ["road_width"],
        "road_surface": ["road_surface"],
        "datetime": ["datetime", "date_time", "timestamp", "time"],
        "date": ["date"],
        "time": ["time"],
        "value": ["value", "val", "y"],
        "points": ["points"],
        "pollutant": ["pollutant", "pollutant_id"],
        "land_use": ["land_use", "landuse"],
        "concentration": ["concentration", "conc"],
        "decay_coefficient": ["decay_coefficient", "decay"],
        "cleaning_efficiency": ["cleaning_efficiency"],
        "bmp_efficiency": ["bmp_efficiency"],
        "polygon": ["polygon", "vertices", "points", "coordinates"],
        "vertices": ["vertices", "points", "coordinates"],
        "multipliers": ["multipliers", "multiplier", "values"],
        "storage_curve_type": ["storage_curve_type", "storage_type"],
        "storage_curve": ["storage_curve"],
        "area_coefficient": ["area_coefficient", "area_coeff"],
        "area_exponent": ["area_exponent"],
        "area_constant": ["area_constant"],
        "evaporation_factor": ["evaporation_factor", "evap_factor"],
        "seepage_loss": ["seepage_loss"],
    }
    return {field: {normalize_field_name(item) for item in [field, *values]} for field, values in aliases.items()}


ALIAS_CATALOG = build_alias_catalog()


def match_fields(
    columns,
    target_fields,
    *,
    field_map: dict[str, str] | None = None,
    required_fields=(),
):
    """Match source columns to canonical target fields."""

    columns = [str(column) for column in columns]
    target_fields = list(dict.fromkeys(target_fields))
    normalized_columns: dict[str, list[str]] = defaultdict(list)
    for column in columns:
        normalized_columns[normalize_field_name(column)].append(column)

    matches: dict[str, str] = {}
    explicit_sources = set()
    if field_map:
        for target, source in field_map.items():
            if target not in target_fields:
                continue
            if source not in columns:
                normalized_source = normalize_field_name(source)
                source_candidates = normalized_columns.get(normalized_source, [])
                if len(source_candidates) != 1:
                    raise SwmmxImportMissingFieldError(
                        f"field_map source column '{source}' for '{target}' was not found."
                    )
                source = source_candidates[0]
            matches[target] = str(source)
            explicit_sources.add(str(source))

    # Exact canonical field names have higher priority than aliases.  This is
    # especially important for files produced by ``m.export.csv()``, where an
    # input column such as ``max_depth`` can appear beside a result column such
    # as ``depth``.  The exact input field should win and the result column
    # should remain ignored instead of creating an ambiguity.
    matched_sources = set(explicit_sources)
    for target in target_fields:
        if target in matches:
            continue
        exact_columns = [
            column
            for column in columns
            if column not in matched_sources
            and normalize_field_name(column) == normalize_field_name(target)
        ]
        unique = list(dict.fromkeys(exact_columns))
        if len(unique) > 1:
            raise SwmmxImportAmbiguousFieldError(
                f"Multiple columns match import field '{target}': {unique}. Use field_map to resolve this."
            )
        if unique:
            matches[target] = unique[0]
            matched_sources.add(unique[0])

    reverse_aliases: dict[str, list[str]] = defaultdict(list)
    for target in target_fields:
        for alias in ALIAS_CATALOG.get(target, {normalize_field_name(target)}):
            reverse_aliases[alias].append(target)

    candidate_matches: dict[str, list[str]] = defaultdict(list)
    for column in columns:
        if column in matched_sources:
            continue
        normalized = normalize_field_name(column)
        possible_targets = reverse_aliases.get(normalized, [])
        possible_targets = [target for target in dict.fromkeys(possible_targets) if target not in matches]
        if len(possible_targets) == 1:
            candidate_matches[possible_targets[0]].append(column)

    for target, source_columns in candidate_matches.items():
        unique = list(dict.fromkeys(source_columns))
        if len(unique) > 1:
            raise SwmmxImportAmbiguousFieldError(
                f"Multiple columns match import field '{target}': {unique}. Use field_map to resolve this."
            )
        matches[target] = unique[0]
        matched_sources.add(unique[0])

    missing = [field for field in required_fields if field not in matches]
    if missing:
        raise SwmmxImportMissingFieldError(f"Missing required import field(s): {', '.join(missing)}.")

    ignored = [column for column in columns if column not in set(matches.values())]
    return matches, ignored
