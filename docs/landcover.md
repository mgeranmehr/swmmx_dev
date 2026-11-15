# Landcover API and modelling guide

SWMMX `landcover` describes physical surface composition. EPA SWMM `[LANDUSES]`,
`[COVERAGES]`, `[BUILDUP]`, and `[WASHOFF]` remain independent water-quality data.
Landcover aggregates properties into the existing SWMM subcatchment/subarea
representation. It does **not** add independent runoff planes or a new solver.

Start with `from swmmx import swmm, landcover`. `landcover(m)` returns the attached
manager, or loads `m.path.with_suffix('.swmmx.json')` when present. `landcover()`
creates standalone metadata and `lc.attach(m)` validates its IDs and areas.

## Start with the small workflow

Define classes, set coverage, inspect a preview, then apply it. Start with only
the parameter groups you have enough information to calculate. A coverage map
does not require roughness, infiltration or depression-storage properties.

```python
from swmmx import swmm, landcover

m = swmm("model.inp")
lc = landcover(m, units="SI")
lc.define_classes({"roof": {"impervious": 1}, "green": {"impervious": 0}})
lc.set_coverage({"S1": {"roof": 0.4, "green": 0.6}})
preview = lc.preview(parameters=["imperviousness"])
print(preview.changes)  # inspect before/after values and units
if preview.can_apply:
    lc.apply(preview)
m.save("landcover_model.inp")  # also writes landcover_model.swmmx.json
```

`S1` must already exist in your model. With `landcover(units="SI")`, the same
class and coverage operations work without a model. Standalone previews can
calculate values, but cannot apply until you attach a compatible model.

`define_classes` accepts a mapping, records, DataFrame or CSV with `name`.
`set_coverage` accepts a subcatchment-to-composition mapping, a wide DataFrame,
or a long table with `subcatchment`, `class` (or stable `class_id`) and one of
`fraction`, `percent`, `area_m2`, `area_ha`. Standalone area input also needs
total catchment area (`total_area_m2` in a long table or `area_m2` argument).
Both methods validate the entire batch before changing metadata. Use
`validate_only=True` to obtain a `LandCoverReport`; invalid regular batches raise
`LandCoverValidationError` with a `.report` containing all detected row issues.
Use `overwrite=True` when replacing existing definitions/coverage explicitly.

`landcover(preset="urban")` supplies names only. Engineering values remain
unset until you provide them. `update_class("roof", impervious=0.95)` edits a
definition while keeping its stable ID; `rename_class` changes its label.

`preview(parameters=[...])` supports `imperviousness`, `roughness`,
`depression_storage`, `pct_zero`, and `infiltration`. The default includes the
first three. Inspect `values`, `changes`, `issues`, `assumptions`, and
`can_apply`. Previews are immutable snapshots: editing returned tables cannot
change the values applied. `apply(preview)` rejects stale or foreign previews
and applies the reviewed native values atomically. Generate a fresh preview
after any model or metadata change. Legacy `derive_*` and `apply_hydrology`
remain available.

`status`, `history()`, `undo()` and `redo()` help guided workflows. Undo covers
metadata edits only, not native model application. `scenario("future")` makes
independent metadata without copying the model; use `clone_model=True` when
you intend to run an independent simulation. Legacy `copy()` still clones.

## Capability and API reference

| Area | Public methods | Returns / mutation |
|---|---|---|
| Classes | `add_class`, `get_class`, `has_class`, `list_classes`, `remove_class`, `rename_class`, `classes` | Validated definitions; metadata only; snapshots prevent accidental edits |
| Composition | `assign`, `normalize`, `coverage`, `coverage_fraction`, `coverage_area`, `dominant_class` | Structured coverage, fractions or m²; metadata only |
| Tables | `classes_dataframe`, `coverage_table`, `to_dataframe` | Independent pandas DataFrames |
| Hydrology | `derive_hydrology`, `derive_infiltration` | Read-only previews; missing contributing properties raise `ValidationError` |
| Application | `apply_hydrology` | Selective native setters, atomic validation, modified/stale state |
| GIS | `from_gis`, `from_geodataframe`, `overlay`, `to_geodataframe`, `coverage_geodataframe`, `intersections_geodataframe` | Optional GeoPandas; metadata only |
| LID | `lid_candidates` | Independent candidate upper bounds; creates no controls or usage |
| Scenarios | `copy`, `convert`, `compare` | Independent model/metadata copy; conversion edits metadata only |
| Quality | `apply_swmm_landuses(overwrite=False)` | Explicit native LANDUSES/COVERAGES conversion |
| Persistence | `save`, `LandCover.load` | Versioned JSON sidecar; no extra INP sections |
| Inspection | `validate`, `summary`, `plot` | Diagnostics, summary dictionary, Matplotlib Axes |

See the public docstrings for argument signatures and the executable
[notebook 23](../examples/23_landcover.ipynb) for all workflows.

## Classes, units and coverage

`add_class(name, impervious=None, n_imp=None, n_perv=None, dstore_imp=None,
dstore_perv=None, pct_zero=None, infiltration=None, lids=None, attributes=None,
description=None)` accepts locally selected parameters. No engineering values
are invented. Names are case-insensitively unique. Numeric values must be finite;
roughness must be positive, storage nonnegative, impervious/LID fractions 0..1,
and `pct_zero` 0..100. Attributes must be finite JSON-serializable dictionaries.
`classes` and `get_class` return snapshots. Rename updates coverage/GIS references;
remove refuses referenced classes. Use `update_class` to edit a definition while preserving references and IDs;
direct snapshot edits do not update the manager.

`assign(sid, composition, units='fraction', normalize=False, area_m2=None,
overwrite=False)` accepts fraction, percent, m2 or ha. Totals must equal one within
1e-8. Normalization is explicit; individual fraction/percentage bounds remain
validated. A duplicate assignment requires `overwrite=True`. Standalone area
assignment requires an explicit total `area_m2`; the manager never assumes a
partial mapped area is the whole catchment. Standalone fractions need no area
until area-dependent operations are called. Attached areas use hectares in SI
models and acres in US models (1 acre = 4046.8564224 m²). Assigned area snapshots
are checked against subsequent model area changes; explicitly reassign to accept
an area change. Metadata does not mark simulation results stale.

Declare property units once: `landcover(units="SI")` uses mm and mm/hr;
`units="US"` uses inches and inches/hr. `preview` converts length/rate properties
into attached model units, including infiltration parameters where applicable.
Dimensionless values remain unchanged. Legacy `units="native"` assumes class
properties already match model units and records this assumption in previews.
`derive_hydrology`/`derive_infiltration` retain declared source property units.
Catchment area input/output remains explicitly m²/ha (or native model area where
documented); class property units do not change coverage area units.

## Hydrological aggregation and subcatchments

For class area fraction f and impervious fraction I:

- Impervious percent = 100 × Σ(f I).
- N-impervious = Σ(f I n_imp) / Σ(f I).
- N-pervious = Σ(f (1−I) n_perv) / Σ(f (1−I)).
- Depression storage uses the same respective weights with dstore values.
- Optional PctZero uses impervious weights and class percentages.

These are explicit effective-parameter approximations, not exact runoff
preservation for heterogeneous surfaces. Roughness, storage, infiltration and
suitability require locally appropriate data and calibration. An absent surface
has NaN in the preview, and application preserves its existing native parameters.
Any **contributing** missing property is an error. Selective derivation/application
can omit roughness or depression storage when only imperviousness is required.

`apply_hydrology(imperviousness=True, roughness=True, depression_storage=True,
infiltration=False, pct_zero=False)` validates all selected changes through
existing setters on an isolated model document before committing. Unrelated
parameters are preserved. Changed native inputs mark the model modified and
invalidate prior results according to SWMMX conventions. Applying identical
values does not invalidate results.

## Infiltration

`derive_infiltration(method='area_weighted', function=None)` uses **pervious**
weights, or the largest pervious contribution for `dominant`. `custom` calls
`function(parts)` with dictionaries containing class, weight, model and parameters.
The callback must return a complete valid parameter dictionary including model.
Incompatible source models require a custom rule, and the result must match the
attached model's infiltration method. All methods are preprocessing approximations.

Supported metadata model tokens and required keys:

| Model | Required parameters besides `model` |
|---|---|
| HORTON / MODIFIED_HORTON | maximum_rate, minimum_rate, decay, dry_time, maximum_volume |
| GREEN_AMPT / MODIFIED_GREEN_AMPT | suction_head, hydraulic_conductivity, initial_moisture_deficit |
| CURVE_NUMBER | curve_number, conductivity, dry_time |

No universal conversion between infiltration models is supplied. Horton volume
must be supplied explicitly (zero may be chosen by the user). Fully impervious
subcatchments have no derived infiltration record.

## GIS and CRS

GIS dependencies remain optional: install `geopandas shapely` for GIS workflows.
`from_gis` delegates format support to GeoPandas (GeoPackage, Shapefile, GeoJSON,
etc.), with optional `layer`. `from_geodataframe` requires a class column, unique
index IDs, valid nonempty Polygon/MultiPolygon geometry, and explicit CRS.
Repeated class names are allowed. Duplicate subcatchment IDs are rejected;
represent multipart subcatchments as MultiPolygon records.

`overlay(landcover=None, subcatchments=None, area_crs=None, model_crs=None,
class_field='class', subcatchment_field='subcatchment', overlap='error',
overwrite=False)` uses indexed GeoPandas intersection. An INP file has no reliable
CRS tag: when using its polygons, supply `model_crs` explicitly. Geographic area
calculations are rejected. CRS mismatch requires explicit `area_crs`, which
reprojects both layers. Projected coordinate units are converted to m², including
feet-based CRS. Choose a projection appropriate for the study area; projection
distortion is the user's responsibility.

Source/subcatchment polygon overlaps are errors, even within the same class.
Invalid geometries are never silently repaired. Gaps are errors; polygons outside
the subcatchments contribute nothing. Positive slivers are retained, avoiding
hidden area loss. Fractions use **polygon** area. Attached coverage and LID areas
use **SWMM model** area; polygon areas are retained in provenance so differences
can be inspected. Intersection `area_m2` is geometric, so it can differ from
`coverage_area` when native and mapped areas disagree.

Overlay stages assignments before committing, and requires `overwrite=True`
when replacing coverage. Imported/reassigned/converted coverage invalidates cached
intersections. Changes to attached model polygon rows are detected before GIS
outputs. Sidecars retain source/projection provenance but omit geometries; reimport
and overlay to reconstruct GIS products after loading. `plot()` delegates to
GeoPandas/Matplotlib, sharing SWMMX's plotting dependency ecosystem.

`set_surfaces(...)` is the friendly alias for GIS input;
`calculate_coverage(...)` performs overlay. `to_geodataframe()` now returns
coverage without deriving hydrology; request `include_hydrology=True` or
`include_lids=True` explicitly. Plotting calculates only what its selected kind
needs. Overlay accepts `progress(event)` and `cancelled()` callbacks; cancellation
rolls metadata back. Checks occur between stages, not inside a GEOS operation.

## LID suitability and optimisation

`lids={'bioretention': .4}` means 40% of that class is eligible. Rich metadata accepts
`suitable_fraction`, `min_area` (m²), and `priority` (0..1, descriptive only).
The first implementation applies min_area to the **aggregate class contribution
within a subcatchment**, not individual polygons. No slope, soil, ownership,
exclusion-zone or engineering feasibility is inferred.

Candidate area = subcatchment area × Σ(class fraction × suitability).
`lid_candidates(subcatchment=None, filter_function=None)` returns deterministic
`subcatchment`, `lid_type`, `candidate_area_m2`, `candidate_fraction` columns.
An optional callback returns a nonnegative candidate area no larger than the
unfiltered area. Different LID types can compete for the same surfaces; do not
sum independent bounds as if they were jointly available. Optimisation variables
can use 0 ≤ A(s,l) ≤ candidate_area(s,l), with separate shared-area constraints.
No LID_CONTROLS or LID_USAGE are created, deleted or allocated automatically.

## Scenarios, quality and persistence

`future = lc.copy()` copies metadata and clones the model. `convert` accepts
exactly one of `area` (m2/ha) and `fraction` (fraction of the **whole subcatchment**).
It rejects source overdraw and preserves total area. Hydrology changes only on
explicit application. `lc.compare(future)` returns numeric future-minus-baseline
coverage, areas, hydrology and LID bounds. Comparisons require matching IDs/areas.

`apply_swmm_landuses()` explicitly creates native water-quality land uses and
coverage percentages. Existing matching land uses or assigned-subcatchment
coverage are protected unless `overwrite=True`. That option replaces coverage
for assigned subcatchments, retaining sweeping metadata and BUILDUP/WASHOFF.
New land uses have zero sweeping settings; no pollution properties are invented.
Native rows can be inspected with `m.section('LANDUSES')` and
`m.section('COVERAGES')`. This step is never required for hydrology or GIS.

Once landcover is attached, `m.save('model.inp')` writes `model.swmmx.json` too.
Reopen with `m2 = swmm('model.inp'); lc2 = landcover(m2)`. Loading is lazy and
opt-in; ordinary users do not read/write sidecars. `lc.save('cover.json')` and
`LandCover.load('cover.json', model=None)` support explicit standalone persistence.
Class properties, coverage, suitability, custom attributes and provenance survive.
Unknown top-level JSON keys are preserved. Corrupt metadata raises ValidationError.
JSON replacement is atomic; the INP/sidecar pair is not a filesystem transaction.
Keep both files together, and load landcover before saving a reopened model under
another name if you want its metadata copied. No nonstandard INP sections appear.

## Related documentation

- [Main API and subcatchment examples](../README.md)
- [Examples index: GIS, LID usage and scenarios](../examples/README.md)
- [Release notes](../CHANGELOG.md)
- [Complete executable landcover tutorial](../examples/23_landcover.ipynb)

Notebook 23 combines the A-to-Z guide and advanced examples (previously 24).
See the [frontend/backend contract](landcover_backend.md) for stable IDs,
versioned persistence, preview handles, diagnostics and service boundaries.
