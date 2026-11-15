"""Versioned opt-in sidecars; no nonstandard INP sections."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import ValidationError
from .classes import json_check


def payload(manager):
    return manager.to_project().to_dict()


def read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("Expected object")
        json_check(data)
        return data
    except (OSError, ValueError, TypeError) as exc:
        raise ValidationError(f"Cannot read landcover sidecar {path}: {exc}") from exc


def save(manager, path):
    path = Path(path)
    data = read(path) if path.exists() else {}
    data["landcover"] = payload(manager)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(data, indent=2, allow_nan=False), encoding="utf-8"
        )
        temporary.replace(path)
    except OSError as exc:
        raise ValidationError(f"Cannot save landcover sidecar {path}: {exc}") from exc
    return path


def from_payload(data, model=None):
    """Validate/migrate a JSON project; attach only after validation succeeds."""
    from uuid import uuid4

    from .classes import name_check
    from .core import LandCover

    try:
        if not isinstance(data, dict) or data.get("version") not in (1, 2):
            raise ValueError("Unsupported landcover metadata version")
        json_check(data)
        version = data["version"]
        result = LandCover(units=data.get("units", "native"))
        result._editing = True
        ids = set()
        for item in data["classes"]:
            row = dict(item)
            class_id = row.pop("class_id") if version == 2 else str(uuid4())
            name_check(class_id)
            if class_id in ids:
                raise ValueError("Duplicate stable class ID")
            ids.add(class_id)
            result.add_class(**row)
            result._class_ids[row["name"]] = class_id
        for cov in data["coverage"]:
            fractions = (
                {result.class_name(k): v for k, v in cov["fractions"].items()}
                if version == 2
                else cov["fractions"]
            )
            result.assign(cov["subcatchment"], fractions, area_m2=cov["area_m2"])
        if not isinstance(data["source"], dict):
            raise TypeError("source must be a dictionary")
        result.source = data["source"]
        result.project_id = data.get("project_id", str(uuid4()))
        name_check(result.project_id)
        result.name = data.get("name")
        if result.name is not None:
            name_check(result.name)
        revision = data.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        result._revision = revision
        result._editing = False
        if model is not None:
            result.attach(model)
        return result
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(f"Invalid landcover project: {exc}") from exc


def load(path, model=None):
    try:
        return from_payload(read(path)["landcover"], model)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid landcover sidecar {path}: {exc}") from exc
