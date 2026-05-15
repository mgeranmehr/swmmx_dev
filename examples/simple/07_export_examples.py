"""07 simple - Export model tables."""

from pathlib import Path

from swmmx import swmm


examples_dir = Path(__file__).resolve().parents[1]
output_dir = examples_dir / "output"
output_dir.mkdir(parents=True, exist_ok=True)

m = swmm(examples_dir / "example.inp")
m.save(output_dir / "simple_07_working_copy.inp")
m.run()

csv_outputs = m.export.csv(path=output_dir / "simple_csv", overwrite=True)
selected_outputs = m.export.csv(
    path=output_dir / "simple_csv_nodes_links",
    elements=["nodes", "links"],
    overwrite=True,
)
print(f"CSV tables exported: {len(csv_outputs)}")
print(f"Selected tables: {sorted(selected_outputs)}")

# Uncomment these when the optional dependencies are installed:
# m.export.gis(path=output_dir / "simple_gis", overwrite=True)
# m.export.excel(path=output_dir, file_name="simple_export.xlsx", overwrite=True)
