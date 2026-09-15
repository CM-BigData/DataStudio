from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator
from dedup_workflow_engine.operators.text_dedup.pipeline import run_text_dedup


class TextDedupOperator(BaseOperator):
    operator_name = "text_dedup"  # Workflow config: public end-to-end text deduplication operator name.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Run end-to-end deduplication for a text dataset.

        Business logic:
            1. Read end-to-end deduplication config from the workflow step.
            2. Call the matching workflow function to orchestrate internal deduplication stages.
            3. Return samples with final actions.

        Args:
            items (list[dict[str, Any]]): Text samples.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Deduplicated samples.

        Examples:
            >>> TextDedupOperator().process_dataset([], {})
            []
        """
        return run_text_dedup(items, context, self.config)
