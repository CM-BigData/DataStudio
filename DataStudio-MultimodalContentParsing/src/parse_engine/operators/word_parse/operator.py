from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.word_parse.pipeline import parse_word_item
from parse_engine.runtime.registry import register_operator


@register_operator
class WordParseOperator(BaseOperator):
    operator_name = "word_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one Word sample through end-to-end parsing.

        Business logic:
            1. Run the Word parsing workflow to extract body structure and media metadata.
            2. Rebuild Markdown and chunks internally.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): Word sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> WordParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_word_item(item, self.config)
