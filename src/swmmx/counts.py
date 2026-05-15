"""Discoverable element-count namespaces for :mod:`swmmx`."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import TYPE_CHECKING

import pandas as pd

from .errors import UnknownCategoryError
from .parameters import OBJECT_SECTIONS, api_name

if TYPE_CHECKING:
    from .api import SWMMModel


COMPOSITE_COUNT_CATEGORIES = {"node", "link"}


@dataclass(frozen=True)
class CountSpec:
    """One public countable category."""

    raw_category: str

    @property
    def api_category(self) -> str:
        """Return the Python-safe public category name."""

        return api_name(self.raw_category)


def count_specs(model: "SWMMModel") -> list[CountSpec]:
    """Return countable schema categories in schema order."""

    specs: list[CountSpec] = []
    seen: set[str] = set()
    for spec in model._parameter_catalog._specs.values():
        if spec.sub_category != "count":
            continue
        if spec.main_category not in OBJECT_SECTIONS or spec.main_category in seen:
            continue
        seen.add(spec.main_category)
        specs.append(CountSpec(spec.main_category))
    return specs


class CountCallable:
    """Inspectable callable backing ``m.count.<category>()``."""

    __signature__ = inspect.Signature(parameters=[])

    def __init__(self, model: "SWMMModel", spec: CountSpec) -> None:
        """Store the model/category pair and publish a helpful docstring."""

        self._model = model
        self._spec = spec
        self.__name__ = spec.api_category
        self.__doc__ = (
            f"Return the number of ``{spec.api_category}`` objects in the model.\n\n"
            "Parameters\n"
            "----------\n"
            "None\n"
            "    Count helpers do not accept ``ids`` or ``format``.\n\n"
            "Returns\n"
            "-------\n"
            "int\n"
            f"    Number of ``{spec.api_category}`` objects currently stored in the model.\n\n"
            "Examples\n"
            "--------\n"
            f">>> m.count.{spec.api_category}()\n\n"
            "Notes\n"
            "-----\n"
            "Counts reflect the current in-memory model, including add/remove edits that have not been saved yet."
        )

    def __call__(self) -> int:
        """Return one current category count."""

        return len(self._model._ids_for_category(self._spec.raw_category))


class CountRoot:
    """Root namespace exposed as ``m.count``."""

    def __init__(self, model: "SWMMModel") -> None:
        """Materialize public count helpers for IDE completion."""

        self._model = model
        self._specs = count_specs(model)
        self._specs_by_api = {spec.api_category: spec for spec in self._specs}
        for spec in self._specs:
            setattr(self, spec.api_category, CountCallable(model, spec))

    def __dir__(self) -> list[str]:
        """Expose countable categories plus model summaries."""

        return [*(spec.api_category for spec in self._specs), "model", "model_dict", "model_df"]

    def __getattr__(self, category_name: str):
        """Resolve one lazy category count helper."""

        spec = self._specs_by_api.get(category_name)
        if spec is None:
            raise UnknownCategoryError(f"Unknown count category '{category_name}'.")
        callable_object = CountCallable(self._model, spec)
        setattr(self, category_name, callable_object)
        return callable_object

    def _detail_specs(self) -> list[CountSpec]:
        """Return leaf-like categories used by model summary helpers."""

        return [spec for spec in self._specs if spec.raw_category not in COMPOSITE_COUNT_CATEGORIES]

    def model(self) -> int:
        """Return the total number of detailed model elements.

        Parameters
        ----------
        None
            The model summary count does not accept ``ids`` or ``format``.

        Returns
        -------
        int
            Total number of detailed element collections, excluding composite
            rollups such as ``node`` and ``link`` to avoid double counting.

        Examples
        --------
        >>> m.count.model()
        """

        return sum(len(self._model._ids_for_category(spec.raw_category)) for spec in self._detail_specs())

    def model_dict(self) -> dict[str, int]:
        """Return detailed model counts as a dictionary.

        Parameters
        ----------
        None
            The summary helper does not accept ``ids`` or ``format``.

        Returns
        -------
        dict[str, int]
            Mapping from detailed category name to current object count.

        Examples
        --------
        >>> m.count.model_dict()
        """

        return {
            spec.api_category: len(self._model._ids_for_category(spec.raw_category))
            for spec in self._detail_specs()
        }

    def model_df(self) -> pd.DataFrame:
        """Return detailed model counts as a two-column DataFrame.

        Parameters
        ----------
        None
            The summary helper does not accept ``ids`` or ``format``.

        Returns
        -------
        pandas.DataFrame
            DataFrame with ``category`` and ``count`` columns.

        Examples
        --------
        >>> m.count.model_df()
        """

        counts = self.model_dict()
        return pd.DataFrame({"category": list(counts), "count": list(counts.values())})
