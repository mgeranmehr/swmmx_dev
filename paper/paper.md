---
title: 'swmmx: A Python toolkit for building, editing, running, importing, visualizing, and exporting EPA SWMM models'
tags:
  - Python
  - EPA SWMM
  - hydrology
  - hydraulics
  - urban drainage
  - stormwater
  - wastewater
  - environmental modelling
  - GIS
  - scientific software
authors:
  - name: Mohammadali Geranmehr
    orcid: 0000-0001-7075-915X
    affiliation: 1
affiliations:
  - name: University of Sheffield, United Kingdom
    index: 1
date: 20 May 2026
bibliography: paper.bib
---

# Summary

`swmmx` is an open-source Python package for working with United States Environmental Protection Agency Storm Water Management Model (EPA SWMM) projects from Python. It provides a high-level interface for opening, creating, editing, validating, running, visualizing, importing, and exporting SWMM models. The package is designed for researchers, engineers, and data scientists who use SWMM in reproducible modelling workflows, scenario analysis, teaching, and applied research.

The package centres on a single model object:

```python
from swmmx import swmm

m = swmm("examples/example.inp")
m.plot_layout()
lengths = m.get.conduit.length()
m.set.conduit.roughness(0.013)
m.run()
m.plot_timeseries.link.flow()
```

This object exposes a discoverable API for model access and modification, including `m.get`, `m.set`, `m.count`, `m.add`, `m.remove`, `m.import_csv`, `m.import_gis`, `m.export`, `m.validate`, `m.run`, and `m.runs`. The package supports both conventional batch simulation with `m.run()` and step-by-step simulation with `m.runs()`, which exposes the native SWMM step loop as a Python iterator. It also includes plotting tools for model layouts, result time series, and longitudinal profiles, as well as export tools for CSV, GIS, and Excel outputs.

# Statement of need

EPA SWMM is widely used for modelling stormwater, wastewater, combined sewer, and urban drainage systems [@rossman2015swmm]. It is an established hydrologic and hydraulic simulation engine, but many research and engineering workflows require repeated model editing, scenario generation, automated simulation, data exchange with GIS or tabular datasets, and reproducible post-processing. These workflows are often difficult to manage through a graphical interface alone, especially when models must be generated or modified programmatically.

Several Python packages already support SWMM-related workflows. `PySWMM` provides Pythonic access to the SWMM engine and is particularly useful for simulation control and interaction during a run [@mcdonnell2020pyswmm]. `swmm_api` provides tools for reading, modifying, writing, and analysing SWMM input, report, and output files [@pichler2024swmmapi]. `swmmio` supports pandas-oriented access to SWMM input and result data for pre- and post-processing [@swmmio]. `swmm-toolkit` provides lower-level wrappers around SWMM solver and output libraries [@swmmtoolkit].

`swmmx` addresses a complementary need: an integrated, high-level Python modelling interface that covers the full SWMM model lifecycle in one consistent API. The goal is not only to run SWMM from Python, but also to make model construction, inspection, editing, validation, plotting, import, export, and iterative analysis accessible through a single object-oriented workflow. This is useful for research applications such as scenario analysis, sensitivity and uncertainty analysis, design and operational optimisation, model calibration workflows, teaching examples, reproducible urban drainage studies, and data-driven integration with GIS and monitoring datasets.

# Software design and functionality

`swmmx` is designed around a single model object returned by the `swmm` constructor. The constructor can open an existing SWMM input file or create a new model using SI or US unit conventions:

```python
m = swmm("examples/example.inp")
m = swmm()
m = swmm(new="SI", flow_unit="CMS")
m = swmm(new="US", flow_unit="GPM")
```

The public interface is organized into namespaces that mirror common modelling tasks. Parameter access is provided through `m.get.<category>.<parameter>()`, while editing is provided through `m.set.<category>.<parameter>()`. For example:

```python
lengths = m.get.conduit.length()
one_length = m.get.conduit.length("P001")
flow = m.get.link.flow(ids=["P001", "P005"], format="df")

m.set.conduit.roughness(0.013)
m.set.conduit.roughness([0.013, 0.014], ids=["P001", "P005"])
```

The getter interface supports model input fields, derived values, attached records, and result variables when simulation output is available. The setter interface exposes editable parameters and raises clear errors when users attempt to modify read-only, derived, or result fields.

Model construction is supported through `m.add.<category>.<element_type>()`. For example, a simple model can be assembled from scratch by adding nodes, links, a rainfall time series, a rain gage, and a subcatchment:

```python
m = swmm(new="SI")

m.add.node.junction("J1", x=0.0, y=0.0, invert_elevation=10, max_depth=3)
m.add.node.outfall("OUT1", x=100.0, y=0.0, invert_elevation=9, type="FREE")

m.add.link.conduit(
    "C1",
    from_node="J1",
    to_node="OUT1",
    length=100,
    roughness=0.013,
    shape="CIRCULAR",
    diameter=1.0,
)

m.add.time.time_series(
    "Rain1",
    data=[
        ("2026-01-01 00:00", 0.0),
        ("2026-01-01 00:05", 5.0),
    ],
)

m.add.hydrology.rain_gage(
    "RG1",
    format="INTENSITY",
    interval="00:05",
    source_type="TIMESERIES",
    time_series="Rain1",
)

m.add.hydrology.subcatchment(
    "S1",
    rain_gage="RG1",
    outlet="J1",
    x=0.0,
    y=0.0,
    area=1.0,
)

m.save("new_model.inp")
```

The add and remove interfaces validate IDs, required values, numeric values, enumerated options, references, and removal dependencies. Removing elements uses `m.remove.<category>.<element_type>()`; unsafe removals are refused by default, while conservative cascades may be performed when `force=True` is used. Model edits set the in-memory model state as modified and mark previous simulation results as stale.

# Simulation workflows

`swmmx` supports normal and step-wise simulation workflows. The `m.run()` method executes the SWMM model and makes result variables available through the result-aware getter and plotting interfaces. The `m.runs()` method exposes the simulation step loop as an iterator:

```python
for step in m.runs():
    print(step.index, step.time, step.elapsed_days)

print(m.time.count_run())
```

This design supports progress monitoring, interactive workflows, dynamic inspection, and future extensions for control-oriented modelling. Pre-run time helpers, such as `m.time.vector()` and `m.time.count()`, reflect the expected report period. Post-run helpers, such as `m.time.vector_run()` and `m.time.count_run()`, use the actual period count read from the SWMM output file after the engine finishes.

`swmmx` uses lazy native-engine loading and supports bundled Windows and Linux engines, with a custom engine path option for other deployments. This allows users to work with SWMM models from Python while retaining access to the native SWMM simulation engine.

# Import, export, and data exchange

Urban drainage models commonly interact with external asset databases, GIS layers, survey tables, calibration datasets, and reporting tools. `swmmx` includes import and export interfaces to support these workflows.

CSV import is exposed through:

```python
m.import_csv.node.junction("junctions.csv")
m.import_csv.node.outfall("outfalls.csv")
m.import_csv.link.conduit("conduits.csv")
m.import_csv.hydrology.subcatchment("subcatchments.csv")
```

GIS import is exposed through:

```python
m.import_gis.node.junction("junctions.shp")
m.import_gis.link.conduit("pipes.geojson")
m.import_gis.hydrology.subcatchment("subcatchments.gpkg", layer="subcatchments")
```

The importers normalize column names, apply common aliases, validate rows, and return an `ImportResult` object. Users may provide explicit field maps when their source data use project-specific naming conventions:

```python
result = m.import_csv.link.conduit(
    "pipes.csv",
    field_map={
        "id": "PipeID",
        "from_node": "FromNode",
        "to_node": "ToNode",
        "length": "Length",
        "roughness": "ManningN",
        "diameter": "Diameter",
    },
)
```

The import API supports dry runs, update and upsert modes, error handling options, unknown-field handling, and group-level shortcuts that dispatch rows by type. GIS import uses optional `geopandas` and `shapely` dependencies.

Export is available through:

```python
m.export.gis()
m.export.csv(path="exports/csv", elements="all", time_step=-1)
m.export.excel(path="exports", file_name="model_export.xlsx")
```

CSV exports write one table per file, Excel exports write one workbook with one sheet per selected table, and GIS exports write spatial layers for nodes, links, subcatchments, and rain gages. Exported tables can include model parameters and, when results are available, result snapshots. CSV files generated by `m.export.csv()` are designed to import back cleanly where possible, which supports round-trip editing and data exchange.

# Visualization

`swmmx` provides built-in visualization tools using Matplotlib [@hunter2007matplotlib]. The layout plotter draws mapped subcatchments, links, nodes, rain gages, and LID-related objects where available:

```python
m.plot_layout(
    title="Drainage Network",
    legend=True,
    grid=True,
    axis=True,
)
```

Layer dictionaries support static and data-driven symbology. Nodes, links, and subcatchments can be styled by input parameters, result variables, or user-supplied mappings. For example, links can be coloured by conduit roughness or plotted with result-driven widths. Legends and sampled continuous swatches are created to make encoded values interpretable on the final figure.

Time-series plotting is available through `m.plot_timeseries.<category>.<parameter>()`. These functions read through the result API and can plot one or many object time series. Longitudinal profile plotting is available through `m.plot_profile.nodes()`, `m.plot_profile.links()`, and `m.plot_profile.longest()`, with hydraulic grade line and water-depth overlays when simulation results are available. Plotting functions return Matplotlib `(fig, ax)` objects, support `ax=` for composition, and support saving through `save_path` and `save_format`.

# Validation and reproducibility

The `m.validate()` interface checks common model issues, including duplicate IDs, missing required options, invalid unit values, missing nodes or links, conduit endpoint problems, and several cross-section and reference errors. The returned validation object exposes a summary status and tabular representation:

```python
validation = m.validate()
print(validation.ok)
print(validation.to_frame())
```

Validation does not replace engineering review, but it helps identify common input problems before simulation or publication of results. The package also includes logging and cloning helpers, as well as preservation-aware parsing and writing of SWMM input files. When possible, `swmmx` preserves comments, unknown sections, and section order during `.inp` file round trips. This is important for real engineering models, where files often include manual comments, legacy sections, and formatting conventions that users do not want to lose during automation.

The package documentation includes executable examples and reference notebooks for the getter, setter, add, remove, plot, import, and export interfaces. These examples are intended to support both learning and regression-style checking of expected behaviours.

# Relationship to existing software

The Python SWMM ecosystem includes several mature and useful packages. `PySWMM` is well suited to simulation control and real-time interaction with the SWMM engine [@mcdonnell2020pyswmm]. `swmm_api` provides extensive tools for SWMM input, report, and output file automation [@pichler2024swmmapi]. `swmmio` gives users a pandas-oriented interface for model and result processing [@swmmio]. `swmm-toolkit` exposes lower-level solver and output bindings [@swmmtoolkit].

`swmmx` is intended to complement these tools by providing a high-level, integrated modelling environment. Its main contribution is a consistent API that covers model creation, editing, validation, import, export, plotting, and simulation in one workflow. This makes it suitable for users who need to build reproducible scripts around complete SWMM modelling tasks rather than only one part of the workflow.

# Availability

The source code for `swmmx` is available from GitHub at:

\url{https://github.com/mgeranmehr/swmmx_dev}

The package is available from the Python Package Index at:

\url{https://pypi.org/project/swmmx/}


# Software status and responsible use

`swmmx` is under active development and testing. Users are encouraged to use the latest available release and to report unexpected behaviour through the project issue tracker.

The package is a programmatic toolkit for EPA SWMM and assumes that users have appropriate knowledge of hydrology, hydraulics, SWMM input conventions, and the EPA SWMM simulation engine. Simulation results should be checked carefully before use in research, design, planning, or operational decision-making. As with any modelling software, professional engineering judgement and independent verification are required for critical applications.

# Acknowledgements

The author acknowledges the developers and maintainers of EPA SWMM and the wider open-source Python scientific computing ecosystem. `swmmx` builds on widely used Python tools including NumPy [@harris2020array], pandas [@reback2020pandas; @mckinney2010data], Matplotlib [@hunter2007matplotlib], and NetworkX [@hagberg2008networkx]. The author also acknowledges the developers of existing Python SWMM packages, including PySWMM, swmm_api, swmmio, and swmm-toolkit, which have helped establish and grow the Python ecosystem for SWMM modelling.

# AI usage disclosure

AI tools were used during software development to assist with repetitive programming, documentation, and debugging tasks. For the manuscript, AI tools were used for grammar checking and language refinement. All outputs were reviewed and validated by the author.

# References
