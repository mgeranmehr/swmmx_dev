"""Explicit approximations for native SWMM pervious infiltration parameters."""

from __future__ import annotations

from ..errors import ValidationError
from .classes import number

FIELDS = {
    "HORTON": ("maximum_rate", "minimum_rate", "decay", "dry_time", "maximum_volume"),
    "MODIFIED_HORTON": (
        "maximum_rate",
        "minimum_rate",
        "decay",
        "dry_time",
        "maximum_volume",
    ),
    "GREEN_AMPT": (
        "suction_head",
        "hydraulic_conductivity",
        "initial_moisture_deficit",
    ),
    "MODIFIED_GREEN_AMPT": (
        "suction_head",
        "hydraulic_conductivity",
        "initial_moisture_deficit",
    ),
    "CURVE_NUMBER": ("curve_number", "conductivity", "dry_time"),
}


def validate_parameters(params: dict) -> str:
    if not isinstance(params, dict) or params.get("model") not in FIELDS:
        raise ValidationError(f"Infiltration requires model in {list(FIELDS)}")
    model = params["model"]
    if set(params) != {"model", *FIELDS[model]}:
        raise ValidationError(f"{model} requires exactly {FIELDS[model]} plus model")
    for key in FIELDS[model]:
        number(
            params[key],
            key,
            high=1
            if key == "initial_moisture_deficit"
            else 100
            if key == "curve_number"
            else float("inf"),
            positive=key == "curve_number",
        )
    if "maximum_rate" in params and params["maximum_rate"] < params["minimum_rate"]:
        raise ValidationError("maximum_rate must be >= minimum_rate")
    return model


def derive(manager, method: str, function):
    import pandas as pd

    if method not in ("area_weighted", "dominant", "custom") or (
        method == "custom" and not callable(function)
    ):
        raise ValidationError(
            "Choose area_weighted, dominant, or custom with a callable function"
        )
    rows = {}
    for sid in manager._coverage:
        parts = []
        for cls, fraction in manager._parts(sid):
            weight = fraction * (1 - cls.impervious)
            if weight > 0:
                if cls.infiltration is None:
                    raise ValidationError(
                        f"{sid}: {cls.name} needs infiltration metadata"
                    )
                parts.append({"class": cls.name, "weight": weight, **cls.infiltration})
        if not parts:
            continue
        models = {p["model"] for p in parts}
        if method == "custom":
            result = function(parts)
        else:
            if len(models) != 1:
                raise ValidationError(
                    f"{sid}: incompatible infiltration models {models}"
                )
            model = parts[0]["model"]
            if method == "dominant":
                chosen = max(parts, key=lambda p: p["weight"])
                result = {key: chosen[key] for key in ("model", *FIELDS[model])}
            else:
                result = {
                    "model": model,
                    **{
                        key: sum(p["weight"] * p[key] for p in parts)
                        / sum(p["weight"] for p in parts)
                        for key in FIELDS[model]
                    },
                }
        model = validate_parameters(result)
        if manager.model is not None and model != manager.model.options["INFILTRATION"]:
            raise ValidationError(
                f"{sid}: {model} differs from attached model INFILTRATION"
            )
        rows[sid] = result
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("subcatchment")
