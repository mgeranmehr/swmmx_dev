# Landcover backend contract — SWMMX 0.0.44

The Python API is suitable for a future notebook, desktop or web interface.
It provides state, validation and review contracts; it does not provide an HTTP
server, authentication, task queue or frontend. Use one serialized writer per
manager. An application must manage sessions, authorization and concurrent edits.

## Guided workflow

1. Load a model or create `landcover(units="SI")`.
2. Define classes with `define_classes`; use `validate_only=True` for form feedback.
3. Assign a table with `set_coverage`, or import `set_surfaces` and run
   `calculate_coverage` against subcatchment polygons in an explicit projected CRS.
4. Request only the parameter groups the user wants to update through `preview`.
5. Display changes, issues, assumptions and `can_apply`.
6. Submit the returned `preview_id` to the same manager's `apply` method.
7. Save the model and sidecar. Run SWMM separately when needed.

Coverage mapping works with names alone. The urban preset provides labels and
does not insert unverified engineering defaults. Missing parameters become
actionable issues only when requested calculations need them.

## JSON boundary

```python
from swmmx import LandCover

project_response = lc.to_project().to_dict()
preview_response = lc.preview(parameters=["imperviousness"]).to_dict()
# After the user reviews preview_response, the server accepts only its handle:
lc.apply(preview_response["preview_id"])
# A later session reloads durable state, then generates a fresh preview:
restored = LandCover.from_project(project_response)
```

`LandCoverProject` and `LandCoverPreview` are frozen JSON snapshots. Returned
dictionaries and DataFrames are independent copies. Keep the manager on the
server; never accept client-edited proposed values as an application command.

Project schema version 2 contains `version`, `project_id`, `name`, `revision`,
`units`, `classes`, `coverage`, and `source`. Class records include a stable
`class_id`, mutable `name`, and property fields. Coverage records contain
`subcatchment`, optional `area_m2`, and `fractions` keyed by stable class ID.
Renaming/updating retains IDs. New classes get new IDs. Load validates IDs and
references. Version-1 sidecars migrate automatically; unknown versions fail.
The sidecar stores this object under its `landcover` key and preserves unrelated
top-level metadata. GIS geometry is session data; reimport it after loading.

Preview schema contains `preview_id`, `project_id`, `revision`, project/model
fingerprints, selected `parameters`, target `units`, `values`, `changes`,
`issues`, `assumptions` and `can_apply`. Each change has `subcatchment`,
`parameter`, `current`, `proposed`, `unit`. Standalone previews calculate without
an attached model but cannot apply. Retain up to 16 preview handles per manager;
they are session-local and all are cleared after application. Edits, undo/redo,
model changes or a different manager invalidate a previous review. A stale handle
requires a fresh preview, not an automatic retry with recalculated values.

Issue records contain `code`, `severity`, `object_id`, `field`, `message`,
`remedy` and optional zero-based `row`. Use `LandCoverValidationError.report`
or a validation-only `LandCoverReport` to display all detected row errors.
`report.to_dict()` returns `issues` and `can_apply`; `to_dataframe()` supports
notebook inspection. Invalid batches leave metadata unchanged.

## Units, transactions and state

Declare source property units with `units="SI"` or `"US"`. Preview converts
lengths/rates to native model units. Legacy `"native"` assumes compatibility.
Coverage areas are explicit m²/ha, independent of property units. The older
`derive_*` methods return source-unit values. Scenario comparisons require the
same property units; no subtraction of incompatible unit systems is performed.

`status` reports coverage availability, preview readiness, whether the applied
state is still current, spatial readiness/reason and undo/redo availability.
Coverage availability does not guarantee complete model coverage or full design
readiness. Metadata history keeps at most 20 transactions. `undo` and `redo`
increase the revision and do not undo native model application. History and
preview handles are not persisted. Use a model clone for reversible simulation
experiments: `lc.scenario("future", clone_model=True)`. The default lightweight
scenario freezes attached areas/units and has no attached model.

`calculate_coverage(progress=callback, cancelled=predicate)` emits dictionaries
with `stage`, `completed`, `total`. Stages include input/overlap validation,
intersection, aggregation, assignment and precommit. Counts are stage-local,
not a uniform estimate of elapsed runtime. Cancellation raises
`LandCoverCancelled` and rolls back metadata. Checks occur between stages/rows;
a running GEOS intersection is not interruptible. Callbacks should observe the
operation, not mutate the manager. A UI should dispatch work off its main thread
and serialize all manager edits.

## Implementation boundaries and compatibility

- `contracts.py`: portable immutable project, preview, report and issue objects.
- `workflow.py`: public bulk operations, history, state and preview handles.
- `services.py`: calculation and preview assembly without native writes.
- `adapter.py`: native unit conversion, fingerprinting and atomic SWMM setters.
- `core.py`, `gis.py`, `infiltration.py`, `persistence.py`: domain operations,
  optional spatial processing, infiltration and versioned storage.

Existing `add_class`, `assign`, `derive_hydrology`, `apply_hydrology`, `copy`,
GIS and persistence APIs remain usable. `to_geodataframe()` now defaults to
coverage only; opt into `include_hydrology=True` and/or `include_lids=True`.
`to_dataframe()` retains its existing richer defaults. Native SWMM water-quality
LANDUSES remain a separate, explicit integration.

For executable requests and response inspection, use the final lessons in
[notebook 23](../examples/23_landcover.ipynb).
