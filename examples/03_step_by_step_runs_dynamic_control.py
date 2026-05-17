"""03 simple - Inspect the first few records from a step-by-step run."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parent
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_03_working_copy.inp")

# In swmmx, ``runs()`` exposes timing records. Live ``step.get`` /
# ``step.set`` runtime control is reserved for a future release.
steps = m.runs()
for step in steps:
    print(step.index, step.time, step.elapsed_days)
    if step.index >= 5:
        break
steps.close()

# Future safe runtime-control pattern:
# depth = step.get.node.depth("J1")
# step.set.pump.status("P1", "ON")

