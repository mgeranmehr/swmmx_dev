"""09 simple - Read and update model parameters."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")

print(m.get.conduit.length())
print(m.get.conduit.length("P001"))
print(m.get.conduit.length(["P001", "P005"]))
print(m.get.conduit.length(format="df"))

m.set.conduit.roughness(0.013)
m.set.conduit.roughness(0.014, ids="P001")
m.set.conduit.roughness([0.015, 0.016], ids=["P001", "P005"])
m.set.option_date_time.report_step("00:00:30")

print(m.get.conduit.roughness(format="df"))
print(m.get.option_date_time.report_step())

# Result and derived parameters are read-only:
# m.set.conduit.flow(1.0)

m.save(output_dir / "simple_get_set_modified_model.inp")
