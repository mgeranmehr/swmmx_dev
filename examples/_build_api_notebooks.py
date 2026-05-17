"""Generate the public API reference notebooks for the examples suite."""

from __future__ import annotations

import json
import inspect
from pathlib import Path
from typing import Iterable

from swmmx import swmm
from swmmx.elements import EDITABLE_ELEMENT_SPECS
from swmmx.parameters import OBJECT_SECTIONS, api_name


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"
GET_NOTEBOOK = ROOT / "examples" / "11_all_get_functions.ipynb"
SET_NOTEBOOK = ROOT / "examples" / "12_all_set_functions.ipynb"
ADD_NOTEBOOK = ROOT / "examples" / "13_all_add_functions.ipynb"
REMOVE_NOTEBOOK = ROOT / "examples" / "14_all_remove_functions.ipynb"


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

EDITABLE_CATEGORY_GROUPS = [
    ("Hydrology", ["hydrology"]),
    ("Nodes", ["node"]),
    ("Links", ["link"]),
    ("Hydraulics", ["hydraulic"]),
    ("Water quality", ["quality"]),
    ("Curves", ["curve"]),
    ("Time data", ["time"]),
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


def _grouped_editable_categories(all_categories: Iterable[str]) -> list[tuple[str, list[str]]]:
    """Return add/remove categories in a human-friendly group order."""

    all_categories = list(all_categories)
    seen: set[str] = set()
    grouped: list[tuple[str, list[str]]] = []
    for title, category_names in EDITABLE_CATEGORY_GROUPS:
        present = [name for name in category_names if name in all_categories]
        if present:
            grouped.append((title, present))
            seen.update(present)
    remaining = [name for name in all_categories if name not in seen]
    if remaining:
        grouped.append(("Other editable categories", remaining))
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


def _editable_specs_for_category(category: str):
    """Return editable element specs in registry order for one category."""

    return [spec for spec in EDITABLE_ELEMENT_SPECS if spec.category == category]


def _coordinate_policy_note(policy: str | None) -> str:
    """Render one concise user-facing coordinate note."""

    labels = {
        None: "None",
        "mapped_max": "Optional x/y; defaults to maximum mapped point",
        "mapped_min": "Optional x/y; defaults to minimum mapped point",
        "node_next": "Optional x/y; defaults beside the current node map",
        "explicit_required": "Explicit x/y required",
        "explicit_centroid_required": "Explicit centroid x/y required",
    }
    return labels.get(policy, policy or "None")


def _editable_status(spec) -> str:
    """Return a public implementation-status label."""

    return "Implemented" if spec.implemented else "Reserved; raises `NotImplementedYetError`"


def _editable_parameter_names(spec) -> list[str]:
    """Return every unique public input name for one add endpoint."""

    names = ["id", *spec.required_parameters, *spec.optional_parameters]
    for parameter in spec.positional_parameters:
        if parameter.name not in names:
            names.append(parameter.name)
    return names


def _editable_input_role(spec, name: str) -> str:
    """Describe whether one add input is required, optional, or positional."""

    positional = {parameter.name for parameter in spec.positional_parameters}
    if name == "id":
        return "Required first positional"
    if name in spec.required_parameters and name in positional:
        return "Required positional"
    if name in spec.required_parameters:
        return "Required keyword"
    if name in positional:
        return "Optional positional"
    return "Optional keyword"


def _editable_default(spec, name: str) -> str:
    """Return a readable add-input default."""

    if name in spec.defaults:
        return repr(spec.defaults[name])
    for parameter in spec.positional_parameters:
        if parameter.name == name and parameter.default is not inspect._empty:
            return repr(parameter.default)
    return "None"


def _editable_type_hint(spec, name: str) -> str:
    """Return a practical public type hint for one add option."""

    reference_target = spec.references.get(name)
    if name == "id":
        return "`str`"
    if reference_target:
        return f"`str` ID of existing `{reference_target}` object"
    if name in {"x", "y", "length", "width", "height", "diameter", "offset", "crest_height"}:
        return "`float`"
    if name in {"barrels", "number", "end_contractions"}:
        return "`int`"
    if name in {"points", "polygon", "vertices"}:
        return "`list[tuple[float, float]]`, pandas DataFrame, or NumPy `(n, 2)` array"
    if name == "data":
        return "time/value pairs, pandas Series/DataFrame, or compatible array-like data"
    if name == "multipliers":
        return "1D numeric sequence"
    if name == "geometry":
        return "numeric sequence of 1 to 4 values"
    if name == "parameters":
        return "`dict` or structured layer data"
    if name in {"text", "description", "filename", "station", "units", "drain_to", "outlet"}:
        return "`str`"
    if any(token in name for token in ("fraction", "percent", "coefficient", "roughness", "slope", "depth", "area", "flow", "rate", "elevation", "porosity", "conductivity", "moisture", "exponent", "storage", "availability", "swept", "clogging", "saturation", "temperature", "capacity", "delay")):
        return "`float`"
    if name in {"type", "shape", "format", "source_type", "rating_type", "curve_type", "grate_type", "storage_curve_type", "initial_status", "subarea_routing"}:
        return "`str` enum"
    if name in {"flap_gate", "tide_gate", "surcharge", "snow_only"}:
        return "`bool` or SWMM `YES`/`NO` string"
    return "value compatible with the named SWMM field"


def _editable_condition(spec, name: str) -> str:
    """Return the main validation/usage note for one add option."""

    if name in {"x", "y"} and spec.category == "node":
        return "Required map coordinate for node placement"
    if name in {"x", "y"} and spec.path == "hydrology.subcatchment":
        return "Required subcatchment centroid coordinate"
    if name in spec.references:
        return f"Must reference an existing `{spec.references[name]}` object"
    path_notes = {
        ("node.outfall", "fixed_stage"): "Required only when `type='FIXED'`",
        ("node.outfall", "tidal_curve"): "Required only when `type='TIDAL'`",
        ("node.outfall", "time_series"): "Required only when `type='TIMESERIES'`",
        ("link.conduit", "length"): "If omitted, computed from node coordinates when available; otherwise 1.0",
        ("link.conduit", "diameter"): "Used as circular `geometry_1` when no explicit geometry is supplied",
        ("hydrology.rain_gage", "time_series"): "Required when `source_type='TIMESERIES'`",
        ("hydrology.rain_gage", "filename"): "Used when `source_type='FILE'`",
        ("hydrology.subcatchment", "polygon"): "Optional outline; fallback polygon is centered on x/y",
        ("curve.generic", "type"): "Explicit SWMM curve type",
    }
    return path_notes.get((spec.path, name), "Validated according to the element definition")


def _element_conditions(spec) -> str:
    """Return element-level special behavior notes."""

    notes = {
        "hydrology.rain_gage": "Requires `format`, `interval`, and `source_type`; `time_series` is checked when used.",
        "hydrology.subcatchment": "Requires explicit centroid `x`/`y`; outlet may be a node or another subcatchment.",
        "node.junction": "Requires explicit map `x`/`y` coordinates.",
        "node.outfall": "Requires explicit map `x`/`y`; stage input depends on outfall `type`.",
        "link.conduit": "Requires existing endpoint nodes; length can be computed from their coordinates.",
        "curve.generic": "Requires explicit curve `type` plus x/y `points`.",
        "time.time_series": "Accepts inline time/value data or filename-based series metadata.",
        "time.time_pattern": "Pattern `type` must be MONTHLY, DAILY, HOURLY, or WEEKEND.",
    }
    return notes.get(spec.path, "Use the listed required inputs; unsupported reserved endpoints raise a clear error.")


def _editable_add_overview(category: str) -> str:
    """Build one category overview table for add endpoints."""

    specs = _editable_specs_for_category(category)
    lines = [
        f"### `{category}`",
        "",
        "| Add function | Status | Required inputs | Optional inputs | Coordinate rule | Output | Conditions |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for spec in specs:
        required = ", ".join(("id", *spec.required_parameters))
        optional = ", ".join(spec.optional_parameters) or "None"
        lines.append(
            f"| `m.add.{spec.path}(...)` | {_editable_status(spec)} | "
            f"{_escape(required)} | {_escape(optional)} | "
            f"{_coordinate_policy_note(spec.coordinate_policy)} | created object ID (`str`) | "
            f"{_escape(_element_conditions(spec))} |"
        )
    return "\n".join(lines)


def _editable_add_detail(spec) -> str:
    """Build one detailed parameter table for one add endpoint."""

    lines = [
        f"#### `m.add.{spec.path}()`",
        "",
        spec.purpose or f"Add one `{spec.element_type}` object.",
        "",
        "| Input | Role | Expected type | Default | Conditions / validation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in _editable_parameter_names(spec):
        lines.append(
            f"| `{name}` | {_editable_input_role(spec, name)} | "
            f"{_editable_type_hint(spec, name)} | {_escape(_editable_default(spec, name))} | "
            f"{_escape(_editable_condition(spec, name))} |"
        )
    references = ", ".join(f"{name} -> {target}" for name, target in spec.references.items()) or "None"
    dependencies = ", ".join(spec.dependency_rules) or "None"
    lines.extend(
        [
            "",
            f"- **INP sections:** `{', '.join(spec.inp_sections)}`",
            f"- **Reference checks:** {references}",
            f"- **Removal dependency rules:** {dependencies}",
            f"- **Implementation status:** {_editable_status(spec)}",
            f"- **Example:** `{spec.example or f'm.add.{spec.path}(\"ID\", ...)'}`",
        ]
    )
    return "\n".join(lines)


def _editable_remove_overview(category: str) -> str:
    """Build one category overview table for remove endpoints."""

    specs = _editable_specs_for_category(category)
    lines = [
        f"### `{category}`",
        "",
        "| Remove function | Status | `ids` input | `force` input | Dependency rules | Output | Conditions |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for spec in specs:
        dependencies = ", ".join(spec.dependency_rules) or "No explicit dependency rules"
        lines.append(
            f"| `m.remove.{spec.path}(ids, force=False)` | {_editable_status(spec)} | "
            "one `str` ID or `list[str]` | `bool`, default `False` | "
            f"{_escape(dependencies)} | removal summary `dict` | "
            f"{_escape(_element_conditions(spec))} |"
        )
    return "\n".join(lines)


def _editable_remove_detail(spec) -> str:
    """Build one detailed remove table for one endpoint."""

    dependencies = ", ".join(spec.dependency_rules) or "No explicit dependency rules"
    lines = [
        f"#### `m.remove.{spec.path}()`",
        "",
        "| Input | Required | Type | Default | Conditions / validation |",
        "| --- | --- | --- | --- | --- |",
        "| `ids` | Yes | one `str` ID or `list[str]` | None | Every ID must already exist. |",
        "| `force` | No | `bool` | `False` | Without force, dependencies block removal. With force, only conservative safe cascades run. |",
        "",
        f"- **Dependency rules:** {dependencies}",
        "- **Return value:** `{'removed': [...], 'warnings': [...], 'dependencies_removed': [...]}`",
        f"- **Implementation status:** {_editable_status(spec)}",
        f"- **Example:** `m.remove.{spec.path}('ID')`",
    ]
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


def _add_notebook() -> dict:
    """Build the complete add-reference notebook."""

    categories = list(dict.fromkeys(spec.category for spec in EDITABLE_ELEMENT_SPECS))
    cells = [
        _md(
            "# swmmx: all `add` functions\n\n"
            "This notebook is a categorized reference for every public add endpoint in `swmmx`.\n\n"
            "Add pattern:\n\n"
            "```python\n"
            "m.add.<category>.<element_type>(id, **options)\n"
            "```\n\n"
            "- The first argument is always the new object ID.\n"
            "- Implemented endpoints create records, mark the model modified, and invalidate stale results.\n"
            "- Reserved endpoints are intentionally visible for autocomplete but raise `NotImplementedYetError` until implemented.\n"
            "- Node-like additions require explicit `x`/`y` map coordinates.\n"
            "- Subcatchments require explicit centroid `x`/`y`; an optional polygon can still define their outline.\n"
        ),
        _code(
            "from swmmx import swmm\n\n"
            "m = swmm(new='SI')\n"
            "# Build on this scratch model when trying the examples below.\n"
        ),
        _md(
            "## Common add patterns\n\n"
            "```python\n"
            "m.add.node.junction('J1', x=0.0, y=0.0, invert_elevation=10.0, max_depth=3.0)\n"
            "m.add.node.outfall('OUT1', x=100.0, y=0.0, invert_elevation=9.0, type='FREE')\n"
            "m.add.link.conduit('C1', from_node='J1', to_node='OUT1', roughness=0.013)\n"
            "m.add.hydrology.subcatchment('S1', rain_gage='RG1', outlet='J1', x=0.0, y=0.0)\n"
            "```\n"
        ),
    ]
    for group_title, group_categories in _grouped_editable_categories(categories):
        cells.append(_md(f"## {group_title}"))
        for category in group_categories:
            cells.append(_md(_editable_add_overview(category)))
            for spec in _editable_specs_for_category(category):
                cells.append(_md(_editable_add_detail(spec)))
    return _notebook(cells)


def _remove_notebook() -> dict:
    """Build the complete remove-reference notebook."""

    categories = list(dict.fromkeys(spec.category for spec in EDITABLE_ELEMENT_SPECS))
    cells = [
        _md(
            "# swmmx: all `remove` functions\n\n"
            "This notebook is a categorized reference for every public remove endpoint in `swmmx`.\n\n"
            "Remove pattern:\n\n"
            "```python\n"
            "m.remove.<category>.<element_type>(ids, force=False)\n"
            "```\n\n"
            "- `ids` can be one string ID or a list of string IDs.\n"
            "- By default, referenced objects are protected from unsafe removal.\n"
            "- `force=True` only performs conservative cascades that are implemented safely; otherwise a clear error is raised.\n"
            "- Successful removals return a summary dictionary and invalidate stale results.\n"
        ),
        _code(
            "from swmmx import swmm\n\n"
            "m = swmm(new='SI')\n"
            "# Use a scratch model or clone before experimenting with removals.\n"
        ),
        _md(
            "## Common remove patterns\n\n"
            "```python\n"
            "m.remove.link.conduit('C1')\n"
            "m.remove.node.junction(['J1', 'J2'])\n"
            "m.remove.node.junction('J1', force=True)\n"
            "```\n"
        ),
    ]
    for group_title, group_categories in _grouped_editable_categories(categories):
        cells.append(_md(f"## {group_title}"))
        for category in group_categories:
            cells.append(_md(_editable_remove_overview(category)))
            for spec in _editable_specs_for_category(category):
                cells.append(_md(_editable_remove_detail(spec)))
    return _notebook(cells)


def _notebook(cells: list[dict]) -> dict:
    """Return shared notebook metadata around prebuilt cells."""

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
    """Generate all API reference notebooks from the current public catalog."""

    model = swmm(EXAMPLE)
    GET_NOTEBOOK.write_text(json.dumps(_get_notebook(model), indent=2), encoding="utf-8")
    SET_NOTEBOOK.write_text(json.dumps(_set_notebook(model), indent=2), encoding="utf-8")
    ADD_NOTEBOOK.write_text(json.dumps(_add_notebook(), indent=2), encoding="utf-8")
    REMOVE_NOTEBOOK.write_text(json.dumps(_remove_notebook(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
