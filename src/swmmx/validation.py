"""Model validation helpers for the first public release."""

from __future__ import annotations

from collections import Counter

from .inp import InpDocument
from .models import ValidationIssue, ValidationResult


FLOW_UNITS_US = {"CFS", "GPM", "MGD"}
FLOW_UNITS_SI = {"CMS", "LPS", "MLD"}
FLOW_UNITS_ALL = FLOW_UNITS_US | FLOW_UNITS_SI


def _ids(document: InpDocument, section_name: str) -> list[str]:
    """Return the first-token IDs for one SWMM object section."""

    return [row[0] for row in document.rows(section_name) if row]


def validate_document(document: InpDocument, has_results: bool) -> ValidationResult:
    """Run the built-in structural validator against one model document."""

    issues: list[ValidationIssue] = []

    # Required time and unit options are the minimum foundation for model timing
    # and engine execution.
    required_options = ("FLOW_UNITS", "START_DATE", "END_DATE", "REPORT_STEP")
    for option in required_options:
        if not document.get_option(option):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="MISSING_REQUIRED_OPTION",
                    message=f"Required option '{option}' is missing.",
                    section="OPTIONS",
                )
            )

    flow_units = document.get_option("FLOW_UNITS")
    if flow_units and flow_units.upper() not in FLOW_UNITS_ALL:
        issues.append(
            ValidationIssue(
                severity="error",
                code="INVALID_FLOW_UNITS",
                message=f"FLOW_UNITS '{flow_units}' is not one of {sorted(FLOW_UNITS_ALL)}.",
                section="OPTIONS",
            )
        )

    # Duplicate IDs inside a section are almost always accidental and can make
    # references ambiguous even before the native engine sees the file.
    id_sections = (
        "RAINGAGES",
        "SUBCATCHMENTS",
        "JUNCTIONS",
        "OUTFALLS",
        "STORAGE",
        "DIVIDERS",
        "CONDUITS",
        "PUMPS",
        "ORIFICES",
        "WEIRS",
        "OUTLETS",
    )
    for section_name in id_sections:
        counts = Counter(_ids(document, section_name))
        for object_id, count in counts.items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DUPLICATE_ID",
                        message=f"ID '{object_id}' appears {count} times in [{section_name}].",
                        section=section_name,
                        object_id=object_id,
                    )
                )

    # Build the object sets used by the cross-reference checks below.
    nodes = set().union(
        _ids(document, "JUNCTIONS"),
        _ids(document, "OUTFALLS"),
        _ids(document, "STORAGE"),
        _ids(document, "DIVIDERS"),
    )
    links = set().union(
        _ids(document, "CONDUITS"),
        _ids(document, "PUMPS"),
        _ids(document, "ORIFICES"),
        _ids(document, "WEIRS"),
        _ids(document, "OUTLETS"),
    )
    subcatchments = set(_ids(document, "SUBCATCHMENTS"))
    raingages = set(_ids(document, "RAINGAGES"))
    timeseries = set(_ids(document, "TIMESERIES"))
    curves = set(_ids(document, "CURVES"))
    patterns = set(_ids(document, "PATTERNS"))

    if not nodes:
        issues.append(
            ValidationIssue(
                severity="error",
                code="MISSING_NODES",
                message="The model does not contain any hydraulic nodes.",
            )
        )
    if not links:
        issues.append(
            ValidationIssue(
                severity="error",
                code="MISSING_LINKS",
                message="The model does not contain any hydraulic links.",
            )
        )

    # A conduit row begins with ID, from-node, and to-node.  Checking both sides
    # catches the most common topology mistakes before native execution.
    for row in document.rows("CONDUITS"):
        if len(row) < 3:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="MISSING_REQUIRED_FIELDS",
                    message="Conduit rows require at least ID, from-node, and to-node.",
                    section="CONDUITS",
                    object_id=row[0] if row else None,
                )
            )
            continue
        conduit_id, from_node, to_node = row[:3]
        if from_node not in nodes or to_node not in nodes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="INVALID_CONDUIT_ENDPOINT",
                    message=f"Conduit '{conduit_id}' references missing endpoint(s): {from_node}, {to_node}.",
                    section="CONDUITS",
                    object_id=conduit_id,
                )
            )

    for row in document.rows("XSECTIONS"):
        if row and row[0] not in links:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="INVALID_LINK_REFERENCE",
                    message=f"XSECTION '{row[0]}' does not reference an existing link.",
                    section="XSECTIONS",
                    object_id=row[0],
                )
            )

    for row in document.rows("SUBCATCHMENTS"):
        if len(row) < 3:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="MISSING_REQUIRED_FIELDS",
                    message="Subcatchment rows require at least ID, rain gage, and outlet.",
                    section="SUBCATCHMENTS",
                    object_id=row[0] if row else None,
                )
            )
            continue
        subcatchment_id, gage, outlet = row[:3]
        if gage not in raingages:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="INVALID_RAINGAGE_REFERENCE",
                    message=f"Subcatchment '{subcatchment_id}' references missing rain gage '{gage}'.",
                    section="SUBCATCHMENTS",
                    object_id=subcatchment_id,
                )
            )
        if outlet not in nodes and outlet not in subcatchments:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="INVALID_OUTLET_REFERENCE",
                    message=f"Subcatchment '{subcatchment_id}' references missing outlet '{outlet}'.",
                    section="SUBCATCHMENTS",
                    object_id=subcatchment_id,
                )
            )

    # The example file uses ``TIMESERIES <name>`` in the RAINGAGES source field;
    # this compact check also provides the requested invalid-timeseries signal.
    for row in document.rows("RAINGAGES"):
        if len(row) >= 6 and row[4].upper() == "TIMESERIES":
            series_id = row[5]
            if series_id not in timeseries:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_TIMESERIES_REFERENCE",
                        message=f"Rain gage '{row[0]}' references missing time series '{series_id}'.",
                        section="RAINGAGES",
                        object_id=row[0],
                    )
                )

    # Curves appear in several link/device sections; the first release checks
    # the most common pump form without pretending to understand every variant.
    for row in document.rows("PUMPS"):
        if len(row) >= 4:
            curve_id = row[3]
            if curve_id not in curves:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_CURVE_REFERENCE",
                        message=f"Pump '{row[0]}' references missing curve '{curve_id}'.",
                        section="PUMPS",
                        object_id=row[0],
                    )
                )

    # Patterns are commonly referenced by dry-weather inflows.  SWMM uses an
    # asterisk when no pattern applies, so that sentinel is exempt.
    for row in document.rows("DWF"):
        for pattern_id in row[3:]:
            if pattern_id != "*" and pattern_id not in patterns:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_PATTERN_REFERENCE",
                        message=f"DWF entry '{row[0]}' references missing pattern '{pattern_id}'.",
                        section="DWF",
                        object_id=row[0],
                    )
                )

    # Result access is not an input-file defect, so it is intentionally a
    # warning.  It still gives callers one place to see why run-only accessors
    # would currently fail.
    if not has_results:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="RESULTS_NOT_AVAILABLE",
                message="Run-dependent results are not available until the model has been executed.",
            )
        )

    return ValidationResult(issues=issues)
