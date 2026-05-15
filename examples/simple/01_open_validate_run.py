"""01 simple - Open, validate, and run a model."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
issues = m.validate()
print(issues.to_frame().head())
print(f"errors={len(issues.errors)} warnings={len(issues.warnings)}")

m.save(output_dir / "simple_01_working_copy.inp")
run_info = m.run()
print(run_info)
print("Run complete")
