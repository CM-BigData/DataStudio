from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.html_parse.pipeline import parse_html_item
from parse_engine.runtime.registry import register_operator


@register_operator
class HtmlParseOperator(BaseOperator):
    operator_name = "html_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one HTML sample through end-to-end parsing.

        Business logic:
            1. Run the HTML parsing workflow to extract page body structure.
            2. Rebuild Markdown and chunks internally.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): HTML sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> HtmlParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_html_item(item, self.config)
