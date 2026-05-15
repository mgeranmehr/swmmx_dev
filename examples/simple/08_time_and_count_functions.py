"""08 simple - Inspect model time vectors and object counts."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
print(m.time.vector().head())
print(m.time.count())
print(m.count.conduit())
print(m.count.node())
print(m.count.subcatchment())
print(m.count.model_dict())

m.save(output_dir / "simple_08_working_copy.inp")
m.run()
print(m.time.vector_run().head())
print(m.time.count_run())
print(m.count.model_df())
