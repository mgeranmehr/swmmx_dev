"""04 - Create several network layout plots."""

from swmmx import swmm

from _helpers import get_example_path, get_output_dir, print_header, save_working_copy


def main() -> None:
    """Render static, parameter-driven, result-driven, and user-driven maps."""

    print_header("04 - Plot layout examples")
    output_dir = get_output_dir()
    model = swmm(get_example_path())
    save_working_copy(model, "04_plot_layout_working_copy.inp")
    model.run()

    model.plot_layout(show=False, save_path=output_dir / "layout_default.png")
    model.plot_layout(
        title="Network Layout",
        grid=True,
        axis=True,
        show=False,
        save_path=output_dir / "layout_basic.png",
    )
    model.plot_layout(
        nodes={"size": 45, "color": "black", "edge_color": "white"},
        links={"width": 2.0, "color": "slategray"},
        subcatchments={"color": "lightgreen", "edge_color": "green", "alpha": 0.30},
        show=False,
        save_path=output_dir / "layout_custom_styles.png",
    )
    model.plot_layout(
        links={
            "color": {
                "by": "parameter",
                "category": "conduit",
                "variable": "roughness",
                "mode": "continuous",
                "cmap": "viridis",
                "legend_title": "Roughness",
            }
        },
        show=False,
        save_path=output_dir / "layout_by_roughness.png",
    )
    model.plot_layout(
        links={
            "color": {
                "by": "result",
                "category": "link",
                "variable": "flow",
                "aggregation": "max",
                "mode": "continuous",
                "cmap": "plasma",
                "legend_title": "Max flow",
            }
        },
        show=False,
        save_path=output_dir / "layout_by_max_flow.png",
    )

    link_ids = model.get.conduit.id(format="df").columns.tolist()
    risk_scores = {link_id: index % 3 for index, link_id in enumerate(link_ids, start=1)}
    model.plot_layout(
        links={
            "color": {
                "by": "user",
                "data": risk_scores,
                "mode": "discrete",
                "cmap": "tab10",
                "legend_title": "Risk score",
            }
        },
        show=False,
        save_path=output_dir / "layout_by_user_risk.png",
    )
    print(f"Saved layout plots to: {output_dir}")


if __name__ == "__main__":
    main()

