"""Helpers for reading the small slice of SWMM output needed in ``0.0.1``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct


@dataclass(frozen=True)
class OutputSummary:
    """Trailer values exposed by a SWMM binary ``.out`` file."""

    id_start_position: int
    input_start_position: int
    output_start_position: int
    periods: int
    error_code: int
    magic_number: int

    @classmethod
    def from_file(cls, path: str | Path) -> "OutputSummary":
        """Read the fixed six-integer trailer from a SWMM binary output file."""

        output_path = Path(path)
        data = output_path.read_bytes()
        if len(data) < 24:
            raise ValueError(f"Output file '{output_path}' is too small to contain a SWMM trailer.")

        # SWMM writes six little-endian 32-bit integers at the end of the file.
        values = struct.unpack("<6i", data[-24:])
        return cls(*values)

