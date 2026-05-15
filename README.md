# swmmx

`swmmx` is a Python 3.10+ toolkit for EPA SWMM with a deliberately small, stable first public surface:

```python
from swmmx import swmm

m = swmm("example/example.inp")
print(m.time.count())
result = m.run()
print(m.time.count_run())
```

Version `0.0.7` currently provides:

- `swmm(path=None, new=None, flow_unit=None, custom_dll_path=None)`
- `m.time.vector()`, `m.time.count()`, `m.time.vector_run()`, `m.time.count_run()`
- structured parameter access through `m.get.<main_category>.<sub_category>()` and `m.set.<main_category>.<sub_category>()`
- discoverable object counts through `m.count.<main_category>()`, `m.count.model()`, `m.count.model_dict()`, and `m.count.model_df()`
- editable model construction through `m.add.<category>.<element_type>()` and `m.remove.<category>.<element_type>()`
- matplotlib plotting through `m.plot_layout()`, `m.plot_timeseries.<category>.<sub_category>()`, and `m.plot_profile.*`
- external-format export through `m.export.gis()`, `m.export.csv()`, and `m.export.excel()`
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

## Time semantics

`m.time.vector()` mirrors SWMM reporting behavior: it starts at the first report interval after `REPORT_START_*` and proceeds through `END_*`.

```python
frame = m.time.vector() # pandas DataFrame with timestamp index
```

Run-time vectors use the actual period count read from the `.out` file after the engine finishes.
`m.time.count()` remains the expected pre-run count; `m.time.count_run()` is the actual post-run count and requires results.

## Parameter access

```python
lengths = m.get.conduit.length()
one_length = m.get.conduit.length("P001")
flow = m.get.link.flow(ids=["P001", "P005"], format="df")

m.set.conduit.roughness(0.013)
m.set.conduit.roughness([0.013, 0.014], ids=["P001", "P005"])
```

Supported getters default to NumPy output; `format="df"` gives pandas output. Writable parameters appear in `dir(m.set.<category>)`; attempting to set a derived or result parameter raises a read-only error.

## Counts

```python
m.count.conduit()
m.count.node()
m.count.subcatchment()

total = m.count.model()
by_type = m.count.model_dict()
summary = m.count.model_df()
```

Count helpers take no `ids` or `format` arguments and always reflect the current in-memory model, including unsaved add/remove edits. `m.count.model()` totals detailed element types without double-counting composite rollups such as `node` and `link`; the dictionary and DataFrame summaries expose the detailed counts behind that total.

## Add and remove elements

```python
from swmmx import swmm

m = swmm(new="SI")

m.add.node.junction("J1", invert_elevation=10, max_depth=3)
m.add.node.outfall("OUT1", invert_elevation=9, type="FREE")

m.add.link.conduit(
    "C1",
    from_node="J1",
    to_node="OUT1",
    length=100,
    roughness=0.013,
    shape="CIRCULAR",
    diameter=1.0,
)

# Referenced objects must exist before they are used.
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

m.save("new_model.inp")

m.remove.link.conduit("C1")
```

The add API validates IDs, required fields, numeric values, enums, and references before it writes EPA SWMM records. The remove API validates dependencies before deletion; by default it refuses unsafe removals, while `force=True` performs only conservative cascades that are known to remain valid. For example, removing a node with `force=True` can remove dependent conduits, but unsupported cascades raise a clear error instead of leaving broken references.

When coordinates are omitted, `swmmx` uses practical display defaults:

- new nodes use `x = max(node x) + 100`, `y = max(node y)`, or `(0, 0)` when the model has no node coordinates;
- new rain gages use the maximum mapped `x` and `y`, or `(0, 0)` when the model has no map coordinates;
- new subcatchments use the minimum mapped `x` and `y`, or `(0, 0)` when the model has no map coordinates.

Every add or remove operation sets `m.modified` to `True`. If the model already had results, the edit also sets `m.results_stale` to `True` and invalidates the old result accessors until the model is run again.

Generic fallbacks are also available:

```python
m.add_element("node", "junction", "J2", invert_elevation=11, max_depth=2)
m.remove_element("node", "junction", "J2")
```

## Plotting

`swmmx` uses matplotlib directly for network maps, result time series, and longitudinal profiles:

```python
m.plot_layout()

m.plot_layout(
    title="Drainage Network",
    legend=True,
    grid=True,
    axis=True,
)

m.plot_layout(
    links={
        "color": {
            "by": "parameter",
            "category": "conduit",
            "variable": "roughness",
            "mode": "continuous",
            "cmap": "viridis",
        }
    }
)

m.plot_timeseries.link.flow(["C1", "C2"])

m.plot_profile.nodes(
    "J1",
    "OUT1",
    show_hgl=True,
    aggregation="max",
)
```

`m.plot_layout()` draws mapped subcatchments, links, nodes, and rain gages from the model coordinates. Layer dictionaries support ordinary static styling as well as data-driven styling from fixed input parameters, simulation results, or your own ID-to-value mappings. Result-driven styles require a completed run; user-data styles are useful for classes such as risk bands, inspection status, or scenario groups.

`m.plot_timeseries.<category>.<sub_category>()` routes through the result API and plots one or many timestamped series with matplotlib. `m.plot_profile.nodes()`, `.links()`, and `.longest()` build directed hydraulic paths and render geometry-first longitudinal profiles, with HGL/water overlays available after a run.

All plotting calls return `(fig, ax)`, accept `ax=` for composition, and support `save_path=` / `save_format=`. Common errors are explicit: layout plots need coordinates, result-based plots need `m.run()`, invalid IDs raise `UnknownIDError`, and disconnected profile requests raise `NoPathError`.

## Export

```python
m.export.gis()

m.export.gis(
    path="exports/gis",
    elements=["nodes", "links", "subcatchments"],
)

m.export.csv(
    path="exports/csv",
    elements="all",
    time_step=-1,
)

m.export.excel(
    path="exports",
    file_name="model_export.xlsx",
)
```

If `path` is omitted, exports go beside the model file when one exists, otherwise into the current working directory. `file_name` controls a single workbook name or the prefix used for multi-file CSV/GIS exports. `elements` accepts named tables, groups such as `hydrology` or `quality`, or `"all"`.

When results are available, `time_step=-1` attaches the last simulated snapshot to result-capable tables. Without results, exports continue with parameter-only tables and a warning by default; use `strict_results=True` when missing results should be treated as an error. CSV writes one UTF-8 file per table, while Excel writes one workbook with one sheet per selected table.

GIS export writes spatial layers for nodes, links, subcatchments, and rain gages. It requires the optional packages `geopandas` and `shapely` (`pip install geopandas shapely`). Existing outputs are protected by default; pass `overwrite=True` only when replacing files is intentional.

## Public parameter catalog

The public dotted API is organized into the following categories and subcategories:

- **`option_general`**: `flow_units`, `infiltration_model`, `flow_routing`, `link_offsets`, `force_main_equation`, `allow_ponding`, `minimum_slope`, `skip_steady_state`, `system_flow_tolerance`, `lateral_flow_tolerance`
- **`option_process`**: `ignore_rainfall`, `ignore_snowmelt`, `ignore_groundwater`, `ignore_rdii`, `ignore_routing`, `ignore_quality`
- **`option_date_time`**: `start_date`, `start_time`, `end_date`, `end_time`, `report_start_date`, `report_start_time`, `report_step`, `wet_step`, `dry_step`, `routing_step`, `rule_step`, `sweep_start`, `sweep_end`, `dry_days`
- **`option_dynamic_wave`**: `inertial_damping`, `normal_flow_limited`, `surcharge_method`, `variable_step`, `minimum_step`, `lengthening_step`, `minimum_surface_area`, `head_tolerance`, `maximum_trials`, `threads`
- **`rain_gage`**: `id`, `count`, `format`, `interval`, `snow_catch_factor`, `source_type`, `time_series`, `filename`, `station`, `units`, `rainfall`
- **`subcatchment`**: `id`, `count`, `rain_gage`, `outlet`, `area`, `width`, `slope`, `impervious_percent`, `curb_length`, `snow_pack`, `tag`, `polygon`, `centroid`, `rainfall`, `snow_depth`, `evaporation`, `infiltration`, `runoff`, `groundwater_flow`, `groundwater_elevation`, `soil_moisture`, `pollutant_concentration`, `n_impervious`, `n_pervious`, `depression_storage_impervious`, `depression_storage_pervious`, `zero_depression_storage_impervious_percent`, `subarea_routing`, `percent_routed`
- **`infiltration_horton`**: `maximum_rate`, `minimum_rate`, `decay`, `dry_time`, `maximum_volume`
- **`infiltration_green_ampt`**: `suction_head`, `hydraulic_conductivity`, `initial_moisture_deficit`
- **`infiltration_curve_number`**: `curve_number`, `conductivity`, `dry_time`
- **`node`**: `id`, `count`, `type`, `invert_elevation`, `max_depth`, `initial_depth`, `surcharge_depth`, `ponded_area`, `tag`, `coordinate`, `external_inflow`, `dry_weather_flow`, `treatment`, `depth`, `head`, `volume`, `lateral_inflow`, `total_inflow`, `flooding`, `overflow`, `pollutant_concentration`
- **`junction`**: `id`, `count`, `invert_elevation`, `max_depth`, `initial_depth`, `surcharge_depth`, `ponded_area`
- **`outfall`**: `id`, `count`, `invert_elevation`, `type`, `fixed_stage`, `tidal_curve`, `time_series`, `tide_gate`, `route_to`
- **`flow_divider`**: `id`, `count`, `invert_elevation`, `max_depth`, `initial_depth`, `surcharge_depth`, `ponded_area`, `type`, `diverted_link`, `cutoff_flow`, `diversion_curve`, `weir_height`, `weir_coefficient`
- **`storage_unit`**: `id`, `count`, `invert_elevation`, `max_depth`, `initial_depth`, `storage_curve_type`, `storage_curve`, `area`, `area_coefficient`, `area_exponent`, `area_constant`, `evaporation_factor`, `seepage_loss`
- **`link`**: `id`, `count`, `type`, `from_node`, `to_node`, `inlet_offset`, `outlet_offset`, `initial_flow`, `maximum_flow`, `flap_gate`, `tag`, `vertices`, `flow`, `depth`, `velocity`, `volume`, `capacity`, `setting`, `pollutant_concentration`
- **`conduit`**: `id`, `count`, `from_node`, `to_node`, `length`, `roughness`, `inlet_offset`, `outlet_offset`, `initial_flow`, `maximum_flow`, `shape`, `geometry`, `barrels`, `culvert_code`, `entry_loss`, `exit_loss`, `average_loss`, `flap_gate`, `seepage_rate`, `slope`, `full_area`, `full_depth`, `hydraulic_radius`, `full_flow`, `normal_depth`, `critical_depth`, `flow`, `depth`, `velocity`, `capacity`
- **`pump`**: `id`, `count`, `from_node`, `to_node`, `curve`, `initial_status`, `startup_depth`, `shutoff_depth`, `flow`, `status`, `setting`, `energy`
- **`orifice`**: `id`, `count`, `from_node`, `to_node`, `type`, `shape`, `height`, `width`, `offset`, `discharge_coefficient`, `flap_gate`, `open_close_time`, `flow`, `setting`
- **`weir`**: `id`, `count`, `from_node`, `to_node`, `type`, `crest_height`, `length`, `side_slope`, `discharge_coefficient`, `flap_gate`, `end_contractions`, `end_coefficient`, `surcharge`, `road_width`, `road_surface`, `flow`, `setting`
- **`outlet`**: `id`, `count`, `from_node`, `to_node`, `offset`, `flap_gate`, `rating_type`, `curve`, `coefficient`, `exponent`, `flow`, `setting`
- **`cross_section`**: `link`, `shape`, `geometry_1`, `geometry_2`, `geometry_3`, `geometry_4`, `barrels`, `culvert_code`, `height`, `width`, `side_slope`, `shape_curve`
- **`transect`**: `id`, `count`, `roughness_left`, `roughness_right`, `roughness_channel`, `left_bank`, `right_bank`, `stations`, `elevations`, `modifiers`
- **`curve`**: `id`, `count`, `type`, `x`, `y`, `points`
- **`coordinate`**: `node_coordinates`, `subcatchment_coordinates`, `link_vertices`, `polygons`, `labels`, `map_dimensions`, `map_units`
- **`street`**: `id`, `count`, `crown_width`, `curb_height`, `cross_slope`, `roughness`, `depression_storage`, `gutter_width`, `gutter_slope`, `spread`
- **`inlet`**: `id`, `count`, `type`, `grate_length`, `grate_width`, `grate_type`, `curb_length`, `curb_height`, `slotted_length`, `slotted_width`, `captured_flow`
- **`inlet_usage`**: `node`, `inlet`, `conduit`, `number`, `clogging_factor`, `flow_restriction`
- **`lid_control`**: `id`, `count`, `type`
- **`lid_surface`**: `storage_depth`, `vegetation_fraction`, `roughness`, `slope`, `side_slope`
- **`lid_pavement`**: `thickness`, `void_ratio`, `impervious_surface_fraction`, `permeability`, `clogging_factor`
- **`lid_soil`**: `thickness`, `porosity`, `field_capacity`, `wilting_point`, `conductivity`, `conductivity_slope`, `suction_head`
- **`lid_storage`**: `height`, `void_ratio`, `seepage_rate`, `clogging_factor`
- **`lid_drain`**: `coefficient`, `exponent`, `offset_height`, `delay`, `open_level`, `closed_level`, `control_curve`
- **`lid_usage`**: `subcatchment`, `lid_control`, `number`, `area`, `width`, `initial_saturation`, `from_impervious_percent`, `from_pervious_percent`, `outlet`, `drain_to`, `inflow`, `evaporation`, `infiltration`, `surface_outflow`, `drain_outflow`, `storage`
- **`aquifer`**: `id`, `count`, `porosity`, `wilting_point`, `field_capacity`, `conductivity`, `conductivity_slope`, `tension_slope`, `upper_evaporation_fraction`, `lower_evaporation_depth`, `lower_groundwater_loss_rate`, `bottom_elevation`, `water_table_elevation`, `unsaturated_moisture`, `upper_evaporation_pattern`
- **`groundwater`**: `subcatchment`, `aquifer`, `node`, `surface_elevation`, `a1`, `b1`, `a2`, `b2`, `a3`, `fixed_depth`, `threshold_elevation`, `lateral_flow_equation`, `deep_flow_equation`
- **`snow_pack`**: `id`, `count`, `plowable_fraction`, `impervious_fraction`, `pervious_fraction`, `minimum_melt_coefficient`, `maximum_melt_coefficient`, `base_temperature`, `free_water_capacity_fraction`, `initial_snow_depth`, `initial_free_water`, `depth_at_100_percent_cover`, `removal_depth`, `fraction_to_impervious`, `fraction_to_pervious`, `fraction_to_immediate_melt`, `fraction_to_subcatchment`, `fraction_to_outflow`, `destination_subcatchment`
- **`climate`**: `temperature_time_series`, `evaporation_type`, `evaporation_constant`, `evaporation_monthly`, `evaporation_time_series`, `evaporation_recovery_pattern`, `evaporation_dry_only`, `wind_speed_type`, `wind_speed_monthly`, `snowmelt_parameters`, `areal_depletion_impervious`, `areal_depletion_pervious`
- **`climate_adjustment`**: `temperature`, `evaporation`, `rainfall`, `conductivity`
- **`pollutant`**: `id`, `count`, `units`, `rain_concentration`, `groundwater_concentration`, `rdii_concentration`, `decay_coefficient`, `snow_only`, `co_pollutant`, `co_pollutant_fraction`, `dry_weather_flow_concentration`, `initial_concentration`
- **`land_use`**: `id`, `count`, `sweeping_interval`, `sweeping_availability`, `last_swept`
- **`coverage`**: `subcatchment`, `land_use`, `percent`
- **`loading`**: `subcatchment`, `pollutant`, `initial_buildup`
- **`buildup`**: `land_use`, `pollutant`, `function`, `maximum_buildup`, `rate_constant`, `power`, `normalizer`
- **`washoff`**: `land_use`, `pollutant`, `function`, `coefficient`, `exponent`, `cleaning_efficiency`, `bmp_efficiency`
- **`treatment`**: `node`, `pollutant`, `expression`
- **`time_series`**: `id`, `count`, `datetime`, `values`, `filename`, `description`
- **`time_pattern`**: `id`, `count`, `type`, `multipliers`
- **`external_inflow`**: `node`, `constituent`, `time_series`, `type`, `units_factor`, `scale_factor`, `baseline`, `pattern`
- **`dry_weather_flow`**: `node`, `constituent`, `average_value`, `monthly_pattern`, `daily_pattern`, `hourly_pattern`, `weekend_pattern`
- **`rdii`**: `node`, `unit_hydrograph`, `sewer_area`
- **`unit_hydrograph`**: `id`, `count`, `rain_gage`, `month`, `short_term_r`, `short_term_t`, `short_term_k`, `medium_term_r`, `medium_term_t`, `medium_term_k`, `long_term_r`, `long_term_t`, `long_term_k`
- **`control_rule`**: `id`, `count`, `text`, `conditions`, `actions`, `priority`, `enabled`, `action_log`
- **`interface_file`**: `rainfall`, `runoff`, `hotstart`, `rdii`, `inflow`, `outflow`, `use_file`, `save_file`
- **`system_result`**: `air_temperature`, `rainfall`, `snow_depth`, `evaporation`, `infiltration`, `runoff`, `dry_weather_inflow`, `groundwater_inflow`, `rdii_inflow`, `direct_inflow`, `total_lateral_inflow`, `flooding`, `outfall_flow`, `storage_volume`, `pollutant_loading`
- **`summary`**: `model`, `counts`, `options`, `subcatchment_runoff`, `subcatchment_washoff`, `node_depth`, `node_inflow`, `node_flooding`, `node_surcharge`, `storage_volume`, `outfall_loading`, `link_flow`, `link_velocity`, `conduit_surcharge`, `pump_operation`, `lid_performance`, `runoff_continuity`, `flow_routing_continuity`, `quality_routing_continuity`, `validation_issues`

## Validation

```python
validation = m.validate()
print(validation.ok)
print(validation.to_frame())
```

The first validator checks duplicate IDs, missing required options, invalid unit values, missing nodes/links, conduit endpoints, and several common cross-section/reference errors.
