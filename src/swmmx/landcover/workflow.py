"""Friendly bulk operations, project snapshots, revision history and frontend handles."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from functools import wraps
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import SWMMXError, ValidationError
from .classes import LandCoverClass, json_check, name_check
from .contracts import (
    LandCoverIssue,
    LandCoverPreview,
    LandCoverProject,
    LandCoverReport,
    LandCoverValidationError,
)

STATE_KEYS = (
    "_classes",
    "_class_ids",
    "_coverage",
    "source",
    "_units",
    "_landcover_gdf",
    "_subcatchments_gdf",
    "_intersections",
    "_geometry_signature",
    "name",
)


def edit(method):
    """Wrap metadata edits in one rollback/history transaction, including nested calls."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if self._editing:
            return method(self, *args, **kwargs)
        before = self._state()
        fingerprint = self._fingerprint()
        self._editing = True
        try:
            result = method(self, *args, **kwargs)
        except Exception:
            self._restore(before)
            raise
        finally:
            self._editing = False
        if self._fingerprint() != fingerprint:
            self._history.append((method.__name__, before))
            self._history = self._history[-20:]
            self._redo.clear()
            self._revision += 1
        return result

    return wrapped


def _records(data, key):
    import pandas as pd

    if isinstance(data, (str, Path)):
        data = pd.read_csv(data)
    if isinstance(data, pd.DataFrame):
        if data.isin([float("inf"), float("-inf")]).any().any():
            raise ValidationError("DataFrame contains infinite values")
        for row in data.to_dict(orient="records"):
            for value in row.values():
                if isinstance(value, (dict, list)):
                    json_check(value)
        if key not in data.columns and data.index.name == key:
            data = data.reset_index()
        return json.loads(data.to_json(orient="records"))
    if isinstance(data, dict):
        if not all(isinstance(v, dict) for v in data.values()):
            raise ValidationError("Mapping values must be dictionaries")
        return [{key: k, **v} for k, v in data.items()]
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return deepcopy(data)
    raise ValidationError("Expected a mapping, list of records, DataFrame or CSV path")


def _issue(row, object_id, field, exc):
    return LandCoverIssue(
        "INVALID_INPUT",
        "error",
        str(object_id) if object_id is not None else None,
        field,
        str(exc),
        "Correct the indicated record and resubmit the whole batch",
        row,
    )


class LandCoverWorkflow:
    """User-facing workflow mixin; calculations and native model adaptation are separate."""

    def _init_workflow(self, units):
        if units not in ("native", "SI", "US"):
            raise ValidationError("units must be native, SI or US")
        self._units = units
        self._class_ids = {}
        self.project_id = str(uuid4())
        self.name = None
        self._revision = 0
        self._history, self._redo = [], []
        self._previews = {}
        self._editing = False
        self._applied = None

    @property
    def units(self) -> str:
        """Declared property units; never silently reinterpreted or converted in storage."""
        return self._units

    @property
    def revision(self) -> int:
        """Monotonic session revision; undo/redo also invalidate old previews."""
        return self._revision

    def _state(self):
        return {k: deepcopy(getattr(self, k)) for k in STATE_KEYS}

    def _restore(self, state):
        for key, value in state.items():
            setattr(self, key, deepcopy(value))

    def _fingerprint(self):
        state = self.to_project().to_dict()
        state.pop("revision", None)
        for key in ("_landcover_gdf", "_subcatchments_gdf", "_intersections"):
            frame = getattr(self, key)
            state[key] = (
                None
                if frame is None
                else {
                    "crs": str(frame.crs),
                    "rows": frame.drop(columns=frame.geometry.name).to_json(
                        orient="split"
                    ),
                    "geometry": list(frame.geometry.to_wkb(hex=True)),
                }
            )
        return sha256(
            json.dumps(state, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    def _working_copy(self):
        from .core import LandCover

        result = LandCover(units=self.units)
        result._restore(self._state())
        result.model = self.model
        result._editing = True
        return result

    def class_id(self, name: str) -> str:
        """Return stable class identity; renaming changes only its human label."""
        self.get_class(name)
        return self._class_ids[name]

    def class_name(self, class_id: str) -> str:
        """Resolve stable identity to its current label; unknown IDs raise ValidationError."""
        for name, value in self._class_ids.items():
            if value == class_id:
                return name
        raise ValidationError(f"Unknown class ID: {class_id}")

    @edit
    def define_classes(
        self, data: Any, *, overwrite: bool = False, validate_only: bool = False
    ) -> Any:
        """Atomically define a mapping/DataFrame/CSV class library; collect all row errors.

        Example: lc.define_classes({'roof': {'impervious': 1}}).
        CSV nested dictionaries use JSON cells. Null optional properties are unset.
        validate_only returns LandCoverReport without edits; otherwise returns self.
        Existing definitions require overwrite=True. Stable IDs are retained.
        """
        stage = self._working_copy()
        issues, seen = [], set()
        for index, row in enumerate(_records(data, "name")):
            name = row.get("name")
            try:
                name_check(name)
                if name.casefold() in seen:
                    raise ValidationError(f"Duplicate name in batch: {name}")
                seen.add(name.casefold())
                for field in ("lids", "attributes", "infiltration"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
                if stage.has_class(name) and overwrite:
                    stage.update_class(
                        name, **{k: v for k, v in row.items() if k != "name"}
                    )
                else:
                    stage.add_class(**row)
            except (SWMMXError, TypeError, ValueError) as exc:
                issues.append(_issue(index, name, "classes", exc))
        report = LandCoverReport(tuple(issues))
        if validate_only:
            return report
        if not report.can_apply:
            raise LandCoverValidationError(report)
        self._restore(stage._state())
        return self

    @edit
    def update_class(self, name: str, **changes: Any) -> LandCoverClass:
        """Validate and update supplied properties while retaining ID and references.

        Metadata only. Example: lc.update_class('roof', n_imp=.013).
        Use rename_class for labels; previews become stale, GIS geometry stays valid.
        """
        if "name" in changes or "class_id" in changes:
            raise ValidationError(
                "Use rename_class to change labels; class IDs are immutable"
            )
        old = asdict(self.get_class(name))
        unknown = set(changes) - set(old)
        if unknown:
            raise ValidationError(f"Unknown class properties: {sorted(unknown)}")
        old.update(deepcopy(changes))
        for key in ("lids", "attributes"):
            if old[key] is None:
                old[key] = {}
        updated = LandCoverClass(**old)
        self._classes[name] = updated
        return deepcopy(updated)

    @edit
    def set_coverage(
        self,
        data: Any,
        *,
        units: str | None = None,
        area_m2: Any = None,
        overwrite: bool = False,
        normalize: bool = False,
        validate_only: bool = False,
    ) -> Any:
        """Bulk mapping, wide table or explicit long table, committed atomically.

        Wide: subcatchment, class columns, optional total area_m2. Mapping:
        {'S1': {'roof': .4, 'green': .6}}. Long: subcatchment, class/class_id,
        exactly one of fraction/percent/area_m2/area_ha, optional total_area_m2.
        area_m2 argument is a scalar or ID mapping. Returns self, or a dry-run report.
        Duplicate rows/assignments need correction or explicit overwrite, never silent summation.
        """
        records = _records(data, "subcatchment")
        stage = self._working_copy()
        issues, assignments, seen = [], {}, set()
        for index, raw in enumerate(records):
            row = dict(raw)
            sid = row.pop("subcatchment", None)
            try:
                name_check(sid)
                total = area_m2.get(sid) if isinstance(area_m2, dict) else area_m2
                if "class" in row or "class_id" in row:
                    if "class" in row and "class_id" in row:
                        raise ValidationError("Use class or class_id, not both")
                    key = (
                        row.pop("class")
                        if "class" in row
                        else self.class_name(row.pop("class_id"))
                    )
                    self.get_class(key)
                    value_fields = set(row).intersection(
                        {"fraction", "percent", "area_m2", "area_ha"}
                    )
                    if len(value_fields) != 1:
                        raise ValidationError(
                            "Long coverage requires exactly one explicit value column"
                        )
                    value_field = next(iter(value_fields))
                    inferred = {"area_m2": "m2", "area_ha": "ha"}.get(
                        value_field, value_field
                    )
                    if units is not None and units != inferred:
                        raise ValidationError(
                            "units conflicts with the explicit value column"
                        )
                    value = row.pop(value_field)
                    total = row.pop("total_area_m2", total)
                    if row:
                        raise ValidationError(f"Unknown coverage columns: {list(row)}")
                    if (sid, key) in seen:
                        raise ValidationError(f"Duplicate coverage row: {sid}/{key}")
                    seen.add((sid, key))
                    item = assignments.setdefault(
                        sid,
                        {"values": {}, "units": inferred, "area": total, "row": index},
                    )
                    if item["units"] != inferred or item["area"] != total:
                        raise ValidationError(
                            f"{sid}: inconsistent units or total area"
                        )
                    item["values"][key] = value
                else:
                    if sid in assignments:
                        raise ValidationError(f"Duplicate subcatchment row: {sid}")
                    total = row.pop("area_m2", total)
                    assignments[sid] = {
                        "values": row,
                        "units": units or "fraction",
                        "area": total,
                        "row": index,
                    }
            except (SWMMXError, TypeError, ValueError) as exc:
                issues.append(_issue(index, sid, "coverage", exc))
        for sid, item in assignments.items():
            try:
                stage.assign(
                    sid,
                    item["values"],
                    units=item["units"],
                    area_m2=item["area"],
                    normalize=normalize,
                    overwrite=overwrite,
                )
            except (SWMMXError, TypeError, ValueError) as exc:
                issues.append(_issue(item["row"], sid, "coverage", exc))
        report = LandCoverReport(tuple(issues))
        if validate_only:
            return report
        if not report.can_apply:
            raise LandCoverValidationError(report)
        self._restore(stage._state())
        return self

    def preview(
        self,
        parameters: list[str] | None = None,
        *,
        infiltration_method: str = "area_weighted",
        function: Callable | None = None,
    ) -> LandCoverPreview:
        """Read-only review with native-target values, current/proposed changes and issues.

        parameters selects imperviousness, roughness, depression_storage, pct_zero,
        infiltration. Standalone calculation works but cannot apply until attached.
        Example: p=lc.preview(['imperviousness']); lc.apply(p).
        """
        from .services import preview

        return preview(self, parameters, infiltration_method, function)

    def apply(self, preview: LandCoverPreview | str) -> Any:
        """Apply a registered immutable preview or its frontend preview_id atomically.

        Rejects stale project/model revisions and previews from other managers.
        Does not recalculate unreviewed values. Returns a copy of applied values.
        """
        from .adapter import SWMMLandCoverAdapter

        key = preview if isinstance(preview, str) else preview.preview_id
        stored = self._previews.get(key)
        if stored is None or (not isinstance(preview, str) and stored != preview):
            raise ValidationError(
                "Unknown/modified preview; generate a new preview in this manager"
            )
        data = stored.to_dict()
        adapter = SWMMLandCoverAdapter(self.model) if self.model is not None else None
        if (
            data["revision"] != self.revision
            or data["project_fingerprint"] != self._fingerprint()
            or adapter is None
            or data["model_fingerprint"] != adapter.fingerprint()
        ):
            raise ValidationError(
                "Stale preview: project or model changed; generate and review a new preview"
            )
        if not stored.can_apply:
            raise LandCoverValidationError(LandCoverReport(stored.issues))
        adapter.apply(data["values"])
        self._applied = (self._fingerprint(), adapter.fingerprint())
        self._previews.clear()
        return stored.values

    def set_surfaces(
        self, data: Any, *, class_column: str = "class", layer: str | None = None
    ) -> Any:
        """Import a GeoDataFrame or vector path; alias with beginner-friendly naming."""
        return (
            self.from_gis(data, class_field=class_column, layer=layer)
            if isinstance(data, (str, Path))
            else self.from_geodataframe(data, class_field=class_column)
        )

    def calculate_coverage(
        self,
        subcatchments: Any = None,
        *,
        area_crs: Any = None,
        model_crs: Any = None,
        overwrite: bool = False,
        progress: Callable | None = None,
        cancelled: Callable | None = None,
    ) -> Any:
        """Calculate GIS coverage with progress events and cooperative cancellation.

        progress receives {stage, completed, total}; cancelled()->bool is checked
        between stages and assignment rows. GEOS overlay itself is not interruptible.
        Cancellation/callback failure rolls metadata back. No native inputs change.
        """
        return self.overlay(
            subcatchments=subcatchments,
            area_crs=area_crs,
            model_crs=model_crs,
            overwrite=overwrite,
            progress=progress,
            cancelled=cancelled,
        )

    def scenario(self, name: str | None = None, *, clone_model: bool = False) -> Any:
        """Create lightweight independent metadata by default; model cloning is explicit.

        Attached areas/units are frozen on detach. Example: future=lc.scenario('green').
        Legacy copy() retains its model-cloning default for compatibility.
        """
        result = self.copy(clone_model=clone_model)
        result.name = name
        return result

    def history(self) -> list[dict[str, Any]]:
        """Return up to 20 undoable operation labels; native model edits are excluded."""
        return [{"operation": name} for name, _ in self._history]

    def undo(self) -> None:
        """Undo one metadata transaction; preserves native inputs and increases revision."""
        if not self._history:
            raise ValidationError("No metadata operation to undo")
        name, state = self._history.pop()
        self._redo.append((name, self._state()))
        self._restore(state)
        self._revision += 1

    def redo(self) -> None:
        """Redo one undone metadata transaction; old previews remain stale."""
        if not self._redo:
            raise ValidationError("No metadata operation to redo")
        name, state = self._redo.pop()
        self._history.append((name, self._state()))
        self._restore(state)
        self._revision += 1

    @property
    def status(self) -> dict[str, Any]:
        """JSON workflow state with explicit spatial validity and model-application status."""
        from .adapter import SWMMLandCoverAdapter

        fingerprint = self._fingerprint()
        model_stamp = (
            SWMMLandCoverAdapter(self.model).fingerprint() if self.model else None
        )
        current = [
            p
            for p in self._previews.values()
            if p.to_dict()["revision"] == self.revision
            and p.to_dict()["project_fingerprint"] == fingerprint
            and p.to_dict()["model_fingerprint"] == model_stamp
        ]
        spatial, reason = (
            "not_loaded",
            "No GIS products; import surfaces and calculate coverage",
        )
        if self._subcatchments_gdf is not None:
            try:
                self.intersections_geodataframe()
                spatial, reason = "ready", None
            except ValidationError as exc:
                spatial, reason = "stale", str(exc)
        return {
            "project_id": self.project_id,
            "revision": self.revision,
            "coverage_ready": bool(self._coverage),
            "preview_ready": any(
                not any(i.severity == "error" for i in p.issues) for p in current
            ),
            "model_updated": self._applied == (fingerprint, model_stamp),
            "spatial_state": spatial,
            "spatial_message": reason,
            "can_undo": bool(self._history),
            "can_redo": bool(self._redo),
        }

    def to_project(self) -> LandCoverProject:
        """Export version-2 backend data; stable IDs separate labels from references."""
        data = {
            "version": 2,
            "project_id": self.project_id,
            "name": self.name,
            "revision": self.revision,
            "units": self.units,
            "classes": [
                {"class_id": self._class_ids[c.name], **asdict(c)}
                for c in self._classes.values()
            ],
            "coverage": [
                {
                    "subcatchment": c.subcatchment,
                    "area_m2": c.area_m2,
                    "fractions": {
                        self._class_ids[k]: v for k, v in c.fractions.items()
                    },
                }
                for c in self._coverage.values()
            ],
            "source": self.source,
        }
        json_check(data)
        return LandCoverProject(json.dumps(data, allow_nan=False))

    @classmethod
    def from_project(
        cls, project: LandCoverProject | dict | str, model: Any = None
    ) -> Any:
        """Load versioned JSON/data and validate every reference; migrate v1 sidecars.

        History, previews and geometries are session-only. Unknown versions fail.
        Loading never changes native inputs. Malformed data raises ValidationError.
        """
        from .persistence import from_payload

        try:
            data = (
                project.to_dict()
                if isinstance(project, LandCoverProject)
                else json.loads(project)
                if isinstance(project, str)
                else deepcopy(project)
            )
        except ValueError as exc:
            raise ValidationError(f"Invalid project JSON: {exc}") from exc
        return from_payload(data, model)
