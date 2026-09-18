from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    TEXT_QA_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class TextQaSynthesisOperator(BaseOperator):
    operator_name = "text_qa_synthesis"  # Public end-to-end operator for document QA synthesis.

    def setup(self) -> None:
        """Prepare internal text QA synthesis stages

        Business logic:
            1. Build QA mapper and quality gate stages
            2. Run stage setup hooks
            3. Store stages for per-sample processing

        Args:
            None.

        Returns:
            None: Stores internal stages on the operator instance.

        Examples:
            >>> TextQaSynthesisOperator().operator_name
            'text_qa_synthesis'
        """
        self.stages = setup_synthesis_stages(self.config, TEXT_QA_SYNTHESIS_STAGES)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run text QA synthesis end to end."""
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal text QA synthesis stages."""
        teardown_synthesis_stages(getattr(self, "stages", []))
