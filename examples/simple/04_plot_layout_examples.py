"""04 simple - Save a few network layout plots."""

from pathlib import Path

#import matplotlib
#matplotlib.use("Agg")

import matplotlib.pyplot as plt

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_04_working_copy.inp")
m.run()

fig, _ = m.plot_layout(show=False, save_path=output_dir / "simple_layout_basic.png")
plt.close(fig)

fig, _ = m.plot_layout(
    title="Network Layout",
    grid=True,
    axis=True,
    show=True,
    save_path=output_dir / "simple_layout_axes.png",
)
plt.close(fig)

fig, _ = m.plot_layout(
    nodes={"size": 40, "color": "black"},
    links={"width": 2.0, "color": "gray"},
    subcatchments={"color": "lightgreen", "edge_color": "green"},
    show=True,
    save_path=output_dir / "simple_layout_custom_styles.png",
)
plt.close(fig)

fig, _ = m.plot_layout(
    links={
        "color": {
            "by": "parameter",
            "category": "conduit",
            "variable": "roughness",
            "mode": "continuous",
            "cmap": "viridis",
        }
    },
    show=True,
    save_path=output_dir / "simple_layout_by_roughness.png",
)
plt.close(fig)

fig, _ = m.plot_layout(
    links={
        "color": {
            "by": "result",
            "category": "link",
            "variable": "flow",
            "aggregation": "max",
            "mode": "continuous",
        }
    },
    show=True,
    save_path=output_dir / "simple_layout_by_max_flow.png",
)
plt.close(fig)

risk_score = {"P001": 1, "P005": 2, "P009": 1, "P011": 3}
fig, _ = m.plot_layout(
    links={"color": {"by": "user", "data": risk_score, "mode": "discrete"}},
    show=True,
    save_path=output_dir / "simple_layout_by_user_risk.png",
)
plt.close(fig)
