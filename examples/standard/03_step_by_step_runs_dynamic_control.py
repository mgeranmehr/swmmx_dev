"""03 - Inspect a step-by-step run and explain live-control limits."""

from swmmx import swmm

from _helpers import get_example_path, print_header, save_working_copy


def main() -> None:
    """Iterate simulation steps and explain safe runtime-control intent."""

    print_header("03 - Step-by-step runs and dynamic control")
    model = swmm(get_example_path())
    save_working_copy(model, "03_stepwise_working_copy.inp")

    pump_count = model.count.pump()
    orifice_count = model.count.orifice()
    if pump_count == 0 and orifice_count == 0:
        print("This example model has no pumps or orifices to control at runtime.")

    print(
        "m.runs() currently yields SimulationStep timing records "
        "(index, time, elapsed_days). Live step.get/step.set state control is "
        "reserved for a future release, so this example stays honest and only inspects timing."
    )
    print("Do not change structural inputs such as diameters or invert elevations during a live run.")

    first_five_steps = []
    for step in model.runs():
        if len(first_five_steps) < 5:
            first_five_steps.append(step)

    print("\nFirst five simulation steps:")
    for step in first_five_steps:
        print(f"step={step.index:>2} time={step.time} elapsed_days={step.elapsed_days:.8f}")

    print("\nFuture pattern once runtime controls are exposed:")
    print("# depth = step.get.node.depth(node_id)")
    print("# if depth > threshold: step.set.pump.status(pump_id, 'ON')")
    print("Step-by-step run complete.")


if __name__ == "__main__":
    main()
