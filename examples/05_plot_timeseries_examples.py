"""05 simple - Plot result time series."""

from pathlib import Path

#import matplotlib
#matplotlib.use("Agg")

import matplotlib.pyplot as plt

from swmmx import swmm


examples_dir = Path(__file__).resolve().parent
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_05_working_copy.inp")
m.run()

fig, _ = m.plot_timeseries.conduit.flow(
    "P001",
    show=True,
    save_path=output_dir / "simple_timeseries_one_conduit.png",
)
plt.close(fig)

fig, _ = m.plot_timeseries.conduit.flow(
    ["P001", "P005"],
    title="Conduit Flow",
    y_axis_title="Flow",
    grid=True,
    show=True,
    save_path=output_dir / "simple_timeseries_two_conduits.png",
)
plt.close(fig)

fig, _ = m.plot_timeseries.node.depth(
    "P001",
    title="Node Depth",
    show=True,
    save_path=output_dir / "simple_timeseries_node_depth.png",
)
plt.close(fig)



