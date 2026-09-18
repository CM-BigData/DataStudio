from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    SYNONYM_REPLACEMENT_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class SynonymReplacementSynthesisOperator(BaseOperator):
    operator_name = "synonym_replacement_synthesis"  # Public end-to-end operator for synonym replacement synthesis.

    def setup(self) -> None:
        """Prepare internal synonym replacement stages."""
        self.stages = setup_synthesis_stages(self.config, SYNONYM_REPLACEMENT_SYNTHESIS_STAGES)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run synonym replacement synthesis end to end."""
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal synonym replacement stages."""
        teardown_synthesis_stages(getattr(self, "stages", []))
