"""01 - Open, validate, and run a SWMM model."""

from swmmx import swmm

from _helpers import get_example_path, print_header, save_working_copy


def main() -> None:
    """Open the example model, validate it, run it, and print a short summary."""

    print_header("01 - Open, validate, and run")
    model = swmm(get_example_path())

    # Save a working copy before running so generated .rpt/.out files stay in output/.
    save_working_copy(model, "01_working_copy.inp")

    issues = model.validate()
    issues_frame = issues.to_frame()
    print("Validation issues (first rows):")
    print(issues_frame.head() if not issues_frame.empty else "No validation issues.")
    print(f"Warnings: {len(issues.warnings)} | Errors: {len(issues.errors)}")

    run_info = model.run()
    print("\nRun summary:")
    print(run_info)
    print(f"Results available: {model.has_run}")
    print(f"Reported periods: {model.time.count_run()}")
    print("Run complete")


if __name__ == "__main__":
    main()

