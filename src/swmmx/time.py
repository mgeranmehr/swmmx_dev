"""Time-vector accessors exposed as ``m.time``."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from .errors import ModelNotRunError

if TYPE_CHECKING:
    from .api import SWMMModel


VectorFormat = Literal["np", "df"]


class TimeAccessor:
    """Namespace object that makes ``m.time.<method>`` discoverable in IDEs."""

    def __init__(self, model: "SWMMModel") -> None:
        """Bind the accessor to exactly one model instance."""

        self._model = model

    def vector(self, format: VectorFormat | None = None):
        """Return expected report timestamps before a run.

        Parameters
        ----------
        format:
            ``"np"`` (default) returns a NumPy ``datetime64`` vector.
            ``"df"`` returns a pandas ``DataFrame`` with a timestamp index.
        """

        # The model owns the datetime calculation so the run-time and pre-run
        # accessors use the same rules.
        timestamps = self._model._expected_timestamps()
        return self._format(timestamps, format)

    def count(self) -> int:
        """Return the expected report-period count before a run."""

        # Counting the vector itself avoids a second, subtly different formula.
        return len(self._model._expected_timestamps())

    def vector_run(self, format: VectorFormat | None = None):
        """Return actual report timestamps after a completed run."""

        if self._model._run_timestamps is None:
            raise ModelNotRunError("Run-time timestamps are unavailable until the model has been run.")
        return self._format(self._model._run_timestamps, format)

    def count_run(self) -> int:
        """Return the actual report-period count after a completed run."""

        if self._model._run_timestamps is None:
            raise ModelNotRunError("Run-time timestamps are unavailable until the model has been run.")
        return len(self._model._run_timestamps)

    @staticmethod
    def _format(timestamps, format: VectorFormat | None):
        """Render one timestamp sequence in the requested public format."""

        selected = "np" if format is None else format
        if selected == "np":
            return np.asarray(timestamps, dtype="datetime64[ns]")
        if selected == "df":
            index = pd.DatetimeIndex(timestamps, name="time")
            return pd.DataFrame(index=index)
        raise ValueError("Unsupported time vector format. Use 'np' or 'df'.")


def build_timestamps(report_start, end, report_step, periods: int | None = None):
    """Build SWMM-style report timestamps from input options and a period count."""

    # SWMM's first reported value arrives after one report interval rather than
    # at the report-start instant itself.  When ``periods`` is omitted, keep
    # stepping until the next candidate would exceed ``END_*``.
    timestamps = []
    current = report_start + report_step

    if periods is None:
        while current <= end:
            timestamps.append(current)
            current += report_step
        return timestamps

    for _ in range(periods):
        timestamps.append(current)
        current += report_step
    return timestamps


def parse_duration(value: str) -> timedelta:
    """Parse common SWMM time-step strings into a ``timedelta``."""

    # ``REPORT_STEP`` conventionally uses ``HH:MM:SS``.  The parser also accepts
    # one- or two-digit hour fields because SWMM files often use both forms.
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid SWMM duration '{value}'. Expected HH:MM:SS.")
    hours, minutes, seconds = (int(float(part)) for part in parts)
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)

