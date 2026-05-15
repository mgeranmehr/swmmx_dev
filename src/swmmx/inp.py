"""Parsing and writing support for SWMM ``.inp`` files.

The parser deliberately keeps raw lines alongside structured helpers.  This lets
the package modify known values while preserving comments, unsupported sections,
and the author's original section order whenever possible.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import shlex
from typing import Iterable


SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")


def _strip_inline_comment(line: str) -> str:
    """Return the data part of a line before a semicolon comment marker."""

    # SWMM comments begin with ``;``.  Splitting only once preserves any text
    # after the first marker for the raw-line writer while keeping tokenization
    # simple for the structured parser.
    return line.split(";", 1)[0].rstrip()


def tokenize_data_line(line: str) -> list[str]:
    """Tokenize one non-comment SWMM data line while respecting quotes."""

    # ``shlex`` handles paths and labels wrapped in quotes better than a naïve
    # whitespace split, which matters in sections such as ``[FILES]``.
    data = _strip_inline_comment(line).strip()
    if not data:
        return []
    return shlex.split(data, posix=True)


@dataclass
class InpSection:
    """One input-file section plus its original raw lines."""

    name: str
    header: str
    lines: list[str] = field(default_factory=list)
    modified: bool = False

    @property
    def key(self) -> str:
        """Return the case-insensitive lookup key used by the document."""

        return self.name.upper()

    def data_rows(self) -> list[list[str]]:
        """Return tokenized rows while skipping comments and blank lines."""

        rows: list[list[str]] = []
        for line in self.lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = tokenize_data_line(line)
            if tokens:
                rows.append(tokens)
        return rows


@dataclass
class InpDocument:
    """A preserving representation of a SWMM input document."""

    preamble: list[str] = field(default_factory=list)
    sections: "OrderedDict[str, InpSection]" = field(default_factory=OrderedDict)
    _options: "OrderedDict[str, str]" | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_path(cls, path: str | Path) -> "InpDocument":
        """Read and parse a SWMM input file from disk."""

        # ``utf-8-sig`` gracefully accepts files saved with or without a BOM.
        text = Path(path).read_text(encoding="utf-8-sig")
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> "InpDocument":
        """Parse raw input text into preserved sections."""

        document = cls()
        current: InpSection | None = None

        # ``splitlines`` drops the line endings intentionally; ``to_text`` later
        # re-emits a normalized trailing newline while preserving line content.
        for line in text.splitlines():
            match = SECTION_RE.match(line)
            if match:
                name = match.group("name").strip()
                current = InpSection(name=name, header=line)
                document.sections[current.key] = current
                continue

            if current is None:
                document.preamble.append(line)
            else:
                current.lines.append(line)

        return document

    @classmethod
    def from_template(cls, flow_units: str) -> "InpDocument":
        """Create a minimal, valid starter document for a new model."""

        # Fixed seed dates keep tests reproducible and give users a concrete
        # model that can immediately answer pre-run time queries.
        template = f"""[TITLE]
;;Project Title/Notes
 swmmx model

[OPTIONS]
;;Option             Value
FLOW_UNITS           {flow_units}
INFILTRATION         HORTON
FLOW_ROUTING         DYNWAVE
START_DATE           01/01/2000
START_TIME           00:00:00
REPORT_START_DATE    01/01/2000
REPORT_START_TIME    00:00:00
END_DATE             01/01/2000
END_TIME             01:00:00
REPORT_STEP          00:05:00
ROUTING_STEP         0:00:30

[REPORT]
INPUT               NO
CONTROLS            NO
SUBCATCHMENTS       ALL
NODES               ALL
LINKS               ALL
"""
        return cls.from_text(template)

    def copy(self) -> "InpDocument":
        """Return a structurally independent copy of this document."""

        # Serializing through text is intentionally conservative: it preserves
        # the same public document semantics without sharing mutable containers.
        return self.from_text(self.to_text())

    def has_section(self, name: str) -> bool:
        """Return whether the document contains a named section."""

        return name.upper() in self.sections

    def section(self, name: str) -> InpSection | None:
        """Return a section by case-insensitive name if present."""

        return self.sections.get(name.upper())

    def rows(self, name: str) -> list[list[str]]:
        """Return tokenized rows for a section, or an empty list if absent."""

        section = self.section(name)
        return section.data_rows() if section else []

    def options(self) -> "OrderedDict[str, str]":
        """Return parsed options as an ordered, mutable mapping."""

        if self._options is None:
            parsed: "OrderedDict[str, str]" = OrderedDict()
            for row in self.rows("OPTIONS"):
                if len(row) >= 2:
                    key = row[0].upper()
                    value = " ".join(row[1:])
                    parsed[key] = value
            self._options = parsed
        return self._options

    def get_option(self, key: str, default: str | None = None) -> str | None:
        """Return one option value using a case-insensitive key."""

        return self.options().get(key.upper(), default)

    def set_option(self, key: str, value: str) -> None:
        """Set or add one option and mark the section for re-rendering."""

        # Mutating the cached mapping is enough; rendering consults this cache.
        self.options()[key.upper()] = str(value)

        # Ensure a newly-created document still gets a real ``[OPTIONS]`` block.
        section = self.section("OPTIONS")
        if section is None:
            section = InpSection(name="OPTIONS", header="[OPTIONS]")
            self.sections[section.key] = section
        section.modified = True

    def delete_option(self, key: str) -> None:
        """Delete one option and mark the section for re-rendering."""

        del self.options()[key.upper()]
        section = self.section("OPTIONS")
        if section is not None:
            section.modified = True

    def to_text(self) -> str:
        """Render the current document back to valid SWMM input text."""

        emitted: list[str] = []
        emitted.extend(self.preamble)

        for key, section in self.sections.items():
            emitted.append(section.header)
            if key == "OPTIONS" and section.modified:
                emitted.extend(self._render_options(section))
            else:
                emitted.extend(section.lines)

        # SWMM accepts normalized LF endings; the final newline keeps command
        # line tools and diff viewers pleasantly conventional.
        return "\n".join(emitted).rstrip() + "\n"

    def _render_options(self, section: InpSection) -> list[str]:
        """Render options while preserving comment and blank rows."""

        rendered: list[str] = []
        emitted_keys: set[str] = set()

        for line in section.lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith(";"):
                rendered.append(line)
                continue

            tokens = tokenize_data_line(line)
            if not tokens:
                rendered.append(line)
                continue

            key = tokens[0].upper()
            if key in self.options():
                rendered.append(f"{key:<20} {self.options()[key]}")
                emitted_keys.add(key)
            # Deleted options are simply omitted from the regenerated block.

        # New options that did not exist in the original file are appended in
        # insertion order, which keeps mutations deterministic.
        for key, value in self.options().items():
            if key not in emitted_keys:
                rendered.append(f"{key:<20} {value}")

        return rendered

    def datetimes(self) -> tuple[datetime, datetime, datetime]:
        """Return start, report-start, and end datetimes from `[OPTIONS]`."""

        # The SWMM input format stores date and time separately.  Report-start
        # values are optional, so they fall back to simulation start when absent.
        start_date = self.get_option("START_DATE")
        start_time = self.get_option("START_TIME", "00:00:00")
        report_date = self.get_option("REPORT_START_DATE", start_date)
        report_time = self.get_option("REPORT_START_TIME", start_time)
        end_date = self.get_option("END_DATE")
        end_time = self.get_option("END_TIME", "00:00:00")

        if not start_date or not report_date or not end_date:
            raise ValueError("START_DATE, REPORT_START_DATE, and END_DATE are required for time vectors.")

        def combine(date_text: str, time_text: str | None) -> datetime:
            # SWMM dates are conventionally month/day/year.  Seconds are always
            # accepted in this first release to keep parsing strict and clear.
            return datetime.strptime(f"{date_text} {time_text or '00:00:00'}", "%m/%d/%Y %H:%M:%S")

        return combine(start_date, start_time), combine(report_date, report_time), combine(end_date, end_time)

