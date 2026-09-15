from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.text_validation import extract_first_rewrite_text, validate_text_length


class TextFormatValidateOperator(BaseOperator):
    operator_name = "text_format_validate"  # Registry name for the text-format validation workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Validate text output format

        Business logic:
            1. Skip non-text task samples
            2. Read the minimum length setting
            3. Append a format issue when text is too short

        Args:
            item (GenerationItem): Sample to validate.

        Returns:
            GenerationItem: Sample carrying text-format issues.

        Examples:
            >>> TextFormatValidateOperator().operator_name
            'text_format_validate'
        """
        if item.task_type != "text":  # Text-format rules only apply to text tasks.
            return item

        min_length = int(self.config.get("min_length", 30))
        text = str(item.generated.get("text", ""))
        item.issues.extend(validate_text_length(text, min_length))
        return item


class SynonymRewriteValidateOperator(BaseOperator):
    operator_name = "synonym_rewrite_validate"  # Registry name for synonym-rewrite output validation.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Validate synonym rewrite output format

        Business logic:
            1. Skip non-text samples
            2. Read the first rewritten text from the configured generated output key
            3. Append a format issue when the rewritten text is shorter than the threshold

        Args:
            item (GenerationItem): Sample to validate.

        Returns:
            GenerationItem: Sample carrying synonym rewrite format issues.

        Examples:
            >>> SynonymRewriteValidateOperator().operator_name
            'synonym_rewrite_validate'
        """
        if item.task_type != "text":  # Synonym rewrite validation only applies to text tasks.
            return item

        min_length = int(self.config.get("min_length", 8))
        output_key = str(self.config.get("output_key", "synonym_rewrites"))
        text = extract_first_rewrite_text(item.generated.get(output_key, []))
        item.issues.extend(validate_text_length(text, min_length))
        return item
