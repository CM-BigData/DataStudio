from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    STRUCTURED_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class StructuredSynthesisOperator(BaseOperator):
    operator_name = "structured_synthesis"  # Public end-to-end operator for structured data synthesis.

    def setup(self) -> None:
        """Prepare internal structured synthesis stages."""
        self.stages = setup_synthesis_stages(self.config, STRUCTURED_SYNTHESIS_STAGES)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run structured data synthesis end to end."""
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal structured synthesis stages."""
        teardown_synthesis_stages(getattr(self, "stages", []))
