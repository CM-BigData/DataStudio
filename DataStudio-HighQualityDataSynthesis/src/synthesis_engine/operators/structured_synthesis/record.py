from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.structured_synthesis import generate_structured_record

class StructuredRecordSynthesisOperator(BaseOperator):
    operator_name = "structured_record_synthesis"  # Registry name for the structured-record synthesis workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Synthesize a structured record

        Business logic:
            1. Skip non-structured task samples
            2. Generate deterministic values for each field from schema
            3. Write the JSON-style record and lineage

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Sample updated with the structured record.

        Examples:
            >>> StructuredRecordSynthesisOperator().operator_name
            'structured_record_synthesis'
        """
        if item.task_type != "structured":  # Record generation only applies to structured tasks.
            return item

        schema = item.payload.get("schema", [])
        source_index = int(item.payload.get("source_index", 0))
        item.generated["record"] = generate_structured_record(schema, item.id, source_index)
        item.generated["format"] = "json"
        item.lineage["generator"] = self.operator_name
        return item
