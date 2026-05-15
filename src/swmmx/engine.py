"""Isolated native-engine loading and invocation for SWMM."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import platform
from typing import Iterator

from .errors import EngineLoadError, EngineNotFoundError


class Engine:
    """Thin safe wrapper around the exported SWMM C API."""

    def __init__(self, library: ctypes.CDLL, path: Path) -> None:
        """Store the loaded library and configure the symbols we call."""

        self._library = library
        self.path = path
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        """Attach ctypes signatures for the engine calls used by the package."""

        # The explicit signatures prevent ctypes from guessing pointer widths or
        # return types incorrectly on 64-bit Python.
        self._library.swmm_run.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self._library.swmm_run.restype = ctypes.c_int
        self._library.swmm_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self._library.swmm_open.restype = ctypes.c_int
        self._library.swmm_start.argtypes = [ctypes.c_int]
        self._library.swmm_start.restype = ctypes.c_int
        self._library.swmm_step.argtypes = [ctypes.POINTER(ctypes.c_double)]
        self._library.swmm_step.restype = ctypes.c_int
        self._library.swmm_end.argtypes = []
        self._library.swmm_end.restype = ctypes.c_int
        self._library.swmm_report.argtypes = []
        self._library.swmm_report.restype = ctypes.c_int
        self._library.swmm_close.argtypes = []
        self._library.swmm_close.restype = ctypes.c_int
        if hasattr(self._library, "swmm_getVersion"):
            self._library.swmm_getVersion.argtypes = []
            self._library.swmm_getVersion.restype = ctypes.c_int

    @property
    def version(self) -> str | None:
        """Return the engine version as ``major.minor.patch`` when available."""

        if not hasattr(self._library, "swmm_getVersion"):
            return None
        encoded = int(self._library.swmm_getVersion())
        major = encoded // 10000
        minor = (encoded % 10000) // 1000
        patch = encoded % 1000
        return f"{major}.{minor}.{patch}"

    def run(self, inp_path: Path, rpt_path: Path, out_path: Path) -> int:
        """Execute a complete SWMM simulation in one native call."""

        return int(
            self._library.swmm_run(
                os.fsencode(inp_path),
                os.fsencode(rpt_path),
                os.fsencode(out_path),
            )
        )

    @contextmanager
    def session(self, inp_path: Path, rpt_path: Path, out_path: Path) -> Iterator["EngineSession"]:
        """Open a stepwise engine session and guarantee native cleanup."""

        session = EngineSession(self, inp_path, rpt_path, out_path)
        try:
            session.open()
            yield session
        finally:
            session.close()


class EngineSession:
    """Stateful wrapper for ``swmm_open/start/step/end/report/close``."""

    def __init__(self, engine: Engine, inp_path: Path, rpt_path: Path, out_path: Path) -> None:
        """Store the engine and the three file paths SWMM requires."""

        self.engine = engine
        self.inp_path = inp_path
        self.rpt_path = rpt_path
        self.out_path = out_path
        self._opened = False
        self._started = False
        self._closed = False

    def open(self) -> None:
        """Open the project and start a results-writing stepwise run."""

        # ``swmm_open`` separates file parsing from execution and lets Python
        # retain control between each subsequent ``swmm_step`` call.
        error = int(
            self.engine._library.swmm_open(
                os.fsencode(self.inp_path),
                os.fsencode(self.rpt_path),
                os.fsencode(self.out_path),
            )
        )
        if error != 0:
            raise EngineLoadError(f"swmm_open failed with engine error code {error}.")
        self._opened = True

        # ``1`` asks SWMM to save results so post-run vector methods can inspect
        # the actual output file after the generator completes.
        error = int(self.engine._library.swmm_start(1))
        if error != 0:
            raise EngineLoadError(f"swmm_start failed with engine error code {error}.")
        self._started = True

    def step(self) -> float:
        """Advance one routing step and return elapsed simulation days."""

        elapsed_days = ctypes.c_double(0.0)
        error = int(self.engine._library.swmm_step(ctypes.byref(elapsed_days)))
        if error != 0:
            raise EngineLoadError(f"swmm_step failed with engine error code {error}.")
        return float(elapsed_days.value)

    def close(self) -> None:
        """Finish reporting and release native resources exactly once."""

        if self._closed:
            return

        # The calls are intentionally ordered to mirror the official toolkit
        # lifecycle and to leave a readable report even after partial iteration.
        if self._started:
            self.engine._library.swmm_end()
            self.engine._library.swmm_report()
        if self._opened:
            self.engine._library.swmm_close()
        self._closed = True


class EngineLoader:
    """Lazy resolver for bundled or user-supplied native SWMM libraries."""

    def __init__(self, custom_path: str | Path | None = None) -> None:
        """Remember an optional custom path without touching native code yet."""

        self.custom_path = Path(custom_path).expanduser() if custom_path else None
        self._engine: Engine | None = None
        self._dll_directory_handles: list[object] = []

    def get(self) -> Engine:
        """Return a loaded engine, resolving and loading only on first use."""

        if self._engine is None:
            path = self.resolve_path()
            self._engine = self._load(path)
        return self._engine

    def resolve_path(self) -> Path:
        """Resolve the platform-appropriate library path."""

        if self.custom_path is not None:
            candidate = self.custom_path.resolve()
            if not candidate.exists():
                raise EngineNotFoundError(f"Custom SWMM engine not found at '{candidate}'.")
            return candidate

        system = platform.system().lower()
        machine = platform.machine().lower()
        package_root = Path(__file__).resolve().parent

        if system == "windows" and machine in {"amd64", "x86_64"}:
            candidate = package_root / "bin" / "win64" / "swmm5.dll"
        elif system == "linux" and machine in {"amd64", "x86_64"}:
            candidate = package_root / "bin" / "linux" / "libswmm5.so"
        elif system == "darwin":
            raise EngineNotFoundError(
                "No bundled macOS SWMM engine is included yet. "
                "Provide a custom engine path now; a GitHub Actions build slot is reserved for a future release."
            )
        else:
            raise EngineNotFoundError(f"No bundled SWMM engine is available for platform '{system}/{machine}'.")

        if not candidate.exists():
            raise EngineNotFoundError(f"Bundled SWMM engine not found at '{candidate}'.")
        return candidate

    def _load(self, path: Path) -> Engine:
        """Load a shared library safely and translate OS failures clearly."""

        try:
            # On Windows, dependency lookup no longer includes arbitrary folders
            # by default.  Keep the returned handle alive so ``vcomp140.dll`` can
            # be found beside the packaged SWMM DLL for the process lifetime.
            if platform.system().lower() == "windows" and hasattr(os, "add_dll_directory"):
                handle = os.add_dll_directory(str(path.parent))
                self._dll_directory_handles.append(handle)
            library = ctypes.CDLL(str(path))
        except OSError as exc:
            raise EngineLoadError(f"Failed to load SWMM engine '{path}': {exc}") from exc
        return Engine(library=library, path=path)

