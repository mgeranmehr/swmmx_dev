# Landcover 0.0.44 implementation report

Implemented in the existing working tree, preserving pre-existing changes.
This release simplifies Python workflows and supplies backend contracts for a
future frontend. It does not include a frontend server or application.

## Delivered changes

- Atomic bulk classes/coverage from dictionaries, records, DataFrames and CSV;
  validation-only mode and structured row diagnostics.
- Stable class IDs, direct updates, immutable project/preview snapshots,
  JSON interchange, version-1 sidecar migration and schema-version checks.
- Selective reviewed application with before/after values, assumptions,
  SI/US conversion and rejection of stale, altered or foreign previews.
- Metadata undo/redo, workflow status, lightweight scenarios and explicit model
  cloning. Comparisons reject incompatible property units.
- Coverage-only spatial inspection, friendly GIS aliases and cooperative progress
  and cancellation with rollback.
- Separate contracts, workflow, calculation and native SWMM adapter modules.
- Existing hydrology, infiltration, GIS, LID suitability and native water-quality
  integration retained. Legacy methods remain available.
- Examples 23 and 24 consolidated into `examples/23_landcover.ipynb`, with a
  reproducible builder and 46 progressive lessons.

## Verification

The final suite covers existing APIs plus landcover numerical derivation, GIS,
persistence, units, atomic bulk edits, stale previews, history and JSON contracts.
Machine-readable results: `.tmp/lc044-final.xml`; log: `.tmp/lc044-final.log`.

Notebook: 92 cells, all 44 code cells executed, zero errors, five embedded plots.
Includes two native SWMM simulations, save/reopen checks, GIS overlay, expected
errors and JSON examples. HTML and execution report are under
`examples/output/landcover_044`.

Ruff checks pass for all landcover modules, new workflow tests and the notebook
builder. Runtime verification uses Python 3.12 and local dependencies. Other
operating systems and Python versions were not executed in this session.

## Release artifacts

Package metadata, public version, citation, README and changelog use **0.0.44**.
Build outputs: `dist/swmmx-0.0.44-py3-none-any.whl` and
`dist/swmmx-0.0.44.tar.gz`. Artifact verification checks all ten landcover modules,
version metadata, engine assets, `py.typed`, merged notebook and documentation.
The isolated wheel smoke test exercises the public factory and reviewed
application without importing the source checkout.

```bash
pip install --force-reinstall "dist/swmmx-0.0.44-py3-none-any.whl"
```

## Practical limits

Landcover aggregates surfaces into existing SWMM subcatchments; it does not
delineate drainage areas or replace hydraulic design/calibration. Engineering
defaults are not inferred. LID suitability is an upper bound, not an allocation.
Undo affects metadata, not native model edits. Geometry, history and previews
are session-local. GIS cancellation checks occur between stages; GEOS operations
are not interrupted internally. INP and sidecar saves are not one filesystem
transaction. No commit, push or package publication was performed.

See [the modelling guide](landcover.md) and [backend contract](landcover_backend.md).
