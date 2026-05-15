from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swmmx import ModelNotRunError, swmm


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example.inp"


def test_open_and_pre_run_time_vector():
    model = swmm.open(EXAMPLE)

    assert model.schema.is_loaded
    assert "option_general" in model.schema.main_categories

    vector = model.time.vector()
    assert isinstance(vector, np.ndarray)
    assert model.time.count() == 45
    assert str(vector[0]) == "1977-07-15T06:35:00.000000000"
    assert str(vector[-1]) == "1977-07-15T10:15:00.000000000"

    frame = model.time.vector("df")
    assert isinstance(frame, pd.DataFrame)
    assert frame.index.name == "time"
    assert len(frame) == 45


def test_run_dependent_time_requires_results():
    model = swmm.open(EXAMPLE)

    with pytest.raises(ModelNotRunError):
        model.time.vector_run()
    with pytest.raises(ModelNotRunError):
        model.time.count_run()


def test_new_models_have_expected_default_units():
    assert swmm.new_SI().options["FLOW_UNITS"] == "LPS"
    assert swmm.new_SI("CMS").options["FLOW_UNITS"] == "CMS"
    assert swmm.new_US().options["FLOW_UNITS"] == "CFS"
    assert swmm.new_US("MGD").options["FLOW_UNITS"] == "MGD"


def test_clone_is_independent():
    model = swmm.open(EXAMPLE)
    cloned = model.clone()

    cloned.options["FLOW_UNITS"] = "LPS"
    assert model.options["FLOW_UNITS"] == "CFS"
    assert cloned.options["FLOW_UNITS"] == "LPS"


def test_save_preserves_unknown_sections_and_writes_modifications(tmp_path):
    model = swmm.open(EXAMPLE)
    model.options["FLOW_UNITS"] = "LPS"

    output = model.save(tmp_path / "nested" / "saved.inp")
    text = output.read_text(encoding="utf-8")

    assert "FLOW_UNITS           LPS" in text
    assert "[CONTROLS]" in text
    assert "; assume 21 minute valve open period" in text


def test_validate_example_has_no_errors_before_run():
    model = swmm.open(EXAMPLE)
    validation = model.validate()

    assert validation.ok
    assert any(issue.code == "RESULTS_NOT_AVAILABLE" for issue in validation.warnings)


def test_full_run_uses_bundled_windows_engine_when_available():
    model = swmm.open(EXAMPLE)
    result = model.run()

    assert result.success
    assert result.periods == 45
    assert result.engine_version == "5.2.4"
    assert model.time.count_run() == 45
    assert len(model.log()) > 0


def test_stepwise_runs_yield_simulation_steps():
    model = swmm.open(EXAMPLE)
    steps = model.runs()
    first = next(steps)
    steps.close()

    assert first.index == 1
    assert first.elapsed_days > 0
