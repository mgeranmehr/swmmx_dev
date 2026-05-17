"""08 - Work with model time vectors and object counts."""

import pandas as pd

from swmmx import swmm

from _helpers import get_example_path, get_output_dir, print_header, save_working_copy


def main() -> None:
    """Show pre-run time helpers, count helpers, and post-run time helpers."""

    print_header("08 - Time and count functions")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    save_working_copy(model, "08_time_count_working_copy.inp")

    # Time helpers live under m.time and return pandas DataFrames.
    expected_time_df = model.time.vector()
    expected_time_np = expected_time_df.index.to_numpy()
    print(f"Expected pre-run report periods: {model.time.count()}")
    print(f"First expected timestamp (NumPy view): {expected_time_np[0]}")
    print(expected_time_df.head(3))

    print("\nSelected counts:")
    print(f"conduits={model.count.conduit()} nodes={model.count.node()} subcatchments={model.count.subcatchment()}")
    print(f"total detailed elements={model.count.model()}")
    print(model.count.model_df().head())

    model.run()
    run_time_df = model.time.vector_run()
    run_time_np = run_time_df.index.to_numpy()
    print(f"\nActual run periods: {model.time.count_run()}")
    print(f"Last actual timestamp (NumPy view): {run_time_np[-1]}")

    summary = pd.DataFrame(
        {
            "expected_count": [model.time.count()],
            "run_count": [model.time.count_run()],
            "first_expected": [expected_time_df.index[0]],
            "last_run": [run_time_df.index[-1]],
        }
    )
    summary.to_csv(output_dir / "time_count_summary.csv", index=False)
    print(f"Saved compact summary to: {output_dir / 'time_count_summary.csv'}")


if __name__ == "__main__":
    main()
