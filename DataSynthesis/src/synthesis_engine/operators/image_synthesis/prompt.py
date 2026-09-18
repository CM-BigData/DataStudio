from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.image_synthesis import build_negative_prompt

class NegativePromptBuildOperator(BaseOperator):
    operator_name = "negative_prompt_build"  # Registry name for the image negative-prompt workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Build the image negative prompt

        Business logic:
            1. Skip non-image task samples
            2. Read phrases to avoid from config
            3. Write the merged negative_prompt and lineage

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Sample updated with the negative prompt.

        Examples:
            >>> NegativePromptBuildOperator().operator_name
            'negative_prompt_build'
        """
        if item.task_type != "image":  # Negative prompts apply only to image-generation tasks.
            return item

        item.generated["negative_prompt"] = build_negative_prompt(self.config.get("avoid"))
        item.lineage["negative_prompt_operator"] = self.operator_name
        return item
