"""Generate the public get/set API reference notebooks for the examples suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from swmmx import swmm
from swmmx.parameters import OBJECT_SECTIONS, api_name


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"
GET_NOTEBOOK = ROOT / "examples" / "11_all_get_functions.ipynb"
SET_NOTEBOOK = ROOT / "examples" / "12_all_set_functions.ipynb"


CATEGORY_GROUPS = [
    (
        "Model options",
        [
            "option_general",
            "option_process",
            "option_date_time",
            "option_dynamic_wave",
        ],
    ),
    (
        "Climate and rainfall",
        [
            "climate",
            "climate_adjustment",
            "rain_gage",
        ],
    ),
    (
        "Hydrology and catchments",
        [
            "subcatchment",
            "infiltration_horton",
            "infiltration_green_ampt",
            "infiltration_curve_number",
            "aquifer",
            "groundwater",
            "snow_pack",
            "unit_hydrograph",
            "lid_control",
            "lid_surface",
            "lid_pavement",
            "lid_soil",
            "lid_storage",
            "lid_drain",
            "lid_usage",
        ],
    ),
    (
        "Nodes",
        [
            "node",
            "junction",
            "outfall",
            "flow_divider",
            "storage_unit",
        ],
    ),
    (
        "Links and conveyance",
        [
            "link",
            "conduit",
            "cross_section",
            "pump",
            "orifice",
            "weir",
            "outlet",
        ],
    ),
    (
        "Inlets and hydraulic geometry",
        [
            "street",
            "inlet",
            "inlet_usage",
            "transect",
        ],
    ),
    (
        "Water quality",
        [
            "pollutant",
            "land_use",
            "coverage",
            "loading",
            "buildup",
            "washoff",
            "treatment",
        ],
    ),
    (
        "Time, curves, controls, and inflows",
        [
            "time_series",
            "time_pattern",
            "curve",
            "control_rule",
            "external_inflow",
            "dry_weather_flow",
            "rdii",
            "interface_file",
        ],
    ),
    (
        "Map data, summaries, and system results",
        [
            "coordinate",
            "summary",
            "system_result",
        ],
    ),
]


def _md(text: str) -> dict:
    """Return one markdown notebook cell."""

    return {"cell_type": "markdown", "metadata": {}, "source": text}


def _code(text: str) -> dict:
    """Return one code notebook cell."""

    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text,
    }


def _escape(value: object) -> str:
    """Escape one table value for markdown."""

    text = str(value or "—")
    return text.replace("|", "\\|").replace("\n", "<br>")


def _grouped_categories(all_categories: Iterable[str]) -> list[tuple[str, list[str]]]:
    """Return the documented group order plus a safe fallback group."""

    all_categories = list(all_categories)
    seen: set[str] = set()
    grouped: list[tuple[str, list[str]]] = []
    for title, category_names in CATEGORY_GROUPS:
        present = [name for name in category_names if name in all_categories]
        if present:
            grouped.append((title, present))
            seen.update(present)

    remaining = [name for name in all_categories if name not in seen]
    if remaining:
        grouped.append(("Other public categories", remaining))
    return grouped


def _specs_for_category(model, raw_category: str):
    """Return one category's specs in public-name order."""

    specs = [
        spec
        for spec in model._parameter_catalog._specs.values()
        if spec.main_category == raw_category
    ]
    return sorted(specs, key=lambda spec: api_name(spec.sub_category))


def _getter_call(raw_category: str, sub_category: str) -> str:
    """Return a copy-ready getter call signature."""

    category_name = api_name(raw_category)
    sub_name = api_name(sub_category)
    if raw_category in OBJECT_SECTIONS:
        return f"m.get.{category_name}.{sub_name}(ids=None, format=None)"
    return f"m.get.{category_name}.{sub_name}(format=None)"


def _setter_call(raw_category: str, sub_category: str) -> str:
    """Return a copy-ready setter call signature."""

    category_name = api_name(raw_category)
    sub_name = api_name(sub_category)
    if raw_category in OBJECT_SECTIONS:
        return f"m.set.{category_name}.{sub_name}(value, ids=None)"
    return f"m.set.{category_name}.{sub_name}(value)"


def _getter_output_note(spec) -> str:
    """Describe the practical getter output shape."""

    if spec.sub_category == "count":
        return "`int` scalar count"
    if spec.source_kind == "result":
        return "Time series; NumPy by default, or timestamp-indexed DataFrame with `format='df'`"
    if spec.main_category in OBJECT_SECTIONS:
        return "One ID → scalar/structured value; many/all IDs → NumPy array or one-row DataFrame"
    return "Model-level scalar, sequence, mapping, or table depending on the declared type"


def _setter_value_note(spec) -> str:
    """Describe the setter input shape users should prepare."""

    lowered_size = spec.size.lower()
    lowered_type = spec.type.lower()
    if not spec.is_writable:
        return "Read-only; setter raises `ReadOnlyParameterError`"
    if spec.main_category not in OBJECT_SECTIONS:
        return f"One model-level `{_escape(spec.type)}` value"
    if "pair" in lowered_size or "coordinates" in lowered_type:
        return "One coordinate pair per selected ID"
    if any(token in lowered_size for token in ("sequence", "list", "table")):
        return f"One structured `{_escape(spec.type)}` value per selected ID"
    return f"`{_escape(spec.type)}` scalar, or 1D vector/Series matching selected IDs"


def _setter_behavior_note(spec) -> str:
    """Describe whether the setter writes data or rejects the call."""

    if not spec.is_writable:
        noun = "result" if spec.source_kind == "result" else spec.source_kind
        return f"Read-only `{noun}` parameter"
    if spec.source_kind == "ref":
        return "Writable reference; target IDs are validated where possible"
    if spec.main_category in OBJECT_SECTIONS:
        return "Writable; scalar inputs broadcast across selected IDs"
    return "Writable model-level value"


def _category_markdown(model, raw_category: str, mode: str) -> str:
    """Build one rich markdown section for one public category."""

    category_name = api_name(raw_category)
    specs = _specs_for_category(model, raw_category)
    object_note = (
        "Object collection"
        if raw_category in OBJECT_SECTIONS
        else "Model-level category"
    )
    lines = [f"### `{category_name}`", "", f"**Kind:** {object_note}", ""]

    if mode == "get":
        lines.extend(
            [
                "| Getter | Source | Declared type | Declared size | Output note |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for spec in specs:
            lines.append(
                "| `"
                + _getter_call(spec.main_category, spec.sub_category)
                + "` | "
                + _escape(spec.source)
                + " | "
                + _escape(spec.type)
                + " | "
                + _escape(spec.size)
                + " | "
                + _getter_output_note(spec)
                + " |"
            )
        lines.extend(["", "Copy-ready call list:", "", "```python"])
        lines.extend(_getter_call(spec.main_category, spec.sub_category) for spec in specs)
        lines.append("```")
        return "\n".join(lines)

    lines.extend(
        [
            "| Setter | Source | Declared type | Value input | Behavior |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for spec in specs:
        lines.append(
            "| `"
            + _setter_call(spec.main_category, spec.sub_category)
            + "` | "
            + _escape(spec.source)
            + " | "
            + _escape(spec.type)
            + " | "
            + _setter_value_note(spec)
            + " | "
            + _setter_behavior_note(spec)
            + " |"
        )
    lines.extend(["", "Copy-ready call list:", "", "```python"])
    for spec in specs:
        suffix = "" if spec.is_writable else "  # read-only: raises ReadOnlyParameterError"
        lines.append(_setter_call(spec.main_category, spec.sub_category) + suffix)
    lines.append("```")
    return "\n".join(lines)


def _get_notebook(model) -> dict:
    """Build the complete getter reference notebook."""

    categories = [api_name(raw) for raw in model._parameter_catalog._subcategories_by_api_name]
    category_lookup = {
        api_name(raw): raw
        for raw in model._parameter_catalog._subcategories_by_api_name
    }
    cells = [
        _md(
            "# swmmx: all `get` functions\n\n"
            "This notebook is a categorized reference for every public getter available in `swmmx`.\n\n"
            "Getter pattern:\n\n"
            "```python\n"
            "m.get.<main_category>.<sub_category>(ids=None, format=None)\n"
            "```\n\n"
            "- For object collections, `ids` can be `None`, one string ID, or a list of string IDs.\n"
            "- `format=None` defaults to NumPy-style output; `format='df'` requests pandas output.\n"
            "- A single explicit ID usually returns a scalar or one structured value.\n"
            "- Multiple IDs or `ids=None` usually return arrays/DataFrames.\n"
            "- Result variables require a completed run when matching objects exist.\n"
            "- If a valid model has no objects of a requested type, an all-object getter returns an empty result.\n"
        ),
        _code(
            "from pathlib import Path\n"
            "from swmmx import swmm\n\n"
            "example_path = Path('examples/example.inp')\n"
            "m = swmm(example_path)\n\n"
            "# Run the model before using result getters such as m.get.link.flow(...)\n"
            "# when matching objects exist and you want actual simulation results.\n"
            "# m.run()\n"
        ),
        _md(
            "## Common getter patterns\n\n"
            "```python\n"
            "m.get.conduit.length()                         # all conduits, NumPy output\n"
            "m.get.conduit.length(ids='C1')                  # one conduit, scalar output\n"
            "m.get.conduit.length(ids=['C1', 'C2'])          # selected conduits\n"
            "m.get.link.flow(ids=['C1', 'C2'], format='df')  # result time series after m.run()\n"
            "m.get.weir.crest_height()                       # empty array if the model has no weirs\n"
            "```\n"
        ),
    ]

    for group_title, group_categories in _grouped_categories(categories):
        cells.append(_md(f"## {group_title}"))
        for category_name in group_categories:
            cells.append(_md(_category_markdown(model, category_lookup[category_name], "get")))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _set_notebook(model) -> dict:
    """Build the complete setter reference notebook."""

    categories = [api_name(raw) for raw in model._parameter_catalog._subcategories_by_api_name]
    category_lookup = {
        api_name(raw): raw
        for raw in model._parameter_catalog._subcategories_by_api_name
    }
    cells = [
        _md(
            "# swmmx: all `set` functions\n\n"
            "This notebook is a categorized reference for every public setter path in `swmmx`, including read-only paths that intentionally raise `ReadOnlyParameterError`.\n\n"
            "Setter pattern:\n\n"
            "```python\n"
            "m.set.<main_category>.<sub_category>(value, ids=None)\n"
            "```\n\n"
            "- Object-level setters accept one scalar value, a 1D NumPy array, or a pandas Series.\n"
            "- Scalars broadcast across all selected IDs; vector inputs must match the number of selected IDs.\n"
            "- Structured fields such as coordinates, geometry, points, and row groups require one structured payload per selected ID.\n"
            "- Reference fields validate target IDs where practical.\n"
            "- Derived and result parameters are read-only and raise `ReadOnlyParameterError` if set.\n"
            "- Use a cloned model when experimenting so the original input remains untouched.\n"
        ),
        _code(
            "from pathlib import Path\n"
            "from swmmx import swmm\n\n"
            "example_path = Path('examples/example.inp')\n"
            "m = swmm(example_path).clone()  # safe working copy for experiments\n"
        ),
        _md(
            "## Common setter patterns\n\n"
            "```python\n"
            "m.set.conduit.roughness(0.013)                          # broadcast to all conduits\n"
            "m.set.conduit.roughness(0.014, ids='C1')                 # one conduit\n"
            "m.set.conduit.roughness([0.013, 0.014], ids=['C1','C2']) # one value per selected ID\n"
            "m.set.node.coordinate((100.0, 200.0), ids='J1')         # structured value\n"
            "m.set.conduit.flow(1.0)                                 # read-only -> error\n"
            "```\n"
        ),
    ]

    for group_title, group_categories in _grouped_categories(categories):
        cells.append(_md(f"## {group_title}"))
        for category_name in group_categories:
            cells.append(_md(_category_markdown(model, category_lookup[category_name], "set")))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    """Generate both API reference notebooks from the current public catalog."""

    model = swmm(EXAMPLE)
    GET_NOTEBOOK.write_text(json.dumps(_get_notebook(model), indent=2), encoding="utf-8")
    SET_NOTEBOOK.write_text(json.dumps(_set_notebook(model), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
