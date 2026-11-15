"""Build the merged 23/24 guide for SWMMX 0.0.44 (no external data needed)."""

import json
from pathlib import Path

LESSONS = [
    [
        "Installation and environment check",
        "Use Python 3.10+ and a Jupyter kernel with SWMMX installed. If dependencies are\nmissing, install them **in that same kernel**, then restart it. This command is\nshown for guidance and is not automatically executed:\n\n```python\n%pip install swmmx numpy pandas matplotlib networkx geopandas shapely pyogrio\n```\n\nFor a local release, replace `swmmx` with your wheel path. JupyterLab itself can\nbe installed using `pip install jupyterlab`. This complete guide needs the GIS\npackages; standalone landcover calculations do not. The simulation lesson uses\nthe bundled native engine. The first cell supports a checkout or installed package.",
        "from pathlib import Path\nimport importlib.util\nimport sys\nrepo = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p/'src/swmmx/landcover').is_dir()), None)\nif repo is not None:\n    sys.path.insert(0, str(repo/'src'))\nrequired = ['swmmx','numpy','pandas','matplotlib','networkx','geopandas','shapely','pyogrio']\nmissing = [name for name in required if importlib.util.find_spec(name) is None]\nif missing:\n    raise RuntimeError('Install in this notebook kernel: '+', '.join(missing))\n%matplotlib inline\nimport numpy as np\nimport pandas as pd\nimport geopandas as gpd\nimport matplotlib.pyplot as plt\nfrom shapely.geometry import box\nfrom IPython.display import display\nfrom swmmx import landcover, swmm, LandCover, SWMMXError, LandCoverValidationError, __version__\nOUTPUT = (repo/'examples/output' if repo else Path.cwd())/'landcover_044'\nOUTPUT.mkdir(parents=True,exist_ok=True)\npd.set_option('display.max_columns',14)\nprint('SWMMX:',__version__, 'Python:',sys.version.split()[0])\nprint('Outputs:',OUTPUT)\n\ndef explain_error(label, action):\n    try:\n        action()\n    except SWMMXError as exc:\n        print(f'{label}: {type(exc).__name__}: {exc}')\n    else:\n        raise AssertionError(f'{label}: expected a validation error')",
    ],
    [
        "Separate subcatchments, landcover and native LANDUSES",
        "| Concept | Question | Example |\n|---|---|---|\n| Subcatchment | Which land drains to this outlet? | S1 drains to J1 |\n| Landcover | What physical surfaces occupy this area? | Roof, road, green |\n| Native LANDUSES | Which water-quality categories apply? | Pollutant buildup categories |\n\nLandcover aggregates surface properties into SWMM's subcatchment/subarea model.\nIt does not create an independent runoff plane per class, delineate drainage\nboundaries or size pipes. Use **reviewed subcatchments → surface intersection →\nparameter preview → explicit application → simulation**.\n\nEstablish actual drainage connections first. One node need not have exactly one\nsubcatchment. The nearest node need not receive the runoff. Terrain, buried-pipe\nlevels, soil, rainfall and outfall conditions remain separate project inputs.",
        None,
    ],
    [
        "Quick start: define, cover, preview",
        "Start with these three operations. A standalone project needs no SWMM model.\nDeclare SI property units, define classes together, and assign complete fractions.\n`preview()` calculates values and diagnostics without changing anything. Once a\nmodel is attached, `apply(preview)` is the fourth step. The model lesson demonstrates it.\n\nDo not fill in advanced properties you do not need: choose\n`preview(parameters=['imperviousness'])` if you only want impervious percentage.",
        "simple = landcover(units='SI')\nsimple.define_classes({\n    'roof': {'impervious':1, 'n_imp':.012, 'dstore_imp':1.5},\n    'green': {'impervious':0, 'n_perv':.2, 'dstore_perv':5},\n})\nsimple.set_coverage({'S1': {'roof':.4, 'green':.6}}, area_m2=10000)\nreview = simple.preview()\ndisplay(review.values)\nprint('Can apply to SWMM now?', review.can_apply)  # False: no attached model yet.\nassert review.values.loc['S1','percent_impervious'] == 40\n# A standalone warning is expected; calculation itself succeeded.\nprint(review.issues[0].message)",
    ],
    [
        "Units you must keep consistent",
        "Declare `units='SI'` or `units='US'` when creating your library. Derivation uses\nthose declared units. An attached preview converts length/rate values into the\nmodel's native units and explains the conversion; application uses those reviewed\nvalues. Original class definitions are unchanged.\n\n| Quantity | Convention |\n|---|---|\n| Coverage / impervious / suitability fractions | 0..1 |\n| Native imperviousness and pct_zero | 0..100 percent |\n| Coverage/LID area | Always m² |\n| Native model area | SI hectares / US acres |\n| Class depression storage | SI mm / US inches |\n| Infiltration conductivity | SI mm/hr / US inches/hr |\n| Infiltration dry_time / decay / deficit | Model-specific time/dimensionless units; unchanged |\n\nLegacy `landcover()` retains `units='native'`, assuming values match the model.\nPrefer explicit units in new projects. Existing saved units cannot be overridden\nsilently when reopening. Area units on set_coverage are independent of class units.",
        None,
    ],
    [
        "Four equivalent coverage inputs",
        "`units` describes the composition values. Standalone area input needs an\nexplicit total area; the manager never assumes the mapped part is the whole\ncatchment. These four assignments must give the same fractions.",
        "units_demo = landcover()\nunits_demo.add_class('roof',impervious=1)\nunits_demo.add_class('green',impervious=0)\nfor sid, values, units in [\n ('fraction',{'roof':.4,'green':.6},'fraction'),\n ('percent',{'roof':40,'green':60},'percent'),\n ('m2',{'roof':4000,'green':6000},'m2'),\n ('ha',{'roof':.4,'green':.6},'ha')]:\n    units_demo.assign(sid,values,units=units,area_m2=10000)\ndisplay(units_demo.coverage_table())\nassert np.allclose(units_demo.coverage_table()['roof'],.4)\nexplain_error('Missing total area',lambda: units_demo.assign('unknown',{'roof':100},units='m2'))",
    ],
    [
        "Replacement and explicit normalization",
        "Use `overwrite=True` to replace an existing assignment. Incomplete totals\nare rejected unless normalization is explicitly requested. Normalization only\nrescales values; it does not identify missing land or justify ignoring it.\nIndividual fractions must still lie in 0..1 before normalization.",
        "explain_error('Duplicate',lambda: simple.assign('S1',{'roof':1}))\nexplain_error('Incomplete',lambda: units_demo.assign('incomplete',{'roof':.2,'green':.3}))\nunits_demo.assign('rescaled',{'roof':.2,'green':.3},normalize=True,area_m2=10000)\nunits_demo.normalize('rescaled')\nassert units_demo.coverage_fraction('rescaled','roof') == .4\nunits_demo.assign('rescaled',{'roof':.3,'green':.7},overwrite=True,area_m2=10000)\ndisplay(units_demo.coverage_table().loc[['rescaled']])",
    ],
    [
        "Class management and independent snapshots",
        "`classes` and `get_class()` return snapshots. Use `update_class()` to change\nproperties safely and `rename_class()` to change labels. Stable class IDs survive\nboth operations; coverage references and JSON links stay consistent. Removal\nstill refuses referenced classes. All edits can be reviewed through metadata history.",
        "manage = simple.copy()\nmanage.add_class('unused',impervious=.3,attributes={'cost_factor':1.2},description='Teaching metadata')\nprint(manage.list_classes(),manage.has_class('unused'))\nsnapshot = manage.get_class('unused')\nsnapshot.attributes['cost_factor'] = 9\nassert manage.classes['unused'].attributes['cost_factor'] == 1.2\nmanage.remove_class('unused')\nmanage.rename_class('roof','building_roof')\nassert manage.coverage_fraction('S1','building_roof') == .4\nexplain_error('Referenced class',lambda: manage.remove_class('building_roof'))\ndisplay(manage.classes_dataframe())\nclass_identity = manage.class_id('building_roof')\nmanage.update_class('building_roof', n_imp=.014)\nassert manage.class_id('building_roof') == class_identity\nassert manage.classes['building_roof'].n_imp == .014\nmanage.undo()\nassert manage.classes['building_roof'].n_imp == .012\nmanage.redo()\ndisplay(pd.DataFrame(manage.history()))",
    ],
    [
        "A reusable five-class SI library",
        "The helper creates independent managers for later lessons. `pedestrian` is\npartly impervious and needs both property sets. Infiltration metadata describes\nthe pervious portion. Suitability describes eligible area, not installed controls.\n`pct_zero` is a percentage of the class's impervious portion.\nAll values are illustrative; replace them with locally justified data.",
        "def green_ampt(suction, conductivity, deficit):\n    return {'model':'GREEN_AMPT','suction_head':suction,\n            'hydraulic_conductivity':conductivity,'initial_moisture_deficit':deficit}\n\ndef urban_library(model=None):\n    obj = landcover(model, units=\"SI\")\n    obj.add_class('roof',impervious=1,n_imp=.012,dstore_imp=1.5,pct_zero=70,\n        lids={'green_roof':.7,'rain_barrel':1},attributes={'source':'teaching example'})\n    obj.add_class('road',impervious=1,n_imp=.013,dstore_imp=2,pct_zero=20,\n        lids={'permeable_pavement':.25,'bioretention':.1})\n    obj.add_class('pedestrian',impervious=.8,n_imp=.015,n_perv=.15,dstore_imp=2,dstore_perv=4,\n        pct_zero=30,infiltration=green_ampt(90,8,.2),lids={'permeable_pavement':.4})\n    obj.add_class('green',impervious=0,n_perv=.2,dstore_perv=5,\n        infiltration=green_ampt(110,12,.25),lids={'bioretention':.4,'swale':.5})\n    obj.add_class('other',impervious=.3,n_imp=.015,n_perv=.18,dstore_imp=2,dstore_perv=5,\n        pct_zero=10,infiltration=green_ampt(80,6,.15))\n    return obj\n\nbaseline = urban_library()\ncomposition = {'roof':.30,'road':.25,'pedestrian':.10,'green':.25,'other':.10}\nbaseline.assign('S1',composition,area_m2=10000)\nbaseline.assign('S2',{'roof':.2,'road':.2,'pedestrian':.1,'green':.4,'other':.1},area_m2=10000)\nbaseline.assign('S3',{'roof':.1,'road':.2,'pedestrian':.2,'green':.4,'other':.1},area_m2=10000)\nbaseline.classes_dataframe()",
    ],
    [
        "Bulk tables, CSV and complete row diagnostics",
        "Use mappings, DataFrames or CSV paths. Wide coverage has subcatchment and\nclass columns, plus optional area_m2. Long coverage has subcatchment, class (or\nstable class_id), and exactly one of fraction/percent/area_m2/area_ha. Area-based\nlong rows may carry total_area_m2. Duplicate rows are errors, not silently summed.\n`validate_only=True` returns all detected row issues without changing data.\nOtherwise invalid batches raise LandCoverValidationError with `.report` and make\nno partial changes. CSV cells for lids/infiltration/attributes contain JSON.",
        "bulk = landcover(units='SI')\nbulk.define_classes(pd.DataFrame([\n    {'name':'roof','impervious':1}, {'name':'green','impervious':0}]))\nlong_cover = pd.DataFrame([\n    {'subcatchment':'A','class':'roof','percent':40,'total_area_m2':1000},\n    {'subcatchment':'A','class':'green','percent':60,'total_area_m2':1000}])\nlong_cover.to_csv(OUTPUT/'bulk_cover.csv',index=False)\nbulk.set_coverage(OUTPUT/'bulk_cover.csv')\nreport = bulk.define_classes([{'name':'bad1','impervious':2},{'name':'bad2','n_imp':0}],validate_only=True)\nassert len(report.issues)==2 and not bulk.has_class('bad1')\ndisplay(report.to_dataframe())\ndisplay(bulk.preview(['imperviousness']).values)",
    ],
    [
        "Coverage inspection and table export",
        "`coverage()` returns a structured snapshot; `coverage_table()` returns fractions.\n`to_dataframe()` combines area, coverage, hydrology and LID bounds, so it requires\nenough properties and area information for those calculations.",
        "display(baseline.coverage_table())\nprint('Roof area:',baseline.coverage_area('S1','roof'),'m²')\nprint('Fraction:',baseline.coverage_fraction('S1','roof'))\nprint('Dominant class:',baseline.dominant_class('S1'))\nprint(baseline.coverage('S1'))\nbaseline.coverage_table().to_csv(OUTPUT/'coverage_fractions.csv')\nbaseline.classes_dataframe().to_json(OUTPUT/'classes_table.json',orient='records',indent=2)\nbaseline.to_dataframe().round(4)",
    ],
    [
        "Hand-check the hydrological formulas",
        "For class fraction $f_i$ and impervious fraction $I_i$:\n\n$$\\%Imperv=100\\sum_i f_i I_i$$\n$$N_{imp}=\\frac{\\sum_i f_i I_i n_{imp,i}}{\\sum_i f_i I_i},\\quad\nN_{perv}=\\frac{\\sum_i f_i(1-I_i)n_{perv,i}}{\\sum_i f_i(1-I_i)}$$\n\nStorage uses the corresponding surface weights. These are effective-parameter\napproximations, not exact separate-surface simulations. S1 has imperviousness\n0.30 + 0.25 + 0.10×0.80 + 0.10×0.30 = 0.66.",
        "hydro = baseline.derive_hydrology()\nexpected = {\n 'percent_impervious':66,\n 'n_imperv':(.30*.012+.25*.013+.08*.015+.03*.015)/.66,\n 'n_perv':(.02*.15+.25*.20+.07*.18)/.34,\n 'dstore_imperv':(.30*1.5+.25*2+.08*2+.03*2)/.66,\n 'dstore_perv':(.02*4+.25*5+.07*5)/.34}\nfor key,value in expected.items():\n    assert np.isclose(hydro.loc['S1',key],value)\ndisplay(pd.DataFrame({'calculated':hydro.loc['S1'],'hand_checked':pd.Series(expected)}))",
    ],
    [
        "Missing properties versus absent surfaces",
        "Missing properties of a contributing surface raise errors. A zero-area surface\nreturns NaN for its effective parameters; application preserves its existing\nnative values. Do not substitute zero for missing roughness. If only imperviousness\nis needed, request only that calculation.",
        "partial = landcover()\npartial.add_class('roof',impervious=1)\npartial.assign('S',{'roof':1})\nexplain_error('Missing roughness',lambda: partial.derive_hydrology())\ndisplay(partial.derive_hydrology(roughness=False,depression_storage=False))\nonly_roof = baseline.copy()\nonly_roof.assign('S1',{'roof':1},overwrite=True,area_m2=10000)\nrow = only_roof.derive_hydrology().loc['S1']\nassert pd.isna(row.n_perv) and pd.isna(row.dstore_perv)\ndisplay(row.to_frame('fully_impervious_example'))",
    ],
    [
        "Optional zero-storage percentage",
        "`pct_zero=True` requests impervious-area-weighted class percentages. This is\nnot a percentage of the whole catchment. Every contributing impervious class\nmust supply the property.",
        "with_zero = baseline.derive_hydrology(pct_zero=True)\nassert np.isclose(with_zero.loc['S1','pct_zero'],(.30*70+.25*20+.08*30+.03*10)/.66)\nwith_zero.round(4)",
    ],
    [
        "Infiltration: pervious weighting and dominant classes",
        "SWMM uses one native infiltration parameter set for a subcatchment's pervious\npart. `area_weighted` uses pervious weights; `dominant` selects the largest\npervious contribution. Neither exactly reproduces arbitrary heterogeneous soils.\nThe calculation below excludes roofs and roads because they are fully impervious.",
        "weighted_inf = baseline.derive_infiltration(method='area_weighted')\ndominant_inf = baseline.derive_infiltration(method='dominant')\nassert np.isclose(weighted_inf.loc['S1','hydraulic_conductivity'],(.02*8+.25*12+.07*6)/.34)\nassert dominant_inf.loc['S1','hydraulic_conductivity'] == 12\ndisplay(weighted_inf)\ndisplay(dominant_inf)",
    ],
    [
        "Advanced infiltration: custom rules and method compatibility",
        "A callback receives parts containing class, weight, model and parameters, and\nreturns a complete parameter dictionary. This example selects the lowest-\nconductivity class. It demonstrates the callback contract, **not a universal\nconservative design rule**.\n\nSupported model tokens: HORTON, MODIFIED_HORTON, GREEN_AMPT,\nMODIFIED_GREEN_AMPT and CURVE_NUMBER. Built-in aggregation rejects mixed models.\nAn attached model must match the resulting method. Custom conversion rules need\nindependent scientific justification.",
        "def choose_lowest_conductivity(parts):\n    chosen = min(parts,key=lambda p:p['hydraulic_conductivity'])\n    return {key:chosen[key] for key in ['model','suction_head','hydraulic_conductivity','initial_moisture_deficit']}\ncustom_inf = baseline.derive_infiltration(method='custom',function=choose_lowest_conductivity)\nassert custom_inf.loc['S1','hydraulic_conductivity'] == 6\ndisplay(custom_inf)\nmixed = baseline.copy()\nmixed.add_class('cn_soil',impervious=0,infiltration={'model':'CURVE_NUMBER','curve_number':80,'conductivity':0,'dry_time':3})\nmixed.convert('S1','green','cn_soil',fraction=.1)\nexplain_error('Mixed methods',lambda: mixed.derive_infiltration())",
    ],
    [
        "Create a small SI SWMM model and attach the manager",
        "We build three one-hectare catchments, three junctions and an outfall using\nexplicit teaching elevations, sizes, slope, width, rainfall and infiltration.\nCoordinates are synthetic projected coordinates, not a surveyed city.\n\n`attach()` checks IDs and total areas. A model has one attached manager;\n`landcover(m)` returns that manager. This example avoids external sample files.",
        "CRS = 'EPSG:32639'\nsub_polygons = [box(500000+i*100,4000000,500100+i*100,4000100) for i in range(3)]\nsubcatchments = gpd.GeoDataFrame({'subcatchment':['S1','S2','S3']},geometry=sub_polygons,crs=CRS)\nm = swmm(new='SI',flow_unit='CMS')\nm.options['INFILTRATION'] = 'GREEN_AMPT'\nfor key in ['START_DATE','END_DATE','REPORT_START_DATE']:\n    m.options[key] = '01/01/2026'\nm.options['START_TIME'] = '00:00:00'\nm.options['REPORT_START_TIME'] = '00:00:00'\nm.options['END_TIME'] = '03:00:00'\nm.options['REPORT_STEP'] = '00:05:00'\nm.options['FLOW_ROUTING'] = 'DYNWAVE'\nm.add.time.time_series('Rain',data=[('2026-01-01 00:00',0),('2026-01-01 00:05',15),\n    ('2026-01-01 00:10',30),('2026-01-01 00:15',15),('2026-01-01 00:20',0)])\nm.add.hydrology.rain_gage('RG',format='INTENSITY',interval='00:05',source_type='TIMESERIES',time_series='Rain')\nfor i in range(3):\n    m.add.node.junction(f'J{i+1}',x=500050+i*100,y=4000000,invert_elevation=99-i,max_depth=3)\nm.add.node.outfall('OUT',x=500350,y=4000000,invert_elevation=96)\nfor i in range(3):\n    m.add.link.conduit(f'C{i+1}',from_node=f'J{i+1}',to_node=f'J{i+2}' if i<2 else 'OUT',\n                       length=100,diameter=.6,roughness=.013)\nfor i,polygon in enumerate(sub_polygons):\n    m.add.hydrology.subcatchment(f'S{i+1}',rain_gage='RG',outlet=f'J{i+1}',\n        x=polygon.centroid.x,y=polygon.centroid.y,area=1,width=100,slope=1,\n        polygon=list(polygon.exterior.coords),suction_head=110,hydraulic_conductivity=12,\n        initial_moisture_deficit=.25)\nattached = baseline.copy()\nattached.attach(m)\nassert landcover(m) is attached\nassert attached.coverage_area('S1','roof') == 3000\nassert m.validate().ok\npd.DataFrame(m.section('SUBCATCHMENTS'),columns=['id','gage','outlet','area_ha','impervious_pct','width_m','slope_pct','curb_m'])",
    ],
    [
        "Preview and selectively apply native hydrology",
        "Review before applying. A preview contains independent `.values` and\n`.changes` tables, structured `.issues`, `.assumptions` and `.can_apply`.\nIt remembers the project revision and complete native-model fingerprint.\nAny later edit makes it stale, even an edit that is subsequently undone.\nNative application is atomic and uses existing validated SWMM setters.\nThe legacy `apply_hydrology()` delegates to this same preview/adapter workflow.",
        "before_subareas = m.section('SUBAREAS')\nbefore_imp = m.get.subcatchment.impervious_percent(ids='S1')\np = attached.preview(parameters=['imperviousness'])\ndisplay(p.changes)\nassert p.can_apply and m.get.subcatchment.impervious_percent(ids='S1') == before_imp\nattached.apply(p)\nassert m.section('SUBAREAS') == before_subareas\nassert m.get.subcatchment.impervious_percent(ids='S1') == 66\nfull_review = attached.preview(['imperviousness','roughness','depression_storage','pct_zero','infiltration'])\ndisplay(full_review.changes.head(8))\nprint(full_review.assumptions)\nattached.apply(full_review)\nassert attached.status['model_updated']\nprint(attached.status)",
    ],
    [
        "Safe stale-preview handling and workflow state",
        "Inspect state rather than guessing what has been applied. Revisions increase\non successful metadata edits and undo/redo. History holds up to 20 in-memory\nmetadata transactions; application to SWMM is excluded. Native model edits are\nfingerprinted too. Preview handles are local to the originating manager/session.",
        "review = attached.preview(['imperviousness'])\nattached.update_class('roof',description='Reviewed teaching roof')\nexplain_error('Stale review',lambda: attached.apply(review))\nattached.undo()\nexplain_error('Undo does not revive old reviews',lambda: attached.apply(review))\nattached.apply(attached.preview(['imperviousness']))\nassert attached.status['model_updated']\ndisplay(pd.Series(attached.status))",
    ],
    [
        "Validation reports and summaries",
        "`lc.validate()` checks metadata/derivation and reports unassigned model\ncatchments. `m.validate()` performs structural model checks. Neither certifies\nengineering adequacy. `summary()` reports assigned area and area-weighted\nimperviousness. Record uncertain assumptions even when validation passes.",
        "display(attached.validate())\ndisplay(m.validate().to_frame())\nsummary = attached.summary()\ndisplay(pd.Series({k:v for k,v in summary.items() if k not in ['source','validation']}))\nassert attached.validate().empty",
    ],
    [
        "Explicit units at the SWMM boundary",
        "This separate small US model illustrates class-property conversion only;\nit is not a conversion of an existing SI network. Classes are declared in SI,\nwhile preview/application convert storage and infiltration lengths/rates to US.\nTime, fractions and Manning coefficients are unchanged. Derived standalone\nvalues and class definitions remain in the declared source units.",
        "us = swmm(new='US')\nus.options['INFILTRATION']='GREEN_AMPT'\nus.add.time.time_series('Dry',data=[('2026-01-01 00:00',0)])\nus.add.hydrology.rain_gage('R',format='INTENSITY',interval='00:05',source_type='TIMESERIES',time_series='Dry')\nus.add.node.outfall('O',x=0,y=0,invert_elevation=0)\nus.add.hydrology.subcatchment('A',rain_gage='R',outlet='O',x=0,y=10,area=1,width=100,slope=1,\n    suction_head=1,hydraulic_conductivity=1,initial_moisture_deficit=.2)\nunit_demo=landcover(us,units='SI')\nunit_demo.define_classes({'roof':{'impervious':1,'n_imp':.012,'dstore_imp':25.4}})\nunit_demo.set_coverage({'A':{'roof':1}})\nunit_review=unit_demo.preview()\nassert np.isclose(unit_review.values.loc['A','dstore_imperv'],1)\nunit_demo.apply(unit_review)\nassert np.isclose(us.get.subcatchment.depression_storage_impervious(ids='A'),1)\nassert unit_demo.classes['roof'].dstore_imp==25.4\nprint(unit_review.assumptions[0])",
    ],
    [
        "GIS foundations: subcatchments and surface polygons",
        "Use two layers with known CRS. The synthetic catchments are 100 × 100 m.\nEach surface polygon has a class matching the library. Repeated class names are\nexpected; GIS row indices must be unique. These stripes illustrate known fractions,\nnot a method for delineating actual urban drainage boundaries.",
        "surface_records = []\nfor i in range(3):\n    x = 500000+i*100\n    for name,left,right in [('roof',0,30),('road',30,55),('pedestrian',55,65),('green',65,90),('other',90,100)]:\n        surface_records.append({'class':name,'geometry':box(x+left,4000000,x+right,4000100)})\nsurfaces = gpd.GeoDataFrame(surface_records,crs=CRS)\nassert surfaces.geometry.is_valid.all()\nfig,ax = plt.subplots(figsize=(10,4))\nsurfaces.plot(column='class',legend=True,ax=ax,alpha=.75)\nsubcatchments.boundary.plot(ax=ax,color='black',linewidth=2)\nfor row in subcatchments.itertuples():\n    ax.text(row.geometry.centroid.x,row.geometry.centroid.y,row.subcatchment,ha='center')\nax.set_title('Synthetic landcover and subcatchments (metres)')\nax.ticklabel_format(style='plain',useOffset=False)\nplt.show()",
    ],
    [
        "Overlay GeoDataFrames and verify areas",
        "`overlay(landcover=..., subcatchments=...)` works without an attached model.\nIt requires complete coverage and rejects overlapping source polygons. Inspect\nboth aggregated fractions and detailed intersection areas. Missing areas are not\nautomatically assigned to 'other'; resolve them explicitly upstream.",
        "spatial = urban_library()\nspatial.overlay(landcover=surfaces,subcatchments=subcatchments)\nassert np.allclose(spatial.coverage_table().sum(axis=1),1)\nassert np.isclose(spatial.intersections_geodataframe().area_m2.sum(),30000)\nassert spatial.coverage_fraction('S1','roof') == .3\ndisplay(spatial.coverage_table())\ndisplay(spatial.intersections_geodataframe().head())\ndisplay(spatial.to_geodataframe(include_hydrology=True)[['subcatchment','area_m2','roof_fraction','percent_impervious']])",
    ],
    [
        "Names-only presets and coverage-first maps",
        "The urban starter creates familiar labels but invents no engineering values.\nYou can map composition before collecting hydrological parameters. Request only\nthe calculations you are ready to support. GIS still requires reviewed boundaries,\nknown CRS, no overlaps and complete coverage.",
        "starter = landcover(units='SI',preset='urban')\nassert starter.classes['roof'].impervious is None\nstarter.set_surfaces(surfaces)\nstarter.calculate_coverage(subcatchments=subcatchments)\ndisplay(starter.coverage_geodataframe()[['subcatchment','roof_fraction','green_fraction']])\nassert 'percent_impervious' not in starter.coverage_geodataframe()\nstarter.plot(class_name='roof',vmin=0,vmax=1,legend=True)\nplt.title('Coverage can be mapped before hydrology is complete'); plt.show()\nissues = starter.preview(['imperviousness']).issues\nassert any(i.code=='MISSING_PROPERTY' for i in issues)\nprint('Missing-property issues:',len(issues))",
    ],
    [
        "GIS files and model polygon workflows",
        "GeoPandas supports formats such as GeoPackage, Shapefile and GeoJSON. Here we\nwrite and read synthetic local files. `layer` selects the GeoPackage layer.\nWhen using attached model polygons instead of an explicit subcatchment layer,\nsupply `model_crs`: INP has no reliable standard CRS field. Existing coverage\nneeds explicit overwrite.",
        "surface_file = OUTPUT/'teaching_surfaces.gpkg'\nsurfaces.to_file(surface_file,layer='surfaces',driver='GPKG',mode='w')\nsubcatchments.to_file(OUTPUT/'teaching_subcatchments.geojson',driver='GeoJSON')\nfile_workflow = urban_library()\nfile_workflow.from_gis(surface_file,class_field='class',layer='surfaces')\nfile_workflow.overlay(subcatchments=subcatchments)\npd.testing.assert_frame_equal(spatial.coverage_table(),file_workflow.coverage_table())\nmodel_gis = attached.copy()\nmodel_gis.set_surfaces(surfaces,class_column='class')\nmodel_gis.calculate_coverage(model_crs=CRS,overwrite=True)\nassert np.allclose(model_gis.coverage_table().sum(axis=1),1)\ndisplay(pd.Series(file_workflow.source))",
    ],
    [
        "CRS protection and explicit reprojection",
        "Geographic degrees are not usable area units. Both inputs need a known CRS.\nGeographic or mismatched inputs require an explicit projected `area_crs`.\nChoose a projection suitable for your region; projected feet are converted to m².\n`set_crs` labels coordinates; `to_crs` transforms them. Never relabel longitude/\nlatitude as metres.",
        "geo_surfaces = surfaces.to_crs('EPSG:4326')\ngeo_subs = subcatchments.to_crs('EPSG:4326')\nexplain_error('Geographic area',lambda: urban_library().overlay(geo_surfaces,geo_subs))\nexplain_error('Different CRS',lambda: urban_library().overlay(geo_surfaces,subcatchments))\nreprojected = urban_library()\nreprojected.overlay(geo_surfaces,geo_subs,area_crs=CRS)\nassert np.isclose(reprojected.coverage_area('S1','roof'),3000,atol=.001)\nprint('Recovered roof area:',reprojected.coverage_area('S1','roof'),'m²')",
    ],
    [
        "GIS errors: overlaps, gaps, labels and geometry",
        "Resolve geometry errors explicitly. Do not hide them by rescaling fractions.\nOutside polygons contribute nothing; positive slivers are retained. Valid\nMultiPolygon geometry is supported. Repeated class labels are allowed, whereas\nduplicate source indices are rejected. The following examples must fail clearly.",
        "overlap = surfaces.copy()\noverlap.loc[0,'geometry'] = box(500000,4000000,500040,4000100)\nexplain_error('Overlap',lambda: urban_library().overlay(overlap,subcatchments))\ngap = surfaces.drop(index=0)\nexplain_error('Uncovered area',lambda: urban_library().overlay(gap,subcatchments))\nunknown = surfaces.copy()\nunknown.loc[0,'class'] = 'undefined'\nexplain_error('Unknown class',lambda: urban_library().from_geodataframe(unknown))\nempty = surfaces.copy()\nempty.loc[0,'geometry'] = None\nexplain_error('Missing geometry',lambda: urban_library().from_geodataframe(empty))\nduplicate = surfaces.copy()\nduplicate.index = [0]*len(duplicate)\nexplain_error('Duplicate index',lambda: urban_library().from_geodataframe(duplicate))",
    ],
    [
        "Area reconciliation, GIS output and maps",
        "Coverage GeoDataFrames and maps now work without complete hydrological\nproperties. Use `include_hydrology=True` / `include_lids=True` for optional joined\nresults. Attached fractions use polygon intersections; physical coverage/LID areas\nuse SWMM area. Reconcile both totals rather than assuming they agree.",
        "area_audit = subcatchments[['subcatchment']].copy()\narea_audit['polygon_area_m2'] = subcatchments.area\narea_audit['model_area_m2'] = [m.get.subcatchment.area(ids=s)*10000 for s in area_audit.subcatchment]\narea_audit['difference_m2'] = area_audit.model_area_m2-area_audit.polygon_area_m2\nassert np.allclose(area_audit.difference_m2,0)\ndisplay(area_audit)\nmodel_gis.to_geodataframe().to_file(OUTPUT/'landcover_results.gpkg',layer='subcatchments',driver='GPKG',mode='w')\nmodel_gis.intersections_geodataframe().to_file(OUTPUT/'landcover_intersections.geojson',driver='GeoJSON')\nfig,axes = plt.subplots(1,2,figsize=(12,4))\nmodel_gis.plot(class_name='roof',ax=axes[0],legend=True,vmin=0,vmax=1,edgecolor='white')\nmodel_gis.plot(kind='imperviousness',ax=axes[1],legend=True,vmin=0,vmax=100,edgecolor='white')\naxes[0].set_title('Roof fraction'); axes[1].set_title('Imperviousness (%)')\nplt.tight_layout(); plt.show()",
    ],
    [
        "Stale spatial products after conversion",
        "Importing surfaces or changing coverage invalidates cached intersections.\nChanges to attached model polygon rows are also detected. Aggregate conversion\ndoes not specify where new polygons should lie. Use scenario tables, or supply\nrevised GIS polygons before making a new scenario map.",
        "spatial_change = model_gis.copy()\nspatial_change.convert('S1','road','green',area=100)\nexplain_error('Stale intersections',lambda: spatial_change.intersections_geodataframe())\nassert len(model_gis.intersections_geodataframe()) == 15",
    ],
    [
        "Progress, cancellation and GIS rollback",
        "A progress callback receives stage/completed/total dictionaries; cancelled()\ncan cooperatively stop the operation. Checks run between stages and during overlap\nchecks. The GEOS intersection call itself is not interruptible, so cancellation\nmay wait for it to return. Callbacks should observe progress, not edit the project.\nNo partial coverage is saved after cancellation or callback failure.",
        "events=[]\njob=urban_library()\njob.set_surfaces(surfaces)\nbefore=job.to_project().to_json()\nexplain_error('Cancelled overlay',lambda: job.calculate_coverage(subcatchments=subcatchments,\n    progress=events.append,cancelled=lambda: len(events)>=3))\nassert before==job.to_project().to_json()\njob.calculate_coverage(subcatchments=subcatchments,progress=events.append)\ndisplay(pd.DataFrame(events).drop_duplicates())",
    ],
    [
        "LID candidates and numerical checks",
        "Candidate area for type $l$ is $A_s\\sum_i f_i u_{i,l}$. Roof suitability 0.7\nmeans 70% of roof area is eligible, not that a control was created or structural\nsuitability confirmed. Different technologies may compete for the same land.\nNever sum their bounds as if they were jointly available. Rain-barrel candidate\narea is associated screening area, not barrel count or storage volume.",
        "candidates = baseline.lid_candidates()\nfirst = baseline.lid_candidates('S1').set_index('lid_type')\nassert np.isclose(first.loc['green_roof','candidate_area_m2'],10000*.3*.7)\nassert np.isclose(first.loc['bioretention','candidate_area_m2'],10000*(.25*.1+.25*.4))\ndisplay(candidates.head(10))\ncandidates.pivot(index='subcatchment',columns='lid_type',values='candidate_area_m2').plot.bar(figsize=(10,4))\nplt.ylabel('Independent candidate upper bound (m²)')\nplt.legend(title='LID type',bbox_to_anchor=(1.02,1),loc='upper left')\nplt.tight_layout(); plt.show()",
    ],
    [
        "Advanced suitability and user-defined filters",
        "Rich metadata supports suitable_fraction, min_area in m², and priority.\nHere min_area applies to each **aggregate class contribution**, not individual\npolygons. Priority is descriptive; no optimiser acts on it automatically.\nA callback may reduce the candidate area but cannot increase it. The example\nhalves the bound as an explicit hypothetical ownership constraint.",
        "rich = landcover()\nrich.add_class('parking',impervious=1,lids={'bioretention':{'suitable_fraction':.2,'min_area':50,'priority':.8}})\nrich.assign('small',{'parking':1},area_m2=100)\nrich.assign('large',{'parking':1},area_m2=1000)\ndisplay(rich.lid_candidates())\nassert rich.lid_candidates('small').candidate_area_m2.iloc[0] == 0\nfiltered = baseline.lid_candidates(filter_function=lambda row:row['candidate_area_m2']*.5)\nassert np.allclose(filtered.candidate_area_m2,candidates.candidate_area_m2*.5)\nexplain_error('Filter increases bound',lambda: baseline.lid_candidates(filter_function=lambda row:row['candidate_area_m2']+1))",
    ],
    [
        "Independent scenarios: convert area or whole-catchment fraction",
        "`copy()` duplicates metadata and clones an attached model. `convert()` accepts\nexactly one of area (m2/ha) or fraction. Fraction means a share of the **whole\nsubcatchment**, not the source class. Conversion preserves total coverage and\nrejects overdraw. Native parameters change only on explicit application.",
        "future = attached.copy()\noriginal_native = m.get.subcatchment.impervious_percent(ids='S1')\nfuture.convert('S1',source='road',target='green',area=500,units='m2')\nassert attached.coverage_fraction('S1','road') == .25\nassert np.isclose(future.coverage_fraction('S1','road'),.20)\nassert future.model.get.subcatchment.impervious_percent(ids='S1') == original_native\nfuture.apply_hydrology(infiltration=True)\nassert np.isclose(future.model.get.subcatchment.impervious_percent(ids='S1'),61)\nassert m.get.subcatchment.impervious_percent(ids='S1') == 66\nexplain_error('Source overdraw',lambda: future.convert('S1','road','green',fraction=.9))\nfraction_scenario = attached.copy()\nfraction_scenario.convert('S1','road','green',fraction=.05)\npd.testing.assert_frame_equal(future.coverage_table(),fraction_scenario.coverage_table())",
    ],
    [
        "Compare scenarios and explore a conversion sweep",
        "`baseline.compare(future)` returns future minus baseline. Assigned IDs and\ntotal areas must match. New classes/LID types align to zero; absent-surface\nhydrology may remain NaN. The sweep below explores derived parameters without\nrepeatedly running SWMM.",
        "delta = attached.compare(future)\ndisplay(delta.loc[['S1'],['road_area_m2','green_area_m2','percent_impervious','n_imperv','n_perv']])\nassert np.isclose(delta.loc['S1','percent_impervious'],-5)\nrows = []\nfor area in [0,250,500,1000]:\n    scenario = attached.scenario('conversion sweep')\n    scenario.convert('S1','road','green',area=area)\n    rows.append({'road_to_green_m2':area,'impervious_percent':scenario.derive_hydrology().loc['S1','percent_impervious']})\nsweep = pd.DataFrame(rows)\nsweep.plot(x='road_to_green_m2',y='impervious_percent',marker='o',legend=False)\nplt.ylabel('S1 imperviousness (%)'); plt.show()\ndisplay(sweep)",
    ],
    [
        "Lightweight scenarios and explicit model cloning",
        "`scenario()` detaches independent metadata, freezing attached areas and\nresolving legacy native property units. It does not clone a native model by\ndefault. Use scenario(clone_model=True) when the alternative must run SWMM.\nLegacy copy() retains its old model-cloning default. Stable class IDs survive\ncopies while the new project receives a separate identity.",
        "light=attached.scenario('more green')\nassert light.model is None and light.project_id!=attached.project_id\nassert light.class_id('roof')==attached.class_id('roof')\nlight.convert('S1','road','green',area=500)\ndisplay(attached.compare(light).loc[['S1'],['road_area_m2','green_area_m2','percent_impervious']])\nassert attached.coverage_fraction('S1','road')==.25\nrunnable=attached.scenario('runnable alternative',clone_model=True)\nassert runnable.model is not m",
    ],
    [
        "Update a used class in one operation",
        "`update_class()` validates changed properties and preserves identity and\ncoverage. It invalidates previews but keeps valid GIS intersections: changing\nroughness does not redraw surface polygons. Undo/redo affect metadata only;\nthey do not roll back native SWMM application.",
        "revised = baseline.scenario('revised road')\nidentity = revised.class_id('road')\nrevised.update_class('road',impervious=.9,n_imp=.014,n_perv=.18,\n                     dstore_perv=5,infiltration=green_ampt(80,6,.15))\nassert revised.class_id('road') == identity\nassert revised.coverage_fraction('S1','road') == .25\ndisplay(revised.preview().values)\nrevised.undo(); assert revised.classes['road'].impervious == 1\nrevised.redo(); assert revised.classes['road'].impervious == .9",
    ],
    [
        "Optimisation bounds without an optimiser",
        "Convert candidate areas into decision-variable bounds. Shared-area, budget,\nengineering feasibility, hydraulic performance and actual LID configuration must\nbe added by your optimisation formulation. This table does not allocate native\nLID_USAGE records or enforce competition between technologies.",
        "bounds = attached.lid_candidates().rename(columns={'candidate_area_m2':'upper_bound_m2'})\nbounds['lower_bound_m2'] = 0.0\nbounds = bounds[['subcatchment','lid_type','lower_bound_m2','upper_bound_m2']]\nbounds.to_csv(OUTPUT/'lid_decision_bounds.csv',index=False)\ndisplay(bounds.head())\nfor row in bounds.head(3).itertuples():\n    print(f'0 <= area[{row.subcatchment}, {row.lid_type}] <= {row.upper_bound_m2:.1f} m²')",
    ],
    [
        "Optional native water-quality conversion",
        "Creating landcover classes does not automatically create LANDUSES. Explicit\nconversion creates categories and percentages. Existing configuration is protected\nby default. `overwrite=True` replaces coverage for assigned subcatchments while\nretaining existing sweeping definitions and BUILDUP/WASHOFF. New classes receive\nzero sweeping settings; pollutant parameters are not invented.",
        "quality = attached.copy()\nassert quality.model.section('LANDUSES') == []\nquality.apply_swmm_landuses()\ndisplay(pd.DataFrame(quality.model.section('LANDUSES'),columns=['name','sweep_interval','availability','last_swept']))\ndisplay(pd.DataFrame(quality.model.section('COVERAGES'),columns=['subcatchment','land_use','percent']).head())\nexplain_error('Protect existing quality',lambda: quality.apply_swmm_landuses())\nquality.apply_swmm_landuses(overwrite=True)\nassert m.section('LANDUSES') == []",
    ],
    [
        "Standalone JSON persistence",
        "JSON sidecars preserve definitions, coverage, suitability, custom attributes\nand provenance. Geometry is not duplicated. CSV/DataFrame exports are useful\nanalysis products; `save()` and `LandCover.load()` are the supported metadata\nround-trip API.",
        "standalone_path = baseline.save(OUTPUT/'standalone.swmmx.json')\nrestored = LandCover.load(standalone_path)\npd.testing.assert_frame_equal(baseline.coverage_table(),restored.coverage_table())\nassert restored.classes['roof'].attributes == baseline.classes['roof'].attributes\nassert restored.classes['roof'].lids == baseline.classes['roof'].lids\nprint('Recovered:',standalone_path.name)",
    ],
    [
        "Save and reopen a model-sidecar pair",
        "An attached model's `save('model.inp')` also writes `model.swmmx.json`. Keep\nboth files. `landcover(reopened)` loads metadata lazily; call it **before save-as**\nto carry reopened metadata to another filename. Plain SWMM use does not activate\nsidecars. Missing sidecars yield an empty manager; corrupt sidecars raise errors.\nThe INP/JSON pair is not a filesystem transaction. Reimport/overlay for spatial\noutputs after loading because cached geometry is not persisted.",
        "saved_model = quality.model.save(OUTPUT/'city_with_landcover.inp')\nreopened = swmm(saved_model)\nrecovered = landcover(reopened)\npd.testing.assert_frame_equal(recovered.coverage_table(),quality.coverage_table())\nassert reopened.section('COVERAGES') == quality.model.section('COVERAGES')\nassert reopened.get.subcatchment.impervious_percent(ids='S1') == 66\nassert saved_model.with_suffix('.swmmx.json').exists()\nreopened.save(OUTPUT/'city_copy.inp')\nprint('Verified pair:',saved_model.name,saved_model.with_suffix('.swmmx.json').name)\nspatial.save(OUTPUT/'spatial_metadata.json')\nspatial_reloaded = LandCover.load(OUTPUT/'spatial_metadata.json')\nexplain_error('Geometry not serialized',lambda: spatial_reloaded.intersections_geodataframe())\nspatial_reloaded.from_geodataframe(surfaces)\nspatial_reloaded.overlay(subcatchments=subcatchments,overwrite=True)\nassert len(spatial_reloaded.intersections_geodataframe()) == 15",
    ],
    [
        "Frontend-ready JSON contracts and stable identity",
        "Project snapshots are independent of SWMM. Coverage references stable class\nIDs rather than labels in version-2 JSON. Version-1 sidecars migrate on loading.\nHistory, registered previews and GIS geometry are session-only; source provenance\nsurvives. Unknown versions fail clearly.\n\nA server can return preview.to_dict() for rendering values, changes, issues and\nassumptions, then accept a preview_id for explicit apply on the same manager.\nThe backend verifies that ID and rejects changed or stale payloads. Keep one\nserialized writer per project; this package does not provide an HTTP server,\nauthentication, a database or multi-process locking.",
        "import json\nidentity=attached.class_id('roof')\nsnapshot=attached.to_project()\njson_data=snapshot.to_json()\nrestored_project=LandCover.from_project(json_data)\nassert restored_project.class_id('roof')==identity\nrestored_project.rename_class('roof','building roof')\nassert restored_project.class_name(identity)=='building roof'\nreview=attached.preview(['imperviousness'])\nresponse=review.to_dict()\njson.dumps(response,allow_nan=False)\nrequest={'preview_id':response['preview_id']}\nattached.apply(request['preview_id'])\ndisplay(pd.DataFrame(response['changes']))\n(OUTPUT/'frontend_project.json').write_text(json_data,encoding='utf-8')\nprint('Project schema:',snapshot.to_dict()['version'])",
    ],
    [
        "Run SWMM and understand stale-result state",
        "This small native simulation is an integration demonstration, not design\nvalidation. It proves that metadata conversion/derivation do not invalidate\nresults, but applying changed hydrology does. Run again before interpreting\nresults from changed native inputs. All run files stay in the tutorial folder.",
        "simulation = attached.copy()\nsimulation.model.save(OUTPUT/'baseline_simulation.inp')\nrun = simulation.model.run()\nassert run.success and simulation.model.has_run\nassert not simulation.model.results_stale\nsimulation.convert('S1','road','green',area=100)\nassert not simulation.model.results_stale\nsimulation.derive_hydrology()\nassert not simulation.model.results_stale\nsimulation.apply_hydrology(infiltration=True)\nassert simulation.model.results_stale\nsimulation.model.save(OUTPUT/'changed_simulation.inp')\nrerun = simulation.model.run()\nassert rerun.success and not simulation.model.results_stale\nprint('Both runs succeeded. Reported periods:',run.periods,rerun.periods)",
    ],
    [
        "Troubleshooting reference and validation examples",
        "| Symptom | Action |\n|---|---|\n| Coverage sum not one | Review missing/duplicated cover; normalize only deliberately |\n| Duplicate class/assignment | Restart the tutorial or use explicit overwrite |\n| Missing n_imp or storage | Use update_class or omit that calculation |\n| Unknown subcatchment | Reconcile model and GIS IDs |\n| Stored/model area differs | Review and explicitly reassign coverage |\n| No current intersections | Reimport/overlay when appropriate |\n| Geographic/mismatched CRS | Choose explicit appropriate projected area_crs |\n| Incompatible infiltration | Reconcile models; justify custom conversions |\n| Stale preview | Recalculate and review after an edit; do not reuse the old handle |\n| Native quality exists | Inspect before explicit overwrite |\n| Implausible derived values | Recheck units and source assumptions |\n\nExpected failures below must be caught as SWMMX errors.",
        "explain_error('Impervious fraction',lambda: landcover().add_class('bad',impervious=80))\nexplain_error('Suitability bounds',lambda: landcover().add_class('bad',lids={'swale':1.2}))\nexplain_error('Positive roughness',lambda: landcover().add_class('bad',n_imp=0))\nexplain_error('Finite values',lambda: landcover().add_class('bad',dstore_imp=float('nan')))\nexplain_error('Percent total',lambda: baseline.assign('bad',{'roof':80,'green':40},units='percent'))\nexplain_error('Unknown model ID',lambda: attached.assign('NOT_A_CATCHMENT',{'roof':1}))",
    ],
    [
        "Apply the workflow to your real urban project",
        "1. Define existing-network, new-design or retrofit objectives and local criteria.\n2. Check node/pipe IDs, connectivity, dimensions and surveyed/proposed levels.\n3. Obtain reviewed subcatchments and actual receiving outlets. Do not automatically\n   make one catchment per manhole or assign runoff to the nearest node.\n4. Review terrain, inlets, street drainage and roof connections. A DEM describes\n   ground, not buried-pipe invert elevations.\n5. Verify CRS and polygon/native catchment area agreement.\n6. Map surface labels to a library with documented local parameter sources.\n7. Overlay, inspect fractions and preview hydrology before applying it.\n8. Supply rainfall, soil assumptions, slope, effective width and outfall conditions\n   separately. The library does not derive these from class names.\n9. Check observations, simulation behaviour and sensitivity before design decisions.\n10. Keep model, sidecar, source GIS, assumptions and outputs together.\n\nCurrent landcover does not automatically delineate terrain catchments, size pipes,\ninfer roof drainage, map street flood depths or allocate LIDs. The first real\napplication should be a small area with well-understood drainage connections.\nThe following blank audit table is a practical starting template.",
        "audit_template = pd.DataFrame([{'dataset':name,'file_or_source':'','CRS_or_vertical_datum':'',\n    'units':'','known_or_assumed':'','review_notes':''} for name in\n    ['nodes','pipes','inlets_and_connections','subcatchments','landcover','terrain','rainfall','soil','outfall','observations']])\naudit_template.to_csv(OUTPUT/'real_project_data_audit.csv',index=False)\ndisplay(audit_template)",
    ],
    [
        "Practice exercises and executable solutions",
        "Try these before reading the code:\n\n1. A 20,000 m² catchment is 35% roof. Find roof area.\n2. Convert 200 m² of road to green in baseline S1. Find new imperviousness.\n3. With green-roof suitability 0.7, find the candidate area for exercise 1.\n4. Save and reload the scenario; verify the coverage.\n\nAssertions below provide checkable solutions.",
        "exercise = landcover()\nexercise.add_class('roof',impervious=1,n_imp=.012,dstore_imp=1.5,lids={'green_roof':.7})\nexercise.add_class('green',impervious=0,n_perv=.2,dstore_perv=5)\nexercise.assign('practice',{'roof':.35,'green':.65},area_m2=20000)\nassert exercise.coverage_area('practice','roof') == 7000\nassert np.isclose(exercise.lid_candidates().candidate_area_m2.iloc[0],4900)\nsolution = baseline.copy()\nsolution.convert('S1','road','green',area=200)\nassert np.isclose(solution.derive_hydrology().loc['S1','percent_impervious'],64)\nsolution.save(OUTPUT/'exercise_solution.json')\npd.testing.assert_frame_equal(solution.coverage_table(),LandCover.load(OUTPUT/'exercise_solution.json').coverage_table())\nprint('Solutions: 7000 m² roof, 64% imperviousness, 4900 m² green-roof bound; round-trip verified.')",
    ],
    [
        "API reference and discovering help",
        "The live API table includes both the new simple workflow and compatible\nlow-level methods. `apply`, `apply_hydrology` and `apply_swmm_landuses` write native\ninputs. Class/coverage/GIS edits change metadata; save writes files. Properties\n`status`, `revision`, `units` and `classes` support client UI state.\nUse help(LandCover.preview) or help(LandCover.set_coverage) for full signatures.",
        "import inspect\nmethods = ['define_classes','set_coverage','update_class','preview','apply','set_surfaces','calculate_coverage',\n 'scenario','history','undo','redo','to_project','from_project','class_id','class_name','attach','add_class','remove_class','rename_class','get_class','has_class','list_classes',\n 'assign','normalize','coverage','coverage_fraction','coverage_area','dominant_class','classes_dataframe',\n 'coverage_table','to_dataframe','derive_hydrology','derive_infiltration','apply_hydrology',\n 'from_geodataframe','from_gis','overlay','intersections_geodataframe','to_geodataframe','coverage_geodataframe',\n 'plot','lid_candidates','copy','convert','compare','apply_swmm_landuses','validate','summary','save','load']\nreference = pd.DataFrame([{'method':name,'signature':str(inspect.signature(getattr(LandCover,name))),\n 'purpose':inspect.getdoc(getattr(LandCover,name)).splitlines()[0],\n 'writes_native_inputs':name in ['apply','apply_hydrology','apply_swmm_landuses']} for name in methods])\nreference.to_csv(OUTPUT/'landcover_api_reference.csv',index=False)\nwith pd.option_context('display.max_rows',None,'display.max_colwidth',100):\n    display(reference[['method','purpose','writes_native_inputs']])",
    ],
    [
        "Final summary, generated files and further reading",
        "The summary reports cover percentages, effective hydrology and the largest\nsingle-type LID bound—not a sum of competing bounds. Generated INP/JSON pairs,\nGIS layers, CSV tables and exercise solutions remain in the output folder.\n\n- [SWMMX API/modelling guide](../docs/landcover.md) (repository link).\n- [Frontend/backend contract](../docs/landcover_backend.md).\n- [EPA SWMM documentation](https://www.epa.gov/water-research/storm-water-management-model-swmm).\n- [EPA SWMM 5.2 manual](https://www.epa.gov/system/files/documents/2022-04/swmm-users-manual-version-5.2.pdf).\n\nEngineering use requires locally justified parameters and project-specific\nvalidation; these examples teach API behaviour.",
        "final = baseline.coverage_table().mul(100).add_suffix('_percent')\nfinal.insert(0,'area_m2',baseline.to_dataframe()['area_m2'])\nfinal = final.join(baseline.derive_hydrology())\nfinal['largest_single_lid_bound_m2'] = baseline.lid_candidates().groupby('subcatchment').candidate_area_m2.max()\nfinal.to_csv(OUTPUT/'final_summary.csv')\ndisplay(final.round(4))\nprint('Guide completed successfully.')\nprint('Output directory:',OUTPUT)\nprint('Generated files:',len(list(OUTPUT.iterdir())))",
    ],
]


def build():
    cells = []

    def md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": text})

    def code(text):
        cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "source": text,
                "execution_count": None,
                "outputs": [],
            }
        )

    md(
        "# Landcover made practical: quick start to advanced workflows\n\n**SWMMX 0.0.44 | merged notebooks 23 and 24**\n\nThe everyday workflow is **define classes → set coverage → preview → apply**. Start with the quick-start lesson, then use the linked topics when needed. Standalone previews need no model; model application is demonstrated after building a small SI network.\n\nUse **Restart Kernel and Run All**. This notebook creates local synthetic inputs, checks numerical results, demonstrates expected errors, and runs two teaching simulations. No online data are required. All engineering values and rain are illustrative, not design recommendations. Outputs are written under landcover_044. Existing add_class/assign/derive/apply_hydrology examples remain as compatible advanced APIs; new work should prefer bulk input and reviewed previews."
    )
    md(
        "## Contents\n\n"
        + "\n".join(f"{i}. [{row[0]}](#lesson-{i})" for i, row in enumerate(LESSONS, 1))
    )
    for i, (title, text, example) in enumerate(LESSONS, 1):
        md(f'<a id="lesson-{i}"></a>\n\n## {i}. {title}\n\n{text}')
        if example:
            code(example)
    for i, cell in enumerate(cells):
        cell["id"] = f"landcover-044-{i:03}"
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "cells": cells,
    }
    path = Path(__file__).resolve().parent / "23_landcover.ipynb"
    path.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{len(LESSONS)} lessons; {len(cells)} cells; {path.name}")


if __name__ == "__main__":
    build()
