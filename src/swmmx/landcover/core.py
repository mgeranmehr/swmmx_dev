"""Physical land-cover management, derivation and scenarios."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..errors import DuplicateIDError, ValidationError
from .classes import LandCoverClass, LandCoverCoverage, name_check, number

if TYPE_CHECKING:
    import pandas as pd

    from ..api import SWMMModel

from .workflow import LandCoverWorkflow, edit

TOL = 1e-8
HYDRO = {
    "percent_impervious": ("impervious_percent", None),
    "n_imperv": ("n_impervious", "n_imp"),
    "n_perv": ("n_pervious", "n_perv"),
    "dstore_imperv": ("depression_storage_impervious", "dstore_imp"),
    "dstore_perv": ("depression_storage_pervious", "dstore_perv"),
}


class LandCover(LandCoverWorkflow):
    """Manage physical surfaces independently from EPA water-quality LANDUSES.

    ``LandCover(model=None)`` creates an empty manager. Use the public
    ``landcover(model)`` factory to recover an attached/saved manager.
    Metadata edits never change simulation inputs. All invalid inputs raise
    SWMMX errors. Property units are declared SI/US or legacy native; area outputs use m².
    """

    def __init__(
        self,
        model: SWMMModel | None = None,
        *,
        units: str = "native",
        preset: str | None = None,
    ) -> None:
        if preset not in (None, "urban"):
            raise ValidationError("Only the names-only urban preset is supported")
        self._init_workflow(units)
        self.model = None
        self._classes: dict[str, LandCoverClass] = {}
        self._coverage: dict[str, LandCoverCoverage] = {}
        self.source: dict = {}
        self._landcover_gdf = None
        self._subcatchments_gdf = None
        self._intersections = None
        self._geometry_signature = None
        if model is not None:
            self.attach(model)
        if preset is not None:
            self.define_classes(
                {
                    name: {}
                    for name in (
                        "roof",
                        "road",
                        "pedestrian",
                        "green",
                        "bare_soil",
                        "parking",
                        "water",
                        "other",
                    )
                }
            )

    @property
    def classes(self) -> dict[str, LandCoverClass]:
        """Return independent class snapshots keyed by name; use add_class to edit."""
        return deepcopy(self._classes)

    def attach(self, model: SWMMModel) -> LandCover:
        """Attach to a model, validating IDs/areas; return self without editing inputs.

        Raises ValidationError on incompatible assignments or occupied attachment.
        Example: ``lc.attach(m)``. Native property units must match the model.
        """
        existing = getattr(model, "_landcover", None)
        if existing is not None and existing is not self:
            raise ValidationError(
                "Model already has landcover metadata; use landcover(model)"
            )
        for sid, cov in self._coverage.items():
            area = self._model_area(model, sid)
            if cov.area_m2 is not None and abs(cov.area_m2 - area) > TOL * max(area, 1):
                raise ValidationError(f"{sid}: stored area differs from model area")
        if self.model is not None and getattr(self.model, "_landcover", None) is self:
            del self.model._landcover
        self.model = model
        model._landcover = self
        self._revision += 1
        return self

    @edit
    def add_class(
        self,
        name: str,
        impervious: float | None = None,
        n_imp: float | None = None,
        n_perv: float | None = None,
        dstore_imp: float | None = None,
        dstore_perv: float | None = None,
        pct_zero: float | None = None,
        infiltration: dict | None = None,
        lids: dict | None = None,
        attributes: dict | None = None,
        description: str | None = None,
    ) -> LandCoverClass:
        """Add a validated class; return a snapshot. Duplicate names raise DuplicateIDError.

        Fractions are 0..1; pct_zero 0..100; storage uses native mm/inches.
        Metadata only. Example: ``lc.add_class('roof', impervious=1)``.
        """
        name_check(name)
        if name.casefold() in {key.casefold() for key in self._classes}:
            raise DuplicateIDError(f"Land-cover class already exists: {name}")
        cls = LandCoverClass(
            name,
            impervious,
            n_imp,
            n_perv,
            dstore_imp,
            dstore_perv,
            pct_zero,
            deepcopy(infiltration),
            deepcopy(lids if lids is not None else {}),
            deepcopy(attributes if attributes is not None else {}),
            description,
        )
        self._classes[name] = cls
        self._class_ids[name] = str(uuid4())
        return deepcopy(cls)

    def get_class(self, name: str) -> LandCoverClass:
        """Return a snapshot; raise ValidationError for unknown name. Example: lc.get_class('roof')."""
        if name not in self._classes:
            raise ValidationError(f"Unknown land-cover class: {name}")
        return deepcopy(self._classes[name])

    def has_class(self, name: str) -> bool:
        """Return whether name exists, without mutation. Example: lc.has_class('roof')."""
        return name in self._classes

    def list_classes(self) -> list[str]:
        """Return class names in definition order, without mutation. Example: lc.list_classes()."""
        return list(self._classes)

    @edit
    def remove_class(self, name: str) -> None:
        """Remove an unreferenced class; referenced/unknown names raise ValidationError."""
        self.get_class(name)
        if any(name in c.fractions for c in self._coverage.values()) or (
            self._landcover_gdf is not None
            and name in set(self._landcover_gdf["landcover"])
        ):
            raise ValidationError(f"{name} is referenced by coverage or GIS data")
        del self._classes[name]
        del self._class_ids[name]

    @edit
    def rename_class(self, name: str, new_name: str) -> None:
        """Rename a class and all metadata references; inputs stay unchanged.

        Example: lc.rename_class('road', 'street'). Duplicate/unknown names raise SWMMX errors.
        """
        cls = self.get_class(name)
        name_check(new_name)
        if new_name.casefold() in {key.casefold() for key in self._classes}:
            raise DuplicateIDError(new_name)
        cls.name = new_name
        self._class_ids[new_name] = self._class_ids.pop(name)
        self._classes = {
            new_name if k == name else k: cls if k == name else v
            for k, v in self._classes.items()
        }
        for cov in self._coverage.values():
            cov.fractions = {
                new_name if k == name else k: v for k, v in cov.fractions.items()
            }
        for frame in (self._landcover_gdf, self._intersections):
            if frame is not None:
                frame["landcover"] = frame["landcover"].replace({name: new_name})

    @staticmethod
    def _model_area(model, sid):
        if sid not in model._document.section_ids("SUBCATCHMENTS"):
            raise ValidationError(f"Unknown subcatchment: {sid}")
        value = model.get.subcatchment.area(ids=sid)
        return number(value, f"{sid} model area", positive=True) * (
            4046.8564224
            if model.options["FLOW_UNITS"] in ("CFS", "GPM", "MGD")
            else 10000
        )

    def _area(self, sid: str) -> float:
        if self.model is not None:
            value = self._model_area(self.model, sid)
            cov = self._coverage.get(sid)
            if (
                cov
                and cov.area_m2 is not None
                and abs(cov.area_m2 - value) > TOL * max(value, 1)
            ):
                raise ValidationError(
                    f"{sid}: model area changed; explicitly reassign coverage"
                )
            return value
        cov = self._coverage.get(sid)
        if cov is None or cov.area_m2 is None:
            raise ValidationError(
                f"{sid}: area is required; pass area_m2 to assign or attach a model"
            )
        return cov.area_m2

    @edit
    def assign(
        self,
        subcatchment: str,
        composition: dict[str, float],
        units: str = "fraction",
        normalize: bool = False,
        *,
        area_m2: float | None = None,
        overwrite: bool = False,
    ) -> None:
        """Assign complete coverage (metadata only); duplicate assignment requires overwrite=True.

        units: fraction, percent, m2, ha. Standalone area inputs require area_m2.
        normalize=True explicitly rescales positive totals. ValidationError rejects
        unknown IDs, negative values and incomplete totals. Example:
        ``lc.assign('S1', {'roof': .4, 'green': .6}, area_m2=1000)``.
        """
        name_check(subcatchment)
        if subcatchment in self._coverage and not overwrite:
            raise DuplicateIDError(
                f"{subcatchment} already assigned; use overwrite=True"
            )
        if not isinstance(composition, dict) or not composition:
            raise ValidationError("composition must be a nonempty dictionary")
        if units not in ("fraction", "percent", "m2", "ha"):
            raise ValidationError("units must be fraction, percent, m2 or ha")
        area = (
            number(area_m2, "area_m2", positive=True) if area_m2 is not None else None
        )
        if self.model is not None:
            model_area = self._model_area(self.model, subcatchment)
            if area is not None and abs(area - model_area) > TOL * max(model_area, 1):
                raise ValidationError("area_m2 differs from attached model area")
            area = model_area
        values = {}
        for key, value in composition.items():
            self.get_class(key)
            values[key] = number(
                value,
                key,
                high=1
                if units == "fraction"
                else 100
                if units == "percent"
                else float("inf"),
            )
        if units in ("m2", "ha"):
            if area is None:
                raise ValidationError(
                    "Standalone area assignment requires total area_m2"
                )
            values = {
                k: v * (10000 if units == "ha" else 1) / area for k, v in values.items()
            }
        elif units == "percent":
            values = {k: v / 100 for k, v in values.items()}
        total = number(sum(values.values()), "total coverage")
        if normalize:
            if total <= 0:
                raise ValidationError("Cannot normalize zero coverage")
            values = {k: v / total for k, v in values.items()}
        elif abs(total - 1) > TOL:
            raise ValidationError(
                f"{subcatchment}: coverage sums to {total}; expected 1; use normalize=True explicitly"
            )
        self._coverage[subcatchment] = LandCoverCoverage(subcatchment, values, area)
        self._intersections = None

    @edit
    def normalize(self, subcatchment: str) -> None:
        """Explicitly normalize stored fractions; metadata only. Example: lc.normalize('S1')."""
        cov = self.coverage(subcatchment)
        self.assign(
            subcatchment,
            cov.fractions,
            normalize=True,
            area_m2=cov.area_m2,
            overwrite=True,
        )

    def coverage(self, subcatchment: str) -> LandCoverCoverage:
        """Return an independent assignment snapshot; unknown IDs raise ValidationError."""
        if subcatchment not in self._coverage:
            raise ValidationError(f"No coverage assigned to {subcatchment}")
        return deepcopy(self._coverage[subcatchment])

    def coverage_fraction(self, subcatchment: str, class_name: str) -> float:
        """Return dimensionless class fraction (zero if absent), without mutation."""
        self.get_class(class_name)
        return self.coverage(subcatchment).fractions.get(class_name, 0.0)

    def coverage_area(self, subcatchment: str, class_name: str) -> float:
        """Return covered m²; missing total area raises ValidationError. Read-only."""
        return self.coverage_fraction(subcatchment, class_name) * self._area(
            subcatchment
        )

    def dominant_class(self, subcatchment: str) -> str:
        """Return largest class, breaking ties by assignment order. Read-only."""
        return max(
            self.coverage(subcatchment).fractions,
            key=self.coverage(subcatchment).fractions.get,
        )

    def coverage_table(self) -> pd.DataFrame:
        """Return subcatchment × class fractions as a new DataFrame; no mutation."""
        import pandas as pd

        return (
            pd.DataFrame.from_dict(
                {s: c.fractions for s, c in self._coverage.items()}, orient="index"
            )
            .reindex(columns=self.list_classes())
            .fillna(0.0)
            .rename_axis("subcatchment")
        )

    def classes_dataframe(self) -> pd.DataFrame:
        """Return a new class-property DataFrame (native storage units); no mutation."""
        import pandas as pd

        return pd.DataFrame([asdict(c) for c in self._classes.values()])

    def _parts(self, sid):
        cov = self.coverage(sid)
        if abs(sum(cov.fractions.values()) - 1) > TOL:
            raise ValidationError(f"{sid}: coverage must sum to 1")
        if self.model is not None:
            self._area(sid)
        parts = []
        for key, fraction in cov.fractions.items():
            cls = self.get_class(key)
            cls.__post_init__()
            if fraction > 0:
                if cls.impervious is None:
                    raise ValidationError(f"{key}: impervious is required")
                parts.append((cls, fraction))
        return parts

    def derive_hydrology(
        self,
        *,
        imperviousness: bool = True,
        roughness: bool = True,
        depression_storage: bool = True,
        pct_zero: bool = False,
    ) -> pd.DataFrame:
        """Preview area-weighted hydrology without editing model inputs.

        Return DataFrame: percent_impervious, n_imperv/n_perv,
        dstore_imperv/dstore_perv (native mm/inches), optionally pct_zero (%).
        Each surface uses its own impervious/pervious weights. An absent surface
        returns NaN; missing contributing properties raise ValidationError.
        Example: lc.derive_hydrology(depression_storage=False).
        """
        import pandas as pd

        rows = {}
        for sid in self._coverage:
            parts = self._parts(sid)
            imp = sum(f * c.impervious for c, f in parts)
            row = {"percent_impervious": 100 * imp} if imperviousness else {}
            fields = []
            if roughness:
                fields += [("n_imperv", "n_imp", True), ("n_perv", "n_perv", False)]
            if depression_storage:
                fields += [
                    ("dstore_imperv", "dstore_imp", True),
                    ("dstore_perv", "dstore_perv", False),
                ]
            if pct_zero:
                fields += [("pct_zero", "pct_zero", True)]
            for output, prop, imperv in fields:
                weights = [
                    (c, f * (c.impervious if imperv else 1 - c.impervious))
                    for c, f in parts
                ]
                weights = [(c, w) for c, w in weights if w > 0]
                for c, w in weights:
                    if getattr(c, prop) is None:
                        raise ValidationError(f"{sid}: class {c.name} needs {prop}")
                row[output] = (
                    sum(w * getattr(c, prop) for c, w in weights)
                    / sum(w for _, w in weights)
                    if weights
                    else float("nan")
                )
            rows[sid] = row
        return pd.DataFrame.from_dict(rows, orient="index").rename_axis("subcatchment")

    def derive_infiltration(
        self, method: str = "area_weighted", function: Callable | None = None
    ) -> pd.DataFrame:
        """Preview pervious infiltration approximation; never edits the model.

        method: area_weighted, dominant, or custom with function(parts)->dict.
        Native mm/hr or in/hr and model-specific units apply. Incompatible or
        missing metadata raises ValidationError. Example: lc.derive_infiltration().
        """
        from .infiltration import derive

        return derive(self, method, function)

    def apply_hydrology(
        self,
        imperviousness: bool = True,
        roughness: bool = True,
        depression_storage: bool = True,
        infiltration: bool = False,
        *,
        pct_zero: bool = False,
        infiltration_method: str = "area_weighted",
        function: Callable | None = None,
    ) -> pd.DataFrame:
        """Apply selected preview values through native setters; return hydrology DataFrame.

        Requires attached model. Validate on an isolated document before committing;
        changes mark inputs modified and existing results stale. Absent surfaces keep
        existing native values. Example: lc.apply_hydrology(infiltration=True).
        """
        groups = []
        for enabled, name in (
            (imperviousness, "imperviousness"),
            (roughness, "roughness"),
            (depression_storage, "depression_storage"),
            (pct_zero, "pct_zero"),
            (infiltration, "infiltration"),
        ):
            if enabled:
                groups.append(name)
        if not groups:
            import pandas as pd

            return pd.DataFrame()
        result = self.preview(
            groups, infiltration_method=infiltration_method, function=function
        )
        self.apply(result)
        return result.values.drop(
            columns=[c for c in result.values.columns if c not in {*HYDRO, "pct_zero"}]
        )

    def _commit(self, trial):
        if trial._document.to_text() != self.model._document.to_text():
            self.model._document = trial._document
            self.model._dirty = True
            self.model._invalidate_results()

    def lid_candidates(
        self,
        subcatchment: str | None = None,
        *,
        filter_function: Callable | None = None,
    ) -> pd.DataFrame:
        """Return independent LID upper bounds in m² and total-subcatchment fractions.

        Never creates controls/usage. min_area filters each class contribution;
        priority is descriptive. Different LID types may compete for the same area.
        filter_function(row)->area_m2 may explicitly reduce a candidate bound.
        Missing area or invalid callback output raises ValidationError.
        """
        import pandas as pd

        ids = list(self._coverage) if subcatchment is None else [subcatchment]
        lids = sorted({lid for c in self._classes.values() for lid in c.lids})
        rows = []
        for sid in ids:
            cov = self.coverage(sid)
            total = self._area(sid)
            for lid in lids:
                area = 0.0
                for key, fraction in cov.fractions.items():
                    value = self._classes[key].lids.get(lid, 0)
                    metadata = (
                        value
                        if isinstance(value, dict)
                        else {"suitable_fraction": value}
                    )
                    contribution = total * fraction * metadata["suitable_fraction"]
                    if contribution >= metadata.get("min_area", 0):
                        area += contribution
                row = {
                    "subcatchment": sid,
                    "lid_type": lid,
                    "candidate_area_m2": area,
                    "candidate_fraction": area / total,
                }
                if filter_function is not None:
                    area = number(
                        filter_function(dict(row)), "filtered candidate area", high=area
                    )
                    row.update(candidate_area_m2=area, candidate_fraction=area / total)
                rows.append(row)
        return pd.DataFrame(
            rows,
            columns=[
                "subcatchment",
                "lid_type",
                "candidate_area_m2",
                "candidate_fraction",
            ],
        )

    def copy(self, *, clone_model: bool = True) -> LandCover:
        """Independent copy. Legacy default clones model; scenario() defaults to metadata only."""
        result = LandCover(units=self.units)
        result._restore(self._state())
        if self.model is not None:
            if clone_model:
                result.model = self.model.clone()
                result.model._landcover = result
            else:
                from .adapter import SWMMLandCoverAdapter

                if result.units == "native":
                    result._units = SWMMLandCoverAdapter(self.model).units
                for sid, cov in result._coverage.items():
                    cov.area_m2 = self._area(sid)
                result._geometry_signature = None
        return result

    def __deepcopy__(self, memo: dict) -> LandCover:
        # Model.clone explicitly copies metadata without recursively cloning its model.
        result = self.copy()
        memo[id(self)] = result
        return result

    @edit
    def convert(
        self,
        subcatchment: str,
        source: str,
        target: str,
        *,
        area: float | None = None,
        units: str = "m2",
        fraction: float | None = None,
    ) -> None:
        """Transfer total-subcatchment fraction or area (m2/ha); metadata only.

        Exactly one of area/fraction is required. Overdraw raises ValidationError.
        Example: lc.convert('S1', 'road', 'green', area=500).
        """
        self.get_class(source)
        self.get_class(target)
        if (area is None) == (fraction is None):
            raise ValidationError("Supply exactly one of area or fraction")
        if units not in ("m2", "ha"):
            raise ValidationError("Area conversion units must be m2 or ha")
        amount = (
            number(fraction, "fraction", high=1)
            if fraction is not None
            else number(area, "area")
            * (10000 if units == "ha" else 1)
            / self._area(subcatchment)
        )
        cov = self.coverage(subcatchment)
        if amount > cov.fractions.get(source, 0):
            raise ValidationError("Conversion exceeds available source coverage")
        cov.fractions[source] = cov.fractions.get(source, 0) - amount
        cov.fractions[target] = cov.fractions.get(target, 0) + amount
        self.assign(subcatchment, cov.fractions, area_m2=cov.area_m2, overwrite=True)

    def to_dataframe(
        self, *, include_hydrology: bool = True, include_lids: bool = True
    ) -> pd.DataFrame:
        """Return coverage fractions, m² area, hydrology and LID bounds; no mutation.

        Missing hydrology/area raises ValidationError. Example: lc.to_dataframe().
        """
        result = self.coverage_table().add_suffix("_fraction")
        result.insert(0, "area_m2", [self._area(s) for s in result.index])
        for name in self.list_classes():
            result[name + "_area_m2"] = result[name + "_fraction"] * result["area_m2"]
        if include_hydrology:
            result = result.join(self.derive_hydrology())
        candidates = self.lid_candidates() if include_lids else []
        if len(candidates):
            result = result.join(
                candidates.pivot(
                    index="subcatchment", columns="lid_type", values="candidate_area_m2"
                )
                .add_prefix("lid_")
                .add_suffix("_area_m2")
            )
        return result

    def compare(self, other_lc: LandCover) -> pd.DataFrame:
        """Return scenario minus baseline numeric values, aligned by ID; no mutation.

        Requires identical assigned IDs and areas. New classes/LID types align to
        zero. Example: lc.compare(future). Missing properties raise ValidationError.
        """
        from .adapter import SWMMLandCoverAdapter

        def property_units(manager):
            if manager.units == "native" and manager.model is not None:
                return SWMMLandCoverAdapter(manager.model).units
            return manager.units

        if property_units(self) != property_units(other_lc):
            raise ValidationError("Comparison requires matching class property units")
        if set(self._coverage) != set(other_lc._coverage) or any(
            abs(self._area(s) - other_lc._area(s)) > TOL for s in self._coverage
        ):
            raise ValidationError(
                "Comparison requires matching subcatchments and total areas"
            )
        first, second = self.to_dataframe(), other_lc.to_dataframe()
        columns = first.columns.union(second.columns, sort=False)
        return second.reindex(columns=columns, fill_value=0) - first.reindex(
            columns=columns, fill_value=0
        )

    def apply_swmm_landuses(self, overwrite: bool = False) -> None:
        """Explicitly create native LANDUSES/COVERAGES; preserve BUILDUP/WASHOFF.

        Existing matching names or coverage require overwrite=True. Existing
        sweeping settings are retained. New native classes have no sweeping.
        Commits atomically, marking changed inputs/results. Example:
        lc.apply_swmm_landuses(). No model raises ValidationError.
        """
        if self.model is None:
            raise ValidationError("Attach a model first")
        existing = {row[0].casefold() for row in self.model._document.rows("LANDUSES")}
        existing_cov = self.model._document.rows("COVERAGES")
        if not overwrite and (
            existing.intersection(k.casefold() for k in self._classes)
            or any(row[0] in self._coverage for row in existing_cov)
        ):
            raise ValidationError(
                "Native quality configuration exists; use overwrite=True explicitly"
            )
        trial = self.model.clone()
        for key in self._classes:
            if key.casefold() not in existing:
                trial._document.append_row("LANDUSES", [key, 0, 0, 0])
        for sid, cov in self._coverage.items():
            if self.model is not None:
                self._area(sid)
            rows = [[sid, key, value * 100] for key, value in cov.fractions.items()]
            trial._replace_related_rows("COVERAGES", sid, rows)
        self._commit(trial)

    def validate(self) -> pd.DataFrame:
        """Return diagnostics (severity, subcatchment, message), without mutation.

        Includes derivation requirements; unassigned model IDs are warnings.
        Example: lc.validate(). Empty table means no detected issues.
        """
        import pandas as pd

        issues = []
        for sid in self._coverage:
            try:
                self._parts(sid)
                self._area(sid)
            except ValidationError as exc:
                issues.append(("error", sid, str(exc)))
        try:
            self.derive_hydrology()
            if any(c.infiltration is not None for c in self._classes.values()):
                self.derive_infiltration()
            if self._intersections is not None:
                self.intersections_geodataframe()
        except ValidationError as exc:
            issues.append(("error", None, str(exc)))
        if self.model is not None:
            for sid in self.model._document.section_ids("SUBCATCHMENTS"):
                if sid not in self._coverage:
                    issues.append(("warning", sid, "No landcover assigned"))
        return pd.DataFrame(issues, columns=["severity", "subcatchment", "message"])

    def summary(self) -> dict[str, Any]:
        """Return counts, covered area, area-weighted imperviousness and diagnostics; read-only."""
        area = sum(self._area(s) for s in self._coverage)
        imp = self.derive_hydrology(roughness=False, depression_storage=False)
        return {
            "classes": len(self._classes),
            "assigned_subcatchments": len(self._coverage),
            "assigned_area_m2": area,
            "mean_percent_impervious": sum(
                self._area(s) * imp.loc[s, "percent_impervious"] for s in self._coverage
            )
            / area
            if area
            else None,
            "source": deepcopy(self.source),
            "validation": self.validate(),
        }

    def save(self, path: str | Path) -> Path:
        """Save explicit JSON sidecar, returning path; no model input mutation.

        Invalid/unserializable data raises ValidationError. Example: lc.save('cover.json').
        """
        from .persistence import save

        return save(self, path)

    @classmethod
    def load(cls, path: str | Path, model: SWMMModel | None = None) -> LandCover:
        """Load validated JSON metadata, optionally attach; malformed data raises ValidationError."""
        from .persistence import load

        return load(path, model)

    @edit
    def from_geodataframe(self, gdf: Any, class_field: str = "class") -> LandCover:
        """Import validated polygons with explicit CRS; return self, metadata only.

        Unknown classes/invalid polygons raise ValidationError. Example:
        lc.from_geodataframe(gdf, class_field='surface'). GIS dependencies optional.
        """
        from .gis import import_frame

        return import_frame(self, gdf, class_field)

    @edit
    def from_gis(
        self, path: str | Path, class_field: str = "class", *, layer: str | None = None
    ) -> LandCover:
        """Read any GeoPandas vector format; retain provenance, return self.

        Example: lc.from_gis('cover.gpkg', layer='surfaces'). No input mutation.
        """
        from ..export.gis import _require_gis_dependencies

        gpd, *_ = _require_gis_dependencies()
        result = self.from_geodataframe(
            gpd.read_file(path, **({"layer": layer} if layer else {})), class_field
        )
        self.source.update(source_file=str(Path(path).resolve()), source_layer=layer)
        return result

    @edit
    def overlay(
        self,
        landcover: Any = None,
        subcatchments: Any = None,
        *,
        area_crs: Any = None,
        model_crs: Any = None,
        class_field: str = "class",
        subcatchment_field: str = "subcatchment",
        overlap: str = "error",
        overwrite: bool = False,
        progress: Callable | None = None,
        cancelled: Callable | None = None,
    ) -> pd.DataFrame:
        """Intersect polygons into coverage; return fraction table, metadata only.

        CRS mismatch requires explicit area_crs. Model polygons require model_crs
        because INP does not encode CRS. Gaps/overlaps/invalid geometry raise
        ValidationError. Fractions use polygon areas; model area sets physical
        coverage areas. Example: lc.overlay(model_crs='EPSG:32639').
        """
        from .gis import overlay

        return overlay(
            self,
            landcover,
            subcatchments,
            area_crs,
            model_crs,
            class_field,
            subcatchment_field,
            overlap,
            overwrite,
            progress,
            cancelled,
        )

    def intersections_geodataframe(self) -> Any:
        """Return intersection snapshot in projected CRS (m², fraction); stale/missing raises ValidationError."""
        from .gis import check_intersections

        check_intersections(self)
        return self._intersections.copy(deep=True)

    def to_geodataframe(
        self, *, include_hydrology: bool = False, include_lids: bool = False
    ) -> Any:
        """Return subcatchment geometry joined to tabular outputs; requires completed overlay."""
        self.intersections_geodataframe()
        return (
            self._subcatchments_gdf.set_index("subcatchment")
            .join(
                self.to_dataframe(
                    include_hydrology=include_hydrology, include_lids=include_lids
                )
            )
            .reset_index()
        )

    def coverage_geodataframe(self) -> Any:
        """Alias for to_geodataframe(); returns new GIS output without mutation."""
        return self.to_geodataframe()

    def plot(
        self,
        class_name: str | None = None,
        subcatchment: str | None = None,
        kind: str = "landcover",
        lid: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Return a GeoPandas/Matplotlib Axes; no mutation (optional plotting/GIS dependencies).

        kind: landcover, imperviousness, lid_candidates. Example: lc.plot(class_name='roof').
        Requires current overlay; kwargs pass to GeoDataFrame.plot.
        """
        if kind == "landcover" and class_name is None:
            frame = self.intersections_geodataframe()
            column = "landcover"
        else:
            frame = self.to_geodataframe(
                include_hydrology=kind == "imperviousness",
                include_lids=kind == "lid_candidates",
            )
            if class_name is not None:
                self.get_class(class_name)
                column = class_name + "_fraction"
            elif kind == "imperviousness":
                column = "percent_impervious"
            elif kind == "lid_candidates" and "lid_" + str(lid) + "_area_m2" in frame:
                column = "lid_" + str(lid) + "_area_m2"
            else:
                raise ValidationError("Unknown plot kind or LID type")
        if subcatchment is not None:
            self.coverage(subcatchment)
            frame = frame[frame.subcatchment == subcatchment]
        return frame.plot(column=column, **kwargs)
