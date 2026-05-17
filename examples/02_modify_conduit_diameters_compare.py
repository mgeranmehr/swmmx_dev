"""02 simple - Increase circular conduit diameters and compare flows."""

from pathlib import Path

import pandas as pd

from swmmx import swmm


examples_dir = Path(__file__).resolve().parent
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_02_working_copy.inp")
m.run()

baseline_flow = m.get.conduit.flow(format="df")
shapes = m.get.cross_section.shape(format="df").iloc[0]
diameters = m.get.cross_section.geometry_1(format="df").iloc[0]
circular_ids = [conduit_id for conduit_id in diameters.index if shapes[conduit_id] == "CIRCULAR"]

new_diameters = diameters.loc[circular_ids] * 1.10
m.set.cross_section.geometry_1(new_diameters, ids=circular_ids)
m.run()
modified_flow = m.get.conduit.flow(format="df")

comparison = pd.DataFrame(
    {
        "baseline_max_flow": baseline_flow.max(),
        "modified_max_flow": modified_flow.max(),
    }
)
comparison["difference"] = comparison["modified_max_flow"] - comparison["baseline_max_flow"]
comparison["percent_difference"] = 100.0 * comparison["difference"] / comparison["baseline_max_flow"]
print(comparison.head())

m.save(output_dir / "simple_example_larger_diameters.inp")

