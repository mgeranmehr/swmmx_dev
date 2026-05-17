from pathlib import Path

import pytest

from swmmx import ObjectNotFoundError, ReadOnlyParameterError, swmm
from swmmx.parameters import api_name


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def _public_paths(model, mode: str):
    """Yield every discoverable getter/setter path in completion order."""

    root = getattr(model, mode)
    for category_name in dir(root):
        category = getattr(root, category_name)
        for subcategory_name in dir(category):
            yield category_name, subcategory_name, getattr(category, subcategory_name)


def test_every_schema_getter_and_setter_path_exists_as_a_callable():
    """Every declared dotted path should resolve, even if not yet publicized in completion."""

    model = swmm(EXAMPLE)

    for spec in model._parameter_catalog._specs.values():
        category_name = api_name(spec.main_category)
        subcategory_name = api_name(spec.sub_category)
        assert callable(getattr(getattr(model.get, category_name), subcategory_name))
        assert callable(getattr(getattr(model.set, category_name), subcategory_name))


def test_every_discoverable_getter_executes_on_a_run_model():
    """Autocomplete should advertise the full getter surface without placeholders."""

    model = swmm(EXAMPLE)
    model.run()

    for category_name, subcategory_name, getter in _public_paths(model, "get"):
        try:
            getter()
        except ObjectNotFoundError:
            pass


def test_every_discoverable_setter_executes_with_existing_values():
    """Autocomplete should advertise the full editable setter surface."""

    model = swmm(EXAMPLE)

    for category_name, subcategory_name, setter in _public_paths(model, "set"):
        getter = getattr(getattr(model.get, category_name), subcategory_name)
        raw_category = model._parameter_catalog.raw_category(category_name)

        if category_name.startswith("option_"):
            current_value = getter()
            if current_value is None:
                # Sparse INP files may omit optional SWMM options.  The setter
                # remains implemented, but there is no existing value worth
                # writing back during a round-trip regression test.
                continue
            setter(current_value)
            continue

        try:
            available_ids = model._ids_for_category(raw_category)
        except Exception:
            available_ids = []
        if not available_ids:
            try:
                setter(getter())
            except ObjectNotFoundError:
                pass
            continue
        first_id = available_ids[0]
        current_value = getter(ids=first_id)
        setter(current_value, ids=first_id)


def test_every_non_writable_parameter_raises_read_only_on_set():
    """Result/derived paths should fail as read-only, not as missing attributes."""

    model = swmm(EXAMPLE)

    for spec in model._parameter_catalog._specs.values():
        if spec.is_writable:
            continue
        setter = getattr(
            getattr(model.set, api_name(spec.main_category)),
            api_name(spec.sub_category),
        )
        with pytest.raises(ReadOnlyParameterError):
            setter(1.0)


def test_get_and_set_raise_clear_errors_when_required_objects_do_not_exist():
    """Empty models should explain that the requested object collection is absent."""

    model = swmm(new="SI")

    with pytest.raises(ObjectNotFoundError, match="No conduit objects are available"):
        model.get.conduit.length()
    with pytest.raises(ObjectNotFoundError, match="No conduit objects are available"):
        model.set.conduit.roughness(0.013)
