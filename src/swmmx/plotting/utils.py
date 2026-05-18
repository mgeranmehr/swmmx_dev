"""Shared matplotlib helpers for the public plotting APIs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import warnings

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerPatch
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Patch

from ..errors import SaveError

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from ..api import SWMMModel


SUPPORTED_SAVE_FORMATS = {"png", "jpg", "jpeg", "pdf", "svg", "tiff"}


class SafeLineLegendProxy(Patch):
    """Primitive line metadata for legends that must not clone real Line2D artists."""

    def __init__(
        self,
        *,
        color,
        linewidth,
        linestyle,
        marker,
        markerfacecolor,
        markeredgecolor,
        markersize,
        alpha,
        label: str,
    ) -> None:
        """Store ordinary line properties for recursion-safe legend rendering."""

        super().__init__(facecolor="none", edgecolor="none", alpha=alpha, label=label)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.marker = marker
        self.markerfacecolor = markerfacecolor
        self.markeredgecolor = markeredgecolor
        self.markersize = markersize


class SafeLineLegendHandler(HandlerPatch):
    """Draw line legend proxies without deep-copying Matplotlib line markers."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        """Create one fresh primitive line artist for a safe legend entry."""

        artist = Line2D(
            [xdescent, xdescent + width],
            [(height - ydescent) / 2, (height - ydescent) / 2],
            color=orig_handle.color,
            linewidth=orig_handle.linewidth,
            linestyle=orig_handle.linestyle,
            marker=orig_handle.marker,
            markerfacecolor=orig_handle.markerfacecolor,
            markeredgecolor=orig_handle.markeredgecolor,
            markersize=orig_handle.markersize,
            alpha=orig_handle.get_alpha(),
        )
        artist.set_transform(trans)
        return [artist]


def _primitive_marker(marker):
    """Return an ordinary marker token instead of a nested MarkerStyle object."""

    primitive = marker.get_marker() if isinstance(marker, MarkerStyle) else marker
    return None if primitive in (None, "None", "", " ") else primitive


def _safe_line_legend_proxy(line) -> SafeLineLegendProxy:
    """Build one recursion-safe legend proxy from a plotted Line2D artist."""

    return SafeLineLegendProxy(
        color=line.get_color(),
        linewidth=line.get_linewidth(),
        linestyle=line.get_linestyle(),
        marker=_primitive_marker(line.get_marker()),
        markerfacecolor=line.get_markerfacecolor(),
        markeredgecolor=line.get_markeredgecolor(),
        markersize=line.get_markersize(),
        alpha=line.get_alpha(),
        label=line.get_label(),
    )


def add_safe_line_legend(ax, *, title: str | None = None, **kwargs):
    """Add a legend for visible plotted lines without using HandlerLine2D."""

    handles = [
        _safe_line_legend_proxy(line)
        for line in ax.lines
        if line.get_label() and not str(line.get_label()).startswith("_")
    ]
    if not handles:
        return None
    return ax.legend(
        handles=handles,
        title=title,
        handler_map={SafeLineLegendProxy: SafeLineLegendHandler()},
        **kwargs,
    )


def ensure_bool(name: str, value: bool) -> bool:
    """Return one boolean option or raise a clear validation error."""

    if not isinstance(value, bool):
        raise TypeError(f"'{name}' must be True or False.")
    return value


def create_axes(*, figsize: tuple[float, float], dpi: int, ax=None):
    """Return a matplotlib figure/axes pair, reusing supplied axes when given."""

    # Supplying ``ax`` is the standard matplotlib composition escape hatch.
    # When it is present, its owning figure controls size and DPI already, so
    # the helper simply returns that existing pair unchanged.
    if ax is not None:
        return ax.figure, ax
    fig, created_ax = plt.subplots(figsize=figsize, dpi=dpi)
    return fig, created_ax


def apply_axes_options(
    ax,
    *,
    grid: bool,
    axis: bool,
    title: str | None,
    x_axis_title: str | None,
    y_axis_title: str | None,
    safe_layout_axes: bool = False,
    safe_cartesian_axes: bool = False,
) -> None:
    """Apply shared axis options, with native-axis-free modes where needed."""

    ensure_bool("grid", grid)
    ensure_bool("axis", axis)
    if safe_layout_axes and safe_cartesian_axes:
        raise ValueError("Only one safe axis mode can be enabled at a time.")
    if not safe_layout_axes and not safe_cartesian_axes:
        ax.grid(grid)
        if title:
            ax.set_title(title)
        if axis:
            ax.set_axis_on()
            if x_axis_title is not None:
                ax.set_xlabel(x_axis_title)
            if y_axis_title is not None:
                ax.set_ylabel(y_axis_title)
        else:
            ax.set_axis_off()
        return

    if safe_cartesian_axes:
        _apply_safe_cartesian_axes(
            ax,
            grid=grid,
            axis=axis,
            title=title,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
        )
        return

    # The layout map keeps Matplotlib's native Axis artists off in every mode.
    # In some Spyder/Agg stacks, merely asking native ticks or grids to draw can
    # recurse inside MarkerStyle deepcopy.  We therefore render the visible map
    # grid / frame / labels with ordinary Line2D and Text artists instead.
    _remove_safe_axis_artists(ax)
    x_limits = ax.get_xlim()
    y_limits = ax.get_ylim()
    ax.grid(False)
    ax.set_axis_off()
    if grid:
        _add_safe_layout_grid(ax, x_limits=x_limits, y_limits=y_limits)
    if axis:
        _add_safe_layout_axis(
            ax,
            x_limits=x_limits,
            y_limits=y_limits,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
        )
    if title:
        _add_safe_axes_title(ax, title, label="_swmmx_layout_title")


def _remove_safe_axis_artists(ax) -> None:
    """Remove any previously drawn safe map-axis artists before redrawing."""

    safe_labels = {
        "_swmmx_layout_title",
        "_swmmx_cartesian_title",
        "_swmmx_grid",
        "_swmmx_axis_frame",
        "_swmmx_axis_tick",
        "_swmmx_axis_tick_label",
        "_swmmx_axis_label",
    }
    for artist in [*ax.lines, *ax.texts]:
        if artist.get_label() in safe_labels:
            artist.remove()


def _linear_positions(lower: float, upper: float, count: int = 5) -> list[float]:
    """Return evenly spaced coordinate positions without invoking tick locators."""

    if lower == upper:
        return [lower]
    return [lower + (upper - lower) * index / (count - 1) for index in range(count)]


def _format_axis_value(value: float) -> str:
    """Format one coordinate label compactly for layout maps."""

    return f"{value:.6g}"


def _add_safe_layout_grid(ax, *, x_limits: tuple[float, float], y_limits: tuple[float, float]) -> None:
    """Draw a reference grid without enabling Matplotlib's native Axis artists."""

    xmin, xmax = x_limits
    ymin, ymax = y_limits
    for x_value in _linear_positions(xmin, xmax):
        ax.plot(
            [x_value, x_value],
            [ymin, ymax],
            color="0.85",
            linewidth=0.8,
            linestyle="-",
            zorder=0,
            label="_swmmx_grid",
        )
    for y_value in _linear_positions(ymin, ymax):
        ax.plot(
            [xmin, xmax],
            [y_value, y_value],
            color="0.85",
            linewidth=0.8,
            linestyle="-",
            zorder=0,
            label="_swmmx_grid",
        )
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)


def _add_safe_layout_axis(
    ax,
    *,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    x_axis_title: str | None,
    y_axis_title: str | None,
) -> None:
    """Draw frame, ticks, tick labels, and axis titles with safe artists."""

    xmin, xmax = x_limits
    ymin, ymax = y_limits
    x_span = xmax - xmin or 1.0
    y_span = ymax - ymin or 1.0
    tick_x_length = 0.012 * x_span
    tick_y_length = 0.012 * y_span
    frame_segments = [
        ([xmin, xmax], [ymin, ymin]),
        ([xmin, xmax], [ymax, ymax]),
        ([xmin, xmin], [ymin, ymax]),
        ([xmax, xmax], [ymin, ymax]),
    ]
    for x_values, y_values in frame_segments:
        ax.plot(
            x_values,
            y_values,
            color="black",
            linewidth=0.8,
            zorder=6,
            label="_swmmx_axis_frame",
        )
    for x_value in _linear_positions(xmin, xmax):
        ax.plot(
            [x_value, x_value],
            [ymin, ymin - tick_y_length],
            color="black",
            linewidth=0.8,
            clip_on=False,
            zorder=6,
            label="_swmmx_axis_tick",
        )
        ax.text(
            x_value,
            ymin - 2.1 * tick_y_length,
            _format_axis_value(x_value),
            ha="center",
            va="top",
            clip_on=False,
            fontsize=8,
            label="_swmmx_axis_tick_label",
        )
    for y_value in _linear_positions(ymin, ymax):
        ax.plot(
            [xmin, xmin - tick_x_length],
            [y_value, y_value],
            color="black",
            linewidth=0.8,
            clip_on=False,
            zorder=6,
            label="_swmmx_axis_tick",
        )
        ax.text(
            xmin - 2.1 * tick_x_length,
            y_value,
            _format_axis_value(y_value),
            ha="right",
            va="center",
            clip_on=False,
            fontsize=8,
            label="_swmmx_axis_tick_label",
        )
    if x_axis_title is not None:
        ax.text(
            0.5,
            -0.10,
            x_axis_title,
            transform=ax.transAxes,
            ha="center",
            va="top",
            clip_on=False,
            label="_swmmx_axis_label",
        )
    if y_axis_title is not None:
        ax.text(
            -0.10,
            0.5,
            y_axis_title,
            transform=ax.transAxes,
            ha="right",
            va="center",
            rotation=90,
            clip_on=False,
            label="_swmmx_axis_label",
        )
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)


def _add_hidden_axis_title(ax, title: str) -> None:
    """Deprecated compatibility wrapper for the original layout-title helper."""

    _add_safe_axes_title(ax, title, label="_swmmx_layout_title")


def _add_safe_axes_title(ax, title: str, *, label: str) -> None:
    """Draw a title without activating Matplotlib's axis-title solver."""

    # ``Axes.set_title`` asks Matplotlib to inspect y-axis tick labels during
    # draw-time title positioning even when a map intentionally hides its axes.
    # Some Spyder/Agg combinations recurse while copying those hidden tick
    # markers.  Ordinary text in axes coordinates gives the same visible title
    # without waking the hidden-axis tick machinery.
    for existing_text in list(ax.texts):
        if existing_text.get_label() == label:
            existing_text.remove()
    ax.set_title("")
    ax.text(
        0.5,
        1.02,
        title,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        clip_on=False,
        fontproperties=ax.title.get_fontproperties(),
        color=ax.title.get_color(),
        label=label,
    )


def _apply_safe_cartesian_axes(
    ax,
    *,
    grid: bool,
    axis: bool,
    title: str | None,
    x_axis_title: str | None,
    y_axis_title: str | None,
) -> None:
    """Render ordinary chart axes without drawing Matplotlib Axis artists."""

    _remove_safe_axis_artists(ax)
    x_limits = ax.get_xlim()
    y_limits = ax.get_ylim()
    x_ticks = _visible_ticks(ax.get_xticks(), x_limits)
    y_ticks = _visible_ticks(ax.get_yticks(), y_limits)
    x_labels = _format_ticks(ax.xaxis, x_ticks)
    y_labels = _format_ticks(ax.yaxis, y_ticks)

    ax.grid(False)
    ax.set_title("")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_axis_off()

    if grid:
        _add_safe_cartesian_grid(ax, x_limits=x_limits, y_limits=y_limits, x_ticks=x_ticks, y_ticks=y_ticks)
    if axis:
        _add_safe_cartesian_axis(
            ax,
            x_limits=x_limits,
            y_limits=y_limits,
            x_ticks=x_ticks,
            y_ticks=y_ticks,
            x_labels=x_labels,
            y_labels=y_labels,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
        )
    if title:
        _add_safe_axes_title(ax, title, label="_swmmx_cartesian_title")


def _visible_ticks(values, limits: tuple[float, float]) -> list[float]:
    """Return visible locator ticks, falling back to evenly spaced values."""

    lower, upper = limits
    minimum, maximum = sorted((float(lower), float(upper)))
    span = maximum - minimum or 1.0
    tolerance = span * 1e-9
    visible = [float(value) for value in values if minimum - tolerance <= float(value) <= maximum + tolerance]
    return visible or _linear_positions(lower, upper)


def _format_ticks(axis, ticks: list[float]) -> list[str]:
    """Format numeric or datetime-like tick values without creating Tick artists."""

    formatter = axis.get_major_formatter()
    try:
        formatter.set_locs(ticks)
    except Exception:
        pass
    try:
        return [str(value) for value in formatter.format_ticks(ticks)]
    except Exception:
        return [_format_axis_value(value) for value in ticks]


def _add_safe_cartesian_grid(
    ax,
    *,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    x_ticks: list[float],
    y_ticks: list[float],
) -> None:
    """Draw an ordinary chart grid without native Matplotlib Axis artists."""

    xmin, xmax = x_limits
    ymin, ymax = y_limits
    for x_value in x_ticks:
        ax.plot(
            [x_value, x_value],
            [ymin, ymax],
            color="0.85",
            linewidth=0.8,
            linestyle="-",
            zorder=0,
            label="_swmmx_grid",
        )
    for y_value in y_ticks:
        ax.plot(
            [xmin, xmax],
            [y_value, y_value],
            color="0.85",
            linewidth=0.8,
            linestyle="-",
            zorder=0,
            label="_swmmx_grid",
        )
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)


def _add_safe_cartesian_axis(
    ax,
    *,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    x_ticks: list[float],
    y_ticks: list[float],
    x_labels: list[str],
    y_labels: list[str],
    x_axis_title: str | None,
    y_axis_title: str | None,
) -> None:
    """Draw frame, tick marks, labels, and titles for ordinary charts."""

    xmin, xmax = x_limits
    ymin, ymax = y_limits
    x_span = xmax - xmin or 1.0
    y_span = ymax - ymin or 1.0
    tick_x_length = 0.012 * x_span
    tick_y_length = 0.018 * y_span
    frame_segments = [
        ([xmin, xmax], [ymin, ymin]),
        ([xmin, xmax], [ymax, ymax]),
        ([xmin, xmin], [ymin, ymax]),
        ([xmax, xmax], [ymin, ymax]),
    ]
    for x_values, y_values in frame_segments:
        ax.plot(
            x_values,
            y_values,
            color="black",
            linewidth=0.8,
            zorder=6,
            label="_swmmx_axis_frame",
        )
    for x_value, text_value in zip(x_ticks, x_labels):
        ax.plot(
            [x_value, x_value],
            [ymin, ymin - tick_y_length],
            color="black",
            linewidth=0.8,
            clip_on=False,
            zorder=6,
            label="_swmmx_axis_tick",
        )
        ax.text(
            x_value,
            ymin - 2.0 * tick_y_length,
            text_value,
            ha="center",
            va="top",
            clip_on=False,
            fontsize=8,
            label="_swmmx_axis_tick_label",
        )
    for y_value, text_value in zip(y_ticks, y_labels):
        ax.plot(
            [xmin, xmin - tick_x_length],
            [y_value, y_value],
            color="black",
            linewidth=0.8,
            clip_on=False,
            zorder=6,
            label="_swmmx_axis_tick",
        )
        ax.text(
            xmin - 2.0 * tick_x_length,
            y_value,
            text_value,
            ha="right",
            va="center",
            clip_on=False,
            fontsize=8,
            label="_swmmx_axis_tick_label",
        )
    if x_axis_title is not None:
        ax.text(
            0.5,
            -0.16,
            x_axis_title,
            transform=ax.transAxes,
            ha="center",
            va="top",
            clip_on=False,
            label="_swmmx_axis_label",
        )
    if y_axis_title is not None:
        ax.text(
            -0.10,
            0.5,
            y_axis_title,
            transform=ax.transAxes,
            ha="right",
            va="center",
            rotation=90,
            clip_on=False,
            label="_swmmx_axis_label",
        )
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)


def resolve_save_target(
    model: "SWMMModel",
    *,
    save_path: str | Path | None,
    save_format: str | None,
    default_stem: str,
) -> tuple[Path | None, str | None]:
    """Resolve user save options into a concrete path and format."""

    if save_path is None and save_format is None:
        return None, None

    explicit_format = save_format.lower().lstrip(".") if save_format else None
    if explicit_format is not None and explicit_format not in SUPPORTED_SAVE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_SAVE_FORMATS))
        raise SaveError(f"Unsupported save_format '{save_format}'. Use one of: {supported}.")

    if save_path is None:
        base_directory = model.path.parent if model.path is not None else Path.cwd()
        chosen_format = explicit_format or "png"
        target = base_directory / f"{default_stem}.{chosen_format}"
        return target.resolve(), chosen_format

    target = Path(save_path).expanduser()
    # Existing directories are unambiguous folder targets.  The generated
    # filename keeps repeated plotting calls predictable and discoverable.
    if target.exists() and target.is_dir():
        chosen_format = explicit_format or "png"
        return (target / f"{default_stem}.{chosen_format}").resolve(), chosen_format

    suffix_format = target.suffix.lower().lstrip(".") if target.suffix else None
    if suffix_format and suffix_format not in SUPPORTED_SAVE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_SAVE_FORMATS))
        raise SaveError(
            f"Unsupported save path extension '.{suffix_format}'. Use one of: {supported}."
        )
    chosen_format = explicit_format or suffix_format or "png"
    if chosen_format not in SUPPORTED_SAVE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_SAVE_FORMATS))
        raise SaveError(f"Unsupported save format '{chosen_format}'. Use one of: {supported}.")
    if not target.suffix:
        target = target.with_suffix(f".{chosen_format}")
    return target.resolve(), chosen_format


def save_figure(
    fig,
    model: "SWMMModel",
    *,
    save_path: str | Path | None,
    save_format: str | None,
    default_stem: str,
    dpi: int,
) -> Path | None:
    """Save a figure when requested and return the written path if any."""

    target, resolved_format = resolve_save_target(
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem=default_stem,
    )
    if target is None:
        return None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(target, format=resolved_format, dpi=dpi, bbox_inches="tight")
    except OSError as exc:
        raise SaveError(f"Could not save plot to '{target}': {exc}") from exc
    except ValueError as exc:
        raise SaveError(f"Could not save plot to '{target}': {exc}") from exc
    return target


def finalize_plot(
    fig,
    model: "SWMMModel",
    *,
    save_path: str | Path | None,
    save_format: str | None,
    default_stem: str,
    dpi: int,
    show: bool,
    close_if_hidden: bool = False,
) -> None:
    """Apply shared save/show behavior after plot artists are assembled."""

    ensure_bool("show", show)
    save_figure(
        fig,
        model,
        save_path=save_path,
        save_format=save_format,
        default_stem=default_stem,
        dpi=dpi,
    )
    backend_name = fig.canvas.__class__.__name__.lower()
    canvas_supports_gui_show = "agg" not in backend_name or "nbagg" in backend_name or "webagg" in backend_name
    if show and canvas_supports_gui_show:
        # Prefer the concrete figure over pyplot's global manager.  Some rich
        # interactive backends can recurse while copying pyplot manager state;
        # the plot itself is already complete, so a backend show failure should
        # not make the plotting API unusable.
        try:
            fig.show()
        except RecursionError:
            warnings.warn(
                "The active matplotlib backend raised a recursion error while displaying the figure. "
                "The figure was created successfully and is still returned; use show=False or display it manually.",
                stacklevel=2,
            )
    elif close_if_hidden:
        # Inline notebook backends can display any still-open figure at the end
        # of a cell even when the library never calls ``show``.  Removing the
        # figure from pyplot's manager keeps ``show=False`` honest while the
        # returned Figure/Axes objects remain fully usable by the caller.
        import matplotlib.pyplot as plt

        plt.close(fig)
