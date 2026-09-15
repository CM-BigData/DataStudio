from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.structured_synthesis import validate_structured_consistency


class StructuredConsistencyValidateOperator(BaseOperator):
    operator_name = "structured_consistency_validate"  # Registry name for the structured-consistency validation workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Validate the consistency of a structured record

        Business logic:
            1. Skip non-structured task samples
            2. Validate categorical values and numeric bounds
            3. Execute cross-field consistency rules declared in payload

        Args:
            item (GenerationItem): Sample to validate.

        Returns:
            GenerationItem: Sample carrying consistency issues.

        Examples:
            >>> StructuredConsistencyValidateOperator().operator_name
            'structured_consistency_validate'
        """
        if item.task_type != "structured":  # Consistency validation only applies to structured tasks.
            return item

        record = item.generated.get("record", {})
        schema = item.payload.get("schema", [])
        rules = item.payload.get("consistency_rules", [])
        item.issues.extend(validate_structured_consistency(record, schema, rules))
        return item
