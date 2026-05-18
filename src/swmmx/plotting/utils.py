"""Shared matplotlib helpers for the public plotting APIs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import warnings

import matplotlib.pyplot as plt

from ..errors import SaveError

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from ..api import SWMMModel


SUPPORTED_SAVE_FORMATS = {"png", "jpg", "jpeg", "pdf", "svg", "tiff"}


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
) -> None:
    """Apply shared title/grid/axis visibility behavior to one axes."""

    ensure_bool("grid", grid)
    ensure_bool("axis", axis)
    if title:
        ax.set_title(title)
    if axis:
        ax.set_axis_on()
        ax.grid(grid)
        if x_axis_title is not None:
            ax.set_xlabel(x_axis_title)
        if y_axis_title is not None:
            ax.set_ylabel(y_axis_title)
    elif grid:
        # ``axis=False`` means "hide coordinate furniture", not "discard a
        # requested reference grid".  Keep the axes technically on so the grid
        # can render, then remove ticks, labels, and spines from view.
        ax.set_axis_on()
        ax.grid(True)
        ax.tick_params(
            axis="both",
            which="both",
            bottom=False,
            left=False,
            labelbottom=False,
            labelleft=False,
        )
        for spine in ax.spines.values():
            spine.set_visible(False)
    else:
        # ``set_axis_off`` hides ticks, spines, and labels while leaving artists
        # intact; this is the clean default for map-style layouts.
        ax.grid(False)
        ax.set_axis_off()


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
