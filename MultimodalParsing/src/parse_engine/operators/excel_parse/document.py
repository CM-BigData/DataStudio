from __future__ import annotations

from pathlib import Path

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class ExcelStructureExtractOperator(BaseOperator):
    operator_name = "excel_structure_extract"  # Operator name: registry name for the Excel worksheet extraction step.

    def process(self, item: DataItem) -> DataItem:
        """Extract structured table information from Excel worksheets.

        Business logic:
            1. Only process samples with excel modality and return other samples unchanged.
            2. Read all sheets with pandas and preserve names, sizes, cell text, and header structure.
            3. Create heading and table artifacts for non-empty sheets and workbook-level metrics.

        Args:
            item (DataItem): Excel sample or other-modality sample in the current workflow.

        Returns:
            DataItem: Sample with Excel structure artifacts appended.

        Examples:
            >>> ExcelStructureExtractOperator({}).operator_name
            'excel_structure_extract'
        """
        if item.modality != "excel":  # Cross-modality guard: the Excel structure operator only handles xls/xlsx samples.
            return item

        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("pandas is required for Excel parsing") from exc

        path = Path(item.payload["path"])
        workbook = pd.ExcelFile(path)
        non_empty_sheet_count = 0
        table_count = 0

        for sheet_index, sheet_name in enumerate(workbook.sheet_names, start=1):  # Sheet iteration: preserve workbook order and stable sheet indexes.
            sheet_frame = workbook.parse(sheet_name=sheet_name, dtype=object, keep_default_na=False)
            rows = self._dataframe_to_rows(sheet_frame)
            row_count = max(len(rows) - 1, 0) if rows else 0
            column_count = max((len(row) for row in rows), default=0)

            if not self._has_sheet_content(rows):  # Empty sheet: record workbook diagnostics instead of producing an empty table artifact.
                item.issues.append(
                    {
                        "type": "empty_excel_sheet",
                        "sheet_name": sheet_name,
                        "sheet_index": sheet_index,
                    }
                )
                continue

            non_empty_sheet_count += 1
            table_count += 1
            table_text = "\n".join(" | ".join(row) for row in rows)
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_sheet_{sheet_index}_heading",
                    type="heading",
                    text=sheet_name,
                    data={"sheet_name": sheet_name, "sheet_index": sheet_index, "heading_level": 3},
                    source_trace=SourceTrace(file=str(path), operator=self.operator_name),
                )
            )
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_sheet_{sheet_index}_table",
                    type="table",
                    text=table_text,
                    data={
                        "sheet_name": sheet_name,
                        "sheet_index": sheet_index,
                        "rows": rows,
                        "row_count": row_count,
                        "column_count": column_count,
                        "header_only": row_count == 0,
                    },
                    source_trace=SourceTrace(file=str(path), operator=self.operator_name),
                )
            )
        item.metrics["sheet_count"] = len(workbook.sheet_names)
        item.metrics["non_empty_sheet_count"] = non_empty_sheet_count
        item.metrics["table_count"] = table_count
        item.action = "parsed" if item.artifacts else "failed"
        if item.action == "failed":  # No usable worksheets: keep failure information for empty or unreadable workbooks.
            item.issues.append({"type": "empty_excel_workbook", "message": "Excel extraction produced no usable sheet content"})
        return item

    def _dataframe_to_rows(self, frame: object) -> list[list[str]]:
        """Normalize a DataFrame into a two-dimensional string array for Markdown rebuild.

        Business logic:
            1. Read column names as the first row to preserve worksheet structure.
            2. Convert each cell to cleaned text, removing line breaks and normalizing empty values.
            3. Return header and data rows for reuse by table artifacts and Markdown rebuild.

        Args:
            frame (object): Worksheet DataFrame read by pandas.

        Returns:
            list[list[str]]: Two-dimensional string array with headers as the first row.

        Examples:
            >>> ExcelStructureExtractOperator({})._normalize_cell("a\\n b")
            'a b'
        """
        columns = [self._normalize_cell(column) for column in getattr(frame, "columns", [])]
        rows: list[list[str]] = [columns] if columns else []
        for row in getattr(frame, "itertuples")(index=False, name=None):  # Tuple rows: preserve original row order and width.
            rows.append([self._normalize_cell(cell) for cell in row])
        return rows

    def _has_sheet_content(self, rows: list[list[str]]) -> bool:
        """Return whether a worksheet contains consumable content.

        Business logic:
            1. Treat worksheets with no rows as empty.
            2. Treat any non-empty header or data cell as consumable content.
            3. Distinguish empty sheets from header-only or data-only minimal cases.

        Args:
            rows (list[list[str]]): Two-dimensional worksheet text array.

        Returns:
            bool: Whether at least one non-empty cell exists.

        Examples:
            >>> ExcelStructureExtractOperator({})._has_sheet_content([["A"], [""]])
            True
        """
        return any(cell.strip() for row in rows for cell in row)

    def _normalize_cell(self, value: object) -> str:
        """Normalize a cell value to plain text.

        Business logic:
            1. Normalize empty values to empty strings to avoid NaN text in artifacts.
            2. Convert non-string values to strings for numbers, booleans, and date objects.
            3. Remove line breaks and edge whitespace for stable Markdown and chunk input.

        Args:
            value (object): Raw cell value.

        Returns:
            str: Cleaned cell text.

        Examples:
            >>> ExcelStructureExtractOperator({})._normalize_cell(None)
            ''
        """
        if value is None:
            return ""
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        return "" if text.lower() == "nan" else text
