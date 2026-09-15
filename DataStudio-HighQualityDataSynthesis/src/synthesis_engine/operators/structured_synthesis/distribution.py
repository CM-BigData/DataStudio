from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.structured_synthesis import build_distribution_profile

class StructuredDistributionAnalyzeOperator(BaseOperator):
    operator_name = "structured_distribution_analyze"  # Registry name for the structured field-distribution analysis workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Analyze structured field-distribution configuration

        Business logic:
            1. Skip non-structured task samples
            2. Extract categorical and numeric field config from schema
            3. Write the distribution profile into sample metrics

        Args:
            item (GenerationItem): Sample to analyze.

        Returns:
            GenerationItem: Sample updated with the distribution profile.

        Examples:
            >>> StructuredDistributionAnalyzeOperator().operator_name
            'structured_distribution_analyze'
        """
        if item.task_type != "structured":  # Distribution profiling only applies to structured tasks.
            return item

        schema = item.payload.get("schema", [])
        item.metrics["distribution_profile"] = build_distribution_profile(schema)
        return item
