"""07 - Export model data to GIS, CSV, and Excel formats."""

from swmmx import OptionalDependencyError, swmm

from _helpers import get_example_path, get_output_dir, print_header, save_working_copy


def main() -> None:
    """Export full and selected model tables while handling optional packages."""

    print_header("07 - Export examples")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    save_working_copy(model, "07_export_working_copy.inp")
    model.run()

    try:
        gis_outputs = model.export.gis(path=output_dir / "gis", overwrite=True)
        print(f"GIS layers: {sorted(gis_outputs)}")
    except OptionalDependencyError as exc:
        print(f"GIS export skipped: {exc}")

    csv_outputs = model.export.csv(path=output_dir / "csv", overwrite=True)
    print(f"CSV tables exported: {len(csv_outputs)}")

    try:
        excel_path = model.export.excel(
            path=output_dir,
            file_name="example_export.xlsx",
            overwrite=True,
        )
        print(f"Excel workbook: {excel_path}")
    except OptionalDependencyError as exc:
        print(f"Excel export skipped: {exc}")

    selected_outputs = model.export.csv(
        path=output_dir / "csv_nodes_links",
        elements=["nodes", "links"],
        overwrite=True,
    )
    print(f"Selected CSV exports: {sorted(selected_outputs)}")

    last_step_outputs = model.export.csv(
        path=output_dir / "csv_last_step",
        time_step=-1,
        overwrite=True,
    )
    print(f"Last-step CSV tables exported: {len(last_step_outputs)}")


if __name__ == "__main__":
    main()

