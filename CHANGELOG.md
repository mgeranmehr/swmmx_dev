# Changelog

## 0.0.44 — 2026-09-20

- Simplify landcover setup with atomic `define_classes` and `set_coverage` batches,
  DataFrame/CSV input, row diagnostics and validation-only mode.
- Add immutable, versioned project/preview contracts, stable class IDs, selective
  preview/apply, stale-preview rejection and explicit SI/US conversion at application.
- Add `update_class`, metadata undo/redo, lightweight scenarios, workflow status,
  coverage-only GIS inspection and cooperative overlay progress/cancellation.
- Preserve the original API, migrate version-1 sidecars, separate calculation and
  SWMM adapter services, and document the future frontend integration contract.
- Merge notebooks 23 and 24 into notebook 23: 46 lessons and 44 executable code cells.


- Add the opt-in `landcover` physical surface framework, distinct from native
  SWMM water-quality LANDUSES, with validated classes and manual area/fraction assignments.
- Add indexed GIS overlay, explicit projected-CRS handling, conservative overlap
  and gap rejection, and DataFrame/GeoDataFrame inspection and plotting.
- Derive weighted imperviousness, roughness, depression storage and optional
  PctZero/infiltration; selectively apply through existing setters with stale-state handling.
- Add LID suitability bounds, independent scenario copies, area conversions and comparisons.
- Explicitly connect native LANDUSES/COVERAGES while protecting existing quality data.
- Persist class, coverage, custom metadata and GIS provenance in opt-in JSON sidecars.
- Add numerical, GIS, integration and persistence tests, the landcover API guide,
  and executable notebook 23 with deterministic local vector data.
## 0.0.43 — 2026-09-11

- Implement `m.add.node.storage_unit`, `m.add.node.divider` and their remove
  endpoints, with finite numeric validation, coordinates, tags and conservative
  dependency handling.
- Share EPA storage/divider row decoding across getters, setters, import/export,
  annotations and structural validation. Support functional/tabular storage,
  EPA 5.2 analytical shapes, surcharge, evaporation and Green-Ampt seepage, and
  CUTOFF/TABULAR/WEIR/OVERFLOW dividers.
- Validate curve types and diverted-link references, protect dependent curves
  and links from removal, and preserve model state when a bulk edit fails.
- Add storage/divider result getters and use binary output IDs to map results
  correctly regardless of input section order or reported object selection.
- Add notebook 22 with executable construction, round-trip and simulation
  examples; expand tests for native execution, dependency safety and interchange.

Existing `.inp` rows are preserved when opened/saved without edits. Prior CSV
exports of storage/dividers used incorrect fixed-column layouts; re-export from
the original `.inp` with this release before importing those tables. Relation
type changes require a mapping of the new type/parameters or a complete import
update row; ID renaming remains guarded.

