from __future__ import annotations

from typing import Any

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.operators.common.filters import QualityGateOperator, SafetyFilterOperator
from synthesis_engine.operators.common.scoring import DiversityScoreOperator
from synthesis_engine.operators.image_synthesis.generation import ImageCardSynthesisOperator
from synthesis_engine.operators.image_synthesis.prompt import NegativePromptBuildOperator
from synthesis_engine.operators.image_synthesis.validation import ImageQualityValidateOperator
from synthesis_engine.operators.structured_synthesis.distribution import StructuredDistributionAnalyzeOperator
from synthesis_engine.operators.structured_synthesis.record import StructuredRecordSynthesisOperator
from synthesis_engine.operators.structured_synthesis.schema import StructuredSchemaValidateOperator
from synthesis_engine.operators.structured_synthesis.validation import StructuredConsistencyValidateOperator
from synthesis_engine.operators.text_synthesis.llm_generation import TextLLMSynthesisOperator
from synthesis_engine.operators.text_synthesis.mapper_synthesis import (
    MultimodalSynthesisOperator,
    QuestionAugmentationSynthesisOperator,
    QuestionDecompositionSynthesisOperator,
    SynonymReplacementSynthesisOperator,
    TableQASynthesisOperator,
    TextQASynthesisOperator,
)
from synthesis_engine.operators.text_synthesis.template import TextTemplateSynthesisOperator
from synthesis_engine.operators.text_synthesis.validation import SynonymRewriteValidateOperator, TextFormatValidateOperator


StageSpec = tuple[type[BaseOperator], str]


TEXT_SYNTHESIS_STAGES: list[StageSpec] = [
    (TextLLMSynthesisOperator, "generation"),
    (TextFormatValidateOperator, "validation"),
    (DiversityScoreOperator, "quality"),
    (SafetyFilterOperator, "quality"),
    (QualityGateOperator, "quality"),
]

TEXT_TEMPLATE_SYNTHESIS_STAGES: list[StageSpec] = [
    (TextTemplateSynthesisOperator, "generation"),
    (TextFormatValidateOperator, "validation"),
    (DiversityScoreOperator, "quality"),
    (SafetyFilterOperator, "quality"),
    (QualityGateOperator, "quality"),
]

TEXT_QA_SYNTHESIS_STAGES: list[StageSpec] = [
    (TextQASynthesisOperator, "generation"),
    (QualityGateOperator, "quality"),
]

TABLE_QA_SYNTHESIS_STAGES: list[StageSpec] = [
    (TableQASynthesisOperator, "generation"),
    (QualityGateOperator, "quality"),
]

SYNONYM_REPLACEMENT_SYNTHESIS_STAGES: list[StageSpec] = [
    (SynonymReplacementSynthesisOperator, "generation"),
    (SynonymRewriteValidateOperator, "validation"),
    (QualityGateOperator, "quality"),
]

QUESTION_AUGMENTATION_SYNTHESIS_STAGES: list[StageSpec] = [
    (QuestionAugmentationSynthesisOperator, "generation"),
    (QualityGateOperator, "quality"),
]

QUESTION_DECOMPOSITION_SYNTHESIS_STAGES: list[StageSpec] = [
    (QuestionDecompositionSynthesisOperator, "generation"),
    (QualityGateOperator, "quality"),
]

MULTIMODAL_SYNTHESIS_STAGES: list[StageSpec] = [
    (MultimodalSynthesisOperator, "generation"),
    (QualityGateOperator, "quality"),
]

IMAGE_SYNTHESIS_STAGES: list[StageSpec] = [
    (NegativePromptBuildOperator, "generation"),
    (ImageCardSynthesisOperator, "generation"),
    (ImageQualityValidateOperator, "validation"),
    (DiversityScoreOperator, "quality"),
    (SafetyFilterOperator, "quality"),
    (QualityGateOperator, "quality"),
]

STRUCTURED_SYNTHESIS_STAGES: list[StageSpec] = [
    (StructuredDistributionAnalyzeOperator, "generation"),
    (StructuredRecordSynthesisOperator, "generation"),
    (StructuredSchemaValidateOperator, "validation"),
    (StructuredConsistencyValidateOperator, "validation"),
    (DiversityScoreOperator, "quality"),
    (SafetyFilterOperator, "quality"),
    (QualityGateOperator, "quality"),
]


def setup_synthesis_stages(config: dict[str, Any], specs: list[StageSpec]) -> list[BaseOperator]:
    """Build internal synthesis stages

    Business logic:
        1. Resolve stage config from profile, generation, validation, and quality sections
        2. Instantiate each internal stage with the resolved config
        3. Call each stage setup hook before sample processing

    Args:
        config (dict[str, Any]): End-to-end operator configuration.
        specs (list[StageSpec]): Internal stage class and config-section specs.

    Returns:
        list[BaseOperator]: Prepared internal stage instances.

    Examples:
        >>> len(setup_synthesis_stages({"generation": {"template": "x"}}, TEXT_TEMPLATE_SYNTHESIS_STAGES)) > 0
        True
    """
    stages = [stage_cls(_stage_config(config, stage_cls.operator_name, section)) for stage_cls, section in specs]

    for stage in stages:
        stage.setup()

    return stages


def process_synthesis_item(item: GenerationItem, stages: list[BaseOperator]) -> GenerationItem:
    """Run one sample through internal synthesis stages

    Business logic:
        1. Iterate through prepared internal stages in order
        2. Stop when the sample reaches a terminal action
        3. Return the updated sample for the outer executor

    Args:
        item (GenerationItem): Current synthesis sample.
        stages (list[BaseOperator]): Prepared internal stages.

    Returns:
        GenerationItem: Processed sample.

    Examples:
        >>> process_synthesis_item(GenerationItem("a", "text", "p"), []).id
        'a'
    """
    for stage in stages:
        if item.action in {"failed", "filtered", "accepted"}:
            break

        item = stage.process(item)

    return item


def teardown_synthesis_stages(stages: list[BaseOperator]) -> None:
    """Release internal synthesis stages

    Business logic:
        1. Iterate through every prepared stage
        2. Call teardown on each stage
        3. Return no value because cleanup is side-effect based

    Args:
        stages (list[BaseOperator]): Prepared internal stages.

    Returns:
        None: Stage teardown has no business return.

    Examples:
        >>> teardown_synthesis_stages([])
    """
    for stage in stages:
        stage.teardown()


def _stage_config(config: dict[str, Any], operator_name: str, section: str) -> dict[str, Any]:
    """Resolve config for one internal stage

    Business logic:
        1. Start with the full end-to-end config for backward-compatible keys
        2. Merge section-level config such as generation, validation, or quality
        3. Merge per-stage config from stages or stage_params when present

    Args:
        config (dict[str, Any]): End-to-end operator configuration.
        operator_name (str): Internal stage operator name.
        section (str): Config section name.

    Returns:
        dict[str, Any]: Config passed to the internal stage.

    Examples:
        >>> _stage_config({"quality": {"pass_score": 0.5}}, "quality_gate", "quality")["pass_score"]
        0.5
    """
    merged = dict(config)
    section_config = config.get(section, {})

    if isinstance(section_config, dict):
        merged.update(section_config)

    stage_configs = config.get("stages", config.get("stage_params", {}))

    if isinstance(stage_configs, dict) and isinstance(stage_configs.get(operator_name), dict):
        merged.update(stage_configs[operator_name])

    return merged
