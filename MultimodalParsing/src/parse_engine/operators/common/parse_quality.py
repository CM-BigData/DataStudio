from __future__ import annotations

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class ParseQualityAssessOperator(BaseOperator):
    operator_name = "parse_quality_assess"  # Operator name: registry name for the parse quality assessment step.

    def process(self, item: DataItem) -> DataItem:
        """Assess the quality of parsing artifacts for a single sample.

        Business logic:
            1. Count the number of artifacts and the total text length.
            2. For samples not already failed, set the action to parsed or failed based on whether artifacts exist.
            3. Add a no_artifacts issue when there are no artifacts and no existing issues.

        Args:
            item: Data item already processed by one or more parsing operators.

        Returns:
            DataItem: Data item with quality metrics and final action written.

        Examples:
            >>> ParseQualityAssessOperator({}).operator_name
            'parse_quality_assess'"""
        text_length = sum(len(artifact.text or "") for artifact in item.artifacts)
        item.metrics["artifact_count"] = len(item.artifacts)
        item.metrics["text_length"] = text_length
        if item.action != "failed":  # Non-failed sample: refresh the final parsing state based on artifact presence.
            item.action = "parsed" if item.artifacts else "failed"
        if item.action == "failed" and not item.issues:  # Failed without a reason: add a default quality issue to make reports easier to explain.
            item.issues.append({"type": "no_artifacts", "message": "No parsing artifacts were generated"})
        return item
