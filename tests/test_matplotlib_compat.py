"""Regression tests for Matplotlib compatibility shims."""

from __future__ import annotations

import copy

import swmmx  # noqa: F401 - importing applies the compatibility patch
from matplotlib.path import Path


def test_swmmx_patches_matplotlib_path_deepcopy():
    path = Path.unit_circle()

    copied = copy.deepcopy(path)

    assert getattr(Path, "_swmmx_deepcopy_patch", False)
    assert isinstance(copied, Path)
    assert copied is not path
    assert copied.vertices.shape == path.vertices.shape
    assert copied.codes.shape == path.codes.shape
    assert not copied.readonly

