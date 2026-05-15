# swmmx

`swmmx` is a Python 3.10+ toolkit for EPA SWMM with a deliberately small, stable first public surface:

```python
from swmmx import swmm

m = swmm("example/example.inp")
print(m.time.count())
result = m.run()
print(m.time.count_run())
```

Version `0.0.2` currently provides:

- `swmm(path=None, new=None, flow_unit=None, custom_dll_path=None)`
- `m.time.vector()`, `m.time.count()`, `m.time.vector_run()`, `m.time.count_run()`
- `m.save()`, `m.run()`, `m.runs()`, `m.validate()`, `m.log()`, and `m.clone()`
- lazy native-engine loading for bundled Windows/Linux engines plus custom engine paths
- preserving `.inp` parsing/writing that keeps comments, unknown sections, and section order whenever possible

Constructor examples:

```python
m = swmm("example/example.inp")          # open an existing model
m = swmm()                               # new SI model, LPS by default
m = swmm(new="SI", flow_unit="CMS")      # new SI model
m = swmm(new="US", flow_unit="GPM")      # new US model
```

## Native engines

The package includes the supplied bundled engines:

- Windows 64-bit: `swmm5.dll`
- Linux 64-bit: `libswmm5.so`
- macOS: reserved path only for now; provide a custom engine path until a GitHub Actions build is added

## Schema-driven growth

`swmmx` looks for `parameters.csv` in this order:

1. an explicit path passed internally,
2. the `SWMMX_SCHEMA_PATH` environment variable,
3. `src/swmmx/schemas/parameters.csv` inside the package,
4. `parameters.csv` in the current working directory.

The expected columns are:

- `main_category`
- `sub_category`
- `source`
- `type`
- `size`

That CSV is treated as the primary API registry for future parameter-facing accessors. Version `0.0.2` ships the current table with the package, uses it as the canonical registry, and exposes the loaded registry through `m.schema`.

Human-readable headers such as `Main category`, `Subcategory / parameter group`, and `Size / structure` are normalized internally to `main_category`, `sub_category`, and `size`, so the source table can stay pleasant to maintain.

## Time semantics

`m.time.vector()` mirrors SWMM reporting behavior: it starts at the first report interval after `REPORT_START_*` and proceeds through `END_*`.

```python
frame = m.time.vector() # pandas DataFrame with timestamp index
```

Run-time vectors use the actual period count read from the `.out` file after the engine finishes.
`m.time.count()` remains the expected pre-run count; `m.time.count_run()` is the actual post-run count and requires results.

## Validation

```python
validation = m.validate()
print(validation.ok)
print(validation.to_frame())
```

The first validator checks duplicate IDs, missing required options, invalid unit values, missing nodes/links, conduit endpoints, and several common cross-section/reference errors.
