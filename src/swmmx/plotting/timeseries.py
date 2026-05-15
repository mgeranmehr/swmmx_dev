"""Dynamic matplotlib time-series plotting namespaces."""

from __future__ import annotations

from pathlib import Path
import inspect
from typing import TYPE_CHECKING
import warnings

import numpy as np
import pandas as pd

from ..errors import (
    ModelNotRunError,
    ObjectNotFoundError,
    PlotDataError,
    UnknownCategoryError,
    UnknownIDError,
    UnknownParameterError,
)
from ..parameters import api_name
from .utils import apply_axes_options, create_axes, finalize_plot

if TYPE_CHECKING:
    from ..api import SWMMModel
    from ..parameters import ParameterSpec


SYSTEM_PARAMETERS = tuple(sorted(
    (
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
    )
))


def _time_series_specs(model: "SWMMModel") -> dict[str, dict[str, "ParameterSpec"]]:
    """Return public plotting categories limited to result time-series specs."""

    specs: dict[str, dict[str, "ParameterSpec"]] = {}
    for spec in model._parameter_catalog._specs.values():
        if spec.source_kind == "result" and spec.is_time_series:
            specs.setdefault(api_name(spec.main_category), {})[api_name(spec.sub_category)] = spec
    return specs


class PlotTimeseriesRoot:
    """Root namespace exposed as ``m.plot_timeseries``."""

    def __init__(self, model: "SWMMModel") -> None:
        """Materialize discoverable plotting categories for one model."""

        self._model = model
        self._specs = _time_series_specs(model)
        for category_name in self.__dir__():
            setattr(self, category_name, PlotTimeseriesCategory(model, category_name, self._specs.get(category_name, {})))

    def __dir__(self) -> list[str]:
        """Expose result-bearing categories for IDE completion."""

        return sorted([*self._specs, "system"])

    def __getattr__(self, category_name: str):
        """Return one plotting category or a clear lookup failure."""

        if category_name not in self.__dir__():
            raise UnknownCategoryError(f"Unknown time-series plotting category '{category_name}'.")
        namespace = PlotTimeseriesCategory(self._model, category_name, self._specs.get(category_name, {}))
        setattr(self, category_name, namespace)
        return namespace


class PlotTimeseriesCategory:
    """Namespace such as ``m.plot_timeseries.link``."""

    def __init__(self, model: "SWMMModel", category_name: str, specs: dict[str, "ParameterSpec"]) -> None:
        """Materialize plottable variable callables for one category."""

        self._model = model
        self._category_name = category_name
        self._specs = specs
        for variable in self.__dir__():
            setattr(self, variable, PlotTimeseriesCallable(model, category_name, variable, specs.get(variable)))

    def __dir__(self) -> list[str]:
        """Expose public variable names for IDE completion."""

        return list(SYSTEM_PARAMETERS) if self._category_name == "system" else sorted(self._specs)

    def __getattr__(self, variable: str):
        """Return one plotting callable or raise a plotting lookup error."""

        if variable not in self.__dir__():
            raise UnknownParameterError(
                f"Unknown time-series plotting parameter '{self._category_name}.{variable}'."
            )
        callable_object = PlotTimeseriesCallable(self._model, self._category_name, variable, self._specs.get(variable))
        setattr(self, variable, callable_object)
        return callable_object


class PlotTimeseriesCallable:
    """Inspectable callable backing one dynamic time-series endpoint."""

    __signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("ids", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
            inspect.Parameter("legend", inspect.Parameter.KEYWORD_ONLY, default=True),
            inspect.Parameter("grid", inspect.Parameter.KEYWORD_ONLY, default=True),
            inspect.Parameter("title", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("legend_title", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("axis", inspect.Parameter.KEYWORD_ONLY, default=True),
            inspect.Parameter("x_axis_title", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("y_axis_title", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("save_format", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("save_path", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("figsize", inspect.Parameter.KEYWORD_ONLY, default=(10, 4)),
            inspect.Parameter("dpi", inspect.Parameter.KEYWORD_ONLY, default=300),
            inspect.Parameter("ax", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("show", inspect.Parameter.KEYWORD_ONLY, default=True),
            inspect.Parameter("unit", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("time_format", inspect.Parameter.KEYWORD_ONLY, default="timestamp"),
            inspect.Parameter("start_time", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("end_time", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("labels", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("linewidth", inspect.Parameter.KEYWORD_ONLY, default=1.5),
            inspect.Parameter("linestyle", inspect.Parameter.KEYWORD_ONLY, default="-"),
            inspect.Parameter("marker", inspect.Parameter.KEYWORD_ONLY, default=None),
            inspect.Parameter("alpha", inspect.Parameter.KEYWORD_ONLY, default=1.0),
            inspect.Parameter("max_series", inspect.Parameter.KEYWORD_ONLY, default=None),
        ]
    )

    def __init__(self, model: "SWMMModel", category: str, variable: str, spec: "ParameterSpec | None") -> None:
        """Store routing metadata and publish a rich user-facing docstring."""

        self._model = model
        self._category = category
        self._variable = variable
        self._spec = spec
        self.__name__ = variable
        self.__doc__ = (
            f"Plot ``{category}.{variable}`` as one or more matplotlib time series.\n\n"
            "Parameters\n"
            "----------\n"
            "ids:\n"
            "    Optional object selector: ``None``, one ID string, or a list of ID strings.\n"
            "legend, grid, title, legend_title, axis, x_axis_title, y_axis_title:\n"
            "    Common presentation controls.  Time-series axes and grid are visible by default.\n"
            "save_format, save_path:\n"
            "    Optional save controls.  With only ``save_format``, files are named\n"
            f"    ``swmm_timeseries_{category}_{variable}.<format>``.\n"
            "unit, time_format, start_time, end_time, labels, linewidth, linestyle, marker, alpha, max_series:\n"
            "    Series filtering and line styling controls.\n\n"
            "Examples\n"
            "--------\n"
            ">>> m.plot_timeseries.link.flow([\"C1\", \"C2\"])\n\n"
            "Returns\n"
            "-------\n"
            "tuple\n"
            "    ``(fig, ax)`` for the matplotlib figure and axes.\n\n"
            "Notes\n"
            "-----\n"
            "Result variables require ``m.run()`` first.  Timestamp indexes are used by default."
        )

    def __call__(self, ids=None, **kwargs):
        """Execute one dynamic plotting route."""

        return plot_timeseries(
            self._model,
            self._category,
            self._variable,
            spec=self._spec,
            ids=ids,
            **kwargs,
        )


def _system_frame(model: "SWMMModel", variable: str) -> pd.DataFrame:
    """Return one system-wide output series as a one-column frame."""

    if not model.has_run or model._last_output_path is None:
        raise ModelNotRunError(
            f"'system.{variable}' is a result variable. Run the model with m.run() before plotting it."
        )
    if model._output_file_cache is None or model._output_file_cache.path != model._last_output_path:
        from ..results import OutputFile

        model._output_file_cache = OutputFile(model._last_output_path)
    try:
        values = model._output_file_cache.system_series(variable)
    except KeyError as exc:
        raise UnknownParameterError(f"Unknown time-series plotting parameter 'system.{variable}'.") from exc
    return pd.DataFrame(
        values,
        index=pd.DatetimeIndex(model._run_timestamps, name="time"),
        columns=[variable],
    )


def _result_frame(model: "SWMMModel", category: str, variable: str, spec, ids) -> pd.DataFrame:
    """Return one plottable result frame with plotting-friendly errors."""

    if spec is None:
        raise UnknownParameterError(f"Unknown time-series plotting parameter '{category}.{variable}'.")
    if not spec.is_time_series:
        raise PlotDataError(f"'{category}.{variable}' is not a time-dependent variable.")
    if spec.source_kind == "result" and not model.has_run:
        raise ModelNotRunError(
            f"'{category}.{variable}' is a result variable. Run the model with m.run() before plotting it."
        )
    if ids is not None:
        requested_ids = [ids] if isinstance(ids, str) else list(ids)
        available_ids = set(model._ids_for_category(category))
        missing = [object_id for object_id in requested_ids if object_id not in available_ids]
        if missing:
            raise UnknownIDError(f"Unknown {category} ID '{missing[0]}'.")
    try:
        getter = getattr(getattr(model.get, category), variable)
        frame = getter(ids=ids, format="df")
    except ObjectNotFoundError as exc:
        raise UnknownIDError(f"Unknown {category} ID.") from exc
    if not isinstance(frame, pd.DataFrame) or frame.shape[0] <= 1:
        raise PlotDataError(f"'{category}.{variable}' is not a time-dependent variable.")
    return frame


def _apply_time_filter(frame: pd.DataFrame, *, start_time, end_time) -> pd.DataFrame:
    """Filter a timestamp-indexed frame to the requested window."""

    filtered = frame
    if start_time is not None:
        filtered = filtered.loc[filtered.index >= pd.Timestamp(start_time)]
    if end_time is not None:
        filtered = filtered.loc[filtered.index <= pd.Timestamp(end_time)]
    if filtered.empty:
        raise PlotDataError("The requested time window does not contain any values.")
    return filtered


def _line_label(column: str, labels, index: int) -> str:
    """Resolve optional custom line labels from a mapping or sequence."""

    if labels is None:
        return column
    if isinstance(labels, dict):
        return str(labels.get(column, column))
    if isinstance(labels, (list, tuple)):
        if index >= len(labels):
            raise PlotDataError("Received fewer custom labels than plotted series.")
        return str(labels[index])
    raise TypeError("'labels' must be None, a dictionary, or a list/tuple.")


def plot_timeseries(
    model: "SWMMModel",
    category: str,
    variable: str,
    *,
    spec=None,
    ids=None,
    legend: bool = True,
    grid: bool = True,
    title: str | None = None,
    legend_title: str | None = None,
    axis: bool = True,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    save_format: str | None = None,
    save_path: str | Path | None = None,
    figsize: tuple[float, float] = (10, 4),
    dpi: int = 300,
    ax=None,
    show: bool = True,
    unit: str | None = None,
    time_format: str = "timestamp",
    start_time=None,
    end_time=None,
    labels=None,
    linewidth: float = 1.5,
    linestyle: str = "-",
    marker=None,
    alpha: float = 1.0,
    max_series: int | None = None,
):
    """Plot one routed result variable as one or more matplotlib time series."""

    frame = _system_frame(model, variable) if category == "system" else _result_frame(model, category, variable, spec, ids)
    frame = _apply_time_filter(frame, start_time=start_time, end_time=end_time)

    if max_series is not None and len(frame.columns) > max_series:
        raise PlotDataError(
            f"Requested {len(frame.columns)} series, which exceeds max_series={max_series}."
        )
    if ids is None and len(frame.columns) > 20:
        warnings.warn(
            f"Plotting {len(frame.columns)} series; consider passing ids=... or max_series=... for readability.",
            stacklevel=2,
        )

    fig, ax = create_axes(figsize=figsize, dpi=dpi, ax=ax)
    if time_format == "timestamp":
        x_values = frame.index
    elif time_format == "elapsed":
        x_values = (frame.index - frame.index[0]).total_seconds() / 3600.0
    else:
        raise PlotDataError("'time_format' must be 'timestamp' or 'elapsed'.")

    for index, column in enumerate(frame.columns):
        ax.plot(
            x_values,
            frame[column].to_numpy(dtype=float),
            label=_line_label(str(column), labels, index),
            linewidth=linewidth,
            linestyle=linestyle,
            marker=marker,
            alpha=alpha,
        )

    generated_title = title or f"{category.replace('_', ' ').title()} {variable.replace('_', ' ').title()}"
    generated_y_label = y_axis_title or f"{variable.replace('_', ' ').title()}{f' ({unit})' if unit else ''}"
    generated_x_label = x_axis_title or ("Time" if time_format == "timestamp" else "Elapsed Time (hours)")
    apply_axes_options(
        ax,
        grid=grid,
        axis=axis,
        title=generated_title,
        x_axis_title=generated_x_label,
        y_axis_title=generated_y_label,
    )
    if legend and len(frame.columns) > 0:
        ax.legend(title=legend_title)

    finalize_plot(
        fig,
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem=f"swmm_timeseries_{category}_{variable}",
        dpi=dpi,
        show=show,
    )
    return fig, ax
