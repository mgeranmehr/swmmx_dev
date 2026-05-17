"""09 - Explore common get/set patterns."""

import numpy as np

from swmmx import ReadOnlyParameterError, swmm

from _helpers import first_id, first_n_ids, get_example_path, get_output_dir, print_header


def main() -> None:
    """Read arrays/frames, update roughness values, and save a modified copy."""

    print_header("09 - Get and set examples")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    conduit_ids = model.get.conduit.id(format="df").columns.tolist()
    if not conduit_ids:
        print("No conduits are available in this model.")
        return

    first_conduit = first_id(conduit_ids)
    selected_conduits = first_n_ids(conduit_ids, 2)

    lengths_np = model.get.conduit.length(format="np")
    lengths_df = model.get.conduit.length(format="df")
    lengths_list = lengths_np.tolist()
    lengths_dict = lengths_df.iloc[0].to_dict()
    print("All conduit lengths (NumPy):", lengths_np)
    print(f"One conduit length ({first_conduit}):", model.get.conduit.length(first_conduit))
    print("Two conduit lengths:", model.get.conduit.length(selected_conduits))
    print("List view:", lengths_list)
    print("Dictionary view:", lengths_dict)

    model.set.conduit.roughness(0.013)
    model.set.conduit.roughness(0.014, ids=first_conduit)
    if len(selected_conduits) == 2:
        model.set.conduit.roughness(np.array([0.015, 0.016]), ids=selected_conduits)

    # Setters accept ordered vectors, not dictionaries directly.  Convert
    # a dictionary to an ID-aligned list when that is the most natural input.
    roughness_by_id = {conduit_ids[0]: 0.017}
    ordered_values = [roughness_by_id[conduit_id] for conduit_id in roughness_by_id]
    model.set.conduit.roughness(ordered_values, ids=list(roughness_by_id))
    print("Updated roughness values:", model.get.conduit.roughness(format="df"))

    model.set.option_date_time.routing_step("00:00:30")
    print("Routing step:", model.get.option_date_time.routing_step())

    try:
        model.set.conduit.flow(1.0)
    except ReadOnlyParameterError as exc:
        print(f"Expected read-only error: {exc}")

    saved_path = model.save(output_dir / "get_set_modified_model.inp")
    print(f"Saved modified copy: {saved_path}")


if __name__ == "__main__":
    main()
