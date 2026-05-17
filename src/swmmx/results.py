"""Helpers for reading SWMM binary output needed by result getters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np


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


@dataclass(frozen=True)
class OutputHeader:
    """Leading metadata stored at the start of a SWMM binary output file."""

    magic_number: int
    version: int
    flow_units: int
    subcatchments: int
    nodes: int
    links: int
    pollutants: int


class OutputFile:
    """Small binary reader for ordinary SWMM object-result matrices."""

    SUBCATCHMENT_VARIABLES = {
        "rainfall": 0,
        "snow_depth": 1,
        "evaporation": 2,
        "infiltration": 3,
        "runoff": 4,
        "groundwater_flow": 5,
        "groundwater_elevation": 6,
        "soil_moisture": 7,
    }
    NODE_VARIABLES = {
        "depth": 0,
        "head": 1,
        "volume": 2,
        "lateral_inflow": 3,
        "total_inflow": 4,
        "flooding": 5,
        "overflow": 5,
    }
    LINK_VARIABLES = {
        "flow": 0,
        "depth": 1,
        "velocity": 2,
        "volume": 3,
        "capacity": 4,
    }
    SYSTEM_VARIABLES = {
        "air_temperature": 0,
        "rainfall": 1,
        "snow_depth": 2,
        "evaporation": 3,
        "infiltration": 4,
        "runoff": 5,
        "dry_weather_inflow": 6,
        "groundwater_inflow": 7,
        "rdii_inflow": 8,
        "direct_inflow": 9,
        "total_lateral_inflow": 10,
        "flooding": 11,
        "outflow": 12,
        "volume": 13,
        "evaporation_loss": 14,
    }

    def __init__(self, path: str | Path) -> None:
        """Read and validate the immutable binary file payload."""

        self.path = Path(path)
        self._data = self.path.read_bytes()
        if len(self._data) < 52:
            raise ValueError(f"Output file '{self.path}' is too small to be a SWMM output file.")

        # The first seven little-endian integers contain the counts needed to
        # walk each period record without interpreting the richer input block.
        self.header = OutputHeader(*struct.unpack("<7i", self._data[:28]))
        self.summary = OutputSummary.from_file(self.path)

    @property
    def subcatchment_result_count(self) -> int:
        """Return float count per subcatchment in each period record."""

        return 8 + self.header.pollutants

    @property
    def node_result_count(self) -> int:
        """Return float count per node in each period record."""

        return 6 + self.header.pollutants

    @property
    def link_result_count(self) -> int:
        """Return float count per link in each period record."""

        return 5 + self.header.pollutants

    @property
    def period_float_count(self) -> int:
        """Return the number of 32-bit float results after each period time."""

        return (
            self.header.subcatchments * self.subcatchment_result_count
            + self.header.nodes * self.node_result_count
            + self.header.links * self.link_result_count
            + 15
        )

    @property
    def period_size(self) -> int:
        """Return bytes occupied by one period record."""

        # Each record starts with an 8-byte datetime, followed by 32-bit floats.
        return 8 + 4 * self.period_float_count

    def matrix(self, object_kind: str, variable: str, pollutant_index: int | None = None) -> np.ndarray:
        """Return one result variable as ``periods × objects`` float matrix."""

        variable_map = {
            "subcatchment": self.SUBCATCHMENT_VARIABLES,
            "node": self.NODE_VARIABLES,
            "link": self.LINK_VARIABLES,
        }
        if object_kind not in variable_map:
            raise KeyError(f"Unsupported output result '{object_kind}.{variable}'.")
        if variable == "pollutant_concentration":
            if pollutant_index is None or pollutant_index < 0 or pollutant_index >= self.header.pollutants:
                raise KeyError(f"Unsupported pollutant result index '{pollutant_index}'.")
            base_counts = {"subcatchment": 8, "node": 6, "link": 5}
            variable_index = base_counts[object_kind] + pollutant_index
        else:
            if variable not in variable_map[object_kind]:
                raise KeyError(f"Unsupported output result '{object_kind}.{variable}'.")
            variable_index = variable_map[object_kind][variable]
        if object_kind == "subcatchment":
            count = self.header.subcatchments
            result_count = self.subcatchment_result_count
            block_offset = 0
        elif object_kind == "node":
            count = self.header.nodes
            result_count = self.node_result_count
            block_offset = self.header.subcatchments * self.subcatchment_result_count
        else:
            count = self.header.links
            result_count = self.link_result_count
            block_offset = (
                self.header.subcatchments * self.subcatchment_result_count
                + self.header.nodes * self.node_result_count
            )

        matrix = np.empty((self.summary.periods, count), dtype=np.float64)
        for period_index in range(self.summary.periods):
            record_start = self.summary.output_start_position + period_index * self.period_size
            floats_start = record_start + 8
            floats_end = floats_start + 4 * self.period_float_count
            float_record = np.frombuffer(self._data[floats_start:floats_end], dtype="<f4")
            block = float_record[block_offset : block_offset + count * result_count]
            matrix[period_index, :] = block.reshape(count, result_count)[:, variable_index]
        return matrix

    def system_series(self, variable: str) -> np.ndarray:
        """Return one system-wide result variable as a one-dimensional series."""

        if variable not in self.SYSTEM_VARIABLES:
            raise KeyError(f"Unsupported output result 'system.{variable}'.")
        variable_index = self.SYSTEM_VARIABLES[variable]
        series = np.empty(self.summary.periods, dtype=np.float64)
        system_offset = (
            self.header.subcatchments * self.subcatchment_result_count
            + self.header.nodes * self.node_result_count
            + self.header.links * self.link_result_count
        )
        for period_index in range(self.summary.periods):
            record_start = self.summary.output_start_position + period_index * self.period_size
            floats_start = record_start + 8
            floats_end = floats_start + 4 * self.period_float_count
            float_record = np.frombuffer(self._data[floats_start:floats_end], dtype="<f4")
            series[period_index] = float_record[system_offset + variable_index]
        return series
