"""Public parameter access for ``m.get`` and ``m.set``."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import keyword
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .errors import (
    DimensionMismatchError,
    InvalidReferenceError,
    ModelNotRunError,
    NotImplementedYetError,
    ObjectNotFoundError,
    ReadOnlyParameterError,
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
    ("junction", "id"): FieldSpec("JUNCTIONS", 0),
    ("junction", "invert_elevation"): FieldSpec("JUNCTIONS", 1),
    ("junction", "max_depth"): FieldSpec("JUNCTIONS", 2),
    ("junction", "initial_depth"): FieldSpec("JUNCTIONS", 3),
    ("junction", "surcharge_depth"): FieldSpec("JUNCTIONS", 4),
    ("junction", "ponded_area"): FieldSpec("JUNCTIONS", 5),
    ("outfall", "id"): FieldSpec("OUTFALLS", 0),
    ("outfall", "invert_elevation"): FieldSpec("OUTFALLS", 1),
}

OBJECT_SECTIONS = {
    "rain_gage": ("RAINGAGES",),
    "subcatchment": ("SUBCATCHMENTS",),
    "junction": ("JUNCTIONS",),
    "outfall": ("OUTFALLS",),
    "conduit": ("CONDUITS",),
    "node": ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE"),
    "link": ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS"),
    "time_series": ("TIMESERIES",),
    "time_pattern": ("PATTERNS",),
    "curve": ("CURVES",),
    "pollutant": ("POLLUTANTS",),
    "land_use": ("LANDUSES",),
    "aquifer": ("AQUIFERS",),
    "snow_pack": ("SNOWPACKS",),
    "lid_control": ("LID_CONTROLS",),
}

RESULT_OBJECT_KIND = {
    "subcatchment": "subcatchment",
    "node": "node",
    "link": "link",
    "conduit": "link",
    "junction": "node",
    "outfall": "node",
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

    def raw_category(self, main_api_name: str) -> str:
        """Return the original category behind one safe API name."""

        return self._categories_by_api_name[main_api_name]

    def has_category(self, main_api_name: str) -> bool:
        """Return whether one category exists in the routed registry."""

        return main_api_name in self._categories_by_api_name

    def has_subcategory(self, raw_main: str, sub_api_name: str) -> bool:
        """Return whether one subcategory exists in the routed registry."""

        return sub_api_name in self._subcategories_by_api_name.get(raw_main, {})


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

        catalog = self._model._parameter_catalog
        if not catalog.has_category(category_name):
            raise AttributeError(category_name)

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

        catalog = self._model._parameter_catalog
        if not catalog.has_subcategory(self._raw_main_category, subcategory_name):
            raise AttributeError(subcategory_name)
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
        self.__doc__ = (
            f"Get ``{spec.path}``.\n\n"
            "Parameters\n"
            "----------\n"
            "ids:\n"
            "    Optional object selector: ``None``, one object ID string, or a list of ID strings.\n"
            "format:\n"
            "    Optional output format: ``'np'`` (default) or ``'df'``.\n"
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
        joined = ", ".join(missing)
        raise ObjectNotFoundError(f"Unknown {category} object ID(s): {joined}.")
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
        values = list(value)
    else:
        values = [value] * selected_count

    if len(values) != selected_count:
        raise DimensionMismatchError(
            f"Received {len(values)} values for {selected_count} selected {category} objects."
        )
    return values
