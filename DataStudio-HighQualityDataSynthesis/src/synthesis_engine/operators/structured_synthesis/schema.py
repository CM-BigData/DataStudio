from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.structured_synthesis import validate_structured_schema

class StructuredSchemaValidateOperator(BaseOperator):
    operator_name = "structured_schema_validate"  # Registry name for the structured-schema validation workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Validate field completeness of a structured record

        Business logic:
            1. Skip non-structured task samples
            2. Traverse fields declared in schema
            3. Append issue records when fields are missing

        Args:
            item (GenerationItem): Sample to validate.

        Returns:
            GenerationItem: Sample carrying schema issues.

        Examples:
            >>> StructuredSchemaValidateOperator().operator_name
            'structured_schema_validate'
        """
        if item.task_type != "structured":  # Schema validation only applies to structured tasks.
            return item

        record = item.generated.get("record", {})
        schema = item.payload.get("schema", [])
        item.issues.extend(validate_structured_schema(record, schema))
        return item
