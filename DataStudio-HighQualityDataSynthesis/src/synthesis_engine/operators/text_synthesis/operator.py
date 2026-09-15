from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    TEXT_SYNTHESIS_STAGES,
    TEXT_TEMPLATE_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class TextSynthesisOperator(BaseOperator):
    operator_name = "text_synthesis"  # Public end-to-end operator for general text synthesis.

    def setup(self) -> None:
        """Prepare internal text synthesis stages

        Business logic:
            1. Read profile from config
            2. Use template profile for offline local generation when requested
            3. Build and setup internal generation, validation, diversity, safety, and quality stages

        Args:
            None.

        Returns:
            None: Stores internal stages on the operator instance.

        Examples:
            >>> op = TextSynthesisOperator({"profile": "template"})
            >>> op.operator_name
            'text_synthesis'
        """
        specs = TEXT_TEMPLATE_SYNTHESIS_STAGES if self.config.get("profile") == "template" else TEXT_SYNTHESIS_STAGES
        self.stages = setup_synthesis_stages(self.config, specs)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run general text synthesis end to end

        Business logic:
            1. Pass the sample through internal text generation
            2. Run validation and quality checks
            3. Return the final sample action and generated fields

        Args:
            item (GenerationItem): Current synthesis sample.

        Returns:
            GenerationItem: Processed synthesis sample.

        Examples:
            >>> TextSynthesisOperator({"profile": "template"}).operator_name
            'text_synthesis'
        """
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal text synthesis stages

        Business logic:
            1. Read prepared stages
            2. Call teardown on each stage
            3. Leave no persistent resources open

        Args:
            None.

        Returns:
            None: Cleanup has no business return.

        Examples:
            >>> callable(TextSynthesisOperator().teardown)
            True
        """
        teardown_synthesis_stages(getattr(self, "stages", []))
