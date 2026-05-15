"""10 - Create a small SI model from scratch, then add and remove elements."""

from swmmx import NotImplementedYetError, swmm

from _helpers import get_output_dir, print_header


def main() -> None:
    """Build a compact valid SI model and save two versions."""

    print_header("10 - Create a model from scratch")
    output_dir = get_output_dir()
    model = swmm(new="SI")

    model.set.option_general.flow_units("CMS")
    model.set.option_date_time.start_date("01/01/2026")
    model.set.option_date_time.start_time("00:00:00")
    model.set.option_date_time.end_date("01/01/2026")
    model.set.option_date_time.end_time("01:00:00")
    model.set.option_date_time.report_step("00:05:00")

    try:
        model.add.node.junction("J1", invert_elevation=10.0, max_depth=3.0, x=0.0, y=0.0)
        model.add.node.outfall("OUT1", invert_elevation=9.0, type="FREE", x=100.0, y=0.0)
        model.add.link.conduit(
            "C1",
            from_node="J1",
            to_node="OUT1",
            length=100.0,
            roughness=0.013,
            shape="CIRCULAR",
            diameter=1.0,
        )
        model.add.time.time_series(
            "Rain1",
            data=[("2026-01-01 00:00", 0.0), ("2026-01-01 00:05", 5.0)],
        )
        model.add.hydrology.rain_gage(
            "RG1",
            format="INTENSITY",
            interval="00:05",
            source_type="TIMESERIES",
            time_series="Rain1",
            x=0.0,
            y=100.0,
        )
        model.add.hydrology.subcatchment(
            "S1",
            rain_gage="RG1",
            outlet="J1",
            area=1.0,
            width=50.0,
            slope=1.0,
            impervious_percent=25.0,
            polygon=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)],
        )
    except NotImplementedYetError as exc:
        print(f"One requested builder is not ready in 0.0.9: {exc}")
        return

    issues = model.validate()
    print(f"Validation: {len(issues.errors)} errors, {len(issues.warnings)} warnings")
    print(issues.to_frame().head())

    created_path = model.save(output_dir / "created_model.inp")
    print(f"Saved created model: {created_path}")

    model.remove.link.conduit("C1")
    removed_path = model.save(output_dir / "created_model_without_conduit.inp")
    print(f"Saved model without conduit: {removed_path}")


if __name__ == "__main__":
    main()
