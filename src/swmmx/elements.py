"""Editable-element namespaces for ``m.add`` and ``m.remove``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import inspect
from math import hypot
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import pandas as pd

from .errors import (
    DependencyError,
    DuplicateIDError,
    InvalidParameterError,
    InvalidReferenceError,
    MissingRequiredParameterError,
    NotImplementedYetError,
    UnknownIDError,
)

if TYPE_CHECKING:
    from .api import SWMMModel


@dataclass(frozen=True)
class PositionalParameter:
    """One optional extra positional argument exposed by an add callable."""

    name: str
    default: Any = inspect._empty


@dataclass(frozen=True)
class EditableElementSpec:
    """One public add/remove element definition."""

    category: str
    element_type: str
    inp_sections: tuple[str, ...]
    id_scope: str
    required_parameters: tuple[str, ...] = ()
    optional_parameters: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    coordinate_policy: str | None = None
    dependency_rules: tuple[str, ...] = ()
    implemented: bool = False
    positional_parameters: tuple[PositionalParameter, ...] = ()
    purpose: str = ""
    example: str = ""

    @property
    def path(self) -> str:
        """Return the dotted public path below ``m.add`` / ``m.remove``."""

        return f"{self.category}.{self.element_type}"


def _spec(
    category: str,
    element_type: str,
    *,
    sections: tuple[str, ...],
    scope: str,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    defaults: dict[str, Any] | None = None,
    references: dict[str, str] | None = None,
    coordinate_policy: str | None = None,
    dependencies: tuple[str, ...] = (),
    implemented: bool = False,
    positional: tuple[PositionalParameter, ...] = (),
    purpose: str = "",
    example: str = "",
) -> EditableElementSpec:
    """Create a concise registry entry."""

    return EditableElementSpec(
        category=category,
        element_type=element_type,
        inp_sections=sections,
        id_scope=scope,
        required_parameters=required,
        optional_parameters=optional,
        defaults=defaults or {},
        references=references or {},
        coordinate_policy=coordinate_policy,
        dependency_rules=dependencies,
        implemented=implemented,
        positional_parameters=positional,
        purpose=purpose,
        example=example,
    )


EDITABLE_ELEMENT_SPECS = (
    # Hydrology
    _spec(
        "hydrology",
        "rain_gage",
        sections=("RAINGAGES", "SYMBOLS"),
        scope="rain_gage",
        required=("format", "interval", "source_type"),
        optional=("x", "y", "snow_catch_factor", "time_series", "filename", "station", "units"),
        defaults={"snow_catch_factor": 1.0},
        references={"time_series": "time_series"},
        coordinate_policy="mapped_max",
        dependencies=("subcatchment.rain_gage",),
        implemented=True,
        purpose="Add a rainfall gage and its map symbol.",
        example='m.add.hydrology.rain_gage("RG1", format="INTENSITY", interval="00:05", source_type="TIMESERIES", time_series="Rain1")',
    ),
    _spec(
        "hydrology",
        "subcatchment",
        sections=("SUBCATCHMENTS", "SUBAREAS", "INFILTRATION", "POLYGONS"),
        scope="subcatchment",
        required=("rain_gage", "outlet"),
        optional=(
            "x",
            "y",
            "area",
            "width",
            "slope",
            "impervious_percent",
            "curb_length",
            "snow_pack",
            "polygon",
            "n_impervious",
            "n_pervious",
            "depression_storage_impervious",
            "depression_storage_pervious",
            "zero_depression_storage_impervious_percent",
            "subarea_routing",
            "percent_routed",
            "maximum_rate",
            "minimum_rate",
            "decay",
            "dry_time",
            "maximum_volume",
            "suction_head",
            "hydraulic_conductivity",
            "initial_moisture_deficit",
            "curve_number",
            "conductivity",
        ),
        defaults={
            "area": 0.0,
            "width": 0.0,
            "slope": 0.0,
            "impervious_percent": 0.0,
            "curb_length": 0.0,
            "n_impervious": 0.01,
            "n_pervious": 0.1,
            "depression_storage_impervious": 0.05,
            "depression_storage_pervious": 0.05,
            "zero_depression_storage_impervious_percent": 25.0,
            "subarea_routing": "OUTLET",
        },
        references={"rain_gage": "rain_gage", "outlet": "node_or_subcatchment", "snow_pack": "snow_pack"},
        coordinate_policy="mapped_min",
        dependencies=("subcatchment.outlet",),
        implemented=True,
        purpose="Add a subcatchment with subarea and infiltration records.",
        example='m.add.hydrology.subcatchment("S1", rain_gage="RG1", outlet="J1", area=1.0)',
    ),
    _spec("hydrology", "aquifer", sections=("AQUIFERS",), scope="aquifer", optional=("porosity", "wilting_point", "field_capacity", "conductivity", "conductivity_slope", "tension_slope", "upper_evaporation_fraction", "lower_evaporation_depth", "lower_groundwater_loss_rate", "bottom_elevation", "water_table_elevation", "unsaturated_moisture", "upper_evaporation_pattern"), purpose="Reserve an aquifer definition."),
    _spec("hydrology", "snow_pack", sections=("SNOWPACKS",), scope="snow_pack", optional=("plowable_fraction", "impervious_fraction", "pervious_fraction", "minimum_melt_coefficient", "maximum_melt_coefficient", "base_temperature", "free_water_capacity_fraction", "initial_snow_depth", "initial_free_water", "depth_at_100_percent_cover"), purpose="Reserve a snow-pack definition."),
    _spec(
        "hydrology",
        "unit_hydrograph",
        sections=("HYDROGRAPHS",),
        scope="unit_hydrograph",
        required=("rain_gage", "data"),
        optional=("month", "short_term_r", "short_term_t", "short_term_k", "medium_term_r", "medium_term_t", "medium_term_k", "long_term_r", "long_term_t", "long_term_k"),
        references={"rain_gage": "rain_gage"},
        positional=(PositionalParameter("rain_gage"), PositionalParameter("data")),
        purpose="Reserve an RDII unit hydrograph definition.",
    ),
    _spec(
        "hydrology",
        "lid_control",
        sections=("LID_CONTROLS",),
        scope="lid_control",
        required=("type",),
        optional=("parameters", "surface", "pavement", "soil", "storage", "drain", "drain_mat"),
        positional=(PositionalParameter("type"), PositionalParameter("parameters", None)),
        purpose="Reserve a multi-layer LID control definition.",
    ),
    # Nodes
    _spec(
        "node",
        "junction",
        sections=("JUNCTIONS", "COORDINATES"),
        scope="node",
        optional=("x", "y", "invert_elevation", "max_depth", "initial_depth", "surcharge_depth", "ponded_area", "spacing"),
        defaults={"invert_elevation": 0.0, "max_depth": 0.0, "initial_depth": 0.0, "surcharge_depth": 0.0, "ponded_area": 0.0},
        coordinate_policy="node_next",
        dependencies=("link.from_node", "link.to_node", "subcatchment.outlet"),
        implemented=True,
        purpose="Add a hydraulic junction and a coordinate record.",
        example='m.add.node.junction("J1", invert_elevation=10.0, max_depth=3.0)',
    ),
    _spec(
        "node",
        "outfall",
        sections=("OUTFALLS", "COORDINATES"),
        scope="node",
        optional=("x", "y", "invert_elevation", "type", "fixed_stage", "tidal_curve", "time_series", "tide_gate", "route_to", "spacing"),
        defaults={"invert_elevation": 0.0, "type": "FREE", "tide_gate": "NO"},
        references={"tidal_curve": "curve", "time_series": "time_series"},
        coordinate_policy="node_next",
        dependencies=("link.from_node", "link.to_node", "subcatchment.outlet"),
        implemented=True,
        purpose="Add an outfall and a coordinate record.",
        example='m.add.node.outfall("OUT1", invert_elevation=9.0, type="FREE")',
    ),
    _spec("node", "divider", sections=("DIVIDERS", "COORDINATES"), scope="node", optional=("x", "y", "invert_elevation", "max_depth", "initial_depth", "surcharge_depth", "ponded_area", "type", "diverted_link", "cutoff_flow", "diversion_curve", "weir_height", "weir_coefficient"), purpose="Reserve a flow-divider node definition."),
    _spec("node", "storage_unit", sections=("STORAGE", "COORDINATES"), scope="node", optional=("x", "y", "invert_elevation", "max_depth", "initial_depth", "storage_curve_type", "storage_curve", "area", "area_coefficient", "area_exponent", "area_constant", "evaporation_factor", "seepage_loss"), purpose="Reserve a storage-unit node definition."),
    # Links
    _spec(
        "link",
        "conduit",
        sections=("CONDUITS", "XSECTIONS", "LOSSES", "VERTICES"),
        scope="link",
        required=("from_node", "to_node"),
        optional=("length", "roughness", "shape", "geometry", "diameter", "geometry_1", "geometry_2", "geometry_3", "geometry_4", "inlet_offset", "outlet_offset", "initial_flow", "maximum_flow", "barrels", "culvert_code", "entry_loss", "exit_loss", "average_loss", "flap_gate", "seepage_rate", "vertices"),
        defaults={"roughness": 0.013, "shape": "CIRCULAR", "diameter": 1.0, "inlet_offset": 0.0, "outlet_offset": 0.0, "initial_flow": 0.0, "maximum_flow": 0.0, "barrels": 1},
        references={"from_node": "node", "to_node": "node"},
        dependencies=("controls",),
        implemented=True,
        purpose="Add a conduit with matching cross-section data.",
        example='m.add.link.conduit("C1", from_node="J1", to_node="OUT1", length=100.0, roughness=0.013, shape="CIRCULAR", diameter=1.0)',
    ),
    _spec("link", "pump", sections=("PUMPS",), scope="link", required=("from_node", "to_node", "curve"), optional=("initial_status", "startup_depth", "shutoff_depth"), references={"from_node": "node", "to_node": "node", "curve": "curve"}, purpose="Reserve a pump-link definition."),
    _spec("link", "orifice", sections=("ORIFICES", "XSECTIONS"), scope="link", required=("from_node", "to_node", "type", "shape", "height", "discharge_coefficient"), optional=("width", "offset", "flap_gate", "open_close_time"), references={"from_node": "node", "to_node": "node"}, purpose="Reserve an orifice-link definition."),
    _spec("link", "weir", sections=("WEIRS",), scope="link", required=("from_node", "to_node", "type", "crest_height", "discharge_coefficient"), optional=("length", "side_slope", "flap_gate", "end_contractions", "end_coefficient", "surcharge", "road_width", "road_surface"), references={"from_node": "node", "to_node": "node"}, purpose="Reserve a weir-link definition."),
    _spec("link", "outlet", sections=("OUTLETS",), scope="link", required=("from_node", "to_node", "rating_type"), optional=("curve", "coefficient", "exponent", "offset", "flap_gate"), references={"from_node": "node", "to_node": "node", "curve": "curve"}, purpose="Reserve an outlet-link definition."),
    # Hydraulics
    _spec("hydraulic", "street", sections=("STREETS",), scope="street", optional=("crown_width", "curb_height", "cross_slope", "roughness", "depression_storage", "gutter_width", "gutter_slope"), purpose="Reserve a street definition."),
    _spec("hydraulic", "inlet", sections=("INLETS",), scope="inlet", optional=("type", "grate_length", "grate_width", "grate_type", "curb_length", "curb_height", "slotted_length", "slotted_width"), purpose="Reserve an inlet definition."),
    _spec("hydraulic", "transect", sections=("TRANSECTS",), scope="transect", optional=("roughness_left", "roughness_right", "roughness_channel", "left_bank", "right_bank", "stations", "elevations", "modifiers"), purpose="Reserve a transect definition."),
    _spec("hydraulic", "control", sections=("CONTROLS",), scope="control", optional=("text", "conditions", "actions", "priority"), positional=(PositionalParameter("text", None),), purpose="Reserve a control-rule definition."),
    # Quality
    _spec("quality", "pollutant", sections=("POLLUTANTS",), scope="pollutant", optional=("units", "rain_concentration", "groundwater_concentration", "rdii_concentration", "decay_coefficient", "snow_only", "co_pollutant", "co_pollutant_fraction", "dry_weather_flow_concentration", "initial_concentration"), purpose="Reserve a pollutant definition."),
    _spec("quality", "land_use", sections=("LANDUSES",), scope="land_use", optional=("sweeping_interval", "sweeping_availability", "last_swept"), purpose="Reserve a land-use definition."),
    # Curves
    _spec("curve", "control", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a control curve."),
    _spec("curve", "diversion", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a diversion curve."),
    _spec(
        "curve",
        "pump",
        sections=("CURVES",),
        scope="curve",
        required=("points",),
        optional=("curve_type",),
        defaults={"curve_type": "PUMP1"},
        positional=(PositionalParameter("points"),),
        implemented=True,
        purpose="Add a pump curve from x/y points.",
        example='m.add.curve.pump("PumpCurve1", [(0.0, 0.0), (1.0, 2.0)])',
    ),
    _spec("curve", "rating", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a rating curve."),
    _spec("curve", "shape", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a shape curve."),
    _spec("curve", "storage", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a storage curve."),
    _spec("curve", "tidal", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a tidal curve."),
    _spec("curve", "weir", sections=("CURVES",), scope="curve", required=("points",), positional=(PositionalParameter("points"),), implemented=True, purpose="Add a weir curve."),
    _spec(
        "curve",
        "generic",
        sections=("CURVES",),
        scope="curve",
        required=("type", "points"),
        positional=(PositionalParameter("type"), PositionalParameter("points")),
        implemented=True,
        purpose="Add a generic explicitly-typed curve.",
    ),
    # Time
    _spec(
        "time",
        "time_series",
        sections=("TIMESERIES",),
        scope="time_series",
        optional=("data", "datetime", "values", "filename", "description"),
        positional=(PositionalParameter("data", None),),
        implemented=True,
        purpose="Add a time series from timestamp/value data or a source file.",
        example='m.add.time.time_series("Rain1", data=[("2026-01-01 00:00", 0.0), ("2026-01-01 00:05", 5.0)])',
    ),
    _spec(
        "time",
        "time_pattern",
        sections=("PATTERNS",),
        scope="time_pattern",
        required=("type", "multipliers"),
        positional=(PositionalParameter("type"), PositionalParameter("multipliers")),
        implemented=True,
        purpose="Add a monthly, daily, hourly, or weekend time pattern.",
        example='m.add.time.time_pattern("Pat1", "DAILY", [1.0] * 24)',
    ),
)


class EditableElementRegistry:
    """Registry powering all add/remove namespaces."""

    def __init__(self) -> None:
        """Index editable element specifications by public category/type."""

        self._by_key = {(spec.category, spec.element_type): spec for spec in EDITABLE_ELEMENT_SPECS}

    def spec(self, category: str, element_type: str) -> EditableElementSpec:
        """Return one editable-element specification or raise ``AttributeError``."""

        try:
            return self._by_key[(category, element_type)]
        except KeyError as exc:
            raise AttributeError(f"{category}.{element_type}") from exc

    def categories(self) -> list[str]:
        """Return all public add/remove categories."""

        return sorted({category for category, _element_type in self._by_key})

    def element_types(self, category: str) -> list[str]:
        """Return all public element types inside one category."""

        return sorted(element_type for spec_category, element_type in self._by_key if spec_category == category)

    def has_category(self, category: str) -> bool:
        """Return whether a public category exists."""

        return category in self.categories()

    def has_element_type(self, category: str, element_type: str) -> bool:
        """Return whether one category/type pair exists."""

        return (category, element_type) in self._by_key


class EditableRoot:
    """Root namespace exposed as ``m.add`` or ``m.remove``."""

    def __init__(self, model: "SWMMModel", mode: str, registry: EditableElementRegistry) -> None:
        """Materialize every category namespace for autocomplete."""

        self._model = model
        self._mode = mode
        self._registry = registry
        for category in registry.categories():
            setattr(self, category, EditableCategoryNamespace(model, mode, registry, category))

    def __dir__(self) -> list[str]:
        """Return available public categories."""

        return self._registry.categories()

    def __getattr__(self, category: str) -> "EditableCategoryNamespace":
        """Return a category namespace, materializing it if needed."""

        if not self._registry.has_category(category):
            raise AttributeError(category)
        namespace = EditableCategoryNamespace(self._model, self._mode, self._registry, category)
        setattr(self, category, namespace)
        return namespace


class EditableCategoryNamespace:
    """Namespace such as ``m.add.link`` or ``m.remove.node``."""

    def __init__(
        self,
        model: "SWMMModel",
        mode: str,
        registry: EditableElementRegistry,
        category: str,
    ) -> None:
        """Materialize every element callable for autocomplete."""

        self._model = model
        self._mode = mode
        self._registry = registry
        self._category = category
        for element_type in registry.element_types(category):
            spec = registry.spec(category, element_type)
            callable_object = AddElementCallable(model, spec) if mode == "add" else RemoveElementCallable(model, spec)
            setattr(self, element_type, callable_object)

    def __dir__(self) -> list[str]:
        """Return element types available below this category."""

        return self._registry.element_types(self._category)

    def __getattr__(self, element_type: str):
        """Return one add/remove callable."""

        if not self._registry.has_element_type(self._category, element_type):
            raise AttributeError(element_type)
        spec = self._registry.spec(self._category, element_type)
        callable_object = AddElementCallable(self._model, spec) if self._mode == "add" else RemoveElementCallable(self._model, spec)
        setattr(self, element_type, callable_object)
        return callable_object


class AddElementCallable:
    """Callable object behind every ``m.add.<category>.<type>`` endpoint."""

    def __init__(self, model: "SWMMModel", spec: EditableElementSpec) -> None:
        """Store the model/spec pair and expose help-friendly metadata."""

        self._model = model
        self._spec = spec
        self.__name__ = spec.element_type
        self.__signature__ = _add_signature(spec)
        self.__doc__ = _add_docstring(spec)

    def __call__(self, id: str, *args, **options):
        """Add one editable model element."""

        if len(args) > len(self._spec.positional_parameters):
            raise TypeError(f"m.add.{self._spec.path}() received too many positional arguments.")
        for parameter, value in zip(self._spec.positional_parameters, args):
            if parameter.name in options:
                raise TypeError(f"m.add.{self._spec.path}() received '{parameter.name}' twice.")
            options[parameter.name] = value
        return self._model.add_element(self._spec.category, self._spec.element_type, id, **options)


class RemoveElementCallable:
    """Callable object behind every ``m.remove.<category>.<type>`` endpoint."""

    __signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("ids", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("force", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False),
        ]
    )

    def __init__(self, model: "SWMMModel", spec: EditableElementSpec) -> None:
        """Store the model/spec pair and expose help-friendly metadata."""

        self._model = model
        self._spec = spec
        self.__name__ = spec.element_type
        self.__doc__ = _remove_docstring(spec)

    def __call__(self, ids, force: bool = False):
        """Remove one or more editable model elements."""

        return self._model.remove_element(self._spec.category, self._spec.element_type, ids, force=force)


def _add_signature(spec: EditableElementSpec) -> inspect.Signature:
    """Return the inspectable signature for one add callable."""

    parameters = [inspect.Parameter("id", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    parameters.extend(
        inspect.Parameter(parameter.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=parameter.default)
        for parameter in spec.positional_parameters
    )
    parameters.append(inspect.Parameter("options", inspect.Parameter.VAR_KEYWORD))
    return inspect.Signature(parameters=parameters)


def _format_names(names: tuple[str, ...]) -> str:
    """Render a concise human-readable parameter list."""

    return ", ".join(names) if names else "None."


def _add_docstring(spec: EditableElementSpec) -> str:
    """Build a useful public docstring for one add endpoint."""

    defaults = ", ".join(f"{key}={value!r}" for key, value in spec.defaults.items()) or "No automatic defaults."
    references = ", ".join(f"{key} -> {target}" for key, target in spec.references.items()) or "No external references."
    example = spec.example or f'm.add.{spec.path}("ID", ...)'
    return (
        f"{spec.purpose or f'Add a {spec.element_type} element.'}\n\n"
        "Required parameters\n"
        "-------------------\n"
        f"id, {_format_names(spec.required_parameters)}\n\n"
        "Optional parameters\n"
        "-------------------\n"
        f"{_format_names(spec.optional_parameters)}\n\n"
        "Defaults\n"
        "--------\n"
        f"{defaults}\n"
        + (f"Coordinate policy: {spec.coordinate_policy}.\n" if spec.coordinate_policy else "")
        + "\nValidation notes\n"
        "----------------\n"
        f"IDs must be unique. Reference checks: {references}\n\n"
        "Examples\n"
        "--------\n"
        f"{example}\n\n"
        "Returns\n"
        "-------\n"
        "str\n"
        "    The created object ID."
    )


def _remove_docstring(spec: EditableElementSpec) -> str:
    """Build a useful public docstring for one remove endpoint."""

    dependencies = ", ".join(spec.dependency_rules) or "No explicit dependency rules."
    example = f'm.remove.{spec.path}("ID")'
    return (
        f"Remove one or more {spec.element_type} elements.\n\n"
        "Required parameters\n"
        "-------------------\n"
        "ids\n"
        "    One ID string or a list of ID strings.\n\n"
        "Optional parameters\n"
        "-------------------\n"
        "force\n"
        "    If False, dependency checks block unsafe removal. If True, only conservative safe cascades are attempted.\n\n"
        "Defaults\n"
        "--------\n"
        "force=False\n\n"
        "Validation notes\n"
        "----------------\n"
        f"IDs must exist. Dependency checks: {dependencies}\n\n"
        "Examples\n"
        "--------\n"
        f"{example}\n\n"
        "Returns\n"
        "-------\n"
        "dict\n"
        "    Removal summary with ``removed``, ``warnings``, and ``dependencies_removed`` lists."
    )


class EditableElementService:
    """Per-model executor for registry-backed add/remove operations."""

    VALID_RAIN_FORMATS = {"INTENSITY", "VOLUME", "CUMULATIVE"}
    VALID_RAIN_SOURCES = {"TIMESERIES", "FILE"}
    VALID_OUTFALL_TYPES = {"FREE", "NORMAL", "FIXED", "TIDAL", "TIMESERIES"}
    VALID_PATTERN_TYPES = {"MONTHLY", "DAILY", "HOURLY", "WEEKEND"}
    VALID_PUMP_CURVE_TYPES = {"PUMP1", "PUMP2", "PUMP3", "PUMP4"}
    VALID_XSECTION_SHAPES = {
        "CIRCULAR",
        "FORCE_MAIN",
        "FILLED_CIRCULAR",
        "RECT_CLOSED",
        "RECT_OPEN",
        "TRAPEZOIDAL",
        "TRIANGULAR",
        "HORIZ_ELLIPSE",
        "VERT_ELLIPSE",
        "ARCH",
        "PARABOLIC",
        "POWER",
        "RECT_TRIANGULAR",
        "RECT_ROUND",
        "MOD_BASKET",
        "EGG",
        "HORSESHOE",
        "GOTHIC",
        "CATENARY",
        "SEMIELLIPTICAL",
        "BASKETHANDLE",
        "SEMICIRCULAR",
        "IRREGULAR",
        "CUSTOM",
    }

    def __init__(self, model: "SWMMModel", registry: EditableElementRegistry) -> None:
        """Bind one executor to one mutable model."""

        self.model = model
        self.registry = registry
        self._add_handlers: dict[tuple[str, str], Callable[[EditableElementSpec, str, dict[str, Any]], str]] = {
            ("node", "junction"): self._add_junction,
            ("node", "outfall"): self._add_outfall,
            ("link", "conduit"): self._add_conduit,
            ("hydrology", "rain_gage"): self._add_rain_gage,
            ("hydrology", "subcatchment"): self._add_subcatchment,
            ("curve", "pump"): self._add_pump_curve,
            ("time", "time_series"): self._add_time_series,
            ("time", "time_pattern"): self._add_time_pattern,
        }
        self._remove_handlers: dict[tuple[str, str], Callable[[EditableElementSpec, list[str], bool], dict[str, list[str]]]] = {
            ("node", "junction"): self._remove_junction,
            ("node", "outfall"): self._remove_outfall,
            ("link", "conduit"): self._remove_conduit,
            ("hydrology", "rain_gage"): self._remove_rain_gage,
            ("hydrology", "subcatchment"): self._remove_subcatchment,
            ("curve", "pump"): self._remove_curve,
            ("time", "time_series"): self._remove_time_series,
            ("time", "time_pattern"): self._remove_time_pattern,
        }
        for curve_type in ("control", "diversion", "rating", "shape", "storage", "tidal", "weir", "generic"):
            self._add_handlers[("curve", curve_type)] = self._add_curve
            self._remove_handlers[("curve", curve_type)] = self._remove_curve

    def add(self, category: str, element_type: str, id: str, **options) -> str:
        """Execute one add operation through the editable-object registry."""

        spec = self.registry.spec(category, element_type)
        if not spec.implemented:
            raise NotImplementedYetError(
                f"m.add.{spec.path}() is reserved but not fully implemented in swmmx 0.0.6."
            )
        self._validate_new_id(spec, id)
        handler = self._add_handlers[(category, element_type)]
        created_id = handler(spec, id, dict(options))
        self.model._dirty = True
        self.model._invalidate_results()
        return created_id

    def remove(self, category: str, element_type: str, ids, *, force: bool = False) -> dict[str, list[str]]:
        """Execute one remove operation through the editable-object registry."""

        spec = self.registry.spec(category, element_type)
        if not spec.implemented:
            raise NotImplementedYetError(
                f"m.remove.{spec.path}() is reserved but not fully implemented in swmmx 0.0.6."
            )
        selected_ids = self._normalize_remove_ids(spec, ids)
        handler = self._remove_handlers[(category, element_type)]
        summary = handler(spec, selected_ids, bool(force))
        self.model._dirty = True
        self.model._invalidate_results()
        return summary

    # ---------- shared validation and geometry helpers ----------

    def _validate_new_id(self, spec: EditableElementSpec, id: str) -> None:
        """Validate a non-empty unique ID inside the requested ID scope."""

        if not isinstance(id, str) or not id.strip():
            raise InvalidParameterError(f"{spec.element_type} ID must be a non-empty string.")
        if id in self._ids_for_scope(spec.id_scope):
            raise DuplicateIDError(f"{spec.element_type} ID '{id}' already exists.")

    def _normalize_remove_ids(self, spec: EditableElementSpec, ids) -> list[str]:
        """Normalize remove ID input and validate existence."""

        if isinstance(ids, str):
            selected = [ids]
        elif isinstance(ids, (list, tuple)) and all(isinstance(value, str) for value in ids):
            selected = list(ids)
        else:
            raise InvalidParameterError("'ids' must be one string or a list of strings.")
        known = set(self._ids_for_scope(spec.id_scope))
        missing = [value for value in selected if value not in known]
        if missing:
            joined = ", ".join(missing)
            raise UnknownIDError(f"Unknown {spec.element_type} ID(s): {joined}.")
        return selected

    def _ids_for_scope(self, scope: str) -> list[str]:
        """Return unique IDs for one logical object scope."""

        section_map = {
            "node": ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE"),
            "link": ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"),
            "rain_gage": ("RAINGAGES",),
            "subcatchment": ("SUBCATCHMENTS",),
            "curve": ("CURVES",),
            "time_series": ("TIMESERIES",),
            "time_pattern": ("PATTERNS",),
            "aquifer": ("AQUIFERS",),
            "snow_pack": ("SNOWPACKS",),
            "lid_control": ("LID_CONTROLS",),
            "unit_hydrograph": ("HYDROGRAPHS",),
            "street": ("STREETS",),
            "inlet": ("INLETS",),
            "transect": ("TRANSECTS",),
            "control": ("CONTROLS",),
            "pollutant": ("POLLUTANTS",),
            "land_use": ("LANDUSES",),
        }
        ids: list[str] = []
        for section in section_map.get(scope, ()):
            ids.extend(self.model._document.section_ids(section))
        return list(dict.fromkeys(ids))

    def _require(self, spec: EditableElementSpec, options: dict[str, Any], name: str) -> Any:
        """Return a required option or raise a clear package error."""

        if name not in options or options[name] is None:
            raise MissingRequiredParameterError(
                f"Cannot add {spec.element_type}: required parameter '{name}' is missing."
            )
        return options[name]

    def _number(self, spec: EditableElementSpec, name: str, value: Any, *, non_negative: bool = False) -> float:
        """Validate one numeric option and return it as ``float``."""

        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must be numeric."
            ) from exc
        if non_negative and number < 0:
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must be non-negative."
            )
        return number

    def _coordinate_value(self, spec: EditableElementSpec, name: str, value: Any) -> float:
        """Validate one numeric coordinate."""

        return self._number(spec, name, value)

    def _assert_reference(self, spec: EditableElementSpec, id: str, name: str, value: Any, target: str) -> None:
        """Validate that a named referenced ID already exists."""

        if value in {None, "", "*"}:
            return
        if target == "node_or_subcatchment":
            known = set(self._ids_for_scope("node")) | set(self._ids_for_scope("subcatchment"))
        else:
            known = set(self._ids_for_scope(target))
        if str(value) not in known:
            raise InvalidReferenceError(
                f"Cannot add {spec.element_type} '{id}': {name} '{value}' does not exist."
            )

    def _all_mapped_points(self) -> list[tuple[float, float]]:
        """Return coordinates from all ordinary map sections."""

        points: list[tuple[float, float]] = []
        for section_name in ("COORDINATES", "SYMBOLS", "POLYGONS", "VERTICES"):
            for row in self.model._document.rows(section_name):
                if len(row) >= 3:
                    try:
                        points.append((float(row[1]), float(row[2])))
                    except ValueError:
                        continue
        return points

    def _node_points(self) -> list[tuple[float, float]]:
        """Return existing node map coordinates."""

        points: list[tuple[float, float]] = []
        for row in self.model._document.rows("COORDINATES"):
            if len(row) >= 3:
                try:
                    points.append((float(row[1]), float(row[2])))
                except ValueError:
                    continue
        return points

    def _node_coordinate(self, node_id: str) -> tuple[float, float] | None:
        """Return one node coordinate if present."""

        for row in self.model._document.rows("COORDINATES"):
            if len(row) >= 3 and row[0] == node_id:
                return float(row[1]), float(row[2])
        return None

    def _default_coordinate(self, spec: EditableElementSpec, options: dict[str, Any]) -> tuple[float, float]:
        """Apply one registry-declared coordinate default policy."""

        x_value = options.pop("x", None)
        y_value = options.pop("y", None)
        if x_value is not None or y_value is not None:
            if x_value is None or y_value is None:
                raise InvalidParameterError(
                    f"Cannot add {spec.element_type}: both 'x' and 'y' must be provided together."
                )
            return self._coordinate_value(spec, "x", x_value), self._coordinate_value(spec, "y", y_value)

        if spec.coordinate_policy == "node_next":
            points = self._node_points()
            spacing = self._number(spec, "spacing", options.pop("spacing", 100.0), non_negative=True)
            return (max(point[0] for point in points) + spacing, max(point[1] for point in points)) if points else (0.0, 0.0)

        points = self._all_mapped_points()
        if not points:
            return 0.0, 0.0
        if spec.coordinate_policy == "mapped_max":
            return max(point[0] for point in points), max(point[1] for point in points)
        if spec.coordinate_policy == "mapped_min":
            return min(point[0] for point in points), min(point[1] for point in points)
        return 0.0, 0.0

    def _ensure_no_unknown_options(self, spec: EditableElementSpec, options: dict[str, Any]) -> None:
        """Reject misspelled add options after a handler consumes expected keys."""

        if options:
            names = ", ".join(sorted(options))
            raise InvalidParameterError(f"Cannot add {spec.element_type}: unknown option(s): {names}.")

    def _yes_no(self, value: Any) -> str:
        """Render booleans and already-valid strings as SWMM YES/NO tokens."""

        if isinstance(value, bool):
            return "YES" if value else "NO"
        text = str(value).upper()
        if text not in {"YES", "NO"}:
            raise InvalidParameterError("Boolean SWMM options must be bool, 'YES', or 'NO'.")
        return text

    # ---------- add handlers ----------

    def _add_junction(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a junction and its defaulted coordinate row."""

        values = {**spec.defaults, **options}
        x, y = self._default_coordinate(spec, values)
        row = [
            id,
            self._number(spec, "invert_elevation", values.pop("invert_elevation")),
            self._number(spec, "max_depth", values.pop("max_depth"), non_negative=True),
            self._number(spec, "initial_depth", values.pop("initial_depth"), non_negative=True),
            self._number(spec, "surcharge_depth", values.pop("surcharge_depth"), non_negative=True),
            self._number(spec, "ponded_area", values.pop("ponded_area"), non_negative=True),
        ]
        self._ensure_no_unknown_options(spec, values)
        self.model._document.append_row("JUNCTIONS", row)
        self.model._document.append_row("COORDINATES", [id, x, y])
        return id

    def _add_outfall(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add an outfall and its defaulted coordinate row."""

        values = {**spec.defaults, **options}
        x, y = self._default_coordinate(spec, values)
        outfall_type = str(values.pop("type")).upper()
        if outfall_type not in self.VALID_OUTFALL_TYPES:
            raise InvalidParameterError(
                f"Cannot add outfall '{id}': type '{outfall_type}' is invalid."
            )
        stage_value = None
        if outfall_type == "FIXED":
            stage_value = self._require(spec, values, "fixed_stage")
        elif outfall_type == "TIDAL":
            stage_value = self._require(spec, values, "tidal_curve")
            self._assert_reference(spec, id, "tidal_curve", stage_value, "curve")
        elif outfall_type == "TIMESERIES":
            stage_value = self._require(spec, values, "time_series")
            self._assert_reference(spec, id, "time_series", stage_value, "time_series")
        gated = self._yes_no(values.pop("tide_gate", "NO"))
        route_to = values.pop("route_to", None)
        row = [
            id,
            self._number(spec, "invert_elevation", values.pop("invert_elevation")),
            outfall_type,
            stage_value,
            gated,
            route_to,
        ]
        # Consume unused alternate stage keys when not relevant; rejecting them
        # would make harmless explicit ``None`` values unpleasant to pass.
        values.pop("fixed_stage", None)
        values.pop("tidal_curve", None)
        values.pop("time_series", None)
        self._ensure_no_unknown_options(spec, values)
        self.model._document.append_row("OUTFALLS", row)
        self.model._document.append_row("COORDINATES", [id, x, y])
        return id

    def _add_conduit(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a conduit, x-section, optional losses, and optional vertices."""

        values = {**spec.defaults, **options}
        from_node = self._require(spec, values, "from_node")
        to_node = self._require(spec, values, "to_node")
        self._assert_reference(spec, id, "from_node", from_node, "node")
        self._assert_reference(spec, id, "to_node", to_node, "node")
        values.pop("from_node", None)
        values.pop("to_node", None)

        length = values.pop("length", None)
        if length is None:
            first = self._node_coordinate(str(from_node))
            second = self._node_coordinate(str(to_node))
            length = hypot(second[0] - first[0], second[1] - first[1]) if first and second else 1.0
        length = self._number(spec, "length", length, non_negative=True)
        roughness = self._number(spec, "roughness", values.pop("roughness"), non_negative=True)
        shape = str(values.pop("shape")).upper()
        if shape not in self.VALID_XSECTION_SHAPES:
            raise InvalidParameterError(f"Cannot add conduit '{id}': shape '{shape}' is invalid.")

        geometry = values.pop("geometry", None)
        if geometry is not None:
            geometry_values = self._normalize_numeric_vector(spec, "geometry", geometry, allowed_lengths={1, 2, 3, 4})
        else:
            geometry_values = [
                values.pop("geometry_1", values.pop("diameter", spec.defaults["diameter"])),
                values.pop("geometry_2", 0.0),
                values.pop("geometry_3", 0.0),
                values.pop("geometry_4", 0.0),
            ]
        geometry_values = [self._number(spec, "geometry", value, non_negative=True) for value in geometry_values]
        while len(geometry_values) < 4:
            geometry_values.append(0.0)

        conduit_row = [
            id,
            from_node,
            to_node,
            length,
            roughness,
            self._number(spec, "inlet_offset", values.pop("inlet_offset"), non_negative=True),
            self._number(spec, "outlet_offset", values.pop("outlet_offset"), non_negative=True),
            self._number(spec, "initial_flow", values.pop("initial_flow")),
            self._number(spec, "maximum_flow", values.pop("maximum_flow"), non_negative=True),
        ]
        xsection_row = [
            id,
            shape,
            *geometry_values,
            int(self._number(spec, "barrels", values.pop("barrels"), non_negative=True)),
            values.pop("culvert_code", None),
        ]
        entry_loss = values.pop("entry_loss", None)
        exit_loss = values.pop("exit_loss", None)
        average_loss = values.pop("average_loss", None)
        flap_gate = values.pop("flap_gate", None)
        seepage_rate = values.pop("seepage_rate", None)
        vertices = values.pop("vertices", None)
        self._ensure_no_unknown_options(spec, values)

        self.model._document.append_row("CONDUITS", conduit_row)
        self.model._document.append_row("XSECTIONS", xsection_row)
        if any(value is not None for value in (entry_loss, exit_loss, average_loss, flap_gate, seepage_rate)):
            self.model._document.append_row(
                "LOSSES",
                [
                    id,
                    self._number(spec, "entry_loss", entry_loss or 0.0, non_negative=True),
                    self._number(spec, "exit_loss", exit_loss or 0.0, non_negative=True),
                    self._number(spec, "average_loss", average_loss or 0.0, non_negative=True),
                    self._yes_no(flap_gate or "NO"),
                    self._number(spec, "seepage_rate", seepage_rate or 0.0, non_negative=True),
                ],
            )
        if vertices is not None:
            for x, y in self._normalize_points(spec, "vertices", vertices):
                self.model._document.append_row("VERTICES", [id, x, y])
        return id

    def _add_rain_gage(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a rain gage and its symbol coordinate."""

        values = {**spec.defaults, **options}
        x, y = self._default_coordinate(spec, values)
        rain_format = str(self._require(spec, values, "format")).upper()
        source_type = str(self._require(spec, values, "source_type")).upper()
        interval = self._require(spec, values, "interval")
        if rain_format not in self.VALID_RAIN_FORMATS:
            raise InvalidParameterError(f"Cannot add rain_gage '{id}': format '{rain_format}' is invalid.")
        if source_type not in self.VALID_RAIN_SOURCES:
            raise InvalidParameterError(f"Cannot add rain_gage '{id}': source_type '{source_type}' is invalid.")
        scf = self._number(spec, "snow_catch_factor", values.pop("snow_catch_factor"), non_negative=True)

        row = [id, rain_format, interval, scf, source_type]
        if source_type == "TIMESERIES":
            time_series = self._require(spec, values, "time_series")
            self._assert_reference(spec, id, "time_series", time_series, "time_series")
            row.append(time_series)
        else:
            filename = self._require(spec, values, "filename")
            row.extend([filename, values.pop("station", None), values.pop("units", None)])
        values.pop("format", None)
        values.pop("interval", None)
        values.pop("source_type", None)
        values.pop("time_series", None)
        values.pop("filename", None)
        self._ensure_no_unknown_options(spec, values)
        self.model._document.append_row("RAINGAGES", row)
        self.model._document.append_row("SYMBOLS", [id, x, y])
        return id

    def _add_subcatchment(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add subcatchment, subarea, infiltration, and display geometry rows."""

        values = {**spec.defaults, **options}
        x, y = self._default_coordinate(spec, values)
        rain_gage = self._require(spec, values, "rain_gage")
        outlet = self._require(spec, values, "outlet")
        self._assert_reference(spec, id, "rain_gage", rain_gage, "rain_gage")
        self._assert_reference(spec, id, "outlet", outlet, "node_or_subcatchment")
        values.pop("rain_gage", None)
        values.pop("outlet", None)
        snow_pack = values.pop("snow_pack", None)
        if snow_pack not in {None, ""}:
            self._assert_reference(spec, id, "snow_pack", snow_pack, "snow_pack")

        subcatchment_row = [
            id,
            rain_gage,
            outlet,
            self._number(spec, "area", values.pop("area"), non_negative=True),
            self._number(spec, "impervious_percent", values.pop("impervious_percent"), non_negative=True),
            self._number(spec, "width", values.pop("width"), non_negative=True),
            self._number(spec, "slope", values.pop("slope"), non_negative=True),
            self._number(spec, "curb_length", values.pop("curb_length"), non_negative=True),
            snow_pack,
        ]
        subarea_row = [
            id,
            self._number(spec, "n_impervious", values.pop("n_impervious"), non_negative=True),
            self._number(spec, "n_pervious", values.pop("n_pervious"), non_negative=True),
            self._number(spec, "depression_storage_impervious", values.pop("depression_storage_impervious"), non_negative=True),
            self._number(spec, "depression_storage_pervious", values.pop("depression_storage_pervious"), non_negative=True),
            self._number(spec, "zero_depression_storage_impervious_percent", values.pop("zero_depression_storage_impervious_percent"), non_negative=True),
            values.pop("subarea_routing"),
            values.pop("percent_routed", None),
        ]
        infiltration_row = self._subcatchment_infiltration_row(spec, id, values)
        polygon = values.pop("polygon", None)
        self._ensure_no_unknown_options(spec, values)

        self.model._document.append_row("SUBCATCHMENTS", subcatchment_row)
        self.model._document.append_row("SUBAREAS", subarea_row)
        self.model._document.append_row("INFILTRATION", infiltration_row)
        points = self._normalize_points(spec, "polygon", polygon) if polygon is not None else [
            (x - 1.0, y - 1.0),
            (x + 1.0, y - 1.0),
            (x + 1.0, y + 1.0),
            (x - 1.0, y + 1.0),
        ]
        for px, py in points:
            self.model._document.append_row("POLYGONS", [id, px, py])
        return id

    def _subcatchment_infiltration_row(self, spec: EditableElementSpec, id: str, values: dict[str, Any]) -> list[Any]:
        """Build infiltration fields appropriate to the model option."""

        infiltration = str(self.model._document.get_option("INFILTRATION", "HORTON")).upper()
        if "GREEN" in infiltration:
            return [
                id,
                self._number(spec, "suction_head", values.pop("suction_head", 0.0), non_negative=True),
                self._number(spec, "hydraulic_conductivity", values.pop("hydraulic_conductivity", 0.0), non_negative=True),
                self._number(spec, "initial_moisture_deficit", values.pop("initial_moisture_deficit", 0.0), non_negative=True),
            ]
        if "CURVE" in infiltration:
            return [
                id,
                self._number(spec, "curve_number", values.pop("curve_number", 0.0), non_negative=True),
                self._number(spec, "conductivity", values.pop("conductivity", 0.0), non_negative=True),
                self._number(spec, "dry_time", values.pop("dry_time", 0.0), non_negative=True),
            ]
        return [
            id,
            self._number(spec, "maximum_rate", values.pop("maximum_rate", 0.0), non_negative=True),
            self._number(spec, "minimum_rate", values.pop("minimum_rate", 0.0), non_negative=True),
            self._number(spec, "decay", values.pop("decay", 0.0), non_negative=True),
            self._number(spec, "dry_time", values.pop("dry_time", 0.0), non_negative=True),
            self._number(spec, "maximum_volume", values.pop("maximum_volume", 0.0), non_negative=True),
        ]

    def _add_pump_curve(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a pump curve using ordinary SWMM curve rows."""

        values = {**spec.defaults, **options}
        points = self._normalize_points(spec, "points", self._require(spec, values, "points"))
        curve_type = str(values.pop("curve_type")).upper()
        if curve_type not in self.VALID_PUMP_CURVE_TYPES:
            raise InvalidParameterError(
                f"Cannot add pump curve '{id}': curve_type '{curve_type}' is invalid."
            )
        values.pop("points", None)
        self._ensure_no_unknown_options(spec, values)
        for index, (x, y) in enumerate(points):
            self.model._document.append_row("CURVES", [id, curve_type if index == 0 else None, x, y])
        return id

    def _add_curve(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add an ordinary explicitly-typed non-pump curve."""

        values = dict(options)
        points = self._normalize_points(spec, "points", self._require(spec, values, "points"))
        public_type_map = {
            "control": "CONTROL",
            "diversion": "DIVERSION",
            "rating": "RATING",
            "shape": "SHAPE",
            "storage": "STORAGE",
            "tidal": "TIDAL",
            "weir": "WEIR",
        }
        curve_type = str(values.pop("type", public_type_map.get(spec.element_type, ""))).upper()
        if not curve_type:
            raise MissingRequiredParameterError(
                "Cannot add generic curve: required parameter 'type' is missing."
            )
        values.pop("points", None)
        self._ensure_no_unknown_options(spec, values)
        for index, (x, y) in enumerate(points):
            self.model._document.append_row("CURVES", [id, curve_type if index == 0 else None, x, y])
        return id

    def _add_time_series(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a time series from structured data or an external file."""

        values = dict(options)
        data = values.pop("data", None)
        filename = values.pop("filename", None)
        description = values.pop("description", None)
        datetimes = values.pop("datetime", None)
        raw_values = values.pop("values", None)
        self._ensure_no_unknown_options(spec, values)

        if filename is not None:
            self.model._document.append_row("TIMESERIES", [id, "FILE", filename])
            return id

        pairs = self._normalize_time_series_data(spec, data, datetimes, raw_values)
        if not pairs:
            raise MissingRequiredParameterError(
                f"Cannot add time_series: provide 'data', 'filename', or both 'datetime' and 'values'."
            )
        for timestamp, value in pairs:
            self.model._document.append_row(
                "TIMESERIES",
                [id, timestamp.strftime("%m/%d/%Y"), timestamp.strftime("%H:%M"), value],
            )
        if description:
            # Comments are valid inside [TIMESERIES] and preserve the human note
            # without changing simulation semantics.
            self.model._document.ensure_section("TIMESERIES").lines.append(f"; {id}: {description}")
        return id

    def _add_time_pattern(self, spec: EditableElementSpec, id: str, options: dict[str, Any]) -> str:
        """Add a time pattern with numeric multipliers."""

        values = dict(options)
        pattern_type = str(self._require(spec, values, "type")).upper()
        if pattern_type not in self.VALID_PATTERN_TYPES:
            raise InvalidParameterError(
                f"Cannot add time_pattern '{id}': type '{pattern_type}' is invalid."
            )
        multipliers = self._normalize_numeric_vector(spec, "multipliers", self._require(spec, values, "multipliers"))
        values.pop("type", None)
        values.pop("multipliers", None)
        self._ensure_no_unknown_options(spec, values)
        self.model._document.append_row("PATTERNS", [id, pattern_type, *multipliers])
        return id

    # ---------- remove handlers ----------

    def _remove_junction(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove junctions, optionally cascading dependent conduits."""

        return self._remove_node_like(spec, ids, force)

    def _remove_outfall(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove outfalls, optionally cascading dependent conduits."""

        return self._remove_node_like(spec, ids, force)

    def _remove_node_like(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove node rows while guarding node references."""

        link_dependencies = self._link_dependencies(ids)
        subcatchment_dependencies = self._subcatchment_outlet_dependencies(ids)
        if (link_dependencies or subcatchment_dependencies) and not force:
            if link_dependencies:
                link_type, link_id, node_id = link_dependencies[0]
                raise DependencyError(
                    f"Cannot remove {spec.element_type} '{node_id}' because it is referenced by {link_type} '{link_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            subcatchment_id, node_id = subcatchment_dependencies[0]
            raise DependencyError(
                f"Cannot remove {spec.element_type} '{node_id}' because it is referenced by subcatchment '{subcatchment_id}'. "
                "Use force=True only if you want to remove dependent objects or references."
            )
        if subcatchment_dependencies and force:
            raise NotImplementedYetError(
                "Automatic removal of subcatchments that outlet to a removed node is not implemented yet."
            )

        dependency_ids: list[str] = []
        if link_dependencies and force:
            unsupported = [item for item in link_dependencies if item[0] != "conduit"]
            if unsupported:
                raise NotImplementedYetError(
                    "Automatic cascading removal is currently implemented only for dependent conduits."
                )
            dependency_ids = list(dict.fromkeys(item[1] for item in link_dependencies))
            self._remove_conduit_rows(dependency_ids)

        section = "JUNCTIONS" if spec.element_type == "junction" else "OUTFALLS"
        self.model._document.remove_rows(section, ids)
        self.model._document.remove_rows("COORDINATES", ids)
        return {
            "removed": ids,
            "warnings": [],
            "dependencies_removed": [f"conduit:{value}" for value in dependency_ids],
        }

    def _remove_conduit(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove conduits while protecting control references."""

        control_refs = self._control_dependencies(ids)
        if control_refs and not force:
            conduit_id = control_refs[0]
            raise DependencyError(
                f"Cannot remove conduit '{conduit_id}' because it is referenced by control text. "
                "Use force=True only if you want to remove dependent objects or references."
            )
        if control_refs and force:
            raise NotImplementedYetError(
                "Automatic control-rule rewriting during conduit removal is not implemented yet."
            )
        self._remove_conduit_rows(ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    def _remove_conduit_rows(self, ids: list[str]) -> None:
        """Remove ordinary conduit-associated rows across all relevant sections."""

        for section in ("CONDUITS", "XSECTIONS", "LOSSES", "VERTICES"):
            self.model._document.remove_rows(section, ids)

    def _remove_rain_gage(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove rain gages when no subcatchments still use them."""

        dependencies = [
            (row[0], row[1])
            for row in self.model._document.rows("SUBCATCHMENTS")
            if len(row) >= 2 and row[1] in ids
        ]
        if dependencies:
            subcatchment_id, rain_gage_id = dependencies[0]
            if not force:
                raise DependencyError(
                    f"Cannot remove rain_gage '{rain_gage_id}' because it is referenced by subcatchment '{subcatchment_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            raise NotImplementedYetError(
                "Automatic removal of subcatchments that use a removed rain gage is not implemented yet."
            )
        self.model._document.remove_rows("RAINGAGES", ids)
        self.model._document.remove_rows("SYMBOLS", ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    def _remove_subcatchment(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove subcatchments and their keyed support rows."""

        dependencies = [
            (row[0], row[2])
            for row in self.model._document.rows("SUBCATCHMENTS")
            if len(row) >= 3 and row[0] not in ids and row[2] in ids
        ]
        if dependencies:
            child_id, parent_id = dependencies[0]
            if not force:
                raise DependencyError(
                    f"Cannot remove subcatchment '{parent_id}' because it is referenced by subcatchment '{child_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            raise NotImplementedYetError(
                "Automatic removal of subcatchments that outlet to another removed subcatchment is not implemented yet."
            )
        for section in ("SUBCATCHMENTS", "SUBAREAS", "INFILTRATION", "POLYGONS", "COVERAGES", "LOADINGS", "LID_USAGE", "GROUNDWATER"):
            self.model._document.remove_rows(section, ids)
        self.model._document.remove_matching_rows("TAGS", lambda row: len(row) >= 2 and row[1] in ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    def _remove_curve(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove curves only when no objects still refer to them."""

        dependencies = self._curve_dependencies(ids)
        if dependencies:
            section_name, object_id, curve_id = dependencies[0]
            if not force:
                public_curve_name = "curve" if spec.element_type == "generic" else f"{spec.element_type} curve"
                raise DependencyError(
                    f"Cannot remove {public_curve_name} '{curve_id}' because it is referenced by {section_name.lower()} '{object_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            raise NotImplementedYetError(
                "Automatic rewriting of curve references during curve removal is not implemented yet."
            )
        self.model._document.remove_rows("CURVES", ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    def _remove_time_series(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove time series only when no dependent records use them."""

        dependencies = self._time_series_dependencies(ids)
        if dependencies:
            source, object_id, series_id = dependencies[0]
            if not force:
                raise DependencyError(
                    f"Cannot remove time_series '{series_id}' because it is referenced by {source} '{object_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            raise NotImplementedYetError(
                "Automatic rewriting of time-series references is not implemented yet."
            )
        self.model._document.remove_rows("TIMESERIES", ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    def _remove_time_pattern(self, spec: EditableElementSpec, ids: list[str], force: bool) -> dict[str, list[str]]:
        """Remove time patterns only when no known dependent records use them."""

        dependencies = self._pattern_dependencies(ids)
        if dependencies:
            source, object_id, pattern_id = dependencies[0]
            if not force:
                raise DependencyError(
                    f"Cannot remove time_pattern '{pattern_id}' because it is referenced by {source} '{object_id}'. "
                    "Use force=True only if you want to remove dependent objects or references."
                )
            raise NotImplementedYetError(
                "Automatic rewriting of time-pattern references is not implemented yet."
            )
        self.model._document.remove_rows("PATTERNS", ids)
        return {"removed": ids, "warnings": [], "dependencies_removed": []}

    # ---------- dependency scanners ----------

    def _link_dependencies(self, node_ids: list[str]) -> list[tuple[str, str, str]]:
        """Return ``(link_type, link_id, node_id)`` tuples referencing nodes."""

        link_sections = {
            "CONDUITS": "conduit",
            "PUMPS": "pump",
            "ORIFICES": "orifice",
            "WEIRS": "weir",
            "OUTLETS": "outlet",
        }
        dependencies: list[tuple[str, str, str]] = []
        for section, link_type in link_sections.items():
            for row in self.model._document.rows(section):
                if len(row) >= 3:
                    for node_id in node_ids:
                        if row[1] == node_id or row[2] == node_id:
                            dependencies.append((link_type, row[0], node_id))
        return dependencies

    def _subcatchment_outlet_dependencies(self, node_ids: list[str]) -> list[tuple[str, str]]:
        """Return subcatchment IDs that use selected nodes as outlets."""

        return [
            (row[0], row[2])
            for row in self.model._document.rows("SUBCATCHMENTS")
            if len(row) >= 3 and row[2] in node_ids
        ]

    def _control_dependencies(self, link_ids: list[str]) -> list[str]:
        """Return conduit IDs mentioned by control-rule text."""

        lines = self.model._document.section("CONTROLS").lines if self.model._document.section("CONTROLS") else []
        return [link_id for link_id in link_ids if any(link_id in line.split() for line in lines)]

    def _curve_dependencies(self, curve_ids: list[str]) -> list[tuple[str, str, str]]:
        """Return known object rows that reference selected curves."""

        dependencies: list[tuple[str, str, str]] = []
        for row in self.model._document.rows("PUMPS"):
            if len(row) >= 4 and row[3] in curve_ids:
                dependencies.append(("PUMPS", row[0], row[3]))
        for row in self.model._document.rows("OUTLETS"):
            if len(row) >= 5 and row[4] in curve_ids:
                dependencies.append(("OUTLETS", row[0], row[4]))
        for row in self.model._document.rows("STORAGE"):
            if len(row) >= 5 and row[4] in curve_ids:
                dependencies.append(("STORAGE", row[0], row[4]))
        return dependencies

    def _time_series_dependencies(self, series_ids: list[str]) -> list[tuple[str, str, str]]:
        """Return known object rows that reference selected time series."""

        dependencies: list[tuple[str, str, str]] = []
        for row in self.model._document.rows("RAINGAGES"):
            if len(row) >= 6 and row[4].upper() == "TIMESERIES" and row[5] in series_ids:
                dependencies.append(("rain_gage", row[0], row[5]))
        for row in self.model._document.rows("OUTFALLS"):
            if len(row) >= 4 and row[2].upper() == "TIMESERIES" and row[3] in series_ids:
                dependencies.append(("outfall", row[0], row[3]))
        return dependencies

    def _pattern_dependencies(self, pattern_ids: list[str]) -> list[tuple[str, str, str]]:
        """Return known object rows that reference selected time patterns."""

        dependencies: list[tuple[str, str, str]] = []
        for row in self.model._document.rows("DWF"):
            for token in row[3:]:
                if token in pattern_ids:
                    dependencies.append(("dry_weather_flow", row[0], token))
        return dependencies

    # ---------- shape normalizers ----------

    def _normalize_numeric_vector(
        self,
        spec: EditableElementSpec,
        name: str,
        values: Any,
        *,
        allowed_lengths: set[int] | None = None,
    ) -> list[float]:
        """Normalize one numeric vector-like input."""

        if isinstance(values, pd.Series):
            raw = values.tolist()
        elif isinstance(values, np.ndarray):
            if values.ndim != 1:
                raise InvalidParameterError(
                    f"Cannot add {spec.element_type}: '{name}' must be one-dimensional."
                )
            raw = values.tolist()
        elif isinstance(values, (list, tuple)):
            raw = list(values)
        else:
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must be a one-dimensional sequence."
            )
        if allowed_lengths is not None and len(raw) not in allowed_lengths:
            allowed = ", ".join(str(value) for value in sorted(allowed_lengths))
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must contain {allowed} values."
            )
        return [self._number(spec, name, value) for value in raw]

    def _normalize_points(self, spec: EditableElementSpec, name: str, points: Any) -> list[tuple[float, float]]:
        """Normalize list/DataFrame/array point input into numeric pairs."""

        if isinstance(points, pd.DataFrame):
            if {"x", "y"}.issubset(points.columns):
                raw_pairs = list(zip(points["x"], points["y"]))
            elif points.shape[1] == 2:
                raw_pairs = list(points.itertuples(index=False, name=None))
            else:
                raise InvalidParameterError(
                    f"Cannot add {spec.element_type}: '{name}' DataFrame must have x/y columns."
                )
        elif isinstance(points, np.ndarray):
            if points.ndim != 2 or points.shape[1] != 2:
                raise InvalidParameterError(
                    f"Cannot add {spec.element_type}: '{name}' array must have shape (n, 2)."
                )
            raw_pairs = points.tolist()
        elif isinstance(points, (list, tuple)):
            raw_pairs = list(points)
        else:
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must be point pairs, a DataFrame, or an (n, 2) array."
            )
        if not raw_pairs:
            raise InvalidParameterError(
                f"Cannot add {spec.element_type}: '{name}' must contain at least one point."
            )
        normalized: list[tuple[float, float]] = []
        for pair in raw_pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise InvalidParameterError(
                    f"Cannot add {spec.element_type}: '{name}' points must be two-value pairs."
                )
            normalized.append(
                (
                    self._number(spec, f"{name}.x", pair[0]),
                    self._number(spec, f"{name}.y", pair[1]),
                )
            )
        return normalized

    def _normalize_time_series_data(
        self,
        spec: EditableElementSpec,
        data: Any,
        datetimes: Any,
        values: Any,
    ) -> list[tuple[pd.Timestamp, float]]:
        """Normalize supported time-series inputs into timestamp/value pairs."""

        raw_pairs: list[tuple[Any, Any]]
        if data is not None:
            if isinstance(data, pd.Series):
                raw_pairs = list(zip(data.index, data.values))
            elif isinstance(data, pd.DataFrame):
                if {"datetime", "values"}.issubset(data.columns):
                    raw_pairs = list(zip(data["datetime"], data["values"]))
                elif data.shape[1] >= 2:
                    raw_pairs = list(data.iloc[:, :2].itertuples(index=False, name=None))
                else:
                    raise InvalidParameterError(
                        "Cannot add time_series: DataFrame data must provide datetime and value columns."
                    )
            elif isinstance(data, np.ndarray):
                if data.ndim != 2 or data.shape[1] != 2:
                    raise InvalidParameterError(
                        "Cannot add time_series: NumPy data must have shape (n, 2)."
                    )
                raw_pairs = [tuple(row) for row in data.tolist()]
            elif isinstance(data, (list, tuple)):
                raw_pairs = list(data)
            else:
                raise InvalidParameterError(
                    "Cannot add time_series: unsupported 'data' input type."
                )
        elif datetimes is not None and values is not None:
            raw_pairs = list(zip(datetimes, values))
        else:
            return []

        normalized: list[tuple[pd.Timestamp, float]] = []
        for pair in raw_pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise InvalidParameterError(
                    "Cannot add time_series: each data row must be a (datetime, value) pair."
                )
            try:
                timestamp = pd.Timestamp(pair[0])
            except Exception as exc:  # pandas raises several date parsing types
                raise InvalidParameterError(
                    f"Cannot add time_series: datetime value '{pair[0]}' is not parseable."
                ) from exc
            normalized.append((timestamp, self._number(spec, "value", pair[1])))
        return normalized
