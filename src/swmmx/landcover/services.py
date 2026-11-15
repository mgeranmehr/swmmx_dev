"""Read-only parameter calculations and review assembly, independent of UI code."""

from __future__ import annotations

import json
from uuid import uuid4

from ..errors import SWMMXError, ValidationError
from .adapter import SWMMLandCoverAdapter
from .contracts import LandCoverIssue, LandCoverPreview

GROUPS = (
    "imperviousness",
    "roughness",
    "depression_storage",
    "pct_zero",
    "infiltration",
)


def calculate(
    manager, parameters=None, infiltration_method="area_weighted", function=None
):
    """Calculate requested groups independently and collect all row diagnostics."""
    if isinstance(parameters, str):
        raise ValidationError('parameters must be a list, e.g. ["imperviousness"]')
    groups = list(
        ("imperviousness", "roughness", "depression_storage")
        if parameters is None
        else parameters
    )
    if (
        not groups
        or any(g not in GROUPS for g in groups)
        or len(groups) != len(set(groups))
    ):
        raise ValidationError(
            f"parameters must be a nonempty unique selection from {GROUPS}"
        )
    issues, records = [], []
    if not manager._coverage:
        issues.append(
            LandCoverIssue(
                "NO_COVERAGE",
                "error",
                None,
                "coverage",
                "No subcatchments assigned",
                "Set coverage or calculate a GIS overlay",
            )
        )
    for sid in manager._coverage:
        one = manager._working_copy()
        one._coverage = {sid: one._coverage[sid]}
        row = {"subcatchment": sid}
        for group in groups:
            missing = []
            for name, fraction in one._coverage[sid].fractions.items():
                if fraction <= 0:
                    continue
                cls = one._classes[name]
                required = ["impervious"]
                if cls.impervious is not None:
                    if group == "roughness":
                        required += (["n_imp"] if cls.impervious > 0 else []) + (
                            ["n_perv"] if cls.impervious < 1 else []
                        )
                    elif group == "depression_storage":
                        required += (["dstore_imp"] if cls.impervious > 0 else []) + (
                            ["dstore_perv"] if cls.impervious < 1 else []
                        )
                    elif group == "pct_zero" and cls.impervious > 0:
                        required += ["pct_zero"]
                    elif group == "infiltration" and cls.impervious < 1:
                        required += ["infiltration"]
                for prop in required:
                    if getattr(cls, prop) is None:
                        issue = LandCoverIssue(
                            "MISSING_PROPERTY",
                            "error",
                            sid,
                            f"classes.{one.class_id(name)}.{prop}",
                            f"{sid}: class {name} needs {prop}",
                            f"Use update_class({name!r}, {prop}=...) or exclude {group}",
                        )
                        if issue not in issues:
                            issues.append(issue)
                        missing.append(issue)
            if missing:
                continue
            try:
                if group == "infiltration":
                    table = one.derive_infiltration(infiltration_method, function)
                else:
                    table = one.derive_hydrology(
                        imperviousness=group == "imperviousness",
                        roughness=group == "roughness",
                        depression_storage=group == "depression_storage",
                        pct_zero=group == "pct_zero",
                    )
                if not table.empty:
                    row.update(
                        json.loads(
                            table.reset_index().to_json(
                                orient="records", double_precision=15
                            )
                        )[0]
                    )
            except SWMMXError as exc:
                issues.append(
                    LandCoverIssue(
                        "PARAMETER_UNAVAILABLE",
                        "error",
                        sid,
                        group,
                        str(exc),
                        "Supply the named class property or exclude this parameter group",
                    )
                )
        records.append(row)
    return groups, records, issues


def preview(
    manager, parameters=None, infiltration_method="area_weighted", function=None
):
    groups, records, issues = calculate(
        manager, parameters, infiltration_method, function
    )
    source_units = manager.units
    adapter = SWMMLandCoverAdapter(manager.model) if manager.model is not None else None
    target_units = adapter.units if adapter else source_units
    assumptions = [
        f"Class length/rate units: {source_units}; preview target units: {target_units}.",
        "Impervious/pervious properties use their respective area weights; effective parameter approximation.",
        "Absent surfaces produce null parameters and preserve native values on application.",
    ]
    if "infiltration" in groups:
        assumptions.append(
            f"Infiltration aggregation: {infiltration_method}; a pervious-area approximation."
        )
    if source_units == "native":
        assumptions.append(
            "Legacy native units: class values are assumed to match the attached model; prefer explicit SI or US."
        )
    if adapter:
        records = adapter.convert(records, source_units)
    else:
        issues.append(
            LandCoverIssue(
                "MODEL_NOT_ATTACHED",
                "warning",
                None,
                "model",
                "Calculation is standalone; native application is unavailable",
                "Attach a model and generate a new preview",
            )
        )
    changes = []
    for row in records:
        for key, value in row.items():
            if key == "subcatchment":
                continue
            current = None
            if adapter:
                try:
                    current = adapter.current(
                        row["subcatchment"], key, row.get("model")
                    )
                except SWMMXError as exc:
                    issues.append(
                        LandCoverIssue(
                            "MODEL_FIELD_UNAVAILABLE",
                            "error",
                            row["subcatchment"],
                            key,
                            str(exc),
                            "Check the model records before applying",
                        )
                    )
            unit = (
                (
                    "mm"
                    if target_units == "SI"
                    else "in"
                    if target_units == "US"
                    else "native"
                )
                if key.startswith("dstore")
                else "%"
                if key in ("percent_impervious", "pct_zero")
                else "model-specific"
                if key not in ("n_imperv", "n_perv")
                else "Manning n"
            )
            changes.append(
                {
                    "subcatchment": row["subcatchment"],
                    "parameter": key,
                    "current": current,
                    "proposed": value,
                    "unit": unit,
                }
            )
    data = {
        "schema_version": 1,
        "preview_id": str(uuid4()),
        "project_id": manager.project_id,
        "revision": manager.revision,
        "project_fingerprint": manager._fingerprint(),
        "model_fingerprint": adapter.fingerprint() if adapter else None,
        "parameters": groups,
        "values": records,
        "changes": changes,
        "issues": [i.to_dict() for i in issues],
        "assumptions": assumptions,
        "units": target_units,
        "can_apply": adapter is not None
        and not any(i.severity == "error" for i in issues),
    }
    result = LandCoverPreview(json.dumps(data, allow_nan=False))
    manager._previews[result.preview_id] = result
    while len(manager._previews) > 16:
        del manager._previews[next(iter(manager._previews))]
    return result
