"""Type-dependent EPA SWMM storage and divider row codecs.

Shared by editing, validation, interchange and annotations so optional fields
cannot shift into the wrong columns. See EPA SWMM 5.2 node.c readParams.
"""

from math import isfinite

from .errors import InvalidParameterError, InvalidReferenceError, MissingRequiredParameterError


NODE_SECTIONS = {"storage_unit": "STORAGE", "flow_divider": "DIVIDERS"}
STORAGE_SHAPES = {"FUNCTIONAL", "TABULAR", "CYLINDRICAL", "CONICAL", "PARABOLIC", "PYRAMIDAL"}
DIVIDER_FIELDS = {
    "OVERFLOW": (), "CUTOFF": ("cutoff_flow",),
    "TABULAR": ("diversion_curve",),
    "WEIR": ("cutoff_flow", "weir_height", "weir_coefficient"),
}
STORAGE_COMMON = ("id", "invert_elevation", "max_depth", "initial_depth", "storage_curve_type")
STORAGE_FUNCTION = ("area_coefficient", "area_exponent", "area_constant")
STORAGE_TAIL = ("surcharge_depth", "evaporation_factor", "suction_head", "hydraulic_conductivity", "initial_moisture_deficit")
DIVIDER_COMMON = ("id", "invert_elevation", "diverted_link", "type")
DIVIDER_TAIL = ("max_depth", "initial_depth", "surcharge_depth", "ponded_area")
TEXT_FIELDS = {"id", "storage_curve_type", "storage_curve", "diverted_link", "type", "diversion_curve", "tag"}


def field_names(category, kind):
    if category == "storage_unit":
        if kind not in STORAGE_SHAPES:
            raise InvalidParameterError(f"Invalid storage_curve_type '{kind}'; expected {sorted(STORAGE_SHAPES)}.")
        return STORAGE_COMMON + (("storage_curve",) if kind == "TABULAR" else STORAGE_FUNCTION) + STORAGE_TAIL
    if kind not in DIVIDER_FIELDS:
        raise InvalidParameterError(f"Invalid divider type '{kind}'; expected {sorted(DIVIDER_FIELDS)}.")
    return DIVIDER_COMMON + DIVIDER_FIELDS[kind] + DIVIDER_TAIL


def read_node_row(category, row):
    """Decode a row including SWMM defaults, leaving inapplicable fields absent."""
    type_index = 4 if category == "storage_unit" else 3
    if len(row) <= type_index:
        raise InvalidParameterError(f"Incomplete [{NODE_SECTIONS[category]}] row: {row}.")
    kind = str(row[type_index]).upper()
    names = field_names(category, kind)
    required = (6 if kind == "TABULAR" else 8) if category == "storage_unit" else 4 + len(DIVIDER_FIELDS[kind])
    if len(row) < required:
        raise InvalidParameterError(f"Incomplete {kind} row for '{row[0]}': requires {required} fields.")
    result = {}
    for index, name in enumerate(names):
        raw = row[index] if index < len(row) else 0.0
        try:
            result[name] = str(raw) if name in TEXT_FIELDS else float(raw)
        except (ValueError, TypeError) as exc:
            raise InvalidParameterError(f"Invalid {name} in {category} '{row[0]}': {raw!r}.") from exc
    result[names[type_index]] = kind
    if category == "storage_unit":
        # EPA also accepts a single Ksat token instead of a Psi/Ksat/IMD triple.
        tail_start = required + 2
        if len(row) == tail_start + 1:
            result.update(suction_head=0.0, hydraulic_conductivity=float(row[tail_start]), initial_moisture_deficit=0.0)
        elif tail_start < len(row) < tail_start + 3:
            raise InvalidParameterError("Storage seepage requires either Ksat or all three Psi, Ksat, IMD values.")
    return result


def number(name, value, *, nonnegative=True):
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise InvalidParameterError(f"{name} must be a finite number.") from exc
    if not isfinite(result) or (nonnegative and result < 0):
        raise InvalidParameterError(f"{name} must be finite" + (" and non-negative." if nonnegative else "."))
    return result


def require_curve(document, curve_id, kind):
    rows = [row for row in document.rows("CURVES") if row and row[0] == str(curve_id)]
    if not rows or len(rows[0]) < 4 or rows[0][1].upper() != kind:
        raise InvalidReferenceError(f"Curve '{curve_id}' must reference an existing {kind} curve.")
    points = []
    for row in rows:
        points.append((number("curve depth/flow", row[-2]), number("curve area/flow", row[-1])))
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise InvalidParameterError(f"Curve '{curve_id}' must have strictly increasing depth/flow values.")


def build_node_row(document, category, object_id, options):
    """Validate completely before constructing a canonical row; never mutate."""
    values = {key: value for key, value in options.items() if value is not None}
    type_field = "storage_curve_type" if category == "storage_unit" else "type"
    kind = str(values.pop(type_field, "FUNCTIONAL" if category == "storage_unit" else "OVERFLOW")).upper()
    names = field_names(category, kind)
    values[type_field] = kind
    values["id"] = object_id
    if category == "storage_unit":
        if "area" in values:
            area = values.pop("area")
            if kind != "FUNCTIONAL":
                raise InvalidParameterError("area is a constant-area shorthand for FUNCTIONAL storage only.")
            if "area_constant" in values and number("area_constant", values["area_constant"]) != number("area", area):
                raise InvalidParameterError("area and area_constant disagree.")
            values["area_constant"] = area
        if "seepage_loss" in values:
            seepage = values.pop("seepage_loss")
            if isinstance(seepage, (list, tuple)):
                if len(seepage) != 3:
                    raise InvalidParameterError("seepage_loss must be Ksat or (suction_head, hydraulic_conductivity, initial_moisture_deficit).")
                seepage = dict(zip(STORAGE_TAIL[2:], seepage))
            elif not isinstance(seepage, dict):
                seepage = {"hydraulic_conductivity": seepage}
            if set(seepage) - set(STORAGE_TAIL[2:]):
                raise InvalidParameterError("Unknown seepage_loss field.")
            for name, value in seepage.items():
                if name in values and number(name, values[name]) != number(name, value):
                    raise InvalidParameterError(f"seepage_loss and {name} disagree.")
                values[name] = value
        if kind == "TABULAR":
            if "storage_curve" not in values:
                raise MissingRequiredParameterError("TABULAR storage requires storage_curve.")
            require_curve(document, values["storage_curve"], "STORAGE")
    else:
        values.setdefault("diverted_link", "*")
        link = str(values["diverted_link"])
        if link != "*":
            rows = [row for section in ("CONDUITS", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS") for row in document.rows(section) if row and row[0] == link]
            if not rows:
                raise InvalidReferenceError(f"diverted_link '{link}' does not exist; omit it during construction and assign it after adding the link.")
            if len(rows[0]) < 3 or rows[0][1] != object_id:
                raise InvalidReferenceError(f"diverted_link '{link}' must leave divider '{object_id}'.")
        for name in DIVIDER_FIELDS[kind]:
            if name not in values:
                raise MissingRequiredParameterError(f"{kind} divider requires {name}.")
        if kind == "TABULAR":
            require_curve(document, values["diversion_curve"], "DIVERSION")
    unknown = set(values) - set(names)
    if unknown:
        raise InvalidParameterError(f"Fields not applicable to {kind} {category}: {', '.join(sorted(unknown))}.")
    for name in names:
        if name not in TEXT_FIELDS:
            signed = name == "invert_elevation" or (kind == "FUNCTIONAL" and name in {"area_coefficient", "area_exponent"})
            values[name] = number(name, values.get(name, 0.0), nonnegative=not signed)
    if values.get("evaporation_factor", 0) > 1 or values.get("initial_moisture_deficit", 0) > 1:
        raise InvalidParameterError("evaporation_factor and initial_moisture_deficit must be between 0 and 1.")
    if values["max_depth"] > 0 and values["initial_depth"] > values["max_depth"] + values["surcharge_depth"]:
        raise InvalidParameterError("initial_depth exceeds max_depth plus surcharge_depth.")
    if kind == "WEIR" and (values["weir_height"] <= 0 or values["weir_coefficient"] <= 0):
        raise InvalidParameterError("WEIR height and coefficient must be positive.")
    if kind == "WEIR" and values["cutoff_flow"] > values["weir_coefficient"] * values["weir_height"] ** 1.5:
        raise InvalidParameterError("WEIR cutoff_flow exceeds flow at the full weir height.")
    if kind == "FUNCTIONAL" and values["area_coefficient"] != 0 and values["max_depth"] > 0:
        try:
            depth, exponent = values["max_depth"], values["area_exponent"]
            volume = values["area_coefficient"] * depth ** (exponent + 1) / (exponent + 1) + values["area_constant"] * depth
        except (OverflowError, ZeroDivisionError) as exc:
            raise InvalidParameterError("Functional storage must produce a finite volume at max_depth.") from exc
        if not isfinite(volume) or volume < 0:
            raise InvalidParameterError("Functional storage must produce a finite non-negative volume at max_depth.")
    if category == "storage_unit" and kind not in {"FUNCTIONAL", "TABULAR"}:
        if values["area_coefficient"] <= 0 or values["area_exponent"] <= 0:
            raise InvalidParameterError("Analytical storage shapes require positive length and width (area_coefficient and area_exponent).")
        if kind == "PARABOLIC" and values["area_constant"] <= 0:
            raise InvalidParameterError("PARABOLIC top height (area_constant) must be positive.")
    return [values[name] for name in names]


def node_record(category, row):
    """Return named fields plus stable public aliases for getters/exports."""
    result = read_node_row(category, row)
    if category == "storage_unit":
        if result["storage_curve_type"] == "FUNCTIONAL":
            result["area"] = result["area_constant"]
        result["seepage_loss"] = result["hydraulic_conductivity"]
    return result
