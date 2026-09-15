from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator
from quality_eval.operators.image_dataset_eval.metadata import ImageDecodeEvalOperator, ImageFormatEvalOperator
from quality_eval.operators.image_dataset_eval.quality import (
    AnnotationBBoxEvalOperator,
    ImageAigcEvalOperator,
    ImageAspectRatioEvalOperator,
    ImageBlankEvalOperator,
    ImageBlurEvalOperator,
    ImageDupEvalOperator,
    ImageLosslessEvalOperator,
    ImageResolutionEvalOperator,
    ImageTextConsistencyEvalOperator,
)
from quality_eval.operators.image_dataset_eval.scoring import ImageDatasetScoreOperator
from quality_eval.utilities.evaluation import StageDependencies, StageSpec, enabled_checks, process_stages, setup_stages

IMAGE_STAGE_SPECS: list[StageSpec] = [
    ("decode", ImageDecodeEvalOperator),
    ("lossless", ImageLosslessEvalOperator),
    ("format", ImageFormatEvalOperator),
    ("resolution", ImageResolutionEvalOperator),
    ("aspect_ratio", ImageAspectRatioEvalOperator),
    ("blur", ImageBlurEvalOperator),
    ("duplicate", ImageDupEvalOperator),
    ("annotation", AnnotationBBoxEvalOperator),
    ("blank", ImageBlankEvalOperator),
    ("aigc", ImageAigcEvalOperator),
    ("image_text_consistency", ImageTextConsistencyEvalOperator),
    ("score", ImageDatasetScoreOperator),
]

IMAGE_STAGE_DEPENDENCIES: StageDependencies = {
    "lossless": ("decode",),
    "format": ("decode",),
    "resolution": ("decode",),
    "aspect_ratio": ("decode",),
    "blur": ("decode",),
    "duplicate": ("decode",),
    "annotation": ("decode",),
    "blank": ("decode",),
    "aigc": ("decode",),
    "image_text_consistency": ("decode",),
}

__all__ = ["setup_image_dataset_eval", "process_image_dataset_eval"]


def setup_image_dataset_eval(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[BaseOperator]:
    """Build internal image dataset evaluation stages.

    Business logic:
        1. Select image checks from `enabled_checks`.
        2. Instantiate internal stages with the end-to-end operator config.
        3. Run setup for stages that need dataset-level indexes.

    Args:
        items (list[dict[str, Any]]): All workflow samples.
        context (dict[str, Any]): Shared workflow context.
        config (dict[str, Any]): End-to-end operator config.

    Returns:
        list[BaseOperator]: Prepared internal stages.

    Examples:
        >>> isinstance(setup_image_dataset_eval([], {}, {}), list)
        True
    """
    selected_checks = enabled_checks(config, IMAGE_STAGE_SPECS, IMAGE_STAGE_DEPENDENCIES)

    return setup_stages(items, context, config, IMAGE_STAGE_SPECS, selected_checks)


def process_image_dataset_eval(item: dict[str, Any], stages: list[BaseOperator]) -> dict[str, Any]:
    """Run image dataset evaluation for one sample.

    Business logic:
        1. Execute all prepared internal image checks in order.
        2. Let scoring run last when enabled.
        3. Return the updated sample.

    Args:
        item (dict[str, Any]): Current sample.
        stages (list[BaseOperator]): Prepared internal stages.

    Returns:
        dict[str, Any]: Updated sample.

    Examples:
        >>> process_image_dataset_eval({"issues": [], "metrics": {}}, [])
        {'issues': [], 'metrics': {}}
    """

    return process_stages(item, stages)
