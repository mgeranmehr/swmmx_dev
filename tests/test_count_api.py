import inspect

import pandas as pd
import pytest

from swmmx import (
    FormatError,
    ModelNotRunError,
    ReadOnlyParameterError,
    UnknownIDError,
    UnknownParameterError,
    swmm,
)
from swmmx.core.errors import EngineRunError, ParseError, ReferenceError, ValidationError


def test_count_namespace_counts_collections_and_model_summaries():
    model = swmm("examples/example.inp")

    assert "conduit" in dir(model.count)
    assert "storage_unit" in dir(model.count)
    assert model.count.conduit() == 4
    assert model.count.node() == 5
    assert model.count.junction() == 4
    assert model.count.subcatchment() == 4
    assert model.count.rain_gage() == 1
    assert model.count.pollutant() == 5
    assert model.count.control_rule() == 2
    counts = model.count.model_dict()
    frame = model.count.model_df()

    assert counts["conduit"] == 4
    assert "node" not in counts
    assert isinstance(model.count.model(), int)
    assert model.count.model() == sum(counts.values())
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["category", "count"]


def test_count_helpers_track_mutations_and_are_documented():
    model = swmm(new="SI")
    model.add.node.junction("J1", x=0.0, y=0.0)
    model.add.node.outfall("OUT1", x=100.0, y=0.0)
    model.add.link.conduit("C1", from_node="J1", to_node="OUT1")

    assert model.count.junction() == 1
    assert model.count.conduit() == 1
    assert str(inspect.signature(model.count.conduit)) == "()"
    assert "Count helpers do not accept" in (model.count.conduit.__doc__ or "")

    model.remove.link.conduit("C1")
    assert model.count.conduit() == 0


def test_dynamic_access_errors_are_specific_and_helpful():
    model = swmm("examples/example.inp")

    with pytest.raises(UnknownParameterError, match="Did you mean 'roughness'"):
        model.get.conduit.roughnes()
    with pytest.raises(UnknownIDError, match="Unknown conduit ID 'C999'"):
        model.get.conduit.length("C999")
    with pytest.raises(FormatError, match="Unsupported format 'excel'"):
        model.get.conduit.length(format="excel")
    with pytest.raises(ModelNotRunError, match=r"Run the model first with m\.run\(\)"):
        model.get.conduit.flow()
    with pytest.raises(ReadOnlyParameterError, match="'conduit.flow' is a result variable and cannot be set"):
        model.set.conduit.flow(1.0)


def test_core_error_module_exports_requested_types():
    assert issubclass(EngineRunError, Exception)
    assert issubclass(ValidationError, Exception)
    assert issubclass(ReferenceError, Exception)
    assert issubclass(ParseError, Exception)


def test_dynamic_getter_docstring_mentions_ids_format_and_read_only_notes():
    model = swmm("examples/example.inp")
    length_doc = model.get.conduit.length.__doc__ or ""
    flow_doc = model.get.conduit.flow.__doc__ or ""

    assert "ids" in length_doc
    assert "format" in length_doc
    assert "Returns" in length_doc
    assert "read-only result variable" in flow_doc


def test_dynamic_namespaces_ignore_private_introspection_hooks():
    """Spyder/IPython private probes should not become public API errors."""

    model = swmm("examples/example.inp")

    assert not hasattr(model.count, "__custom_documentations__")
    assert not hasattr(model.get, "__custom_documentations__")
    assert not hasattr(model.set, "__custom_documentations__")
    assert not hasattr(model.get.conduit, "__custom_documentations__")
    assert not hasattr(model.plot_timeseries, "__custom_documentations__")
    assert not hasattr(model.plot_timeseries.link, "__custom_documentations__")
