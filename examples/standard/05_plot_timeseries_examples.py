"""05 - Plot result time series for links, nodes, and the system."""

from swmmx import swmm

from _helpers import first_id, first_n_ids, get_example_path, get_output_dir, print_header, save_working_copy


def main() -> None:
    """Create compact, saved time-series examples using detected IDs."""

    print_header("05 - Plot time-series examples")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    save_working_copy(model, "05_timeseries_working_copy.inp")
    model.run()

    conduit_ids = model.get.conduit.id(format="df").columns.tolist()
    # Composite node IDs are easiest to discover from a result table after run.
    node_ids = model.get.node.depth(format="df").columns.tolist()
    first_conduit = first_id(conduit_ids)
    selected_conduits = first_n_ids(conduit_ids, 2)
    first_node = first_id(node_ids)

    if first_conduit:
        model.plot_timeseries.conduit.flow(
            first_conduit,
            title=f"Flow in {first_conduit}",
            show=False,
            save_path=output_dir / "timeseries_one_conduit_flow.png",
        )
    if selected_conduits:
        model.plot_timeseries.conduit.flow(
            selected_conduits,
            title="Conduit Flow",
            y_axis_title="Flow",
            grid=True,
            legend=True,
            show=False,
            save_path=output_dir / "timeseries_multiple_conduit_flows.png",
        )
    if first_node:
        model.plot_timeseries.node.depth(
            first_node,
            title=f"Depth at {first_node}",
            show=False,
            save_path=output_dir / "timeseries_node_depth.png",
        )

    model.plot_timeseries.system.runoff(
        title="System Runoff",
        y_axis_title="Runoff",
        show=False,
        save_path=output_dir / "timeseries_system_runoff.png",
    )
    print(f"Saved time-series plots to: {output_dir}")


if __name__ == "__main__":
    main()
