"""Shared matplotlib helpers for the public plotting APIs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
        # ``set_axis_off`` hides ticks, spines, and labels while leaving artists
        # intact; this is the clean default for map-style layouts.
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
    if show:
        plt.show()

