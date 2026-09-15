from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator
from quality_eval.operators.text_dataset_eval.pipeline import process_text_dataset_eval, setup_text_dataset_eval
from quality_eval.runtime.registry import registry


@registry.register
class TextDatasetEvalOperator(BaseOperator):
    operator_name: str = "text_dataset_eval"  # Registry name for text dataset end-to-end evaluation.
    operator_version: str = "1.0.0"  # Version marker used by workflow trace logs.

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Prepare the internal text evaluation workflow.

        Business logic:
            1. Read end-to-end operator config.
            2. Build enabled internal text evaluation stages.
            3. Store stages for per-sample processing.

        Args:
            items (list[dict[str, Any]]): All workflow samples.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            None: Stores prepared stages on the operator instance.

        Examples:
            >>> op = TextDatasetEvalOperator({})
            >>> op.setup([], {})
            >>> isinstance(op.stages, list)
            True
        """
        self.stages = setup_text_dataset_eval(items, context, self.config)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Run text dataset end-to-end evaluation.

        Business logic:
            1. Read the prepared internal stages.
            2. Execute text checks and scoring in order.
            3. Return the updated sample.

        Args:
            item (dict[str, Any]): Current sample.

        Returns:
            dict[str, Any]: Updated sample.

        Examples:
            >>> TextDatasetEvalOperator({}).operator_name
            'text_dataset_eval'
        """
        return process_text_dataset_eval(item, self.stages)
