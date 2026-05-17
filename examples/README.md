# swmmx examples

The main `examples/` folder now contains the simplest learning scripts for the public `swmmx` API. They use `examples/example.inp`, never overwrite it, and write generated files into `examples/output/`.

The fuller runnable versions live in [`examples/standard/`](standard/). Those versions keep the same ten topics but add helper functions, safer branching, and more explanatory handling around optional features.

| Topic | Simple learning script | Standard runnable script |
| --- | --- | --- |
| Open, validate, and run | `01_open_validate_run.py` | `standard/01_open_validate_run.py` |
| Modify conduit diameters and compare | `02_modify_conduit_diameters_compare.py` | `standard/02_modify_conduit_diameters_compare.py` |
| Step-by-step runs | `03_step_by_step_runs_dynamic_control.py` | `standard/03_step_by_step_runs_dynamic_control.py` |
| Layout plots | `04_plot_layout_examples.py` | `standard/04_plot_layout_examples.py` |
| Time-series plots | `05_plot_timeseries_examples.py` | `standard/05_plot_timeseries_examples.py` |
| Profile plots | `06_plot_profile_examples.py` | `standard/06_plot_profile_examples.py` |
| GIS/CSV/Excel export | `07_export_examples.py` | `standard/07_export_examples.py` |
| Time and count helpers | `08_time_and_count_functions.py` | `standard/08_time_and_count_functions.py` |
| Get/set patterns | `09_get_set_examples.py` | `standard/09_get_set_examples.py` |
| Build a model from scratch | `10_create_model_from_scratch_add_remove.py` | `standard/10_create_model_from_scratch_add_remove.py` |

Additional notebooks:

| Notebook | What it demonstrates |
| --- | --- |
| `11_all_get_functions.ipynb` | Categorized reference notebook for every public getter, including input/output notes |
| `12_all_set_functions.ipynb` | Categorized reference notebook for every public setter path, including writable/read-only behavior |
| `13_all_add_functions.ipynb` | Categorized reference notebook for every public add endpoint, including inputs, types, defaults, and conditions |
| `14_all_remove_functions.ipynb` | Categorized reference notebook for every public remove endpoint, including dependencies, force behavior, and outputs |

Run an example from the repository root:

```bash
python examples/01_open_validate_run.py
```

Run the fuller standard version:

```bash
python examples/standard/01_open_validate_run.py
```

Open the notebooks in JupyterLab, Jupyter Notebook, VS Code, or another notebook viewer:

```bash
jupyter notebook examples/11_all_get_functions.ipynb
jupyter notebook examples/12_all_set_functions.ipynb
jupyter notebook examples/13_all_add_functions.ipynb
jupyter notebook examples/14_all_remove_functions.ipynb
```

Notes:

- Plotting examples require `matplotlib`.
- GIS export requires optional `geopandas` and `shapely`.
- Excel export requires optional `openpyxl`.
- Run-based examples require a working EPA SWMM engine for the current platform.
- `03_step_by_step_runs_dynamic_control.py` is intentionally honest about the current boundary: step timing is available, while live `step.get` / `step.set` control is future work.
