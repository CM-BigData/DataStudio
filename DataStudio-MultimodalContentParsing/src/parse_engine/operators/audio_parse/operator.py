from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.operators.audio_parse.pipeline import parse_audio_item
from parse_engine.runtime.registry import register_operator


@register_operator
class AudioParseOperator(BaseOperator):
    operator_name = "audio_parse"

    def process(self, item: DataItem) -> DataItem:
        """Process one audio sample through end-to-end parsing.

        Business logic:
            1. Run the audio parsing workflow to extract audio metadata.
            2. Execute the internal ASR stage according to configuration.
            3. Finish parse quality assessment and return the standard DataItem.

        Args:
            item (DataItem): Audio sample to parse.

        Returns:
            DataItem: Parsed standard sample.

        Examples:
            >>> AudioParseOperator().process(DataItem(id="x", source={}, payload={})).id
            'x'
        """
        return parse_audio_item(item, self.config)
