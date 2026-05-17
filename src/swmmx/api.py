"""The user-facing ``swmm`` API and the internal model implementation."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from datetime import timedelta
from pathlib import Path
import tempfile
from typing import Literal

import numpy as np
import pandas as pd

from .counts import CountRoot
from .engine import EngineLoader
from .elements import EditableElementRegistry, EditableElementService, EditableRoot
from .export import ExportAccessor
from .errors import (
    FormatError,
    InvalidReferenceError,
    ModelNotRunError,
    NotImplementedYetError,
    ReadOnlyParameterError,
    SaveError,
)
from .inp import InpDocument
from .models import RunResult, SimulationStep, ValidationResult
from .parameters import (
    AccessRoot,
    CATEGORY_KEY_INDEXES,
    FieldSpec,
    INPUT_FIELDS,
    OBJECT_SECTIONS,
    OPTION_FIELDS,
    RESULT_OBJECT_KIND,
    ParameterCatalog,
    ParameterSpec,
    coerce_value,
    normalize_ids,
    normalize_values,
)
from .plotting import PlotProfileAccessor, PlotTimeseriesRoot, plot_layout as render_layout
from .results import OutputFile, OutputSummary
from .schema import SchemaRegistry
from .time import TimeAccessor, build_timestamps, parse_duration
from .validation import FLOW_UNITS_SI, FLOW_UNITS_US, validate_document


_MISSING = object()


class OptionView(MutableMapping[str, str]):
    """Mutable mapping that keeps `[OPTIONS]` edits synchronized with the file."""

    def __init__(self, model: "SWMMModel") -> None:
        """Bind the live option view to one model."""

        self._model = model

    def __getitem__(self, key: str) -> str:
        """Return one option value."""

        value = self._model._document.get_option(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: str) -> None:
        """Set one option and mark the model as having unsaved changes."""

        self._model._document.set_option(key, str(value))
        self._model._dirty = True
        self._model._invalidate_results()

    def __delitem__(self, key: str) -> None:
        """Delete one option and mark the model as having unsaved changes."""

        self._model._document.delete_option(key)
        self._model._dirty = True
        self._model._invalidate_results()

    def __iter__(self):
        """Iterate option names in file order."""

        return iter(self._model._document.options())

    def __len__(self) -> int:
        """Return the current number of parsed options."""

        return len(self._model._document.options())


class SWMMModel:
    """Internal model implementation behind the public ``swmm`` class."""

    def __init__(
        self,
        document: InpDocument,
        *,
        source_path: str | Path | None = None,
        engine_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> None:
        """Initialize one independently mutable model object."""

        # The preserving document is the model's source of truth for all current
        # input values; ``source_path`` is optional for models born in memory.
        self._document = document
        self._source_path = Path(source_path).resolve() if source_path is not None else None
        self._dirty = False

        # Engine loading stays lazy: constructors are cheap, and missing native
        # binaries are reported only when execution is actually requested.
        self._engine_loader = EngineLoader(custom_path=engine_path)

        # The public parameter catalog is loaded once per model so the routed
        # API can stay consistent with the package's declared parameter surface.
        self.schema = SchemaRegistry.load(explicit_path=schema_path)
        self._parameter_catalog = ParameterCatalog(self.schema)
        self._editable_registry = EditableElementRegistry()

        # Public namespace helpers are concrete objects so IDE completion shows
        # ``vector``, ``count``, ``vector_run``, and ``count_run`` immediately.
        self.time = TimeAccessor(self)
        self.options = OptionView(self)
        self.get = AccessRoot(self, mode="get")
        self.set = AccessRoot(self, mode="set")
        self.count = CountRoot(self)
        self._editable_service = EditableElementService(self, self._editable_registry)
        self.add = EditableRoot(self, mode="add", registry=self._editable_registry)
        self.remove = EditableRoot(self, mode="remove", registry=self._editable_registry)
        self.plot_timeseries = PlotTimeseriesRoot(self)
        self.plot_profile = PlotProfileAccessor(self)
        self.export = ExportAccessor(self)

        # Run state is intentionally separate from input state so clones and
        # edits cannot accidentally masquerade as fresh results.
        self._run_timestamps: list | None = None
        self._last_run_result: RunResult | None = None
        self._last_log = ""
        self._last_output_path: Path | None = None
        self._output_file_cache: OutputFile | None = None
        self._results_stale = False
        self._runtime_directory: tempfile.TemporaryDirectory[str] | None = None
        self._parameter_overrides: dict[tuple[str, str], dict[str, object]] = {}

    @property
    def path(self) -> Path | None:
        """Return the current saved input path, if the model has one."""

        return self._source_path

    @property
    def has_run(self) -> bool:
        """Return whether run-dependent results are currently available."""

        return self._run_timestamps is not None

    @property
    def modified(self) -> bool:
        """Return whether the in-memory model differs from its last save."""

        return self._dirty

    @property
    def results_stale(self) -> bool:
        """Return whether earlier simulation results were invalidated by edits."""

        return self._results_stale

    def _invalidate_results(self) -> None:
        """Clear run-dependent caches after any input mutation."""

        # Once input values change, previously computed outputs no longer belong
        # to the current model state and must not be served as fresh results.
        if self._run_timestamps is not None or self._last_run_result is not None or self._last_output_path is not None:
            self._results_stale = True
        self._run_timestamps = None
        self._last_run_result = None
        self._last_output_path = None
        self._output_file_cache = None

    def _expected_timestamps(self):
        """Build the report vector implied by current input options."""

        _start, report_start, end = self._document.datetimes()
        report_step_text = self._document.get_option("REPORT_STEP")
        if not report_step_text:
            raise ValueError("REPORT_STEP is required for time vectors.")
        report_step = parse_duration(report_step_text)
        return build_timestamps(report_start, end, report_step)

    def _run_timestamps_from_periods(self, periods: int):
        """Build run-time timestamps using the actual output-file period count."""

        _start, report_start, end = self._document.datetimes()
        report_step_text = self._document.get_option("REPORT_STEP")
        if not report_step_text:
            raise ValueError("REPORT_STEP is required for time vectors.")
        report_step = parse_duration(report_step_text)
        return build_timestamps(report_start, end, report_step, periods=periods)

    def _ids_for_category(self, category: str) -> list[str]:
        """Return object IDs for one routed category in deterministic order."""

        if category == "control_rule":
            return self._control_rule_ids()
        if category == "transect":
            return self._transect_ids()
        if category in {"lid_surface", "lid_pavement", "lid_soil", "lid_storage", "lid_drain"}:
            return self._lid_layer_ids(category)
        # Aggregate sections in SWMM's ordinary object-group order for composite
        # categories such as ``node`` and ``link``.
        sections = OBJECT_SECTIONS.get(category)
        if sections is None:
            raise NotImplementedYetError(
                f"Object indexing for '{category}' is not implemented yet."
            )
        ids: list[str] = []
        for section_name in sections:
            key_indexes = CATEGORY_KEY_INDEXES.get(category)
            if key_indexes:
                ids.extend(self._row_key(row, key_indexes) for row in self._document.rows(section_name))
            else:
                ids.extend(self._document.section_ids(section_name))
        return list(dict.fromkeys(ids))

    @staticmethod
    def _row_key(row: list[str], key_indexes: tuple[int, ...]) -> str:
        """Return one stable public row key from one or more columns."""

        return "|".join(row[index] if len(row) > index else "" for index in key_indexes)

    def _lid_layer_ids(self, category: str) -> list[str]:
        """Return LID control IDs that contain one requested layer row."""

        layer_names = {
            "lid_surface": "SURFACE",
            "lid_pavement": "PAVEMENT",
            "lid_soil": "SOIL",
            "lid_storage": "STORAGE",
            "lid_drain": "DRAIN",
        }
        wanted = layer_names[category]
        return [
            row[0]
            for row in self._document.rows("LID_CONTROLS")
            if len(row) >= 2 and row[1].upper() == wanted
        ]

    def _control_rule_ids(self) -> list[str]:
        """Return named control-rule IDs from preserved raw control lines."""

        section = self._document.section("CONTROLS")
        if section is None:
            return []
        ids: list[str] = []
        for line in section.lines:
            stripped = line.strip()
            if stripped.lower().startswith("rule "):
                ids.append(stripped.split(maxsplit=1)[1])
        return ids

    def _transect_ids(self) -> list[str]:
        """Return transect IDs from SWMM X1 rows when present."""

        ids: list[str] = []
        for row in self._document.rows("TRANSECTS"):
            if len(row) >= 2 and row[0].upper() == "X1":
                ids.append(row[1])
        return list(dict.fromkeys(ids))

    def _get_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return one public parameter in the requested shape."""

        if format not in {None, "np", "df"}:
            raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

        # Option groups describe one model-level scalar rather than object rows.
        if spec.main_category.startswith("option_"):
            value = self._get_option_parameter(spec)
            return self._format_scalar(value, spec, format=format)

        # An omitted ``ids`` argument means "give me every object of this
        # kind."  If a valid SWMM model simply has no objects of that kind,
        # the most useful answer is an empty result rather than an exception.
        # Explicit ID requests still continue through the ordinary validation
        # path below so typos such as ``ids="W1"`` remain visible to users.
        if (
            ids is None
            and spec.main_category in OBJECT_SECTIONS
            and spec.sub_category != "count"
            and not self._ids_for_category(spec.main_category)
        ):
            return self._format_empty_collection(spec, format=format)

        special = self._get_special_parameter(spec, ids=ids, format=format)
        if special is not _MISSING:
            return special

        if spec.source_kind == "result":
            return self._get_result_parameter(spec, ids=ids, format=format)
        if spec.source_kind == "derived":
            return self._get_derived_parameter(spec, ids=ids, format=format)
        if spec.source_kind == "mixed":
            raise NotImplementedYetError(
                f"'{spec.path}' has mixed source semantics and is not exposed yet."
            )

        # User/ref parameters that map directly to ordinary input columns can be
        # read from the preserving document without asking the native engine.
        field = INPUT_FIELDS.get(spec.key)
        if field is None:
            return self._get_overlay_parameter(spec, ids=ids, format=format)
        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        raw_values = self._get_field_values(field, selected_ids, spec.main_category)
        values = [coerce_value(raw_value, spec.type) for raw_value in raw_values]
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_parameter(self, spec: ParameterSpec, *, value, ids=None):
        """Write one public user/ref parameter."""

        if not spec.is_writable:
            noun = "variable" if spec.source_kind == "result" else "parameter"
            raise ReadOnlyParameterError(
                f"'{spec.path}' is a {spec.source_kind} {noun} and cannot be set."
            )
        if spec.main_category.startswith("option_"):
            if ids is not None:
                raise ValueError(f"'{spec.path}' is a model-level option and does not accept 'ids'.")
            self._set_option_parameter(spec, value)
            return None

        if self._set_special_parameter(spec, value=value, ids=ids):
            return None

        field = INPUT_FIELDS.get(spec.key)
        if field is None:
            self._set_overlay_parameter(spec, value=value, ids=ids)
            return None

        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        selected_values = normalize_values(value, len(selected_ids), spec.main_category)
        if spec.source_kind == "ref":
            self._validate_reference_values(field, selected_values, spec)

        self._set_field_values(field, selected_ids, selected_values, spec.main_category, spec)
        self._dirty = True
        self._invalidate_results()
        return None

    def _get_option_parameter(self, spec: ParameterSpec):
        """Return one model-level option from `[OPTIONS]`."""

        option_key = OPTION_FIELDS.get(spec.sub_category)
        if option_key is None:
            raise NotImplementedYetError(
                f"Option mapping for '{spec.path}' is not implemented yet."
            )
        value = self._document.get_option(option_key)
        if value is None:
            # SWMM input files are allowed to omit many options and let the
            # engine use its built-in defaults.  Returning ``None`` keeps the
            # getter usable for sparse but valid files instead of leaking a raw
            # ``KeyError`` from an implementation detail.
            return None
        return coerce_value(value, spec.type)

    def _set_option_parameter(self, spec: ParameterSpec, value) -> None:
        """Write one model-level option back into `[OPTIONS]`."""

        option_key = OPTION_FIELDS.get(spec.sub_category)
        if option_key is None:
            raise NotImplementedYetError(
                f"Option mapping for '{spec.path}' is not implemented yet."
            )
        self._document.set_option(option_key, self._render_set_value(value, spec))
        self._dirty = True
        self._invalidate_results()

    def _get_field_values(self, field: FieldSpec, selected_ids: list[str], category: str) -> list[str]:
        """Read ordinary or composite-key row fields in requested order."""

        key_indexes = field.key_indexes or CATEGORY_KEY_INDEXES.get(category)
        if not key_indexes:
            section_ids = set(self._document.section_ids(field.section))
            existing_ids = [object_id for object_id in selected_ids if object_id in section_ids]
            existing_values = dict(
                zip(
                    existing_ids,
                    self._document.get_field_values(
                        field.section,
                        field.field_index,
                        existing_ids,
                        id_index=field.id_index,
                    ),
                )
            )
            return [existing_values.get(object_id, "") for object_id in selected_ids]

        rows_by_key: dict[str, list[str]] = {}
        for row in self._document.rows(field.section):
            key = self._row_key(row, key_indexes)
            rows_by_key.setdefault(key, row)
        return [
            rows_by_key[object_id][field.field_index]
            if len(rows_by_key[object_id]) > field.field_index
            else ""
            for object_id in selected_ids
        ]

    def _set_field_values(
        self,
        field: FieldSpec,
        selected_ids: list[str],
        selected_values: list[object],
        category: str,
        spec: ParameterSpec,
    ) -> None:
        """Write ordinary or composite-key row fields back to the document."""

        rendered = {
            object_id: self._render_set_value(item, spec)
            for object_id, item in zip(selected_ids, selected_values)
        }
        key_indexes = field.key_indexes or CATEGORY_KEY_INDEXES.get(category)
        if not key_indexes:
            existing_ids = set(self._document.section_ids(field.section))
            for object_id in selected_ids:
                if object_id not in existing_ids:
                    row = [""] * max(field.field_index + 1, field.id_index + 1)
                    row[field.id_index] = object_id
                    self._document.append_row(field.section, row)
            self._document.set_field_values(
                field.section,
                field.field_index,
                rendered,
                id_index=field.id_index,
            )
            return

        section = self._document.section(field.section)
        if section is None:
            raise KeyError(field.section)
        for line_index, line in enumerate(section.lines):
            from .inp import tokenize_data_line

            tokens = tokenize_data_line(line)
            if not tokens:
                continue
            key = self._row_key(tokens, key_indexes)
            if key not in rendered:
                continue
            while len(tokens) <= field.field_index:
                tokens.append("")
            tokens[field.field_index] = rendered[key]
            _, marker, comment = line.partition(";")
            rebuilt = " ".join(tokens)
            if marker:
                rebuilt = f"{rebuilt} ;{comment}"
            section.lines[line_index] = rebuilt.rstrip()
            section.modified = True

    def _get_overlay_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return stored fallback values for writable fields without direct rows."""

        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        overrides = self._parameter_overrides.get(spec.key, {})
        values = [overrides.get(object_id) for object_id in selected_ids]
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_overlay_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Store advanced writable values when they do not fit one flat INP cell."""

        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        selected_values = normalize_values(value, len(selected_ids), spec.main_category)
        self._parameter_overrides.setdefault(spec.key, {}).update(dict(zip(selected_ids, selected_values)))
        self._dirty = True
        self._invalidate_results()

    def _render_set_value(self, value, spec: ParameterSpec) -> str:
        """Render Python values into ordinary SWMM input tokens."""

        # Boolean SWMM options are conventionally stored as YES/NO.  Keeping
        # that convention avoids writing Python's True/False spellings into INP.
        if "bool" in spec.type.lower() and isinstance(value, (bool, np.bool_)):
            return "YES" if bool(value) else "NO"
        return str(value)

    def _get_special_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Handle richer public parameters that are not one flat input column."""

        if spec.main_category == "node":
            return self._get_node_parameter(spec, ids=ids, format=format)
        if spec.main_category == "link":
            return self._get_link_parameter(spec, ids=ids, format=format)
        if spec.main_category == "outfall" and spec.sub_category in {
            "fixed_stage",
            "tidal_curve",
            "time_series",
            "tide_gate",
            "route_to",
        }:
            return self._get_outfall_parameter(spec, ids=ids, format=format)
        if spec.key == ("subcatchment", "polygon"):
            return self._get_points_parameter("POLYGONS", "subcatchment", ids=ids, format=format)
        if spec.key == ("subcatchment", "centroid"):
            return self._get_subcatchment_centroid(ids=ids, format=format)
        if spec.key == ("conduit", "geometry"):
            return self._get_conduit_geometry(ids=ids, format=format)
        if spec.key == ("cross_section", "shape_curve"):
            return self._get_cross_section_shape_curve(ids=ids, format=format)
        if spec.main_category == "cross_section" and spec.sub_category in {"height", "width", "side_slope"}:
            return self._get_cross_section_dimension(spec, ids=ids, format=format)
        if spec.main_category == "curve" and spec.sub_category == "points":
            return self._get_curve_points(ids=ids, format=format)
        if spec.main_category == "time_series" and spec.sub_category in {"datetime", "values", "description"}:
            return self._get_time_series_parameter(spec, ids=ids, format=format)
        if spec.key == ("time_pattern", "multipliers"):
            return self._get_sequence_parameter("PATTERNS", "time_pattern", start_index=2, ids=ids, format=format)
        if spec.main_category == "coordinate":
            return self._get_coordinate_parameter(spec, format=format)
        if spec.main_category == "climate":
            return self._get_climate_parameter(spec, format=format)
        if spec.main_category == "climate_adjustment":
            return self._get_climate_adjustment_parameter(spec, format=format)
        if spec.main_category == "interface_file":
            return self._get_interface_file_parameter(spec, format=format)
        if spec.main_category == "control_rule":
            return self._get_control_rule_parameter(spec, ids=ids, format=format)
        if spec.main_category == "transect":
            return self._get_transect_parameter(spec, ids=ids, format=format)
        if spec.main_category == "snow_pack":
            return self._get_snow_pack_parameter(spec, ids=ids, format=format)
        if spec.main_category in {"lid_surface", "lid_pavement", "lid_soil", "lid_storage", "lid_drain"}:
            return self._get_lid_layer_parameter(spec, ids=ids, format=format)
        if spec.main_category == "summary":
            return self._get_summary_parameter(spec, format=format)
        return _MISSING

    def _set_special_parameter(self, spec: ParameterSpec, *, value, ids=None) -> bool:
        """Write richer public parameters that are not one flat input column."""

        if spec.main_category == "node":
            self._set_node_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category == "link":
            self._set_link_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category == "outfall" and spec.sub_category in {
            "fixed_stage",
            "tidal_curve",
            "time_series",
            "tide_gate",
            "route_to",
        }:
            self._set_overlay_parameter(spec, value=value, ids=ids)
            return True
        if spec.key == ("subcatchment", "polygon"):
            self._set_points_parameter("POLYGONS", "subcatchment", value=value, ids=ids)
            return True
        if spec.key == ("subcatchment", "centroid"):
            self._set_subcatchment_centroid(value=value, ids=ids)
            return True
        if spec.key == ("conduit", "geometry"):
            self._set_conduit_geometry(value=value, ids=ids)
            return True
        if spec.key == ("cross_section", "shape_curve"):
            self._set_overlay_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category == "curve" and spec.sub_category == "points":
            self._set_curve_points(value=value, ids=ids)
            return True
        if spec.main_category == "time_series" and spec.sub_category in {"datetime", "values", "description"}:
            self._set_time_series_parameter(spec, value=value, ids=ids)
            return True
        if spec.key == ("time_pattern", "multipliers"):
            self._set_sequence_parameter("PATTERNS", "time_pattern", start_index=2, value=value, ids=ids)
            return True
        if spec.main_category == "coordinate":
            self._set_coordinate_parameter(spec, value=value)
            return True
        if spec.main_category == "climate":
            self._set_climate_parameter(spec, value=value)
            return True
        if spec.main_category == "climate_adjustment":
            self._set_climate_adjustment_parameter(spec, value=value)
            return True
        if spec.main_category == "interface_file":
            self._set_interface_file_parameter(spec, value=value)
            return True
        if spec.main_category == "control_rule":
            self._set_control_rule_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category == "transect":
            self._set_transect_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category == "snow_pack":
            self._set_snow_pack_parameter(spec, value=value, ids=ids)
            return True
        if spec.main_category in {"lid_surface", "lid_pavement", "lid_soil", "lid_storage", "lid_drain"}:
            # Flat LID layer fields are already handled through direct routes;
            # this branch exists only for the few advanced layer attributes that
            # may be stored as overrides when SWMM omits them.
            return False
        if spec.main_category == "summary":
            if spec.sub_category == "options":
                for option_name, option_value in dict(value).items():
                    self.options[str(option_name)] = str(option_value)
                return True
            raise ReadOnlyParameterError(f"'{spec.path}' is a derived parameter and cannot be set.")
        return False

    def _get_derived_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Compute a derived parameter when this release knows how."""

        if spec.sub_category == "count":
            ids_for_category = self._ids_for_category(spec.main_category)
            if ids is not None:
                raise ValueError(f"'{spec.path}' is a scalar count and does not accept 'ids'.")
            return self._format_scalar(len(ids_for_category), spec, format=format)

        if spec.key == ("conduit", "slope"):
            available_ids = self._ids_for_category("conduit")
            selected_ids, explicit_single = normalize_ids(ids, available_ids, "conduit")
            slopes = [self._conduit_slope(conduit_id) for conduit_id in selected_ids]
            return self._format_non_time_values(slopes, selected_ids, explicit_single, format=format)

        if spec.key in {("node", "type"), ("link", "type")}:
            available_ids = self._ids_for_category(spec.main_category)
            selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
            values = [self._composite_object_type(spec.main_category, object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

        if spec.main_category == "conduit" and spec.sub_category in {
            "full_area",
            "full_depth",
            "hydraulic_radius",
            "full_flow",
            "normal_depth",
            "critical_depth",
        }:
            available_ids = self._ids_for_category("conduit")
            selected_ids, explicit_single = normalize_ids(ids, available_ids, "conduit")
            values = [self._conduit_derived_value(conduit_id, spec.sub_category) for conduit_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

        if spec.main_category == "summary":
            return self._get_summary_parameter(spec, format=format)

        return self._get_overlay_parameter(spec, ids=ids, format=format)

    def _get_result_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Read one result matrix from the latest binary SWMM output file."""

        if self._run_timestamps is None or self._last_output_path is None:
            raise ModelNotRunError(
                f"'{spec.path}' is a result variable. Run the model first with m.run()."
            )

        if spec.main_category == "system_result":
            if ids is not None:
                raise ValueError(f"'{spec.path}' is a system-wide result and does not accept 'ids'.")
            if self._output_file_cache is None or self._output_file_cache.path != self._last_output_path:
                self._output_file_cache = OutputFile(self._last_output_path)
            alias = {"outfall_flow": "outflow", "storage_volume": "volume"}.get(spec.sub_category, spec.sub_category)
            try:
                series = self._output_file_cache.system_series(alias)
            except KeyError as exc:
                if spec.sub_category == "pollutant_loading":
                    series = np.full((len(self._run_timestamps),), np.nan)
                else:
                    raise NotImplementedYetError(
                        f"Result access for '{spec.path}' is not implemented yet."
                    ) from exc
            return self._format_time_values(series.reshape(-1, 1), [spec.sub_category], True, format=format)

        if spec.main_category == "rain_gage" and spec.sub_category == "rainfall":
            return self._rain_gage_rainfall(ids=ids, format=format)

        object_kind = RESULT_OBJECT_KIND.get(spec.main_category)
        if object_kind is None:
            return self._fallback_result_parameter(spec, ids=ids, format=format)

        if self._output_file_cache is None or self._output_file_cache.path != self._last_output_path:
            self._output_file_cache = OutputFile(self._last_output_path)
        variable = {"setting": "capacity"}.get(spec.sub_category, spec.sub_category)
        if spec.sub_category == "pollutant_concentration":
            return self._get_pollutant_result_parameter(spec, object_kind=object_kind, ids=ids, format=format)
        try:
            whole_matrix = self._output_file_cache.matrix(object_kind, variable)
        except KeyError as exc:
            if spec.main_category == "pump" and spec.sub_category == "status":
                whole_matrix = self._output_file_cache.matrix("link", "capacity")
            else:
                return self._fallback_result_parameter(spec, ids=ids, format=format)

        # ``conduit`` is a subset of SWMM's broader link result block, while
        # ``junction`` and ``outfall`` are subsets of the node result block.
        result_ids = self._ids_for_category(object_kind)
        selected_ids, explicit_single = normalize_ids(ids, self._ids_for_category(spec.main_category), spec.main_category)
        column_indexes = [result_ids.index(object_id) for object_id in selected_ids]
        selected_matrix = whole_matrix[:, column_indexes]
        if spec.main_category == "pump" and spec.sub_category == "status":
            selected_matrix = selected_matrix > 0
        return self._format_time_values(selected_matrix, selected_ids, explicit_single, format=format)

    def _format_scalar(self, value, spec: ParameterSpec, *, format=None):
        """Return one scalar or an explicitly requested scalar container."""

        if format is None:
            return value
        if format == "np":
            return np.asarray([value])
        if format == "df":
            return pd.DataFrame([[value]], columns=[spec.sub_category])
        raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

    def _format_non_time_values(self, values, selected_ids, explicit_single: bool, *, format=None):
        """Return scalar or one-row containers for non-time-series values."""

        if explicit_single and format is None:
            return values[0]
        selected_format = "np" if format is None else format
        if selected_format == "np":
            try:
                return np.asarray(values)
            except ValueError:
                return np.asarray(values, dtype=object)
        if selected_format == "df":
            return pd.DataFrame([values], columns=selected_ids)
        raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

    def _format_empty_collection(self, spec: ParameterSpec, *, format=None):
        """Return a shape-appropriate empty value for an absent object family."""

        # Result variables are time-series by definition.  If a previous run is
        # available, preserve its time axis and expose zero object columns.  If
        # no run exists yet, an empty 0x0 result still communicates the central
        # fact cleanly: there are no objects of the requested family.
        if spec.source_kind == "result":
            timestamps = list(self._run_timestamps or [])
            matrix = np.empty((len(timestamps), 0))
            selected_format = "np" if format is None else format
            if selected_format == "np":
                return matrix
            if selected_format == "df":
                return pd.DataFrame(
                    matrix,
                    index=pd.DatetimeIndex(timestamps, name="time"),
                )
            raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

        # Static/user/derived object parameters follow the ordinary non-time
        # getter convention, except that a DataFrame with no selected objects
        # should be genuinely empty rather than a visually confusing one-row
        # frame with zero columns.
        selected_format = "np" if format is None else format
        if selected_format == "np":
            return np.asarray([])
        if selected_format == "df":
            return pd.DataFrame()
        raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

    def _format_time_values(self, matrix, selected_ids, explicit_single: bool, *, format=None):
        """Return one-dimensional or two-dimensional result values."""

        selected_format = "np" if format is None else format
        if selected_format == "np":
            return matrix[:, 0] if explicit_single else matrix
        if selected_format == "df":
            return pd.DataFrame(matrix, index=pd.DatetimeIndex(self._run_timestamps, name="time"), columns=selected_ids)
        raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

    def _validate_reference_values(self, field: FieldSpec, values: list[object], spec: ParameterSpec) -> None:
        """Validate refs against known object IDs when the target is known."""

        target = field.reference_target
        if target is None:
            return
        if target == "node_or_subcatchment":
            valid_ids = set(self._ids_for_category("node")) | set(self._ids_for_category("subcatchment"))
        else:
            valid_ids = set(self._ids_for_category(target))

        missing = [
            str(value)
            for value in values
            if value not in {None, "", "*"} and str(value) not in valid_ids
        ]
        if missing:
            joined = ", ".join(missing)
            raise InvalidReferenceError(
                f"Invalid reference for '{spec.path}': {joined}. "
                f"Expected existing {target} object ID(s)."
            )

    def _node_invert_elevation(self, node_id: str) -> float:
        """Return the invert elevation for an ordinary node ID."""

        for section_name in ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE"):
            section_ids = self._document.section_ids(section_name)
            if node_id in section_ids:
                raw = self._document.get_field_values(section_name, 1, [node_id])[0]
                return float(raw)
        raise KeyError(node_id)

    def _conduit_slope(self, conduit_id: str) -> float:
        """Compute one conduit slope from node inverts and conduit length."""

        # Read the two endpoint IDs and the current conduit length from the same
        # preserving document that backs setters, so derived values immediately
        # reflect in-memory edits.
        from_node = self._document.get_field_values("CONDUITS", 1, [conduit_id])[0]
        to_node = self._document.get_field_values("CONDUITS", 2, [conduit_id])[0]
        length = self._document.get_field_values("CONDUITS", 3, [conduit_id])[0]
        return (self._node_invert_elevation(from_node) - self._node_invert_elevation(to_node)) / float(length)

    def _conduit_derived_value(self, conduit_id: str, variable: str) -> float:
        """Compute common conduit geometry/hydraulic helper values."""

        diameter = float(self._document.get_field_values("XSECTIONS", 2, [conduit_id])[0] or 0.0)
        slope = self._conduit_slope(conduit_id)
        roughness = float(self._document.get_field_values("CONDUITS", 4, [conduit_id])[0] or 0.013)
        area = np.pi * diameter**2 / 4.0
        hydraulic_radius = diameter / 4.0
        full_flow = (1.486 / roughness) * area * hydraulic_radius ** (2 / 3) * max(slope, 0.0) ** 0.5
        values = {
            "full_area": area,
            "full_depth": diameter,
            "hydraulic_radius": hydraulic_radius,
            "full_flow": full_flow,
            "normal_depth": diameter,
            "critical_depth": diameter,
        }
        return float(values[variable])

    def _rain_gage_rainfall(self, *, ids=None, format=None):
        """Return rainfall series for rain gages backed by inline time series."""

        available_ids = self._ids_for_category("rain_gage")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "rain_gage")
        columns = []
        for gage_id in selected_ids:
            source_type = self._document.get_field_values("RAINGAGES", 4, [gage_id])[0].upper()
            source_data = self._document.get_field_values("RAINGAGES", 5, [gage_id])[0]
            if source_type == "TIMESERIES" and source_data in self._ids_for_category("time_series"):
                raw = self._get_time_series_parameter(
                    self._parameter_catalog._specs[("time_series", "values")],
                    ids=source_data,
                    format=None,
                )
                values = np.asarray(raw, dtype=float)
            else:
                values = np.full((len(self._run_timestamps or self._expected_timestamps()),), np.nan)
            periods = len(self._run_timestamps or self._expected_timestamps())
            if len(values) < periods:
                values = np.pad(values, (0, periods - len(values)), constant_values=np.nan)
            columns.append(values[:periods])
        matrix = np.column_stack(columns)
        if self._run_timestamps is None:
            self._run_timestamps = self._expected_timestamps()
        return self._format_time_values(matrix, selected_ids, explicit_single, format=format)

    def _fallback_result_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return an explicit NaN result shape when SWMM lacks a binary column."""

        if spec.main_category not in OBJECT_SECTIONS:
            series = np.full((len(self._run_timestamps or []), 1), np.nan)
            return self._format_time_values(series, [spec.sub_category], True, format=format)
        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        matrix = np.full((len(self._run_timestamps or []), len(selected_ids)), np.nan)
        return self._format_time_values(matrix, selected_ids, explicit_single, format=format)

    def _get_pollutant_result_parameter(self, spec: ParameterSpec, *, object_kind: str, ids=None, format=None):
        """Return pollutant concentration results with pollutant-aware columns."""

        pollutant_ids = self._ids_for_category("pollutant")
        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        if not pollutant_ids:
            return self._fallback_result_parameter(spec, ids=ids, format=format)
        result_ids = self._ids_for_category(object_kind)
        matrices = [self._output_file_cache.matrix(object_kind, "pollutant_concentration", pollutant_index=index) for index, _ in enumerate(pollutant_ids)]
        column_indexes = [result_ids.index(object_id) for object_id in selected_ids]
        tensor = np.stack([matrix[:, column_indexes] for matrix in matrices], axis=-1)
        selected_format = "np" if format is None else format
        if selected_format == "np":
            return tensor[:, 0, :] if explicit_single else tensor
        if selected_format == "df":
            if explicit_single:
                return pd.DataFrame(
                    tensor[:, 0, :],
                    index=pd.DatetimeIndex(self._run_timestamps, name="time"),
                    columns=pollutant_ids,
                )
            columns = pd.MultiIndex.from_product([selected_ids, pollutant_ids], names=["id", "pollutant"])
            return pd.DataFrame(
                tensor.reshape(tensor.shape[0], -1),
                index=pd.DatetimeIndex(self._run_timestamps, name="time"),
                columns=columns,
            )
        raise FormatError(f"Unsupported format '{format}'. Use one of: 'np', 'df'")

    def _composite_object_type(self, category: str, object_id: str) -> str:
        """Return the section-derived type for a composite node/link object."""

        section_names = OBJECT_SECTIONS[category]
        for section_name in section_names:
            if object_id in self._document.section_ids(section_name):
                return section_name.lower()
        raise KeyError(object_id)

    def _field_value_from_sections(self, object_id: str, sections: tuple[str, ...], field_index: int) -> str:
        """Return one field from whichever subtype section owns ``object_id``."""

        for section_name in sections:
            if object_id in self._document.section_ids(section_name):
                return self._document.get_field_values(section_name, field_index, [object_id])[0]
        return ""

    def _set_field_in_sections(self, object_id: str, sections: tuple[str, ...], field_index: int, value: object) -> None:
        """Write one field into whichever subtype section owns ``object_id``."""

        for section_name in sections:
            if object_id in self._document.section_ids(section_name):
                self._document.set_field_values(section_name, field_index, {object_id: value})
                return

    def _get_node_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return union-node fields and node-attached related records."""

        if spec.sub_category in {"count", "type"} or spec.source_kind == "result":
            return _MISSING
        available_ids = self._ids_for_category("node")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "node")
        direct_indexes = {
            "id": 0,
            "invert_elevation": 1,
            "max_depth": 2,
            "initial_depth": 3,
            "surcharge_depth": 4,
            "ponded_area": 5,
        }
        if spec.sub_category in direct_indexes:
            values = [
                coerce_value(
                    self._field_value_from_sections(object_id, OBJECT_SECTIONS["node"], direct_indexes[spec.sub_category]),
                    spec.type,
                )
                for object_id in selected_ids
            ]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "tag":
            values = [self._tag_for("Node", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "coordinate":
            values = [self._point_for("COORDINATES", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "external_inflow":
            values = [self._related_rows("INFLOWS", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "dry_weather_flow":
            values = [self._related_rows("DWF", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "treatment":
            values = [self._related_rows("TREATMENT", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        return _MISSING

    def _set_node_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Write union-node fields and simple attached metadata."""

        available_ids = self._ids_for_category("node")
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, "node")
        selected_values = normalize_values(value, len(selected_ids), "node")
        direct_indexes = {
            "id": 0,
            "invert_elevation": 1,
            "max_depth": 2,
            "initial_depth": 3,
            "surcharge_depth": 4,
            "ponded_area": 5,
        }
        if spec.sub_category in direct_indexes:
            for object_id, item in zip(selected_ids, selected_values):
                self._set_field_in_sections(object_id, OBJECT_SECTIONS["node"], direct_indexes[spec.sub_category], self._render_set_value(item, spec))
        elif spec.sub_category == "tag":
            for object_id, item in zip(selected_ids, selected_values):
                self._set_tag("Node", object_id, item)
        elif spec.sub_category == "coordinate":
            for object_id, item in zip(selected_ids, selected_values):
                self._set_point("COORDINATES", object_id, item)
        elif spec.sub_category in {"external_inflow", "dry_weather_flow", "treatment"}:
            section_name = {
                "external_inflow": "INFLOWS",
                "dry_weather_flow": "DWF",
                "treatment": "TREATMENT",
            }[spec.sub_category]
            for object_id, rows in zip(selected_ids, selected_values):
                self._replace_related_rows(section_name, object_id, rows)
        else:
            self._parameter_overrides.setdefault(spec.key, {}).update(dict(zip(selected_ids, selected_values)))
        self._dirty = True
        self._invalidate_results()

    def _get_link_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return union-link fields, vertices, and link metadata."""

        if spec.sub_category in {"count", "type"} or spec.source_kind == "result":
            return _MISSING
        available_ids = self._ids_for_category("link")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "link")
        direct_indexes = {
            "id": 0,
            "from_node": 1,
            "to_node": 2,
            "inlet_offset": 5,
            "outlet_offset": 6,
            "initial_flow": 7,
            "maximum_flow": 8,
        }
        if spec.sub_category in direct_indexes:
            values = [
                coerce_value(
                    self._field_value_from_sections(object_id, OBJECT_SECTIONS["link"], direct_indexes[spec.sub_category]),
                    spec.type,
                )
                for object_id in selected_ids
            ]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "flap_gate":
            values = [self._field_value_from_sections(object_id, ("LOSSES",), 4) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "tag":
            values = [self._tag_for("Link", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        if spec.sub_category == "vertices":
            values = [self._points_for("VERTICES", object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)
        return _MISSING

    def _set_link_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Write union-link fields, vertices, and link metadata."""

        available_ids = self._ids_for_category("link")
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, "link")
        selected_values = normalize_values(value, len(selected_ids), "link")
        direct_indexes = {
            "id": 0,
            "from_node": 1,
            "to_node": 2,
            "inlet_offset": 5,
            "outlet_offset": 6,
            "initial_flow": 7,
            "maximum_flow": 8,
        }
        if spec.sub_category in direct_indexes:
            for object_id, item in zip(selected_ids, selected_values):
                self._set_field_in_sections(object_id, OBJECT_SECTIONS["link"], direct_indexes[spec.sub_category], self._render_set_value(item, spec))
        elif spec.sub_category == "tag":
            for object_id, item in zip(selected_ids, selected_values):
                self._set_tag("Link", object_id, item)
        elif spec.sub_category == "vertices":
            for object_id, item in zip(selected_ids, selected_values):
                self._replace_points("VERTICES", object_id, item)
        else:
            self._parameter_overrides.setdefault(spec.key, {}).update(dict(zip(selected_ids, selected_values)))
        self._dirty = True
        self._invalidate_results()

    def _get_outfall_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return type-aware optional outfall fields."""

        available_ids = self._ids_for_category("outfall")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "outfall")
        values = []
        for object_id in selected_ids:
            row = next(row for row in self._document.rows("OUTFALLS") if row and row[0] == object_id)
            outfall_type = row[2].upper() if len(row) >= 3 else ""
            stage_value = row[3] if len(row) >= 4 and outfall_type != "FREE" else None
            if spec.sub_category == "fixed_stage":
                values.append(stage_value if outfall_type == "FIXED" else None)
            elif spec.sub_category == "tidal_curve":
                values.append(stage_value if outfall_type == "TIDAL" else None)
            elif spec.sub_category == "time_series":
                values.append(stage_value if outfall_type == "TIMESERIES" else None)
            elif spec.sub_category == "tide_gate":
                values.append(row[-1] if len(row) >= 4 else None)
            else:
                values.append(row[-1] if len(row) >= 5 else None)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _tag_for(self, tag_type: str, object_id: str) -> str | None:
        """Return one tag value from ``[TAGS]``."""

        for row in self._document.rows("TAGS"):
            if len(row) >= 3 and row[0].lower().startswith(tag_type.lower()) and row[1] == object_id:
                return row[2]
        return None

    def _set_tag(self, tag_type: str, object_id: str, value: object) -> None:
        """Insert or update one tag row."""

        section = self._document.ensure_section("TAGS")
        for line_index, line in enumerate(section.lines):
            from .inp import tokenize_data_line

            tokens = tokenize_data_line(line)
            if len(tokens) >= 3 and tokens[0].lower().startswith(tag_type.lower()) and tokens[1] == object_id:
                tokens[2] = str(value)
                section.lines[line_index] = " ".join(tokens)
                section.modified = True
                return
        self._document.append_row("TAGS", [tag_type, object_id, value])

    def _point_for(self, section_name: str, object_id: str):
        """Return one ``(x, y)`` tuple from a point section."""

        points = self._points_for(section_name, object_id)
        return points[0] if points else None

    def _points_for(self, section_name: str, object_id: str) -> list[tuple[float, float]]:
        """Return all numeric coordinate pairs for one ID."""

        points: list[tuple[float, float]] = []
        for row in self._document.rows(section_name):
            if len(row) >= 3 and row[0] == object_id:
                points.append((float(row[1]), float(row[2])))
        return points

    def _set_point(self, section_name: str, object_id: str, value) -> None:
        """Set exactly one point record for an object."""

        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"'{section_name}' coordinates must be a two-item sequence.")
        self._replace_points(section_name, object_id, [value])

    def _replace_points(self, section_name: str, object_id: str, points) -> None:
        """Replace all point rows for one object while preserving the section."""

        normalized = [tuple(point) for point in points]
        if not all(len(point) == 2 for point in normalized):
            raise ValueError("Point data must contain two values per point.")
        self._document.remove_rows(section_name, [object_id])
        for x_value, y_value in normalized:
            self._document.append_row(section_name, [object_id, x_value, y_value])

    def _related_rows(self, section_name: str, object_id: str) -> list[list[str]]:
        """Return rows whose first field references one owning object."""

        return [row for row in self._document.rows(section_name) if row and row[0] == object_id]

    def _replace_related_rows(self, section_name: str, object_id: str, rows) -> None:
        """Replace all attached rows whose first field references one object."""

        self._document.remove_rows(section_name, [object_id])
        for row in rows:
            self._document.append_row(section_name, row)

    def _get_points_parameter(self, section_name: str, category: str, *, ids=None, format=None):
        """Return point-sequence values for all selected objects."""

        available_ids = self._ids_for_category(category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, category)
        values = [self._points_for(section_name, object_id) for object_id in selected_ids]
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_points_parameter(self, section_name: str, category: str, *, value, ids=None) -> None:
        """Replace point sequences for selected objects."""

        available_ids = self._ids_for_category(category)
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, category)
        selected_values = normalize_values(value, len(selected_ids), category)
        for object_id, points in zip(selected_ids, selected_values):
            self._replace_points(section_name, object_id, points)
        self._dirty = True
        self._invalidate_results()

    def _get_subcatchment_centroid(self, *, ids=None, format=None):
        """Return polygon centroids computed from stored subcatchment vertices."""

        available_ids = self._ids_for_category("subcatchment")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "subcatchment")
        values = []
        for object_id in selected_ids:
            points = self._points_for("POLYGONS", object_id)
            if not points:
                values.append(None)
            else:
                values.append(
                    (
                        sum(point[0] for point in points) / len(points),
                        sum(point[1] for point in points) / len(points),
                    )
                )
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_subcatchment_centroid(self, *, value, ids=None) -> None:
        """Store explicit centroid overrides for subcatchments."""

        self._set_overlay_parameter(
            self._parameter_catalog._specs[("subcatchment", "centroid")],
            value=value,
            ids=ids,
        )

    def _get_conduit_geometry(self, *, ids=None, format=None):
        """Return the four SWMM cross-section geometry fields per conduit."""

        available_ids = self._ids_for_category("conduit")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "conduit")
        values = []
        for object_id in selected_ids:
            geometry = []
            for field_index in (2, 3, 4, 5):
                raw = self._document.get_field_values("XSECTIONS", field_index, [object_id])[0]
                geometry.append(coerce_value(raw, "float"))
            values.append(tuple(geometry))
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_conduit_geometry(self, *, value, ids=None) -> None:
        """Write the four SWMM cross-section geometry fields per conduit."""

        available_ids = self._ids_for_category("conduit")
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, "conduit")
        selected_values = normalize_values(value, len(selected_ids), "conduit")
        for object_id, geometry in zip(selected_ids, selected_values):
            if not isinstance(geometry, (list, tuple)) or len(geometry) != 4:
                raise ValueError("Conduit geometry must contain exactly four values.")
            for field_index, item in zip((2, 3, 4, 5), geometry):
                self._document.set_field_values("XSECTIONS", field_index, {object_id: item})
        self._dirty = True
        self._invalidate_results()

    def _get_cross_section_dimension(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return derived/user-friendly cross-section dimensions."""

        available_ids = self._ids_for_category("cross_section")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "cross_section")
        shape_values = self._document.get_field_values("XSECTIONS", 1, selected_ids)
        g1_values = [float(value or 0.0) for value in self._document.get_field_values("XSECTIONS", 2, selected_ids)]
        g2_values = [float(value or 0.0) for value in self._document.get_field_values("XSECTIONS", 3, selected_ids)]
        values: list[float] = []
        for shape, g1, g2 in zip(shape_values, g1_values, g2_values):
            upper = shape.upper()
            if spec.sub_category == "height":
                values.append(g1)
            elif spec.sub_category == "width":
                values.append(g1 if upper == "CIRCULAR" else g2)
            else:
                values.append(g2 if upper in {"TRAPEZOIDAL", "TRIANGULAR"} else 0.0)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _get_cross_section_shape_curve(self, *, ids=None, format=None):
        """Return custom-shape curve references only for CUSTOM cross-sections."""

        available_ids = self._ids_for_category("cross_section")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "cross_section")
        values = []
        for object_id in selected_ids:
            shape = self._document.get_field_values("XSECTIONS", 1, [object_id])[0].upper()
            geometry_1 = self._document.get_field_values("XSECTIONS", 2, [object_id])[0]
            values.append(geometry_1 if shape == "CUSTOM" else None)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _get_curve_points(self, *, ids=None, format=None):
        """Return point sequences for one or more curves."""

        available_ids = self._ids_for_category("curve")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "curve")
        values = []
        for curve_id in selected_ids:
            points = []
            for row in self._document.rows("CURVES"):
                if row and row[0] == curve_id:
                    x_index, y_index = (2, 3) if len(row) >= 4 else (1, 2)
                    points.append((coerce_value(row[x_index], "float"), coerce_value(row[y_index], "float")))
            values.append(points)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_curve_points(self, *, value, ids=None) -> None:
        """Replace all rows for one or more curves while preserving curve type."""

        available_ids = self._ids_for_category("curve")
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, "curve")
        selected_values = normalize_values(value, len(selected_ids), "curve")
        for curve_id, points in zip(selected_ids, selected_values):
            existing_type = None
            for row in self._document.rows("CURVES"):
                if len(row) >= 4 and row[0] == curve_id:
                    existing_type = row[1]
                    break
            self._document.remove_rows("CURVES", [curve_id])
            for index, point in enumerate(points):
                if len(point) != 2:
                    raise ValueError("Curve points must contain x/y pairs.")
                row = [curve_id]
                if index == 0 and existing_type:
                    row.append(existing_type)
                row.extend(point)
                self._document.append_row("CURVES", row)
        self._dirty = True
        self._invalidate_results()

    def _get_time_series_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return parsed time-series timestamps, values, or descriptions."""

        available_ids = self._ids_for_category("time_series")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "time_series")
        if spec.sub_category == "description":
            values = [self._parameter_overrides.get(spec.key, {}).get(object_id) for object_id in selected_ids]
            return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

        values = []
        for series_id in selected_ids:
            last_date = None
            series_values = []
            for row in self._document.rows("TIMESERIES"):
                if not row or row[0] != series_id or (len(row) >= 2 and row[1].upper() == "FILE"):
                    continue
                if len(row) >= 4:
                    last_date, time_text, value_text = row[1], row[2], row[3]
                else:
                    time_text, value_text = row[1], row[2]
                if spec.sub_category == "datetime":
                    series_values.append(f"{last_date or ''} {time_text}".strip())
                else:
                    series_values.append(coerce_value(value_text, "float"))
            values.append(series_values)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_time_series_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Store time-series metadata or replace values when practical."""

        if spec.sub_category == "description":
            self._set_overlay_parameter(spec, value=value, ids=ids)
            return
        self._set_overlay_parameter(spec, value=value, ids=ids)

    def _get_sequence_parameter(self, section_name: str, category: str, *, start_index: int, ids=None, format=None):
        """Return trailing sequence values from a simple row section."""

        available_ids = self._ids_for_category(category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, category)
        values = []
        for object_id in selected_ids:
            row = next(row for row in self._document.rows(section_name) if row and row[0] == object_id)
            values.append([coerce_value(item, "float") for item in row[start_index:]])
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_sequence_parameter(self, section_name: str, category: str, *, start_index: int, value, ids=None) -> None:
        """Replace trailing sequence values in a simple row section."""

        available_ids = self._ids_for_category(category)
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, category)
        selected_values = normalize_values(value, len(selected_ids), category)
        section = self._document.section(section_name)
        if section is None:
            raise KeyError(section_name)
        from .inp import tokenize_data_line

        for line_index, line in enumerate(section.lines):
            tokens = tokenize_data_line(line)
            if not tokens or tokens[0] not in selected_ids:
                continue
            sequence = list(selected_values[selected_ids.index(tokens[0])])
            section.lines[line_index] = " ".join([*tokens[:start_index], *[str(item) for item in sequence]])
            section.modified = True
        self._dirty = True
        self._invalidate_results()

    def _get_coordinate_parameter(self, spec: ParameterSpec, *, format=None):
        """Return whole-map geometry tables and map metadata."""

        if spec.sub_category == "node_coordinates":
            value = {row[0]: (float(row[1]), float(row[2])) for row in self._document.rows("COORDINATES") if len(row) >= 3}
        elif spec.sub_category == "subcatchment_coordinates":
            value = {object_id: self._point_for("POLYGONS", object_id) for object_id in self._ids_for_category("subcatchment")}
        elif spec.sub_category == "link_vertices":
            value = {object_id: self._points_for("VERTICES", object_id) for object_id in self._ids_for_category("link")}
        elif spec.sub_category == "polygons":
            value = {object_id: self._points_for("POLYGONS", object_id) for object_id in self._ids_for_category("subcatchment")}
        elif spec.sub_category == "labels":
            value = self._document.rows("LABELS")
        elif spec.sub_category == "map_dimensions":
            row = next((row for row in self._document.rows("MAP") if row and row[0].upper() == "DIMENSIONS"), [])
            value = tuple(float(item) for item in row[1:5]) if len(row) >= 5 else None
        else:
            row = next((row for row in self._document.rows("MAP") if row and row[0].upper() == "UNITS"), [])
            value = row[1] if len(row) >= 2 else None
        return self._format_scalar(value, spec, format=format)

    def _set_coordinate_parameter(self, spec: ParameterSpec, *, value) -> None:
        """Write whole-map geometry tables and map metadata."""

        if spec.sub_category == "map_dimensions":
            self._upsert_keyed_row("MAP", "DIMENSIONS", list(value))
        elif spec.sub_category == "map_units":
            self._upsert_keyed_row("MAP", "Units", [value])
        elif spec.sub_category == "node_coordinates":
            for object_id, point in dict(value).items():
                self._set_point("COORDINATES", object_id, point)
        elif spec.sub_category == "link_vertices":
            for object_id, points in dict(value).items():
                self._replace_points("VERTICES", object_id, points)
        elif spec.sub_category == "polygons":
            for object_id, points in dict(value).items():
                self._replace_points("POLYGONS", object_id, points)
        elif spec.sub_category == "subcatchment_coordinates":
            self._parameter_overrides.setdefault(spec.key, {}).update(dict(value))
        else:
            self._parameter_overrides.setdefault(spec.key, {})["model"] = value
        self._dirty = True
        self._invalidate_results()

    def _upsert_keyed_row(self, section_name: str, key: str, values: list[object]) -> None:
        """Insert or update a row whose first token is a fixed key."""

        section = self._document.ensure_section(section_name)
        from .inp import tokenize_data_line

        for line_index, line in enumerate(section.lines):
            tokens = tokenize_data_line(line)
            if tokens and tokens[0].upper() == key.upper():
                section.lines[line_index] = " ".join([key, *[str(item) for item in values]])
                section.modified = True
                return
        self._document.append_row(section_name, [key, *values])

    def _get_climate_parameter(self, spec: ParameterSpec, *, format=None):
        """Return parsed climate controls from their source sections."""

        rows_by_section = {
            "temperature_time_series": self._document.rows("TEMPERATURE"),
            "evaporation_type": self._document.rows("EVAPORATION"),
            "evaporation_constant": self._document.rows("EVAPORATION"),
            "evaporation_monthly": self._document.rows("EVAPORATION"),
            "evaporation_time_series": self._document.rows("EVAPORATION"),
            "evaporation_recovery_pattern": self._document.rows("EVAPORATION"),
            "evaporation_dry_only": self._document.rows("EVAPORATION"),
            "wind_speed_type": self._document.rows("WINDSPEED"),
            "wind_speed_monthly": self._document.rows("WINDSPEED"),
            "snowmelt_parameters": self._document.rows("SNOWMELT"),
            "areal_depletion_impervious": self._document.rows("AREAL_DEPLETION"),
            "areal_depletion_pervious": self._document.rows("AREAL_DEPLETION"),
        }
        value = rows_by_section.get(spec.sub_category, [])
        return self._format_scalar(value, spec, format=format)

    def _set_climate_parameter(self, spec: ParameterSpec, *, value) -> None:
        """Store climate inputs in a durable overlay for round-trip access."""

        self._parameter_overrides.setdefault(spec.key, {})["model"] = value
        self._dirty = True
        self._invalidate_results()

    def _get_climate_adjustment_parameter(self, spec: ParameterSpec, *, format=None):
        """Return monthly climate-adjustment rows by keyword."""

        key = {
            "temperature": "TEMPERATURE",
            "evaporation": "EVAPORATION",
            "rainfall": "RAINFALL",
            "conductivity": "CONDUCTIVITY",
        }[spec.sub_category]
        row = next((row for row in self._document.rows("ADJUSTMENTS") if row and row[0].upper() == key), [])
        value = row[1:] if row else self._parameter_overrides.get(spec.key, {}).get("model")
        return self._format_scalar(value, spec, format=format)

    def _set_climate_adjustment_parameter(self, spec: ParameterSpec, *, value) -> None:
        """Write one monthly climate-adjustment row."""

        key = {
            "temperature": "TEMPERATURE",
            "evaporation": "EVAPORATION",
            "rainfall": "RAINFALL",
            "conductivity": "CONDUCTIVITY",
        }[spec.sub_category]
        if value is None:
            self._parameter_overrides.setdefault(spec.key, {})["model"] = None
        else:
            self._upsert_keyed_row("ADJUSTMENTS", key, list(value))
        self._dirty = True
        self._invalidate_results()

    def _get_interface_file_parameter(self, spec: ParameterSpec, *, format=None):
        """Return interface-file declarations from ``[FILES]``."""

        rows = self._document.rows("FILES")
        target = spec.sub_category.upper()
        value = []
        for row in rows:
            joined = " ".join(row).upper()
            if target in joined:
                value.append(row)
        if not value:
            value = self._parameter_overrides.get(spec.key, {}).get("model")
        return self._format_scalar(value, spec, format=format)

    def _set_interface_file_parameter(self, spec: ParameterSpec, *, value) -> None:
        """Store interface-file settings when no exact row grammar applies."""

        self._parameter_overrides.setdefault(spec.key, {})["model"] = value
        self._dirty = True
        self._invalidate_results()

    def _get_control_rule_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return control-rule text, conditions, actions, priority, or enabled state."""

        if spec.sub_category == "count" or spec.source_kind == "result":
            return _MISSING
        available_ids = self._ids_for_category("control_rule")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "control_rule")
        blocks = self._control_rule_blocks()
        values = []
        for rule_id in selected_ids:
            lines = blocks.get(rule_id, [])
            if spec.sub_category == "id":
                values.append(rule_id)
            elif spec.sub_category == "text":
                values.append("\n".join(lines))
            elif spec.sub_category == "conditions":
                values.append([line for line in lines if line.upper().startswith(("IF ", "AND ", "OR "))])
            elif spec.sub_category == "actions":
                values.append([line for line in lines if line.upper().startswith(("THEN ", "ELSE "))])
            elif spec.sub_category == "priority":
                priority = next((line.split(maxsplit=1)[1] for line in lines if line.upper().startswith("PRIORITY ")), None)
                values.append(priority)
            else:
                values.append(True)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_control_rule_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Store edited control-rule metadata as overlays for now."""

        self._set_overlay_parameter(spec, value=value, ids=ids)

    def _control_rule_blocks(self) -> dict[str, list[str]]:
        """Return preserved rule blocks keyed by rule name."""

        blocks: dict[str, list[str]] = {}
        current_id = None
        for raw_line in (self._document.section("CONTROLS").lines if self._document.section("CONTROLS") else []):
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            if line.upper().startswith("RULE "):
                current_id = line.split(maxsplit=1)[1]
                blocks[current_id] = [line]
            elif current_id is not None:
                blocks[current_id].append(line)
        return blocks

    def _get_transect_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return best-effort transect data grouped by transect ID."""

        if spec.sub_category == "count":
            return _MISSING
        available_ids = self._ids_for_category("transect")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "transect")
        values = []
        for transect_id in selected_ids:
            rows = [row for row in self._document.rows("TRANSECTS") if transect_id in row]
            values.append(rows)
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_transect_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Store advanced transect edits in the parameter overlay."""

        self._set_overlay_parameter(spec, value=value, ids=ids)

    def _get_snow_pack_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return snow-pack row groups by ID."""

        if spec.sub_category == "count":
            return _MISSING
        available_ids = self._ids_for_category("snow_pack")
        selected_ids, explicit_single = normalize_ids(ids, available_ids, "snow_pack")
        values = [[row for row in self._document.rows("SNOWPACKS") if row and row[0] == object_id] for object_id in selected_ids]
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _set_snow_pack_parameter(self, spec: ParameterSpec, *, value, ids=None) -> None:
        """Store advanced snow-pack edits in the parameter overlay."""

        self._set_overlay_parameter(spec, value=value, ids=ids)

    def _get_lid_layer_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Return one filtered LID layer field."""

        field = INPUT_FIELDS.get(spec.key)
        if field is None:
            return self._get_overlay_parameter(spec, ids=ids, format=format)
        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        layer_names = {
            "lid_surface": "SURFACE",
            "lid_pavement": "PAVEMENT",
            "lid_soil": "SOIL",
            "lid_storage": "STORAGE",
            "lid_drain": "DRAIN",
        }
        values = []
        for object_id in selected_ids:
            row = next(
                row
                for row in self._document.rows("LID_CONTROLS")
                if len(row) >= 2 and row[0] == object_id and row[1].upper() == layer_names[spec.main_category]
            )
            raw = row[field.field_index] if len(row) > field.field_index else ""
            values.append(coerce_value(raw, spec.type))
        return self._format_non_time_values(values, selected_ids, explicit_single, format=format)

    def _get_summary_parameter(self, spec: ParameterSpec, *, format=None):
        """Return current model summaries or simple result aggregates."""

        if spec.sub_category == "counts":
            value = self.count.model_dict()
        elif spec.sub_category == "options":
            value = dict(self.options)
        elif spec.sub_category == "validation_issues":
            value = self.validate().to_frame()
        elif spec.sub_category == "model":
            value = {"counts": self.count.model_dict(), "options": dict(self.options)}
        else:
            if not self.has_run:
                raise ModelNotRunError(
                    f"'{spec.path}' is a result variable. Run the model first with m.run()."
                )
            value = self._summary_from_results(spec.sub_category)
        return self._format_scalar(value, spec, format=format)

    def _summary_from_results(self, name: str):
        """Build a practical aggregate table for one summary name."""

        mappings = {
            "subcatchment_runoff": ("subcatchment", "runoff"),
            "node_depth": ("node", "depth"),
            "node_inflow": ("node", "total_inflow"),
            "node_flooding": ("node", "flooding"),
            "storage_volume": ("node", "volume"),
            "link_flow": ("link", "flow"),
            "link_velocity": ("link", "velocity"),
        }
        if name in mappings:
            category, variable = mappings[name]
            frame = getattr(getattr(self.get, category), variable)(format="df")
            return pd.DataFrame({"max": frame.max(), "mean": frame.mean(), "last": frame.iloc[-1]})
        return pd.DataFrame()

    def save(self, inp_path: str | Path) -> Path:
        """Save the current model to a valid EPA SWMM ``.inp`` file."""

        target = Path(inp_path).expanduser().resolve()

        # Creating parents is safe and convenient for normal save-as workflows.
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._document.to_text(), encoding="utf-8")
        except OSError as exc:
            raise SaveError(f"Could not save SWMM input file to '{target}': {exc}") from exc

        # Once saved, the model can use this file directly for later runs until
        # a subsequent mutation marks it dirty again.
        self._source_path = target
        self._dirty = False
        return target

    def _prepare_run_files(self) -> tuple[Path, Path, Path]:
        """Return input, report, and output paths for one execution."""

        # A clean saved model can run beside its source file.  Unsaved or dirty
        # models receive an isolated temporary workspace so execution reflects
        # current memory state without silently overwriting the user's source.
        if self._source_path is not None and not self._dirty:
            inp_path = self._source_path
            run_root = self._source_path.parent
        else:
            if self._runtime_directory is not None:
                self._runtime_directory.cleanup()
            self._runtime_directory = tempfile.TemporaryDirectory(prefix="swmmx-")
            run_root = Path(self._runtime_directory.name)
            inp_path = run_root / "model.inp"
            inp_path.write_text(self._document.to_text(), encoding="utf-8")

        stem = inp_path.stem
        rpt_path = run_root / f"{stem}.rpt"
        out_path = run_root / f"{stem}.out"
        return inp_path, rpt_path, out_path

    def run(self) -> RunResult:
        """Run the model, write report/output files, and load result metadata."""

        validation = self.validate()
        inp_path, rpt_path, out_path = self._prepare_run_files()
        engine = self._engine_loader.get()
        error_code = engine.run(inp_path, rpt_path, out_path)

        # Store the report text whether or not SWMM returned success; debugging
        # native failures is much easier when the log survives the call site.
        self._last_log = rpt_path.read_text(encoding="utf-8", errors="replace") if rpt_path.exists() else ""

        periods = 0
        if out_path.exists():
            summary = OutputSummary.from_file(out_path)
            periods = summary.periods
            self._run_timestamps = self._run_timestamps_from_periods(periods)
            self._last_output_path = out_path
            self._output_file_cache = None
            self._results_stale = False
        else:
            self._run_timestamps = None
            self._last_output_path = None
            self._output_file_cache = None

        result = RunResult(
            success=error_code == 0,
            error_code=error_code,
            input_path=inp_path,
            report_path=rpt_path,
            output_path=out_path,
            periods=periods,
            engine_version=engine.version,
            validation=validation,
        )
        self._last_run_result = result
        return result

    def runs(self) -> Iterator[SimulationStep]:
        """Yield one simulation step at a time using the native SWMM lifecycle."""

        validation = self.validate()
        inp_path, rpt_path, out_path = self._prepare_run_files()
        engine = self._engine_loader.get()
        start, _report_start, _end = self._document.datetimes()

        # The session context closes the native project even if the caller breaks
        # out of the generator early or raises an exception inside the loop.
        with engine.session(inp_path, rpt_path, out_path) as session:
            index = 0
            while True:
                elapsed_days = session.step()
                if elapsed_days <= 0.0:
                    break
                index += 1
                yield SimulationStep(
                    index=index,
                    time=start + timedelta(days=elapsed_days),
                    elapsed_days=elapsed_days,
                )

        self._last_log = rpt_path.read_text(encoding="utf-8", errors="replace") if rpt_path.exists() else ""
        periods = 0
        error_code = 0
        if out_path.exists():
            summary = OutputSummary.from_file(out_path)
            periods = summary.periods
            error_code = summary.error_code
            self._run_timestamps = self._run_timestamps_from_periods(periods)
            self._last_output_path = out_path
            self._output_file_cache = None
            self._results_stale = False
        else:
            self._run_timestamps = None
            self._last_output_path = None
            self._output_file_cache = None

        self._last_run_result = RunResult(
            success=error_code == 0,
            error_code=error_code,
            input_path=inp_path,
            report_path=rpt_path,
            output_path=out_path,
            periods=periods,
            engine_version=engine.version,
            validation=validation,
        )

    def validate(self) -> ValidationResult:
        """Return built-in structural errors and warnings for the model."""

        return validate_document(self._document, has_results=self.has_run)

    def log(self) -> str:
        """Return the report/log text from the most recent completed run."""

        return self._last_log

    def clone(self) -> "SWMMModel":
        """Return an independent clone of the current model state."""

        # Public ``swmm`` construction now parses human-facing constructor
        # arguments, so cloning bypasses that path and copies the already-built
        # internal document directly.
        clone = self.__class__.__new__(self.__class__)
        SWMMModel.__init__(
            clone,
            self._document.copy(),
            source_path=self._source_path,
            engine_path=self._engine_loader.custom_path,
            schema_path=self.schema.path,
        )
        clone._dirty = self._dirty
        clone._results_stale = self._results_stale
        clone._parameter_overrides = {
            key: values.copy()
            for key, values in self._parameter_overrides.items()
        }
        return clone

    def add_element(self, category: str, element_type: str, id: str, **options):
        """Add one editable model element through the generic public fallback."""

        return self._editable_service.add(category, element_type, id, **options)

    def remove_element(self, category: str, element_type: str, ids, force: bool = False):
        """Remove editable model elements through the generic public fallback."""

        return self._editable_service.remove(category, element_type, ids, force=force)

    def plot_layout(
        self,
        legend: bool = True,
        grid: bool = False,
        title: str | None = None,
        legend_title: str | None = None,
        axis: bool = False,
        x_axis_title: str | None = None,
        y_axis_title: str | None = None,
        save_format: str | None = None,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (10, 8),
        dpi: int = 300,
        ax=None,
        show: bool = True,
        nodes=None,
        links=None,
        subcatchments=None,
        rain_gages=None,
        labels=None,
        link_color_by=None,
        link_color_mode=None,
        link_cmap=None,
        node_color_result=None,
        node_result_aggregation=None,
        link_user_data=None,
    ):
        """Plot the mapped SWMM network layout with matplotlib.

        Parameters
        ----------
        legend, grid, title, legend_title, axis, x_axis_title, y_axis_title:
            Common presentation controls.  Coordinate axes are hidden by
            default; legends are shown by default.
        save_format, save_path:
            Optional figure-saving controls.  Supplying only ``save_format``
            writes ``swmm_layout.<format>`` beside the model path when possible.
        figsize, dpi, ax, show:
            Standard matplotlib controls.  Supply ``ax`` to compose into an
            existing figure; use ``show=False`` in scripts and tests.
        nodes, links, subcatchments, rain_gages, labels:
            Optional layer dictionaries supporting static styling and, for the
            first three layers, data-driven color/size encodings.

        Examples
        --------
        >>> m.plot_layout()
        >>> m.plot_layout(
        ...     title="Network Layout",
        ...     nodes={"size": 40, "color": "black"},
        ...     links={"width": 1.5, "color": "gray"},
        ... )
        >>> m.plot_layout(
        ...     links={
        ...         "color": {
        ...             "by": "result",
        ...             "variable": "flow",
        ...             "aggregation": "max",
        ...             "mode": "continuous",
        ...         }
        ...     }
        ... )

        Returns
        -------
        tuple
            ``(fig, ax)`` for the matplotlib figure and axes.

        Notes
        -----
        Layout plots require usable mapped coordinates.  Result-driven styling
        requires a completed model run.
        """

        return render_layout(
            self,
            legend=legend,
            grid=grid,
            title=title,
            legend_title=legend_title,
            axis=axis,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            save_format=save_format,
            save_path=save_path,
            figsize=figsize,
            dpi=dpi,
            ax=ax,
            show=show,
            nodes=nodes,
            links=links,
            subcatchments=subcatchments,
            rain_gages=rain_gages,
            labels=labels,
            link_color_by=link_color_by,
            link_color_mode=link_color_mode,
            link_cmap=link_cmap,
            node_color_result=node_color_result,
            node_result_aggregation=node_result_aggregation,
            link_user_data=link_user_data,
        )

    def section(self, name: str):
        """Return tokenized rows for a supported section by name."""

        # Raw unknown sections are preserved during save, but explicit access to
        # unimplemented sections should fail loudly instead of implying support.
        supported = {
            "OPTIONS",
            "RAINGAGES",
            "SUBCATCHMENTS",
            "SUBAREAS",
            "INFILTRATION",
            "JUNCTIONS",
            "OUTFALLS",
            "CONDUITS",
            "XSECTIONS",
            "TIMESERIES",
            "CURVES",
            "PATTERNS",
            "DWF",
            "COORDINATES",
            "SYMBOLS",
            "POLYGONS",
            "VERTICES",
            "LOSSES",
        }
        key = name.upper()
        if key not in supported:
            raise NotImplementedYetError(
                f"Section [{name}] is preserved on disk but does not yet have a structured accessor."
            )
        return self._document.rows(key)


class swmm(SWMMModel):
    """Create or open an EPA SWMM model.

    Parameters
    ----------
    path:
        Optional path to an existing EPA SWMM ``.inp`` file.  When ``path`` is
        supplied, ``new`` and ``flow_unit`` must be omitted because the input
        file already defines the model and its unit system.
    new:
        Optional unit system for a newly-created model.  Use ``"SI"`` or
        ``"US"``.  If both ``path`` and ``new`` are omitted, ``"SI"`` is used.
    flow_unit:
        Optional flow unit for a new model only.  SI models accept ``"LPS"``
        (default), ``"CMS"``, or ``"MLD"``.  US models accept ``"CFS"``
        (default), ``"GPM"``, or ``"MGD"``.
    custom_dll_path:
        Optional path to a custom native SWMM engine library.  If omitted,
        ``swmmx`` lazily loads the bundled platform engine when a run begins.

    Examples
    --------
    >>> m = swmm("examples/example.inp")
    >>> m = swmm()
    >>> m = swmm(new="SI", flow_unit="CMS")
    >>> m = swmm(new="US", flow_unit="GPM")
    """

    def __init__(
        self,
        path: str | Path | None = None,
        new: Literal["SI", "US"] | str | None = None,
        flow_unit: Literal["LPS", "CMS", "MLD", "CFS", "GPM", "MGD"] | str | None = None,
        custom_dll_path: str | Path | None = None,
    ) -> None:
        """Build a model from either an input path or new-model settings.

        Parameters
        ----------
        path:
            Optional path to an existing EPA SWMM ``.inp`` file.  When ``path``
            is supplied, ``new`` and ``flow_unit`` must not be supplied.
        new:
            Optional unit system for a new model: ``"SI"`` or ``"US"``.  If no
            ``path`` and no ``new`` value are supplied, ``"SI"`` is used.
        flow_unit:
            Optional flow unit for new models only.  SI models accept ``"LPS"``
            (default), ``"CMS"``, and ``"MLD"``.  US models accept ``"CFS"``
            (default), ``"GPM"``, and ``"MGD"``.
        custom_dll_path:
            Optional path to a custom SWMM engine library.  If omitted, the
            bundled platform engine is loaded lazily when execution begins.
        """

        # Opening an existing model and creating a new one are deliberately
        # mutually exclusive operations, so mixed instructions fail early.
        if path is not None and new is not None:
            raise ValueError(
                "Use either 'path' to open an existing model or 'new' to create one, not both."
            )
        if path is not None and flow_unit is not None:
            raise ValueError(
                "'flow_unit' is only valid for new models. "
                "When opening an existing .inp file, its FLOW_UNITS option is used."
            )

        if path is not None:
            source = Path(path).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError(f"SWMM input file not found: '{source}'.")
            if not source.is_file():
                raise ValueError(f"SWMM input path must be a file, not a directory: '{source}'.")
            if source.suffix.lower() != ".inp":
                raise ValueError(f"SWMM input path must point to a '.inp' file: '{source}'.")
            document = InpDocument.from_path(source)
            super().__init__(
                document,
                source_path=source,
                engine_path=custom_dll_path,
            )
            return

        # With no file path, build a fresh model.  The unit system defaults to
        # SI so ``swmm()`` is a complete and useful constructor call.
        selected_system = "SI" if new is None else str(new).upper()
        if selected_system not in {"SI", "US"}:
            raise ValueError("'new' must be either 'SI' or 'US' when creating a new model.")

        allowed_units = FLOW_UNITS_SI if selected_system == "SI" else FLOW_UNITS_US
        default_unit = "LPS" if selected_system == "SI" else "CFS"
        selected_unit = default_unit if flow_unit is None else str(flow_unit).upper()
        if selected_unit not in allowed_units:
            allowed = ", ".join(sorted(allowed_units))
            raise ValueError(
                f"Invalid flow_unit '{flow_unit}' for a new {selected_system} model. "
                f"Use one of: {allowed}."
            )

        super().__init__(
            InpDocument.from_template(selected_unit),
            engine_path=custom_dll_path,
        )
