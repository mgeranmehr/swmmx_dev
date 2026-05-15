"""Public ``m.export`` namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .csv import export_csv
from .excel import export_excel
from .gis import export_gis

if TYPE_CHECKING:
    from ..api import SWMMModel


class ExportAccessor:
    """Namespace exposed as ``m.export``."""

    def __init__(self, model: "SWMMModel") -> None:
        """Bind export helpers to one model instance."""

        self._model = model

    def __dir__(self) -> list[str]:
        """Expose discoverable public export formats."""

        return ["csv", "excel", "gis"]

    def gis(
        self,
        path=None,
        file_name=None,
        elements="all",
        time_step=-1,
        include_results=True,
        include_parameters=True,
        include_derived=True,
        strict_results=False,
        crs=None,
        driver="ESRI Shapefile",
        overwrite=False,
        zip_output=False,
        subcatchment_geometry="polygon",
        strict_geometry=False,
        non_spatial=False,
    ):
        """Export spatial SWMM layers to GIS files.

        Parameters
        ----------
        path:
            Optional export directory.  If omitted, exports go beside the model
            ``.inp`` file, or to the current working directory for unsaved
            models.  For ``driver="GPKG"``, ``path`` may also be a ``.gpkg``
            file path.
        file_name:
            Optional filename prefix for shapefiles or GeoPackage filename.
            If omitted, the model stem is used when available.
        elements:
            ``"all"``, one supported element/group name, or a list of names.
            GIS export writes only spatial layers by default.
        time_step:
            Selected result snapshot; ``-1`` means the last available result
            time step.  Exact timestamp strings are also accepted.
        include_results, include_parameters, include_derived:
            Control whether selected result values, static inputs, and simple
            derived columns are attached to GIS attributes.
        strict_results:
            If ``True``, missing results raise ``ModelNotRunError``.  Otherwise
            parameters export with a warning when no run results exist.
        crs, driver, overwrite, zip_output:
            GIS output controls.  Supported drivers are ``"ESRI Shapefile"``
            and ``"GPKG"``.
        subcatchment_geometry:
            ``"polygon"`` (default), ``"centroid"``, or ``"both"``.
        strict_geometry:
            If ``True``, missing geometry raises ``ExportGeometryError``;
            otherwise invalid features are skipped with warnings.

        Examples
        --------
        >>> m.export.gis()
        >>> m.export.gis(
        ...     path="exports/gis",
        ...     elements=["nodes", "links", "subcatchments"],
        ... )

        Returns
        -------
        dict
            Mapping from exported layer name to output path.

        Notes
        -----
        GIS export requires optional ``geopandas`` and ``shapely`` packages.
        Install them with ``pip install geopandas shapely``.  Shapefile field
        names are shortened safely, with a JSON field-name map written beside
        the layers.
        """

        return export_gis(
            self._model,
            path=path,
            file_name=file_name,
            elements=elements,
            time_step=time_step,
            include_results=include_results,
            include_parameters=include_parameters,
            include_derived=include_derived,
            strict_results=strict_results,
            crs=crs,
            driver=driver,
            overwrite=overwrite,
            zip_output=zip_output,
            subcatchment_geometry=subcatchment_geometry,
            strict_geometry=strict_geometry,
            non_spatial=non_spatial,
        )

    def csv(
        self,
        path=None,
        file_name=None,
        elements="all",
        time_step=-1,
        include_results=True,
        include_parameters=True,
        include_derived=True,
        strict_results=False,
        overwrite=False,
        index=False,
        encoding="utf-8",
    ):
        """Export selected SWMM tables to one CSV file per element type.

        Parameters
        ----------
        path, file_name:
            Optional output directory and filename/prefix.  With no ``path``,
            the model folder is used when available, otherwise the current
            working directory.
        elements:
            ``"all"``, one supported element/group name, or a list of names.
        time_step:
            Selected result snapshot; ``-1`` means the final available result
            time step.
        include_results, include_parameters, include_derived:
            Control result, static parameter, and simple derived-column export.
        strict_results:
            If ``True``, requesting results before a run raises
            ``ModelNotRunError``.  Otherwise CSV export proceeds with a warning
            and parameter-only tables.
        overwrite, index, encoding:
            File-writing controls.  UTF-8 and ``index=False`` are the defaults.

        Examples
        --------
        >>> m.export.csv(
        ...     path="exports/csv",
        ...     elements=["conduits", "junctions"],
        ...     time_step=-1,
        ... )

        Returns
        -------
        dict
            Mapping from exported element name to CSV path.

        Notes
        -----
        Curves, time series, and control rules are exported as ordinary tables.
        When selected results are attached, tables include
        ``result_time_step`` and ``result_timestamp`` columns.
        """

        return export_csv(
            self._model,
            path=path,
            file_name=file_name,
            elements=elements,
            time_step=time_step,
            include_results=include_results,
            include_parameters=include_parameters,
            include_derived=include_derived,
            strict_results=strict_results,
            overwrite=overwrite,
            index=index,
            encoding=encoding,
        )

    def excel(
        self,
        path=None,
        file_name=None,
        elements="all",
        time_step=-1,
        include_results=True,
        include_parameters=True,
        include_derived=True,
        strict_results=False,
        overwrite=False,
        engine="openpyxl",
        freeze_panes=True,
        auto_filter=True,
    ):
        """Export selected SWMM tables to one multi-sheet Excel workbook.

        Parameters
        ----------
        path, file_name:
            Optional output directory and workbook name.  Workbooks must end in
            ``.xlsx``; default names use the model stem when available.
        elements:
            ``"all"``, one supported element/group name, or a list of names.
        time_step:
            Selected result snapshot; ``-1`` means the last available result
            time step.
        include_results, include_parameters, include_derived:
            Control result, parameter, and derived-column export.
        strict_results:
            If ``True``, missing requested results raise ``ModelNotRunError``.
        overwrite, engine, freeze_panes, auto_filter:
            Workbook-writing controls.  The default engine is ``openpyxl``.

        Examples
        --------
        >>> m.export.excel(
        ...     path="exports",
        ...     file_name="model_export.xlsx",
        ...     elements="all",
        ... )

        Returns
        -------
        pathlib.Path
            Path to the written workbook.

        Notes
        -----
        Excel export requires optional ``openpyxl``.  Each selected element
        table is written to its own sanitized sheet, with the top row frozen and
        filters enabled by default.
        """

        return export_excel(
            self._model,
            path=path,
            file_name=file_name,
            elements=elements,
            time_step=time_step,
            include_results=include_results,
            include_parameters=include_parameters,
            include_derived=include_derived,
            strict_results=strict_results,
            overwrite=overwrite,
            engine=engine,
            freeze_panes=freeze_panes,
            auto_filter=auto_filter,
        )

