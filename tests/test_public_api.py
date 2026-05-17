from pathlib import Path

import pandas as pd
import pytest

from swmmx import (
    DimensionMismatchError,
    InvalidReferenceError,
    ModelNotRunError,
    OptionalDependencyError,
    ReadOnlyParameterError,
    swmm,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.inp"


def test_open_and_pre_run_time_vector():
    model = swmm(EXAMPLE)

    assert model.schema.is_loaded
    assert "option_general" in model.schema.main_categories

    vector = model.time.vector()
    assert isinstance(vector, pd.DataFrame)
    assert model.time.count() == 45
    assert vector.index.name == "time"
    assert str(vector.index[0]) == "1977-07-15 06:35:00"
    assert str(vector.index[-1]) == "1977-07-15 10:15:00"
    assert len(vector) == 45


def test_run_dependent_time_requires_results():
    model = swmm(EXAMPLE)

    with pytest.raises(ModelNotRunError, match=r"m\.time\.vector_run\(\)"):
        model.time.vector_run()
    with pytest.raises(ModelNotRunError, match=r"m\.time\.count_run\(\)"):
        model.time.count_run()


def test_new_models_have_expected_default_units():
    assert swmm().options["FLOW_UNITS"] == "LPS"
    assert swmm(new="SI").options["FLOW_UNITS"] == "LPS"
    assert swmm(new="SI", flow_unit="CMS").options["FLOW_UNITS"] == "CMS"
    assert swmm(new="US").options["FLOW_UNITS"] == "CFS"
    assert swmm(new="US", flow_unit="MGD").options["FLOW_UNITS"] == "MGD"


def test_model_creation_reports_missing_runtime_dependencies(monkeypatch):
    from swmmx import dependencies

    monkeypatch.setattr(
        dependencies,
        "find_spec",
        lambda name: None if name in {"numpy", "pandas", "matplotlib", "networkx"} else object(),
    )

    with pytest.raises(
        OptionalDependencyError,
        match=r"swmmx runtime dependencies are missing: numpy, pandas, matplotlib, networkx",
    ):
        swmm(new="SI")


def test_constructor_rejects_invalid_argument_combinations():
    with pytest.raises(ValueError, match="not both"):
        swmm(EXAMPLE, new="SI")
    with pytest.raises(ValueError, match="only valid for new models"):
        swmm(EXAMPLE, flow_unit="LPS")
    with pytest.raises(ValueError, match="'new' must be either"):
        swmm(new="metric")
    with pytest.raises(ValueError, match="Invalid flow_unit"):
        swmm(new="SI", flow_unit="CFS")


def test_clone_is_independent():
    model = swmm(EXAMPLE)
    cloned = model.clone()

    cloned.options["FLOW_UNITS"] = "LPS"
    assert model.options["FLOW_UNITS"] == "CFS"
    assert cloned.options["FLOW_UNITS"] == "LPS"


def test_save_preserves_unknown_sections_and_writes_modifications(tmp_path):
    model = swmm(EXAMPLE)
    model.options["FLOW_UNITS"] = "LPS"

    output = model.save(tmp_path / "nested" / "saved.inp")
    text = output.read_text(encoding="utf-8")

    assert "FLOW_UNITS           LPS" in text
    assert "[CONTROLS]" in text
    assert "; assume 21 minute valve open period" in text


def test_validate_example_has_no_errors_before_run():
    model = swmm(EXAMPLE)
    validation = model.validate()

    assert validation.ok
    assert any(issue.code == "RESULTS_NOT_AVAILABLE" for issue in validation.warnings)


def test_full_run_uses_bundled_windows_engine_when_available():
    model = swmm(EXAMPLE)
    result = model.run()

    assert result.success
    assert result.periods == 45
    assert result.engine_version == "5.2.4"
    assert model.time.count_run() == 45
    assert isinstance(model.time.vector_run(), pd.DataFrame)
    assert len(model.log()) > 0


def test_stepwise_runs_yield_simulation_steps():
    model = swmm(EXAMPLE)
    steps = model.runs()
    first = next(steps)
    steps.close()

    assert first.index == 1
    assert first.elapsed_days > 0


def test_dynamic_getters_return_scalar_arrays_and_frames():
    model = swmm(EXAMPLE)

    assert "conduit" in dir(model.get)
    assert "link" in vars(model.get)
    assert "flow" in vars(model.get.link)
    assert "roughness" in dir(model.set.conduit)
    assert "roughness" in vars(model.set.conduit)
    assert "slope" not in dir(model.set.conduit)

    assert model.get.conduit.length("P001") == 220.0
    assert model.get.conduit.length().shape == (4,)
    assert list(model.get.conduit.length(format="df").columns) == ["P001", "P005", "P009", "P011"]
    assert model.get.conduit.count() == 4
    assert model.get.conduit.slope("P005") == pytest.approx((1.58 - 1.10) / 240.0)


def test_dynamic_setters_broadcast_validate_dimensions_and_references():
    model = swmm(EXAMPLE)

    model.set.conduit.roughness(0.013)
    assert model.get.conduit.roughness().tolist() == [0.013, 0.013, 0.013, 0.013]

    model.set.conduit.roughness([0.014, 0.015], ids=["P001", "P005"])
    assert model.get.conduit.roughness(["P001", "P005"]).tolist() == [0.014, 0.015]

    with pytest.raises(DimensionMismatchError, match="Received 3 values for 2 selected conduit objects"):
        model.set.conduit.roughness([0.013, 0.014, 0.015], ids=["P001", "P005"])
    with pytest.raises(InvalidReferenceError, match="Invalid reference"):
        model.set.conduit.from_node("missing", ids="P001")
    with pytest.raises(ReadOnlyParameterError, match="derived parameter"):
        model.set.conduit.slope(0.01)


def test_dynamic_result_getters_require_run_and_return_expected_shapes():
    model = swmm(EXAMPLE)

    with pytest.raises(ModelNotRunError, match="'conduit.flow' is a result variable"):
        model.get.conduit.flow()

    model.run()
    one_link = model.get.link.flow(ids="P001")
    two_links = model.get.link.flow(ids=["P001", "P005"], format="np")
    node_frame = model.get.node.depth(format="df")

    assert one_link.shape == (45,)
    assert two_links.shape == (45, 2)
    assert node_frame.shape == (45, 5)
    assert list(node_frame.columns) == ["P001", "P005", "P009", "P011", "Outlet"]


def test_setter_help_signatures_are_inspectable():
    import inspect

    model = swmm(EXAMPLE)
    assert str(inspect.signature(model.get.conduit.length)) == "(ids=None, format=None)"
    assert str(inspect.signature(model.set.conduit.roughness)) == "(value, ids=None)"
