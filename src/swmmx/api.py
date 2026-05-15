"""The user-facing ``swmm`` API and the internal model implementation."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
from typing import Literal

from .engine import EngineLoader
from .errors import ModelNotRunError, NotImplementedYetError
from .inp import InpDocument
from .models import RunResult, SimulationStep, ValidationResult
from .results import OutputSummary
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

    def __delitem__(self, key: str) -> None:
        """Delete one option and mark the model as having unsaved changes."""

        self._model._document.delete_option(key)
        self._model._dirty = True

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

        # ``parameters.csv`` is a registry rather than guessed code in this
        # first release.  When the user provides it, the model exposes it.
        self.schema = SchemaRegistry.load(explicit_path=schema_path)

        # Public namespace helpers are concrete objects so IDE completion shows
        # ``vector``, ``count``, ``vector_run``, and ``count_run`` immediately.
        self.time = TimeAccessor(self)
        self.options = OptionView(self)

        # Run state is intentionally separate from input state so clones and
        # edits cannot accidentally masquerade as fresh results.
        self._run_timestamps: list | None = None
        self._last_run_result: RunResult | None = None
        self._last_log = ""
        self._runtime_directory: tempfile.TemporaryDirectory[str] | None = None

    @property
    def path(self) -> Path | None:
        """Return the current saved input path, if the model has one."""

        return self._source_path

    @property
    def has_run(self) -> bool:
        """Return whether run-dependent results are currently available."""

        return self._run_timestamps is not None

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

    def save(self, inp_path: str | Path) -> Path:
        """Save the current model to a valid EPA SWMM ``.inp`` file."""

        target = Path(inp_path).expanduser().resolve()

        # Creating parents is safe and convenient for normal save-as workflows.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._document.to_text(), encoding="utf-8")

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
        else:
            self._run_timestamps = None

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
        else:
            self._run_timestamps = None

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

        clone = self.__class__(
            self._document.copy(),
            source_path=self._source_path,
            engine_path=self._engine_loader.custom_path,
        )
        clone._dirty = self._dirty
        return clone

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
        }
        key = name.upper()
        if key not in supported:
            raise NotImplementedYetError(
                f"Section [{name}] is preserved on disk but does not yet have a structured accessor."
            )
        return self._document.rows(key)


class swmm(SWMMModel):
    """Public model class used as ``from swmmx import swmm``."""

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        engine_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> "swmm":
        """Open an existing EPA SWMM input file.

        Parameters
        ----------
        path:
            Path to an existing ``.inp`` file.
        engine_path:
            Optional custom native SWMM library path.  If omitted, the bundled
            platform engine is loaded lazily when ``run`` or ``runs`` is called.
        schema_path:
            Optional path to a ``parameters.csv`` schema registry.
        """

        source = Path(path).expanduser().resolve()
        document = InpDocument.from_path(source)
        return cls(document, source_path=source, engine_path=engine_path, schema_path=schema_path)

    @classmethod
    def new_SI(
        cls,
        flow_unit_SI: Literal["LPS", "CMS", "MLD"] = "LPS",
        *,
        engine_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> "swmm":
        """Create a new SI model.

        Parameters
        ----------
        flow_unit_SI:
            SI flow unit.  Allowed values are ``"LPS"`` (default), ``"CMS"``,
            and ``"MLD"``.
        """

        selected = flow_unit_SI.upper()
        if selected not in FLOW_UNITS_SI:
            raise ValueError(f"Invalid SI flow unit '{flow_unit_SI}'. Use one of {sorted(FLOW_UNITS_SI)}.")
        return cls(
            InpDocument.from_template(selected),
            engine_path=engine_path,
            schema_path=schema_path,
        )

    @classmethod
    def new_US(
        cls,
        flow_unit_US: Literal["CFS", "GPM", "MGD"] = "CFS",
        *,
        engine_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> "swmm":
        """Create a new US-customary model.

        Parameters
        ----------
        flow_unit_US:
            US-customary flow unit.  Allowed values are ``"CFS"`` (default),
            ``"GPM"``, and ``"MGD"``.
        """

        selected = flow_unit_US.upper()
        if selected not in FLOW_UNITS_US:
            raise ValueError(f"Invalid US flow unit '{flow_unit_US}'. Use one of {sorted(FLOW_UNITS_US)}.")
        return cls(
            InpDocument.from_template(selected),
            engine_path=engine_path,
            schema_path=schema_path,
        )
