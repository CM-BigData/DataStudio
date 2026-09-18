from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator



class TextTemplateSynthesisOperator(BaseOperator):
    operator_name = "text_template_synthesis"  # Registry name for the text-template synthesis workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Synthesize a text sample from a template

        Business logic:
            1. Skip non-text task samples
            2. Read topic, audience, and style parameters
            3. Render the template and write generated text

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Sample updated with generated text.

        Examples:
            >>> TextTemplateSynthesisOperator().operator_name
            'text_template_synthesis'
        """
        if item.task_type != "text":  # Text templates only handle text tasks.
            return item

        topic = item.payload.get("topic", item.prompt)
        audience = item.payload.get("audience", "data engineer")
        style = item.payload.get("style", "concise")
        template = self.config.get(
            "template",
            "For {audience}, {topic} should be handled with clear inputs, quality checks, and traceable outputs.",
        )
        text = template.format(topic=topic, audience=audience, style=style, prompt=item.prompt)
        item.generated["text"] = text
        item.generated["format"] = "plain_text"
        item.lineage["generator"] = self.operator_name
        return item
