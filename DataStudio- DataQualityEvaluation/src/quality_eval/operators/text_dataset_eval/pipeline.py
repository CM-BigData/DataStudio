from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator
from quality_eval.operators.text_dataset_eval.consecutive_punctuation import TextConsecutivePunctuationEvalOperator
from quality_eval.operators.text_dataset_eval.language import UnicodeQualityEvalOperator
from quality_eval.operators.text_dataset_eval.length import DatasetSchemaCheckOperator, FieldCompletenessOperator, TextLengthEvalOperator
from quality_eval.operators.text_dataset_eval.quality import (
    LabelCompletenessOperator,
    LowQualityTextEvalOperator,
    TextDupRateOperator,
    TextPunctuationPairingEvalOperator,
)
from quality_eval.operators.text_dataset_eval.scoring import TextDatasetScoreOperator
from quality_eval.operators.text_dataset_eval.special_characters import TextSpecialCharactersEvalOperator
from quality_eval.utilities.evaluation import StageDependencies, StageSpec, enabled_checks, process_stages, setup_stages

TEXT_STAGE_SPECS: list[StageSpec] = [
    ("schema", DatasetSchemaCheckOperator),
    ("completeness", FieldCompletenessOperator),
    ("length", TextLengthEvalOperator),
    ("unicode", UnicodeQualityEvalOperator),
    ("low_quality", LowQualityTextEvalOperator),
    ("duplicate", TextDupRateOperator),
    ("label", LabelCompletenessOperator),
    ("special_characters", TextSpecialCharactersEvalOperator),
    ("consecutive_punctuation", TextConsecutivePunctuationEvalOperator),
    ("punctuation_pairing", TextPunctuationPairingEvalOperator),
    ("score", TextDatasetScoreOperator),
]

TEXT_STAGE_DEPENDENCIES: StageDependencies = {}

__all__ = ["setup_text_dataset_eval", "process_text_dataset_eval"]


def setup_text_dataset_eval(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[BaseOperator]:
    """Build internal text dataset evaluation stages.

    Business logic:
        1. Select text checks from `enabled_checks`.
        2. Instantiate internal stages with the end-to-end operator config.
        3. Run setup for stages that need dataset-level indexes.

    Args:
        items (list[dict[str, Any]]): All workflow samples.
        context (dict[str, Any]): Shared workflow context.
        config (dict[str, Any]): End-to-end operator config.

    Returns:
        list[BaseOperator]: Prepared internal stages.

    Examples:
        >>> isinstance(setup_text_dataset_eval([], {}, {}), list)
        True
    """
    selected_checks = enabled_checks(config, TEXT_STAGE_SPECS, TEXT_STAGE_DEPENDENCIES)

    return setup_stages(items, context, config, TEXT_STAGE_SPECS, selected_checks)


def process_text_dataset_eval(item: dict[str, Any], stages: list[BaseOperator]) -> dict[str, Any]:
    """Run text dataset evaluation for one sample.

    Business logic:
        1. Execute all prepared internal text checks in order.
        2. Let scoring run last when enabled.
        3. Return the updated sample.

    Args:
        item (dict[str, Any]): Current sample.
        stages (list[BaseOperator]): Prepared internal stages.

    Returns:
        dict[str, Any]: Updated sample.

    Examples:
        >>> process_text_dataset_eval({"issues": [], "metrics": {}}, [])
        {'issues': [], 'metrics': {}}
    """

    return process_stages(item, stages)
