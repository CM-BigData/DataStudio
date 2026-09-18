from __future__ import annotations

from typing import Any

from quality_eval.operators.audio_dataset_eval.pipeline import process_audio_dataset_eval, setup_audio_dataset_eval
from quality_eval.operators.common.base import BaseOperator
from quality_eval.runtime.registry import registry


@registry.register
class AudioDatasetEvalOperator(BaseOperator):
    operator_name: str = "audio_dataset_eval"
    operator_version: str = "1.0.0"

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        self.stages = setup_audio_dataset_eval(items, context, self.config)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        return process_audio_dataset_eval(item, self.stages)
