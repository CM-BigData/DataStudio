from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.synthesis import (
    TABLE_QA_SYNTHESIS_STAGES,
    process_synthesis_item,
    setup_synthesis_stages,
    teardown_synthesis_stages,
)
from synthesis_engine.runtime.registry import register_operator


@register_operator
class TableQaSynthesisOperator(BaseOperator):
    operator_name = "table_qa_synthesis"  # Public end-to-end operator for table QA synthesis.

    def setup(self) -> None:
        """Prepare internal table QA synthesis stages."""
        self.stages = setup_synthesis_stages(self.config, TABLE_QA_SYNTHESIS_STAGES)

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run table QA synthesis end to end."""
        return process_synthesis_item(item, self.stages)

    def teardown(self) -> None:
        """Release internal table QA synthesis stages."""
        teardown_synthesis_stages(getattr(self, "stages", []))
