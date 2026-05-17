"""10 simple - Build a small SI model from scratch."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parent
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(new="SI")
m.set.option_general.flow_units("CMS")
m.set.option_date_time.start_date("01/01/2026")
m.set.option_date_time.start_time("00:00:00")
m.set.option_date_time.end_date("01/01/2026")
m.set.option_date_time.end_time("01:00:00")
m.set.option_date_time.report_step("00:05:00")

m.add.node.junction("J1", invert_elevation=10.0, max_depth=3.0, x=0.0, y=0.0)
m.add.node.outfall("OUT1", invert_elevation=9.0, type="FREE", x=100.0, y=0.0)
m.add.link.conduit(
    "C1",
    from_node="J1",
    to_node="OUT1",
    length=100.0,
    roughness=0.013,
    shape="CIRCULAR",
    diameter=1.0,
)
m.add.time.time_series("Rain1", data=[("2026-01-01 00:00", 0.0), ("2026-01-01 00:05", 5.0)])
m.add.hydrology.rain_gage(
    "RG1",
    format="INTENSITY",
    interval="00:05",
    source_type="TIMESERIES",
    time_series="Rain1",
    x=0.0,
    y=100.0,
)
m.add.hydrology.subcatchment(
    "S1",
    rain_gage="RG1",
    outlet="J1",
    x=0.0,
    y=0.0,
    area=1.0,
    width=50.0,
    slope=1.0,
    impervious_percent=25.0,
    polygon=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)],
)

print(m.validate().to_frame())
m.save(output_dir / "simple_created_model.inp")
m.remove.link.conduit("C1")
m.save(output_dir / "simple_created_model_without_conduit.inp")

