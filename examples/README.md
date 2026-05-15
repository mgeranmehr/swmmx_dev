# swmmx examples

These scripts are small, runnable demonstrations of the public `swmmx` API. They use `examples/example.inp`, never overwrite it, and write generated files into `examples/output/`.

For first-time learning, the same ten topics are also available as flatter scripts in [`examples/simple/`](simple/). Those versions have no `main()` function, no `try` blocks, and fewer defensive branches so the API is easier to read line by line.

| Example file | What it demonstrates |
| --- | --- |
| `01_open_validate_run.py` | Open a model, validate it, run it, and inspect the run summary |
| `02_modify_conduit_diameters_compare.py` | Increase circular conduit diameters through cross-section geometry, rerun, compare flows, and save |
| `03_step_by_step_runs_dynamic_control.py` | Iterate `runs()` safely and explain the current live-control boundary |
| `04_plot_layout_examples.py` | Save static, parameter-driven, result-driven, and user-driven network layout maps |
| `05_plot_timeseries_examples.py` | Plot conduit flow, node depth, and system runoff result time series |
| `06_plot_profile_examples.py` | Plot node-to-node, selected-link, and longest-path longitudinal profiles |
| `07_export_examples.py` | Export GIS, CSV, Excel, selected tables, and selected result snapshots |
| `08_time_and_count_functions.py` | Use pre-run/run time vectors and model count summaries |
| `09_get_set_examples.py` | Read values in practical containers, set parameters, update options, and catch read-only errors |
| `10_create_model_from_scratch_add_remove.py` | Build a small SI model from scratch, validate it, save it, remove a link, and save again |

Run an example from the repository root:

```bash
python examples/01_open_validate_run.py
```

Run a simpler learning version:

```bash
python examples/simple/01_open_validate_run.py
```

Notes:

- Plotting examples require `matplotlib`.
- GIS export requires optional `geopandas` and `shapely`.
- Excel export requires optional `openpyxl`.
- Run-based examples require a working EPA SWMM engine for the current platform.
- `03_step_by_step_runs_dynamic_control.py` is intentionally honest about the `0.0.10` boundary: step timing is available, while live `step.get` / `step.set` control is future work.
