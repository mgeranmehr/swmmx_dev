from pathlib import Path

from swmmx import swmm
from swmmx.parameters import api_name


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def test_all_declared_get_functions_exist_and_execute():
    """Every declared getter should resolve and execute on a run model."""

    model = swmm(EXAMPLE)
    model.run()

    for spec in model._parameter_catalog._specs.values():
        category = api_name(spec.main_category)
        parameter = api_name(spec.sub_category)
        getter = getattr(getattr(model.get, category), parameter)
        assert callable(getter), f"m.get.{category}.{parameter} is not callable."
        getter()


def test_get_namespaces_advertise_complete_node_surface():
    """Composite categories should expose both input and result fields."""

    model = swmm(EXAMPLE)

    assert {
        "coordinate",
        "dry_weather_flow",
        "external_inflow",
        "id",
        "initial_depth",
        "invert_elevation",
        "max_depth",
        "pollutant_concentration",
        "ponded_area",
        "tag",
        "treatment",
    } <= set(dir(model.get.node))
