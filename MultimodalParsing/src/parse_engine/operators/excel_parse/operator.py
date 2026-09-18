from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.excel_parse.pipeline import parse_excel_item
from parse_engine.runtime.registry import register_operator


@register_operator
class ExcelParseOperator(BaseOperator):
    operator_name = "excel_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one Excel sample through end-to-end parsing.

        Business logic:
            1. Run the Excel parsing workflow to extract workbook table structure.
            2. Rebuild Markdown internally and optionally produce chunks.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): Excel sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> ExcelParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_excel_item(item, self.config)
