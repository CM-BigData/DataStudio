from __future__ import annotations

from typing import Any

from quality_eval.operators.audio_dataset_eval.quality import (
    AudioBitDepthEvalOperator,
    AudioCleanlinessEvalOperator,
    AudioDecodeEvalOperator,
    AudioDupEvalOperator,
    AudioFormatEvalOperator,
    AudioSampleRateEvalOperator,
    AudioVolumeRangeEvalOperator,
)
from quality_eval.operators.audio_dataset_eval.scoring import AudioDatasetScoreOperator
from quality_eval.operators.common.base import BaseOperator
from quality_eval.utilities.evaluation import StageDependencies, StageSpec, enabled_checks, process_stages, setup_stages


AUDIO_STAGE_SPECS: list[StageSpec] = [
    ("decode", AudioDecodeEvalOperator),
    ("format", AudioFormatEvalOperator),
    ("sample_rate", AudioSampleRateEvalOperator),
    ("bit_depth", AudioBitDepthEvalOperator),
    ("volume_range", AudioVolumeRangeEvalOperator),
    ("cleanliness", AudioCleanlinessEvalOperator),
    ("duplicate", AudioDupEvalOperator),
    ("score", AudioDatasetScoreOperator),
]

AUDIO_STAGE_DEPENDENCIES: StageDependencies = {
    "format": ("decode",),
    "sample_rate": ("decode",),
    "bit_depth": ("decode",),
    "volume_range": ("decode",),
    "cleanliness": ("decode",),
    "duplicate": ("decode",),
}


def setup_audio_dataset_eval(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[BaseOperator]:
    selected_checks = enabled_checks(config, AUDIO_STAGE_SPECS, AUDIO_STAGE_DEPENDENCIES)
    return setup_stages(items, context, config, AUDIO_STAGE_SPECS, selected_checks)


def process_audio_dataset_eval(item: dict[str, Any], stages: list[BaseOperator]) -> dict[str, Any]:
    return process_stages(item, stages)
