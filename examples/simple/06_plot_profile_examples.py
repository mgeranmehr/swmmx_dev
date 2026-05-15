"""06 simple - Plot longitudinal hydraulic profiles."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_06_working_copy.inp")
m.run()

fig, _ = m.plot_profile.nodes(
    "P011",
    "Outlet",
    show_ground=True,
    show_conduits=True,
    show_hgl=True,
    aggregation="max",
    title="Profile from P011 to Outlet",
    show=False,
    save_path=output_dir / "simple_profile_nodes.png",
)
plt.close(fig)

fig, _ = m.plot_profile.links(
    ["P011", "P005", "P001"],
    show_ground=True,
    show_conduits=True,
    show_hgl=True,
    time_step=-1,
    title="Selected Link Profile",
    show=False,
    save_path=output_dir / "simple_profile_links.png",
)
plt.close(fig)

fig, _ = m.plot_profile.longest(
    show_hgl=True,
    aggregation="max",
    title="Longest Path Profile",
    show=False,
    save_path=output_dir / "simple_profile_longest.png",
)
plt.close(fig)
