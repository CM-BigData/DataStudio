from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.audio_dedup.pipeline import run_audio_dedup
from dedup_workflow_engine.operators.base import BaseOperator


class AudioDedupOperator(BaseOperator):
    operator_name = "audio_dedup"  # Workflow config: public end-to-end audio deduplication operator name.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Run end-to-end deduplication for an audio dataset.

        Business logic:
            1. Read end-to-end deduplication config from the workflow step.
            2. Call the matching workflow function to orchestrate internal deduplication stages.
            3. Return samples with final actions.

        Args:
            items (list[dict[str, Any]]): Audio samples.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Deduplicated samples.

        Examples:
            >>> AudioDedupOperator().process_dataset([], {})
            []
        """
        return run_audio_dedup(items, context, self.config)
