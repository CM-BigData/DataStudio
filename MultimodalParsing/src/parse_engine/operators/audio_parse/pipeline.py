from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import ParseQualityAssessOperator
from parse_engine.operators.audio_parse.asr.operator import AudioAsrOperator
from parse_engine.operators.audio_parse.metadata import AudioInfoExtractOperator
from parse_engine.utilities.pipeline import run_stages, stage_config


def parse_audio_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end audio parsing pipeline for one sample.

    Business logic:
        1. Extract audio metadata.
        2. Run ASR with the configured backend.
        3. Assess parsing quality and set the final action.

    Args:
        item (DataItem): Audio sample or non-audio sample passed by the executor.
        config (dict): End-to-end operator configuration.

    Returns:
        DataItem: Sample after audio parsing pipeline stages.

    Examples:
        >>> parse_audio_item(DataItem(id="x", modality="unknown", source={"path": "x"}, payload={}), {}).id
        'x'
    """
    return run_stages(
        item,
        [
            AudioInfoExtractOperator(stage_config(config, "audio_info")),
            AudioAsrOperator(stage_config(config, "asr")),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
