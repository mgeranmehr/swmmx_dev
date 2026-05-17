from pathlib import Path

import pytest

from swmmx import ObjectNotFoundError, ReadOnlyParameterError, swmm
from swmmx.parameters import api_name


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def test_all_declared_set_functions_exist_and_follow_write_rules():
    """Every declared setter should resolve, write when editable, or raise read-only cleanly."""

    model = swmm(EXAMPLE)

    for spec in model._parameter_catalog._specs.values():
        category = api_name(spec.main_category)
        parameter = api_name(spec.sub_category)
        setter = getattr(getattr(model.set, category), parameter)
        assert callable(setter), f"m.set.{category}.{parameter} is not callable."

        if not spec.is_writable:
            with pytest.raises(ReadOnlyParameterError):
                setter(1.0)
            continue

        getter = getattr(getattr(model.get, category), parameter)
        if spec.main_category.startswith("option_"):
            setter(getter())
            continue

        try:
            selected_ids = model._ids_for_category(spec.main_category)
        except Exception:
            selected_ids = []

        if not selected_ids:
            try:
                setter(getter())
            except ObjectNotFoundError:
                pass
            continue

        first_id = selected_ids[0]
        current_value = getter(ids=first_id)
        setter(current_value, ids=first_id)


def test_set_namespaces_advertise_complete_editable_node_surface():
    """Composite setter namespaces should expose every editable node field."""

    model = swmm(EXAMPLE)

    assert {
        "coordinate",
        "dry_weather_flow",
        "external_inflow",
        "id",
        "initial_depth",
        "invert_elevation",
        "max_depth",
        "ponded_area",
        "surcharge_depth",
        "tag",
        "treatment",
    } <= set(dir(model.set.node))
