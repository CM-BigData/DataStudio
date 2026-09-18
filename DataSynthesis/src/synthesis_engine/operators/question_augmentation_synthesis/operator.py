from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    QUESTION_AUGMENTATION_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class QuestionAugmentationSynthesisOperator(BaseOperator):
    operator_name = "question_augmentation_synthesis"  # Public end-to-end operator for question augmentation synthesis.

    def setup(self) -> None:
        """Prepare internal question augmentation stages."""
        self.stages = setup_synthesis_stages(self.config, QUESTION_AUGMENTATION_SYNTHESIS_STAGES)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run question augmentation synthesis end to end."""
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal question augmentation stages."""
        teardown_synthesis_stages(getattr(self, "stages", []))
