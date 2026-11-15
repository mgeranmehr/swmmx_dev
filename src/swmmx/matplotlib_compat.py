"""Small Matplotlib compatibility shims used by :mod:`swmmx`.

The package tries hard not to ask users to remember backend-specific plotting
workarounds.  This module contains narrowly-scoped fixes for Matplotlib issues
that affect normal SWMMX workflows in notebooks and IDEs.
"""

from __future__ import annotations

import copy
from typing import Any


def apply_matplotlib_compat() -> None:
    """Apply safe Matplotlib compatibility patches once.

    Some Python/Matplotlib combinations can recurse indefinitely when
    deep-copying ``matplotlib.path.Path`` objects.  The failure appears while
    drawing ticks, legends, or titles and surfaces as ``RecursionError`` inside
    ``Path.__deepcopy__``.  Matplotlib only needs a mutable copy of the path's
    arrays for this operation, so replacing that method with a direct copy of
    the stored vertices/codes preserves intended behavior without involving
    ``copy.deepcopy(super(), memo)``.
    """

    try:
        from matplotlib.path import Path
    except Exception:
        return

    if getattr(Path, "_swmmx_deepcopy_patch", False):
        return

    def _swmmx_path_deepcopy(self: Any, memo: dict[int, Any]):
        copied = Path(
            copy.deepcopy(self.vertices, memo),
            None if self.codes is None else copy.deepcopy(self.codes, memo),
            _interpolation_steps=getattr(self, "_interpolation_steps", 1),
            readonly=False,
        )
        memo[id(self)] = copied
        for name in ("_simplify_threshold", "_should_simplify"):
            if hasattr(self, name):
                setattr(copied, name, copy.deepcopy(getattr(self, name), memo))
        copied._readonly = False
        return copied

    Path.__deepcopy__ = _swmmx_path_deepcopy  # type: ignore[method-assign]
    Path._swmmx_deepcopy_patch = True  # type: ignore[attr-defined]

