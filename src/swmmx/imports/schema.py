"""Import endpoint schemas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportSchema:
    """One importable public endpoint."""

    category: str
    element_type: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    id_scope: str | None = None
    add_category: str | None = None
    add_element_type: str | None = None
    implemented: bool = True
    group_types: tuple[str, ...] = ()
    type_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def public_path(self) -> str:
        """Return ``category.element_type``."""

        return f"{self.category}.{self.element_type}"

    @property
    def fields(self) -> tuple[str, ...]:
        """Return all fields eligible for matching."""

        return tuple(dict.fromkeys([*self.required_fields, *self.optional_fields]))

    @property
    def effective_add_category(self) -> str:
        """Return the add namespace category used for implemented endpoints."""

        return self.add_category or self.category

    @property
    def effective_add_element_type(self) -> str:
        """Return the add namespace element name used for implemented endpoints."""

        return self.add_element_type or self.element_type


NODE_TYPE_ALIASES = {
    "junction": "junction",
    "junc": "junction",
    "node": "junction",
    "outfall": "outfall",
    "out": "outfall",
    "flow_divider": "flow_divider",
    "divider": "flow_divider",
    "div": "flow_divider",
    "storage": "storage_unit",
    "storage_unit": "storage_unit",
}

LINK_TYPE_ALIASES = {
    "conduit": "conduit",
    "pipe": "conduit",
    "pump": "pump",
    "orifice": "orifice",
    "weir": "weir",
    "outlet": "outlet",
}


JUNCTION_FIELDS = (
    "invert_elevation",
    "max_depth",
    "initial_depth",
    "surcharge_depth",
    "ponded_area",
    "tag",
)

OUTFALL_FIELDS = (
    "invert_elevation",
    "type",
    "stage_data",
    "fixed_stage",
    "tidal_curve",
    "time_series",
    "tide_gate",
    "route_to",
    "tag",
)

FLOW_DIVIDER_FIELDS = (
    "invert_elevation",
    "max_depth",
    "initial_depth",
    "surcharge_depth",
    "ponded_area",
    "type",
    "diverted_link",
    "cutoff_flow",
    "diversion_curve",
    "weir_height",
    "weir_coefficient",
    "tag",
)

STORAGE_FIELDS = (
    "invert_elevation",
    "max_depth",
    "initial_depth",
    "storage_curve_type",
    "storage_curve",
    "area",
    "area_coefficient",
    "area_exponent",
    "area_constant",
    "evaporation_factor",
    "seepage_loss",
    "tag",
)

CONDUIT_FIELDS = (
    "length",
    "roughness",
    "shape",
    "geometry",
    "diameter",
    "geometry_1",
    "geometry_2",
    "geometry_3",
    "geometry_4",
    "inlet_offset",
    "outlet_offset",
    "initial_flow",
    "maximum_flow",
    "barrels",
    "culvert_code",
    "entry_loss",
    "exit_loss",
    "average_loss",
    "flap_gate",
    "seepage_rate",
    "vertices",
    "tag",
)


SCHEMAS: dict[tuple[str, str], ImportSchema] = {}


def _register(schema: ImportSchema) -> ImportSchema:
    SCHEMAS[(schema.category, schema.element_type)] = schema
    return schema


_register(ImportSchema("node", "junction", ("id", "x", "y"), JUNCTION_FIELDS, id_scope="node"))
_register(ImportSchema("node", "outfall", ("id", "x", "y"), OUTFALL_FIELDS, id_scope="node"))
_register(ImportSchema("node", "flow_divider", ("id", "x", "y"), FLOW_DIVIDER_FIELDS, id_scope="node", add_element_type="divider"))
_register(ImportSchema("node", "storage_unit", ("id", "x", "y"), STORAGE_FIELDS, id_scope="node"))
_register(
    ImportSchema(
        "node",
        "__group__",
        ("id", "x", "y"),
        ("type", *JUNCTION_FIELDS, *OUTFALL_FIELDS, *FLOW_DIVIDER_FIELDS, *STORAGE_FIELDS),
        id_scope="node",
        group_types=("junction", "outfall", "flow_divider", "storage_unit"),
        type_aliases=NODE_TYPE_ALIASES,
    )
)

_register(ImportSchema("link", "conduit", ("id", "from_node", "to_node"), CONDUIT_FIELDS, id_scope="link"))
_register(ImportSchema("link", "pump", ("id", "from_node", "to_node", "curve"), ("initial_status", "startup_depth", "shutoff_depth", "vertices", "tag"), id_scope="link"))
_register(ImportSchema("link", "orifice", ("id", "from_node", "to_node", "type", "shape", "height", "discharge_coefficient"), ("width", "offset", "flap_gate", "open_close_time", "vertices", "tag"), id_scope="link"))
_register(ImportSchema("link", "weir", ("id", "from_node", "to_node", "type", "crest_height", "discharge_coefficient"), ("length", "side_slope", "flap_gate", "end_contractions", "end_coefficient", "surcharge", "road_width", "road_surface", "vertices", "tag"), id_scope="link"))
_register(ImportSchema("link", "outlet", ("id", "from_node", "to_node", "rating_type"), ("curve", "coefficient", "exponent", "offset", "flap_gate", "vertices", "tag"), id_scope="link"))
_register(
    ImportSchema(
        "link",
        "__group__",
        ("id", "from_node", "to_node"),
        ("type", *CONDUIT_FIELDS, "curve", "initial_status", "startup_depth", "shutoff_depth", "height", "width", "offset", "discharge_coefficient", "crest_height", "coefficient", "exponent", "rating_type"),
        id_scope="link",
        group_types=("conduit", "pump", "orifice", "weir", "outlet"),
        type_aliases=LINK_TYPE_ALIASES,
    )
)

_register(ImportSchema("hydrology", "rain_gage", ("id",), ("x", "y", "format", "interval", "snow_catch_factor", "source_type", "source_data", "time_series", "filename", "station", "units", "tag"), id_scope="rain_gage"))
_register(ImportSchema("hydrology", "subcatchment", ("id", "rain_gage", "outlet", "x", "y"), ("area", "width", "slope", "impervious_percent", "curb_length", "snow_pack", "tag", "polygon", "n_impervious", "n_pervious", "depression_storage_impervious", "depression_storage_pervious", "zero_depression_storage_impervious_percent", "subarea_routing", "percent_routed"), id_scope="subcatchment"))

_register(ImportSchema("time", "time_series", ("id",), ("datetime", "date", "time", "value", "filename", "description"), id_scope="time_series"))
_register(ImportSchema("time", "time_pattern", ("id", "type", "multipliers"), (), id_scope="time_pattern"))
_register(ImportSchema("curve", "curve", ("id", "x", "y"), ("type",), id_scope="curve", add_category="curve", add_element_type="generic"))

_register(ImportSchema("coordinate", "node_coordinates", ("id", "x", "y"), (), id_scope="node"))
_register(ImportSchema("coordinate", "link_vertices", ("id", "x", "y"), (), id_scope="link"))
_register(ImportSchema("coordinate", "polygons", ("id", "x", "y"), (), id_scope="subcatchment"))
_register(ImportSchema("coordinate", "labels", ("text", "x", "y"), ("anchor_node", "font", "size"), id_scope=None))


def schema_for(category: str, element_type: str) -> ImportSchema:
    """Return one schema."""

    return SCHEMAS[(category, element_type)]


def categories() -> list[str]:
    """Return public import categories."""

    return sorted({category for category, _element_type in SCHEMAS})


def element_types_for(category: str) -> list[str]:
    """Return public element types for one category."""

    return sorted(element_type for schema_category, element_type in SCHEMAS if schema_category == category and element_type != "__group__")
