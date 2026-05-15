"""02 - Increase circular conduit diameters, rerun, and compare flows."""

import pandas as pd

from swmmx import swmm

from _helpers import get_example_path, get_output_dir, print_header, save_working_copy


def main() -> None:
    """Compare baseline and larger-diameter conduit results."""

    print_header("02 - Modify conduit diameters and compare")
    model = swmm(get_example_path())
    save_working_copy(model, "02_working_copy.inp")

    model.run()
    baseline_flow = model.get.conduit.flow(format="df")

    # In SWMM, a circular conduit's diameter is XSECTION geometry_1.
    shapes = model.get.cross_section.shape(format="df").iloc[0]
    diameters = model.get.cross_section.geometry_1(format="df").iloc[0]
    circular_conduit_ids = [conduit_id for conduit_id in diameters.index if shapes[conduit_id] == "CIRCULAR"]
    if not circular_conduit_ids:
        print("No circular conduits were found, so there is nothing to resize.")
        return

    new_diameters = diameters.loc[circular_conduit_ids] * 1.10
    model.set.cross_section.geometry_1(new_diameters, ids=circular_conduit_ids)
    print("Updated circular diameters:")
    print(pd.DataFrame({"baseline": diameters.loc[circular_conduit_ids], "larger": new_diameters}))

    issues = model.validate()
    print(f"Validation after resize: {len(issues.errors)} errors, {len(issues.warnings)} warnings")

    model.run()
    modified_flow = model.get.conduit.flow(format="df")
    comparison = pd.DataFrame(
        {
            "baseline_max_flow": baseline_flow.max(),
            "modified_max_flow": modified_flow.max(),
        }
    )
    comparison["difference"] = comparison["modified_max_flow"] - comparison["baseline_max_flow"]
    comparison["percent_difference"] = (
        100.0 * comparison["difference"] / comparison["baseline_max_flow"].replace(0.0, pd.NA)
    )
    print("\nMaximum-flow comparison:")
    print(comparison.head())

    saved_path = model.save(get_output_dir() / "example_larger_diameters.inp")
    print(f"\nSaved modified model: {saved_path}")


if __name__ == "__main__":
    main()

