from pathlib import Path

import pandas as pd
import pytest

from swmmx import ModelNotRunError, swmm


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example" / "example.inp"


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
