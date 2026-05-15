"""Backward-compatible exception imports for :mod:`swmmx`.

The canonical hierarchy lives in :mod:`swmmx.core.errors`; this module remains
so existing code using ``from swmmx.errors import ...`` keeps working.
"""

from .core.errors import *  # noqa: F401,F403

