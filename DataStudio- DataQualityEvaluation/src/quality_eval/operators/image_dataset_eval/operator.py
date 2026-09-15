from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator
from quality_eval.operators.image_dataset_eval.pipeline import process_image_dataset_eval, setup_image_dataset_eval
from quality_eval.runtime.registry import registry


@registry.register
class ImageDatasetEvalOperator(BaseOperator):
    operator_name: str = "image_dataset_eval"  # Registry name for image dataset end-to-end evaluation.
    operator_version: str = "1.0.0"  # Version marker used by workflow trace logs.

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Prepare the internal image evaluation workflow.

        Business logic:
            1. Read end-to-end operator config.
            2. Build enabled internal image evaluation stages.
            3. Store stages for per-sample processing.

        Args:
            items (list[dict[str, Any]]): All workflow samples.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            None: Stores prepared stages on the operator instance.

        Examples:
            >>> op = ImageDatasetEvalOperator({})
            >>> op.setup([], {})
            >>> isinstance(op.stages, list)
            True
        """
        self.stages = setup_image_dataset_eval(items, context, self.config)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Run image dataset end-to-end evaluation.

        Business logic:
            1. Read the prepared internal stages.
            2. Execute image checks and scoring in order.
            3. Return the updated sample.

        Args:
            item (dict[str, Any]): Current sample.

        Returns:
            dict[str, Any]: Updated sample.

        Examples:
            >>> ImageDatasetEvalOperator({}).operator_name
            'image_dataset_eval'
        """
        return process_image_dataset_eval(item, self.stages)
