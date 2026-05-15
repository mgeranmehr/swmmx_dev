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
        # Aggregate sections in SWMM's ordinary object-group order for composite
        # categories such as ``node`` and ``link``.
        sections = OBJECT_SECTIONS.get(category)
        if sections is None:
            raise NotImplementedYetError(
                f"Object indexing for '{category}' is not implemented in version 0.0.7."
            )
        ids: list[str] = []
        for section_name in sections:
            ids.extend(self._document.section_ids(section_name))
        return list(dict.fromkeys(ids))

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

        if spec.source_kind == "result":
            return self._get_result_parameter(spec, ids=ids, format=format)
        if spec.source_kind == "derived":
            return self._get_derived_parameter(spec, ids=ids, format=format)
        if spec.source_kind == "mixed":
            raise NotImplementedYetError(
                f"'{spec.path}' has mixed source semantics and is not exposed in version 0.0.7."
            )

        # User/ref parameters that map directly to ordinary input columns can be
        # read from the preserving document without asking the native engine.
        field = INPUT_FIELDS.get(spec.key)
        if field is None:
            raise NotImplementedYetError(
                f"Structured access for '{spec.path}' is not implemented in version 0.0.7."
            )
        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        raw_values = self._document.get_field_values(
            field.section,
            field.field_index,
            selected_ids,
            id_index=field.id_index,
        )
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

        field = INPUT_FIELDS.get(spec.key)
        if field is None:
            raise NotImplementedYetError(
                f"Structured setting for '{spec.path}' is not implemented in version 0.0.7."
            )

        available_ids = self._ids_for_category(spec.main_category)
        selected_ids, _explicit_single = normalize_ids(ids, available_ids, spec.main_category)
        selected_values = normalize_values(value, len(selected_ids), spec.main_category)
        if spec.source_kind == "ref":
            self._validate_reference_values(field, selected_values, spec)

        self._document.set_field_values(
            field.section,
            field.field_index,
            dict(zip(selected_ids, [self._render_set_value(item, spec) for item in selected_values])),
            id_index=field.id_index,
        )
        self._dirty = True
        self._invalidate_results()
        return None

    def _get_option_parameter(self, spec: ParameterSpec):
        """Return one model-level option from `[OPTIONS]`."""

        option_key = OPTION_FIELDS.get(spec.sub_category)
        if option_key is None:
            raise NotImplementedYetError(
                f"Option mapping for '{spec.path}' is not implemented in version 0.0.7."
            )
        value = self._document.get_option(option_key)
        if value is None:
            raise KeyError(f"Required option '{option_key}' is not present in this model.")
        return coerce_value(value, spec.type)

    def _set_option_parameter(self, spec: ParameterSpec, value) -> None:
        """Write one model-level option back into `[OPTIONS]`."""

        option_key = OPTION_FIELDS.get(spec.sub_category)
        if option_key is None:
            raise NotImplementedYetError(
                f"Option mapping for '{spec.path}' is not implemented in version 0.0.7."
            )
        self._document.set_option(option_key, self._render_set_value(value, spec))
        self._dirty = True
        self._invalidate_results()

    def _render_set_value(self, value, spec: ParameterSpec) -> str:
        """Render Python values into ordinary SWMM input tokens."""

        # Boolean SWMM options are conventionally stored as YES/NO.  Keeping
        # that convention avoids writing Python's True/False spellings into INP.
        if "bool" in spec.type.lower() and isinstance(value, (bool, np.bool_)):
            return "YES" if bool(value) else "NO"
        return str(value)

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

        raise NotImplementedYetError(
            f"Derived computation for '{spec.path}' is not implemented in version 0.0.7."
        )

    def _get_result_parameter(self, spec: ParameterSpec, *, ids=None, format=None):
        """Read one result matrix from the latest binary SWMM output file."""

        if self._run_timestamps is None or self._last_output_path is None:
            raise ModelNotRunError(
                f"'{spec.path}' is a result variable. Run the model first with m.run()."
            )

        object_kind = RESULT_OBJECT_KIND.get(spec.main_category)
        if object_kind is None:
            raise NotImplementedYetError(
                f"Result access for '{spec.path}' is not implemented in version 0.0.7."
            )

        if self._output_file_cache is None or self._output_file_cache.path != self._last_output_path:
            self._output_file_cache = OutputFile(self._last_output_path)
        try:
            whole_matrix = self._output_file_cache.matrix(object_kind, spec.sub_category)
        except KeyError as exc:
            raise NotImplementedYetError(
                f"Result access for '{spec.path}' is not implemented in version 0.0.7."
            ) from exc

        # ``conduit`` is a subset of SWMM's broader link result block, while
        # ``junction`` and ``outfall`` are subsets of the node result block.
        result_ids = self._ids_for_category(object_kind)
        selected_ids, explicit_single = normalize_ids(ids, self._ids_for_category(spec.main_category), spec.main_category)
        column_indexes = [result_ids.index(object_id) for object_id in selected_ids]
        selected_matrix = whole_matrix[:, column_indexes]
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
            return np.asarray(values)
        if selected_format == "df":
            return pd.DataFrame([values], columns=selected_ids)
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

        missing = [str(value) for value in values if str(value) and str(value) not in valid_ids]
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

    def _composite_object_type(self, category: str, object_id: str) -> str:
        """Return the section-derived type for a composite node/link object."""

        section_names = OBJECT_SECTIONS[category]
        for section_name in section_names:
            if object_id in self._document.section_ids(section_name):
                return section_name.lower()
        raise KeyError(object_id)

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
    >>> m = swmm("example/example.inp")
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
