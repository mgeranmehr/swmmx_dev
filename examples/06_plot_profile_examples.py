"""06 - Plot longitudinal hydraulic profiles."""

from swmmx import NoPathError, swmm

from _helpers import get_example_path, get_output_dir, print_header, save_working_copy


def build_connected_conduit_chain(model) -> list[str]:
    """Return a simple directed conduit chain from the available network."""

    conduit_ids = model.get.conduit.id(format="df").columns.tolist()
    from_nodes = model.get.conduit.from_node(format="df").iloc[0].to_dict()
    to_nodes = model.get.conduit.to_node(format="df").iloc[0].to_dict()
    downstream_nodes = set(to_nodes.values())
    start_links = [link_id for link_id in conduit_ids if from_nodes[link_id] not in downstream_nodes]
    current_link = start_links[0] if start_links else conduit_ids[0]
    chain = [current_link]
    while True:
        next_links = [link_id for link_id in conduit_ids if from_nodes[link_id] == to_nodes[current_link]]
        if not next_links:
            break
        current_link = next_links[0]
        chain.append(current_link)
    return chain


def main() -> None:
    """Create node-path, link-path, and longest-path profile plots."""

    print_header("06 - Plot profile examples")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    save_working_copy(model, "06_profile_working_copy.inp")
    model.run()

    link_chain = build_connected_conduit_chain(model)
    from_nodes = model.get.conduit.from_node(format="df").iloc[0]
    to_nodes = model.get.conduit.to_node(format="df").iloc[0]
    start_node = from_nodes[link_chain[0]]
    end_node = to_nodes[link_chain[-1]]

    try:
        model.plot_profile.nodes(
            start_node,
            end_node,
            title=f"Profile from {start_node} to {end_node}",
            show_ground=True,
            show_conduits=True,
            show_hgl=True,
            show_water_depth=True,
            aggregation="max",
            grid=True,
            show=False,
            save_path=output_dir / "profile_between_nodes.png",
        )
    except NoPathError as exc:
        print(f"Could not plot node-to-node profile: {exc}")

    model.plot_profile.links(
        link_chain,
        title="Profile along selected links",
        show_ground=True,
        show_conduits=True,
        show_hgl=True,
        time_step=-1,
        grid=True,
        show=False,
        save_path=output_dir / "profile_selected_links.png",
    )
    model.plot_profile.longest(
        title="Longest Path Profile",
        show_ground=True,
        show_conduits=True,
        show_hgl=True,
        show_water_depth=True,
        aggregation="max",
        grid=True,
        show=False,
        save_path=output_dir / "profile_longest_path.png",
    )
    # EGL is intentionally omitted here because it is not yet available.
    print(f"Saved profile plots to: {output_dir}")


if __name__ == "__main__":
    main()
