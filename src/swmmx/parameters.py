"""Public parameter access for ``m.get`` and ``m.set``."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
import inspect
import keyword
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .errors import (
    DimensionMismatchError,
    FormatError,
    InvalidReferenceError,
    ModelNotRunError,
    NotImplementedYetError,
    ObjectNotFoundError,
    ReadOnlyParameterError,
    UnknownCategoryError,
    UnknownIDError,
    UnknownParameterError,
)

if TYPE_CHECKING:
    from .api import SWMMModel
    from .schema import SchemaRegistry


def api_name(raw_name: str) -> str:
    """Return a Python-attribute-safe spelling for one schema name."""

    # Most schema names are already valid identifiers.  The replacement keeps
    # the rare human-facing punctuation case, such as ``option_date&time``,
    # reachable through a stable dotted API name.
    safe = re.sub(r"\W+", "_", raw_name).strip("_")
    if not safe:
        safe = "parameter"
    if safe[0].isdigit() or keyword.iskeyword(safe):
        safe = f"_{safe}"
    return safe


def normalize_source(source: str) -> str:
    """Collapse raw schema source text into one access-rule category."""

    lowered = str(source).strip().lower()
    if lowered in {"user", "ref", "derived", "result"}:
        return lowered
    parts = {part.strip() for part in lowered.split("/") if part.strip()}
    if "user" in parts or "ref" in parts:
        # Hybrid editable rows such as ``ref/user`` or ``user/derived`` still
        # have a user-authored input component.  Treating them as writable lets
        # explicit setter calls reach the real implementation boundary rather
        # than being mislabeled as read-only.
        return "ref" if "ref" in parts else "user"
    return "mixed"


@dataclass(frozen=True)
class ParameterSpec:
    """One routable public parameter definition."""

    main_category: str
    sub_category: str
    source: str
    type: str
    size: str
    notes: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Return the unique registry lookup key."""

        return self.main_category, self.sub_category

    @property
    def path(self) -> str:
        """Return the user-facing dotted parameter path."""

        return f"{self.main_category}.{self.sub_category}"

    @property
    def source_kind(self) -> str:
        """Return the normalized source access category."""

        return normalize_source(self.source)

    @property
    def is_writable(self) -> bool:
        """Return whether the source rules permit ordinary user writes."""

        return self.source_kind in {"user", "ref"}

    @property
    def is_time_series(self) -> bool:
        """Return whether schema size declares a time-series shape."""

        return "time series" in self.size.lower()


@dataclass(frozen=True)
class FieldSpec:
    """Physical location of one input-file field."""

    section: str
    field_index: int
    id_index: int = 0
    reference_target: str | None = None
    key_indexes: tuple[int, ...] | None = None
    multirow: bool = False


OPTION_FIELDS = {
    "flow_units": "FLOW_UNITS",
    "infiltration_model": "INFILTRATION",
    "flow_routing": "FLOW_ROUTING",
    "link_offsets": "LINK_OFFSETS",
    "force_main_equation": "FORCE_MAIN_EQUATION",
    "allow_ponding": "ALLOW_PONDING",
    "minimum_slope": "MIN_SLOPE",
    "skip_steady_state": "SKIP_STEADY_STATE",
    "system_flow_tolerance": "SYS_FLOW_TOL",
    "lateral_flow_tolerance": "LAT_FLOW_TOL",
    "ignore_rainfall": "IGNORE_RAINFALL",
    "ignore_snowmelt": "IGNORE_SNOWMELT",
    "ignore_groundwater": "IGNORE_GROUNDWATER",
    "ignore_rdii": "IGNORE_RDII",
    "ignore_routing": "IGNORE_ROUTING",
    "ignore_quality": "IGNORE_QUALITY",
    "start_date": "START_DATE",
    "start_time": "START_TIME",
    "end_date": "END_DATE",
    "end_time": "END_TIME",
    "report_start_date": "REPORT_START_DATE",
    "report_start_time": "REPORT_START_TIME",
    "report_step": "REPORT_STEP",
    "wet_step": "WET_STEP",
    "dry_step": "DRY_STEP",
    "routing_step": "ROUTING_STEP",
    "rule_step": "RULE_STEP",
    "sweep_start": "SWEEP_START",
    "sweep_end": "SWEEP_END",
    "dry_days": "DRY_DAYS",
    "inertial_damping": "INERTIAL_DAMPING",
    "normal_flow_limited": "NORMAL_FLOW_LIMITED",
    "surcharge_method": "SURCHARGE_METHOD",
    "variable_step": "VARIABLE_STEP",
    "minimum_step": "MINIMUM_STEP",
    "lengthening_step": "LENGTHENING_STEP",
    "minimum_surface_area": "MIN_SURFAREA",
    "head_tolerance": "HEAD_TOLERANCE",
    "maximum_trials": "MAX_TRIALS",
    "threads": "THREADS",
}

INPUT_FIELDS = {
    ("rain_gage", "id"): FieldSpec("RAINGAGES", 0),
    ("rain_gage", "format"): FieldSpec("RAINGAGES", 1),
    ("rain_gage", "interval"): FieldSpec("RAINGAGES", 2),
    ("rain_gage", "snow_catch_factor"): FieldSpec("RAINGAGES", 3),
    ("rain_gage", "source_type"): FieldSpec("RAINGAGES", 4),
    ("rain_gage", "time_series"): FieldSpec("RAINGAGES", 5, reference_target="time_series"),
    ("subcatchment", "id"): FieldSpec("SUBCATCHMENTS", 0),
    ("subcatchment", "rain_gage"): FieldSpec("SUBCATCHMENTS", 1, reference_target="rain_gage"),
    ("subcatchment", "outlet"): FieldSpec("SUBCATCHMENTS", 2, reference_target="node_or_subcatchment"),
    ("subcatchment", "area"): FieldSpec("SUBCATCHMENTS", 3),
    ("subcatchment", "impervious_percent"): FieldSpec("SUBCATCHMENTS", 4),
    ("subcatchment", "width"): FieldSpec("SUBCATCHMENTS", 5),
    ("subcatchment", "slope"): FieldSpec("SUBCATCHMENTS", 6),
    ("subcatchment", "curb_length"): FieldSpec("SUBCATCHMENTS", 7),
    ("subcatchment", "snow_pack"): FieldSpec("SUBCATCHMENTS", 8, reference_target="snow_pack"),
    ("subcatchment", "n_impervious"): FieldSpec("SUBAREAS", 1),
    ("subcatchment", "n_pervious"): FieldSpec("SUBAREAS", 2),
    ("subcatchment", "depression_storage_impervious"): FieldSpec("SUBAREAS", 3),
    ("subcatchment", "depression_storage_pervious"): FieldSpec("SUBAREAS", 4),
    ("subcatchment", "zero_depression_storage_impervious_percent"): FieldSpec("SUBAREAS", 5),
    ("subcatchment", "subarea_routing"): FieldSpec("SUBAREAS", 6),
    ("subcatchment", "percent_routed"): FieldSpec("SUBAREAS", 7),
    ("conduit", "id"): FieldSpec("CONDUITS", 0),
    ("conduit", "from_node"): FieldSpec("CONDUITS", 1, reference_target="node"),
    ("conduit", "to_node"): FieldSpec("CONDUITS", 2, reference_target="node"),
    ("conduit", "length"): FieldSpec("CONDUITS", 3),
    ("conduit", "roughness"): FieldSpec("CONDUITS", 4),
    ("conduit", "inlet_offset"): FieldSpec("CONDUITS", 5),
    ("conduit", "outlet_offset"): FieldSpec("CONDUITS", 6),
    ("conduit", "initial_flow"): FieldSpec("CONDUITS", 7),
    ("conduit", "maximum_flow"): FieldSpec("CONDUITS", 8),
    ("cross_section", "shape"): FieldSpec("XSECTIONS", 1),
    ("cross_section", "geometry_1"): FieldSpec("XSECTIONS", 2),
    ("cross_section", "geometry_2"): FieldSpec("XSECTIONS", 3),
    ("cross_section", "geometry_3"): FieldSpec("XSECTIONS", 4),
    ("cross_section", "geometry_4"): FieldSpec("XSECTIONS", 5),
    ("cross_section", "barrels"): FieldSpec("XSECTIONS", 6),
    ("cross_section", "culvert_code"): FieldSpec("XSECTIONS", 7),
    ("junction", "id"): FieldSpec("JUNCTIONS", 0),
    ("junction", "invert_elevation"): FieldSpec("JUNCTIONS", 1),
    ("junction", "max_depth"): FieldSpec("JUNCTIONS", 2),
    ("junction", "initial_depth"): FieldSpec("JUNCTIONS", 3),
    ("junction", "surcharge_depth"): FieldSpec("JUNCTIONS", 4),
    ("junction", "ponded_area"): FieldSpec("JUNCTIONS", 5),
    ("outfall", "id"): FieldSpec("OUTFALLS", 0),
    ("outfall", "invert_elevation"): FieldSpec("OUTFALLS", 1),
}


def _extend_input_fields() -> None:
    """Populate ordinary table-backed fields from compact section layouts."""

    # The first release hand-wrote only the fields needed by the initial
    # examples.  A comprehensive API is easier to keep correct when ordinary
    # section layouts live in one declarative map and generate the repetitive
    # field routes below.
    layouts: dict[str, tuple[str, tuple[str, ...], tuple[int, ...]]] = {
        "flow_divider": (
            "DIVIDERS",
            (
                "id",
                "invert_elevation",
                "diverted_link",
                "type",
                "cutoff_flow",
                "diversion_curve",
                "weir_height",
                "weir_coefficient",
                "max_depth",
                "initial_depth",
                "surcharge_depth",
                "ponded_area",
            ),
            (0,),
        ),
        "storage_unit": (
            "STORAGE",
            (
                "id",
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
            ),
            (0,),
        ),
        "pump": (
            "PUMPS",
            ("id", "from_node", "to_node", "curve", "initial_status", "startup_depth", "shutoff_depth"),
            (0,),
        ),
        "orifice": (
            "ORIFICES",
            (
                "id",
                "from_node",
                "to_node",
                "type",
                "offset",
                "discharge_coefficient",
                "flap_gate",
                "open_close_time",
            ),
            (0,),
        ),
        "weir": (
            "WEIRS",
            (
                "id",
                "from_node",
                "to_node",
                "type",
                "crest_height",
                "discharge_coefficient",
                "flap_gate",
                "end_contractions",
                "end_coefficient",
                "surcharge",
                "road_width",
                "road_surface",
            ),
            (0,),
        ),
        "outlet": (
            "OUTLETS",
            ("id", "from_node", "to_node", "offset", "rating_type", "curve", "exponent", "flap_gate"),
            (0,),
        ),
        "street": (
            "STREETS",
            ("id", "crown_width", "curb_height", "cross_slope", "roughness", "depression_storage", "gutter_width", "gutter_slope"),
            (0,),
        ),
        "inlet": (
            "INLETS",
            ("id", "type", "grate_length", "grate_width", "grate_type", "curb_length", "curb_height", "slotted_length", "slotted_width"),
            (0,),
        ),
        "aquifer": (
            "AQUIFERS",
            (
                "id",
                "porosity",
                "wilting_point",
                "field_capacity",
                "conductivity",
                "conductivity_slope",
                "tension_slope",
                "upper_evaporation_fraction",
                "lower_evaporation_depth",
                "lower_groundwater_loss_rate",
                "bottom_elevation",
                "water_table_elevation",
                "unsaturated_moisture",
                "upper_evaporation_pattern",
            ),
            (0,),
        ),
        "pollutant": (
            "POLLUTANTS",
            (
                "id",
                "units",
                "rain_concentration",
                "groundwater_concentration",
                "rdii_concentration",
                "decay_coefficient",
                "snow_only",
                "co_pollutant",
                "co_pollutant_fraction",
                "dry_weather_flow_concentration",
                "initial_concentration",
            ),
            (0,),
        ),
        "land_use": (
            "LANDUSES",
            ("id", "sweeping_interval", "sweeping_availability", "last_swept"),
            (0,),
        ),
        "coverage": ("COVERAGES", ("subcatchment", "land_use", "percent"), (0, 1)),
        "loading": ("LOADINGS", ("subcatchment", "pollutant", "initial_buildup"), (0, 1)),
        "buildup": (
            "BUILDUP",
            ("land_use", "pollutant", "function", "maximum_buildup", "rate_constant", "power", "normalizer"),
            (0, 1),
        ),
        "washoff": (
            "WASHOFF",
            ("land_use", "pollutant", "function", "coefficient", "exponent", "cleaning_efficiency", "bmp_efficiency"),
            (0, 1),
        ),
        "treatment": ("TREATMENT", ("node", "pollutant", "expression"), (0, 1)),
        "groundwater": (
            "GROUNDWATER",
            (
                "subcatchment",
                "aquifer",
                "node",
                "surface_elevation",
                "a1",
                "b1",
                "a2",
                "b2",
                "a3",
                "fixed_depth",
                "threshold_elevation",
                "lateral_flow_equation",
                "deep_flow_equation",
            ),
            (0,),
        ),
        "inlet_usage": (
            "INLET_USAGE",
            ("node", "inlet", "conduit", "number", "clogging_factor", "flow_restriction"),
            (0, 1, 2),
        ),
        "lid_usage": (
            "LID_USAGE",
            (
                "subcatchment",
                "lid_control",
                "number",
                "area",
                "width",
                "initial_saturation",
                "from_impervious_percent",
                "outlet",
                "drain_to",
                "from_pervious_percent",
            ),
            (0, 1),
        ),
        "external_inflow": (
            "INFLOWS",
            ("node", "constituent", "time_series", "type", "units_factor", "scale_factor", "baseline", "pattern"),
            (0, 1),
        ),
        "dry_weather_flow": (
            "DWF",
            ("node", "constituent", "average_value", "monthly_pattern", "daily_pattern", "hourly_pattern", "weekend_pattern"),
            (0, 1),
        ),
        "rdii": ("RDII", ("node", "unit_hydrograph", "sewer_area"), (0,)),
        "time_pattern": ("PATTERNS", ("id", "type"), (0,)),
        "unit_hydrograph": (
            "HYDROGRAPHS",
            (
                "id",
                "rain_gage",
                "month",
                "short_term_r",
                "short_term_t",
                "short_term_k",
                "medium_term_r",
                "medium_term_t",
                "medium_term_k",
                "long_term_r",
                "long_term_t",
                "long_term_k",
            ),
            (0, 2),
        ),
    }
    references = {
        ("pump", "from_node"): "node",
        ("pump", "to_node"): "node",
        ("pump", "curve"): "curve",
        ("orifice", "from_node"): "node",
        ("orifice", "to_node"): "node",
        ("weir", "from_node"): "node",
        ("weir", "to_node"): "node",
        ("outlet", "from_node"): "node",
        ("outlet", "to_node"): "node",
        ("outlet", "curve"): "curve",
        ("aquifer", "upper_evaporation_pattern"): "time_pattern",
        ("coverage", "subcatchment"): "subcatchment",
        ("coverage", "land_use"): "land_use",
        ("loading", "subcatchment"): "subcatchment",
        ("loading", "pollutant"): "pollutant",
        ("buildup", "land_use"): "land_use",
        ("buildup", "pollutant"): "pollutant",
        ("washoff", "land_use"): "land_use",
        ("washoff", "pollutant"): "pollutant",
        ("treatment", "node"): "node",
        ("treatment", "pollutant"): "pollutant",
        ("groundwater", "subcatchment"): "subcatchment",
        ("groundwater", "aquifer"): "aquifer",
        ("groundwater", "node"): "node",
        ("inlet_usage", "node"): "node",
        ("inlet_usage", "inlet"): "inlet",
        ("inlet_usage", "conduit"): "conduit",
        ("lid_usage", "subcatchment"): "subcatchment",
        ("lid_usage", "lid_control"): "lid_control",
        ("lid_usage", "drain_to"): "subcatchment",
        ("external_inflow", "node"): "node",
        ("external_inflow", "time_series"): "time_series",
        ("external_inflow", "pattern"): "time_pattern",
        ("dry_weather_flow", "node"): "node",
        ("dry_weather_flow", "monthly_pattern"): "time_pattern",
        ("dry_weather_flow", "daily_pattern"): "time_pattern",
        ("dry_weather_flow", "hourly_pattern"): "time_pattern",
        ("dry_weather_flow", "weekend_pattern"): "time_pattern",
        ("rdii", "node"): "node",
        ("rdii", "unit_hydrograph"): "unit_hydrograph",
        ("unit_hydrograph", "rain_gage"): "rain_gage",
    }
    for category, (section, fields, key_indexes) in layouts.items():
        for field_index, field_name in enumerate(fields):
            INPUT_FIELDS.setdefault(
                (category, field_name),
                FieldSpec(
                    section,
                    field_index,
                    id_index=key_indexes[0],
                    reference_target=references.get((category, field_name)),
                    key_indexes=key_indexes,
                    multirow=category in {"unit_hydrograph"},
                ),
            )

    INPUT_FIELDS.update(
        {
            ("rain_gage", "filename"): FieldSpec("RAINGAGES", 5),
            ("rain_gage", "station"): FieldSpec("RAINGAGES", 6),
            ("rain_gage", "units"): FieldSpec("RAINGAGES", 7),
            ("subcatchment", "tag"): FieldSpec("TAGS", 2, id_index=1, key_indexes=(1,)),
            ("infiltration_horton", "maximum_rate"): FieldSpec("INFILTRATION", 1),
            ("infiltration_horton", "minimum_rate"): FieldSpec("INFILTRATION", 2),
            ("infiltration_horton", "decay"): FieldSpec("INFILTRATION", 3),
            ("infiltration_horton", "dry_time"): FieldSpec("INFILTRATION", 4),
            ("infiltration_horton", "maximum_volume"): FieldSpec("INFILTRATION", 5),
            ("infiltration_green_ampt", "suction_head"): FieldSpec("INFILTRATION", 1),
            ("infiltration_green_ampt", "hydraulic_conductivity"): FieldSpec("INFILTRATION", 2),
            ("infiltration_green_ampt", "initial_moisture_deficit"): FieldSpec("INFILTRATION", 3),
            ("infiltration_curve_number", "curve_number"): FieldSpec("INFILTRATION", 1),
            ("infiltration_curve_number", "conductivity"): FieldSpec("INFILTRATION", 2),
            ("infiltration_curve_number", "dry_time"): FieldSpec("INFILTRATION", 3),
            ("outfall", "type"): FieldSpec("OUTFALLS", 2),
            ("outfall", "fixed_stage"): FieldSpec("OUTFALLS", 3),
            ("outfall", "tidal_curve"): FieldSpec("OUTFALLS", 3, reference_target="curve"),
            ("outfall", "time_series"): FieldSpec("OUTFALLS", 3, reference_target="time_series"),
            ("outfall", "tide_gate"): FieldSpec("OUTFALLS", 4),
            ("outfall", "route_to"): FieldSpec("OUTFALLS", 5, reference_target="subcatchment"),
            ("conduit", "shape"): FieldSpec("XSECTIONS", 1),
            ("conduit", "barrels"): FieldSpec("XSECTIONS", 6),
            ("conduit", "culvert_code"): FieldSpec("XSECTIONS", 7),
            ("conduit", "entry_loss"): FieldSpec("LOSSES", 1),
            ("conduit", "exit_loss"): FieldSpec("LOSSES", 2),
            ("conduit", "average_loss"): FieldSpec("LOSSES", 3),
            ("conduit", "flap_gate"): FieldSpec("LOSSES", 4),
            ("conduit", "seepage_rate"): FieldSpec("LOSSES", 5),
            ("cross_section", "link"): FieldSpec("XSECTIONS", 0, reference_target="link"),
            ("cross_section", "shape_curve"): FieldSpec("XSECTIONS", 2, reference_target="curve"),
            ("orifice", "shape"): FieldSpec("XSECTIONS", 1),
            ("orifice", "height"): FieldSpec("XSECTIONS", 2),
            ("orifice", "width"): FieldSpec("XSECTIONS", 3),
            ("weir", "length"): FieldSpec("WEIRS", 6),
            ("weir", "side_slope"): FieldSpec("WEIRS", 7),
            ("outlet", "coefficient"): FieldSpec("OUTLETS", 5),
            ("lid_control", "id"): FieldSpec("LID_CONTROLS", 0),
            ("lid_control", "type"): FieldSpec("LID_CONTROLS", 1),
            ("curve", "id"): FieldSpec("CURVES", 0, multirow=True),
            ("curve", "type"): FieldSpec("CURVES", 1, multirow=True),
            ("curve", "x"): FieldSpec("CURVES", 2, multirow=True),
            ("curve", "y"): FieldSpec("CURVES", 3, multirow=True),
            ("time_series", "id"): FieldSpec("TIMESERIES", 0, multirow=True),
            ("time_series", "filename"): FieldSpec("TIMESERIES", 2, multirow=True),
            ("lid_surface", "storage_depth"): FieldSpec("LID_CONTROLS", 2),
            ("lid_surface", "vegetation_fraction"): FieldSpec("LID_CONTROLS", 3),
            ("lid_surface", "roughness"): FieldSpec("LID_CONTROLS", 4),
            ("lid_surface", "slope"): FieldSpec("LID_CONTROLS", 5),
            ("lid_surface", "side_slope"): FieldSpec("LID_CONTROLS", 6),
            ("lid_pavement", "thickness"): FieldSpec("LID_CONTROLS", 2),
            ("lid_pavement", "void_ratio"): FieldSpec("LID_CONTROLS", 3),
            ("lid_pavement", "impervious_surface_fraction"): FieldSpec("LID_CONTROLS", 4),
            ("lid_pavement", "permeability"): FieldSpec("LID_CONTROLS", 5),
            ("lid_pavement", "clogging_factor"): FieldSpec("LID_CONTROLS", 6),
            ("lid_soil", "thickness"): FieldSpec("LID_CONTROLS", 2),
            ("lid_soil", "porosity"): FieldSpec("LID_CONTROLS", 3),
            ("lid_soil", "field_capacity"): FieldSpec("LID_CONTROLS", 4),
            ("lid_soil", "wilting_point"): FieldSpec("LID_CONTROLS", 5),
            ("lid_soil", "conductivity"): FieldSpec("LID_CONTROLS", 6),
            ("lid_soil", "conductivity_slope"): FieldSpec("LID_CONTROLS", 7),
            ("lid_soil", "suction_head"): FieldSpec("LID_CONTROLS", 8),
            ("lid_storage", "height"): FieldSpec("LID_CONTROLS", 2),
            ("lid_storage", "void_ratio"): FieldSpec("LID_CONTROLS", 3),
            ("lid_storage", "seepage_rate"): FieldSpec("LID_CONTROLS", 4),
            ("lid_storage", "clogging_factor"): FieldSpec("LID_CONTROLS", 5),
            ("lid_drain", "coefficient"): FieldSpec("LID_CONTROLS", 2),
            ("lid_drain", "exponent"): FieldSpec("LID_CONTROLS", 3),
            ("lid_drain", "offset_height"): FieldSpec("LID_CONTROLS", 4),
            ("lid_drain", "delay"): FieldSpec("LID_CONTROLS", 5),
            ("lid_drain", "open_level"): FieldSpec("LID_CONTROLS", 6),
            ("lid_drain", "closed_level"): FieldSpec("LID_CONTROLS", 7),
            ("lid_drain", "control_curve"): FieldSpec("LID_CONTROLS", 8, reference_target="curve"),
        }
    )


_extend_input_fields()

OBJECT_SECTIONS = {
    "rain_gage": ("RAINGAGES",),
    "subcatchment": ("SUBCATCHMENTS",),
    "junction": ("JUNCTIONS",),
    "outfall": ("OUTFALLS",),
    "flow_divider": ("DIVIDERS",),
    "storage_unit": ("STORAGE",),
    "conduit": ("CONDUITS",),
    "cross_section": ("XSECTIONS",),
    "pump": ("PUMPS",),
    "orifice": ("ORIFICES",),
    "weir": ("WEIRS",),
    "outlet": ("OUTLETS",),
    "node": ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE"),
    "link": ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"),
    "time_series": ("TIMESERIES",),
    "time_pattern": ("PATTERNS",),
    "curve": ("CURVES",),
    "transect": ("TRANSECTS",),
    "street": ("STREETS",),
    "inlet": ("INLETS",),
    "pollutant": ("POLLUTANTS",),
    "land_use": ("LANDUSES",),
    "aquifer": ("AQUIFERS",),
    "snow_pack": ("SNOWPACKS",),
    "lid_control": ("LID_CONTROLS",),
    "lid_surface": ("LID_CONTROLS",),
    "lid_pavement": ("LID_CONTROLS",),
    "lid_soil": ("LID_CONTROLS",),
    "lid_storage": ("LID_CONTROLS",),
    "lid_drain": ("LID_CONTROLS",),
    "unit_hydrograph": ("HYDROGRAPHS",),
    "control_rule": ("CONTROLS",),
    "coverage": ("COVERAGES",),
    "loading": ("LOADINGS",),
    "buildup": ("BUILDUP",),
    "washoff": ("WASHOFF",),
    "treatment": ("TREATMENT",),
    "groundwater": ("GROUNDWATER",),
    "inlet_usage": ("INLET_USAGE",),
    "lid_usage": ("LID_USAGE",),
    "external_inflow": ("INFLOWS",),
    "dry_weather_flow": ("DWF",),
    "rdii": ("RDII",),
    "infiltration_horton": ("INFILTRATION",),
    "infiltration_green_ampt": ("INFILTRATION",),
    "infiltration_curve_number": ("INFILTRATION",),
}

CATEGORY_KEY_INDEXES = {
    "coverage": (0, 1),
    "loading": (0, 1),
    "buildup": (0, 1),
    "washoff": (0, 1),
    "treatment": (0, 1),
    "inlet_usage": (0, 1, 2),
    "lid_usage": (0, 1),
    "external_inflow": (0, 1),
    "dry_weather_flow": (0, 1),
    "unit_hydrograph": (0, 2),
}

RESULT_OBJECT_KIND = {
    "subcatchment": "subcatchment",
    "node": "node",
    "link": "link",
    "conduit": "link",
    "junction": "node",
    "outfall": "node",
    "pump": "link",
    "orifice": "link",
    "weir": "link",
    "outlet": "link",
}

RESULT_VARIABLES = {
    "subcatchment": {
        "rainfall",
        "snow_depth",
        "evaporation",
        "infiltration",
        "runoff",
        "groundwater_flow",
        "groundwater_elevation",
        "soil_moisture",
    },
    "node": {"depth", "head", "volume", "lateral_inflow", "total_inflow", "flooding", "overflow"},
    "link": {"flow", "depth", "velocity", "volume", "capacity"},
    "system_result": {
        "air_temperature",
        "rainfall",
        "snow_depth",
        "evaporation",
        "infiltration",
        "runoff",
        "dry_weather_inflow",
        "groundwater_inflow",
        "rdii_inflow",
        "direct_inflow",
        "total_lateral_inflow",
        "flooding",
        "outflow",
        "volume",
        "evaporation_loss",
    },
}


class ParameterCatalog:
    """Public parameter catalog plus the small physical mapping in this release."""

    def __init__(self, schema: "SchemaRegistry") -> None:
        """Build normalized lookups from the loaded primary schema."""

        self.schema = schema
        self._specs: dict[tuple[str, str], ParameterSpec] = {}
        self._categories_by_api_name: dict[str, str] = {}
        self._subcategories_by_api_name: dict[str, dict[str, str]] = {}

        for row in schema.frame.to_dict(orient="records"):
            main = str(row["main_category"])
            sub = str(row["sub_category"])
            spec = ParameterSpec(
                main_category=main,
                sub_category=sub,
                source=str(row["source"]),
                type=str(row["type"]),
                size=str(row["size"]),
                notes=str(row.get("Coding notes / conditions", "")),
            )
            self._specs[spec.key] = spec
            self._categories_by_api_name[api_name(main)] = main
            self._subcategories_by_api_name.setdefault(main, {})[api_name(sub)] = sub

    def spec(self, main_api_name: str, sub_api_name: str) -> ParameterSpec:
        """Resolve one public dotted path to its parameter definition."""

        main = self._categories_by_api_name[main_api_name]
        sub = self._subcategories_by_api_name[main][sub_api_name]
        return self._specs[(main, sub)]

    def categories(self, mode: str) -> list[str]:
        """Return category names visible to one completion mode."""

        names: list[str] = []
        for main_api, raw_main in self._categories_by_api_name.items():
            specs = [spec for spec in self._specs.values() if spec.main_category == raw_main]
            if mode == "get" or any(spec.is_writable for spec in specs):
                names.append(main_api)
        return sorted(names)

    def subcategories(self, raw_main: str, mode: str) -> list[str]:
        """Return subcategory names visible inside one category namespace."""

        names: list[str] = []
        for sub_api, raw_sub in self._subcategories_by_api_name[raw_main].items():
            spec = self._specs[(raw_main, raw_sub)]
            if mode == "get" or spec.is_writable:
                names.append(sub_api)
        return sorted(names)

    def is_supported(self, spec: ParameterSpec, mode: str) -> bool:
        """Return whether one path has a concrete implementation in this runtime."""

        if mode == "get":
            return self._supports_get(spec)
        if mode == "set":
            return self._supports_set(spec)
        raise ValueError(f"Unknown access mode '{mode}'.")

    def _supports_get(self, spec: ParameterSpec) -> bool:
        """Return whether a getter can execute without a structural placeholder."""

        if spec.main_category.startswith("option_"):
            return spec.sub_category in OPTION_FIELDS
        if spec.source_kind == "result":
            if spec.main_category == "system_result":
                return spec.sub_category in RESULT_VARIABLES["system_result"]
            object_kind = RESULT_OBJECT_KIND.get(spec.main_category)
            return object_kind is not None and spec.sub_category in RESULT_VARIABLES[object_kind]
        if spec.source_kind == "derived":
            return (
                spec.sub_category == "count"
                and spec.main_category in OBJECT_SECTIONS
            ) or spec.key in {
                ("conduit", "slope"),
                ("node", "type"),
                ("link", "type"),
            }
        return spec.key in INPUT_FIELDS

    def _supports_set(self, spec: ParameterSpec) -> bool:
        """Return whether a setter can execute without a structural placeholder."""

        if not spec.is_writable:
            return False
        if spec.main_category.startswith("option_"):
            return spec.sub_category in OPTION_FIELDS
        return spec.key in INPUT_FIELDS

    def raw_category(self, main_api_name: str) -> str:
        """Return the original category behind one safe API name."""

        return self._categories_by_api_name[main_api_name]

    def has_category(self, main_api_name: str) -> bool:
        """Return whether one category exists in the routed registry."""

        return main_api_name in self._categories_by_api_name

    def has_subcategory(self, raw_main: str, sub_api_name: str) -> bool:
        """Return whether one subcategory exists in the routed registry."""

        return sub_api_name in self._subcategories_by_api_name.get(raw_main, {})

    def suggest_category(self, main_api_name: str) -> str | None:
        """Return the closest public category name, if one is plausible."""

        matches = get_close_matches(main_api_name, self.categories("get"), n=1, cutoff=0.45)
        return matches[0] if matches else None

    def suggest_subcategory(self, raw_main: str, sub_api_name: str) -> str | None:
        """Return the closest public parameter name in one category."""

        matches = get_close_matches(
            sub_api_name,
            self.subcategories(raw_main, "get"),
            n=1,
            cutoff=0.45,
        )
        return matches[0] if matches else None


class AccessRoot:
    """Root object exposed as ``m.get`` or ``m.set``."""

    def __init__(self, model: "SWMMModel", mode: str) -> None:
        """Remember the model and whether this is a getter or setter tree."""

        self._model = model
        self._mode = mode

        # Some IDEs ask ``dir(obj)`` for completions, while others inspect the
        # instance dictionary directly.  Materialize every visible category as
        # a real attribute so both styles can discover ``m.get.link``.
        catalog = self._model._parameter_catalog
        for category_name in catalog.categories(self._mode):
            raw_category = catalog.raw_category(category_name)
            setattr(self, category_name, CategoryAccessor(self._model, raw_category, self._mode))

    def __dir__(self) -> list[str]:
        """Expose public category names to IDE completion."""

        return self._model._parameter_catalog.categories(self._mode)

    def __getattr__(self, category_name: str) -> "CategoryAccessor":
        """Return a routed category namespace."""

        # IDEs and rich shells inspect private hook names during completion
        # and help rendering.  Treat those as ordinary missing Python
        # attributes so tools such as Spyder can call ``hasattr`` safely.
        if category_name.startswith("_"):
            raise AttributeError(category_name)

        catalog = self._model._parameter_catalog
        if not catalog.has_category(category_name):
            suggestion = catalog.suggest_category(category_name)
            suffix = f" Did you mean '{suggestion}'?" if suggestion else ""
            raise UnknownCategoryError(f"Unknown category '{category_name}'.{suffix}")

        # This fallback mainly protects callers if a future catalog is mutated
        # after construction.  Store the resolved namespace once so later
        # completion and identity checks see an ordinary attribute.
        accessor = CategoryAccessor(self._model, catalog.raw_category(category_name), self._mode)
        setattr(self, category_name, accessor)
        return accessor


class CategoryAccessor:
    """Namespace such as ``m.get.conduit`` or ``m.set.subcatchment``."""

    def __init__(self, model: "SWMMModel", raw_main_category: str, mode: str) -> None:
        """Bind the namespace to one model, one category, and one mode."""

        self._model = model
        self._raw_main_category = raw_main_category
        self._mode = mode

        # As with categories, eagerly attach every visible routed callable so
        # editors that rely on ``vars(m.get.link)`` can offer ``flow`` and its
        # siblings without first invoking ``__getattr__``.
        catalog = self._model._parameter_catalog
        main_api_name = api_name(self._raw_main_category)
        for subcategory_name in catalog.subcategories(self._raw_main_category, self._mode):
            spec = catalog.spec(main_api_name, subcategory_name)
            callable_object = GetterCallable(self._model, spec) if self._mode == "get" else SetterCallable(self._model, spec)
            setattr(self, subcategory_name, callable_object)

    def __dir__(self) -> list[str]:
        """Expose subcategory names suitable for IDE completion."""

        return self._model._parameter_catalog.subcategories(self._raw_main_category, self._mode)

    def __getattr__(self, subcategory_name: str):
        """Return a callable getter or setter for one public parameter."""

        # See ``AccessRoot.__getattr__``: private shell/IDE probes are not
        # user-facing parameter names and therefore should not become
        # ``UnknownParameterError`` exceptions during introspection.
        if subcategory_name.startswith("_"):
            raise AttributeError(subcategory_name)

        catalog = self._model._parameter_catalog
        if not catalog.has_subcategory(self._raw_main_category, subcategory_name):
            suggestion = catalog.suggest_subcategory(self._raw_main_category, subcategory_name)
            suffix = f" Did you mean '{suggestion}'?" if suggestion else ""
            raise UnknownParameterError(
                f"Unknown parameter '{subcategory_name}' for category '{api_name(self._raw_main_category)}'.{suffix}"
            )
        spec = catalog.spec(api_name(self._raw_main_category), subcategory_name)
        callable_object = GetterCallable(self._model, spec) if self._mode == "get" else SetterCallable(self._model, spec)
        setattr(self, subcategory_name, callable_object)
        return callable_object


class GetterCallable:
    """Callable object that gives dynamic getters inspectable signatures."""

    __signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("ids", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
            inspect.Parameter("format", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
        ]
    )

    def __init__(self, model: "SWMMModel", spec: ParameterSpec) -> None:
        """Store the model/spec pair and build a human-facing docstring."""

        self._model = model
        self._spec = spec
        self.__name__ = spec.sub_category
        source_note = ""
        if spec.source_kind == "result":
            source_note = (
                "This is a read-only result variable and requires ``m.run()`` before access.\n"
            )
        elif spec.source_kind == "derived":
            source_note = "This is a read-only derived parameter computed from model data.\n"
        self.__doc__ = (
            f"Get ``{spec.path}``.\n\n"
            "Parameters\n"
            "----------\n"
            "ids:\n"
            "    Optional object selector: ``None``, one object ID string, or a list of ID strings.\n"
            "format:\n"
            "    Optional output format: ``'np'`` (default) or ``'df'``.\n"
            "\nReturns\n"
            "-------\n"
            "object\n"
            "    A scalar for one selected non-time-series ID, otherwise a NumPy array or pandas DataFrame.\n"
            "\nExamples\n"
            "--------\n"
            f">>> m.get.{spec.path}()\n"
            f">>> m.get.{spec.path}(ids=\"ID\", format=\"df\")\n"
            "\nNotes\n"
            "-----\n"
            "``ids=None`` selects every object in the category.  ``format`` controls the returned container only.\n"
            f"{source_note}"
        )

    def __call__(self, ids=None, format=None):
        """Execute the routed getter."""

        return self._model._get_parameter(self._spec, ids=ids, format=format)


class SetterCallable:
    """Callable object that gives dynamic setters inspectable signatures."""

    __signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("value", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("ids", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
        ]
    )

    def __init__(self, model: "SWMMModel", spec: ParameterSpec) -> None:
        """Store the model/spec pair and build a human-facing docstring."""

        self._model = model
        self._spec = spec
        self.__name__ = spec.sub_category
        self.__doc__ = (
            f"Set ``{spec.path}``.\n\n"
            "Parameters\n"
            "----------\n"
            "value:\n"
            "    Scalar value or one-dimensional list/NumPy array/pandas Series. Scalars broadcast across all selected IDs.\n"
            "ids:\n"
            "    Optional object selector: ``None``, one object ID string, or a list of ID strings.\n"
            "\nReturns\n"
            "-------\n"
            "None\n"
            "    Values are written into the in-memory model and old results are invalidated.\n"
            "\nExamples\n"
            "--------\n"
            f">>> m.set.{spec.path}(1.0)\n"
            f">>> m.set.{spec.path}([1.0, 2.0], ids=[\"ID1\", \"ID2\"])\n"
            "\nNotes\n"
            "-----\n"
            "Setters do not accept ``format``.  ``ids=None`` applies the value to every object in the category.\n"
            "Result and derived parameters are read-only; direct writes raise ``ReadOnlyParameterError``.\n"
        )

    def __call__(self, value, ids=None):
        """Execute the routed setter."""

        return self._model._set_parameter(self._spec, value=value, ids=ids)


def coerce_value(value: str, declared_type: str) -> Any:
    """Convert one raw INP token using the declared schema type when safe."""

    lowered = declared_type.lower()
    if "bool" in lowered:
        return value.strip().upper() in {"YES", "TRUE", "1"}
    if "integer" in lowered or lowered == "int":
        try:
            return int(float(value))
        except ValueError:
            return value
    if "float" in lowered:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def normalize_ids(ids, available_ids: list[str], category: str) -> tuple[list[str], bool]:
    """Normalize user ID input and report whether exactly one ID was requested."""

    if not available_ids:
        raise ObjectNotFoundError(f"No {category} objects are available in this model.")

    if ids is None:
        selected = list(available_ids)
        explicit_single = False
    elif isinstance(ids, str):
        selected = [ids]
        explicit_single = True
    elif isinstance(ids, (list, tuple)):
        if not all(isinstance(value, str) for value in ids):
            raise TypeError("'ids' must contain only strings.")
        selected = list(ids)
        explicit_single = len(selected) == 1
    else:
        raise TypeError("'ids' must be None, one string ID, or a list of string IDs.")

    missing = [object_id for object_id in selected if object_id not in available_ids]
    if missing:
        if len(missing) == 1:
            raise UnknownIDError(f"Unknown {category} ID '{missing[0]}'.")
        joined = ", ".join(f"'{object_id}'" for object_id in missing)
        raise UnknownIDError(f"Unknown {category} IDs {joined}.")
    return selected, explicit_single


def normalize_values(value, selected_count: int, category: str) -> list[Any]:
    """Normalize setter input into one value per selected object."""

    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise DimensionMismatchError("2D NumPy arrays are not supported by setters in this version.")
        values = value.tolist()
    elif isinstance(value, pd.Series):
        values = value.tolist()
    elif isinstance(value, (list, tuple)):
        # One selected object may legitimately receive a structured value such
        # as a coordinate pair, conduit geometry tuple, polygon point list, or
        # an empty attached-record list.  Treat those as one scalar payload
        # unless the caller supplied the conventional one-item broadcast form.
        if selected_count == 1 and len(value) != 1:
            values = [value]
        else:
            values = list(value)
    else:
        values = [value] * selected_count

    if len(values) != selected_count:
        raise DimensionMismatchError(
            f"Received {len(values)} values for {selected_count} selected {category} objects."
        )
    return values
