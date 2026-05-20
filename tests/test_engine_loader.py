from pathlib import Path

import pytest

from swmmx.engine import EngineLoader
from swmmx.errors import EngineNotFoundError


def test_engine_loader_resolves_bundled_macos_library(monkeypatch):
    """Darwin should use the packaged GitHub Actions-built SWMM dylib."""

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    path = EngineLoader().resolve_path()

    assert path.name == "libswmm5.dylib"
    assert path.parts[-3:] == ("bin", "macos", "libswmm5.dylib")
    assert path.exists()


def test_engine_loader_custom_path_still_takes_priority_on_macos(tmp_path, monkeypatch):
    """A user-supplied engine path must remain the highest-priority option."""

    custom = tmp_path / "custom-libswmm5.dylib"
    custom.write_bytes(b"not a real dylib")
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    assert EngineLoader(custom).resolve_path() == custom.resolve()


def test_engine_loader_reports_missing_custom_path_clearly(tmp_path):
    missing = tmp_path / "missing" / "libswmm5.dylib"

    with pytest.raises(EngineNotFoundError, match="Custom SWMM engine not found"):
        EngineLoader(Path(missing)).resolve_path()
