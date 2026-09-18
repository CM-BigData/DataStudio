from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator
from dedup_workflow_engine.operators.image_dedup.pipeline import run_image_dedup


class ImageDedupOperator(BaseOperator):
    operator_name = "image_dedup"  # Workflow config: public end-to-end image deduplication operator name.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Run end-to-end deduplication for an image dataset.

        Business logic:
            1. Read end-to-end deduplication config from the workflow step.
            2. Call the matching workflow function to orchestrate internal deduplication stages.
            3. Return samples with final actions.

        Args:
            items (list[dict[str, Any]]): Image samples.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Deduplicated samples.

        Examples:
            >>> ImageDedupOperator().process_dataset([], {})
            []
        """
        return run_image_dedup(items, context, self.config)
