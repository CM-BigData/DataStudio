from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.pdf_parse.pipeline import parse_pdf_item
from parse_engine.runtime.registry import register_operator


@register_operator
class PdfParseOperator(BaseOperator):
    operator_name = "pdf_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one PDF sample through end-to-end parsing.

        Business logic:
            1. Run the PDF parsing workflow to extract text and layout structure.
            2. Rebuild Markdown internally.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): PDF sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> PdfParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_pdf_item(item, self.config)
