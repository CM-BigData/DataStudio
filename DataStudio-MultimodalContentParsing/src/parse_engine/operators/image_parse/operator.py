from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.image_parse.pipeline import parse_image_item
from parse_engine.runtime.registry import register_operator


@register_operator
class ImageParseOperator(BaseOperator):
    operator_name = "image_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one image sample through end-to-end parsing.

        Business logic:
            1. Run the image parsing workflow to inspect basic image quality.
            2. Execute OCR internally.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): Image sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> ImageParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_image_item(item, self.config)
