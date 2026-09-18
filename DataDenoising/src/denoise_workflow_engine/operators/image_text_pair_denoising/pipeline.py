from __future__ import annotations

from typing import Any

from denoise_workflow_engine.utilities.config import model_ref_from_config, quality_gate_params_from_config, thresholds_from_config, with_leakage
from denoise_workflow_engine.operators.common.quality_gate import QualityGateOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.ocr import ImageOCRExtractOperator, OCRKeyFieldConsistencyOperator, OCRTextConsistencyOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.safety import PairSafetyFusionOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.scoring import PairQualityScorer
from denoise_workflow_engine.operators.image_text_pair_denoising.similarity import CLIPImageTextSimilarityOperator, ImageTextKeywordSimilarityOperator, VLMConsistencyOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.structure import PairStructureCheckOperator
from denoise_workflow_engine.utilities.pipeline import ensure_modality, run_stage_specs


def process_image_text_pair_denoise(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """执行端到端图文对去噪流程

    业务逻辑：
        1. 补齐图文对模态
        2. 组装图文对内部 stage 列表
        3. 顺序执行所有 stage 并返回标准样本

    Args:
        item (dict[str, Any]): 当前样本
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 处理后的样本

    Examples:
        >>> callable(process_image_text_pair_denoise)
        True
    """
    ensure_modality(item, "image_text_pair")
    return run_stage_specs(item, build_image_text_pair_stage_specs(config), config.get("_runtime"))


def build_image_text_pair_stage_specs(config: dict[str, Any], include_leakage: bool = True) -> list[tuple[type[Any], dict[str, Any]]]:
    """构建图文对去噪内部 stage 列表

    业务逻辑：
        1. 读取阈值与模型配置
        2. 固化图文对去噪内部执行顺序
        3. 返回可直接运行的 stage 配置

    Args:
        config (dict[str, Any]): 端到端算子配置
        include_leakage (bool): 是否注入防泄露 stage

    Returns:
        list[tuple[type[Any], dict[str, Any]]]: 图文对 stage 列表

    Examples:
        >>> build_image_text_pair_stage_specs({}, include_leakage=False)[0][0].__name__
        'PairStructureCheckOperator'
    """
    thresholds = thresholds_from_config(config)
    model_ref = model_ref_from_config(config)
    specs: list[tuple[type[Any], dict[str, Any]]] = [
        (PairStructureCheckOperator, {}),
        (ImageOCRExtractOperator, {"ocr": model_ref.get("ocr", {})}),
        (OCRTextConsistencyOperator, {"min_ocr_consistency": thresholds.get("min_ocr_consistency", 0.08)}),
        (OCRKeyFieldConsistencyOperator, {}),
        (ImageTextKeywordSimilarityOperator, {"min_keyword_similarity": thresholds.get("min_keyword_similarity", 0.15)}),
        (CLIPImageTextSimilarityOperator, {"min_clip_similarity": thresholds.get("min_clip_similarity", 0.28), "clip": model_ref.get("clip", {})}),
        (VLMConsistencyOperator, {"min_vlm_consistency": thresholds.get("min_vlm_consistency", 0.28), "vlm": model_ref.get("vlm", {})}),
        (PairSafetyFusionOperator, {}),
        (PairQualityScorer, {}),
        (QualityGateOperator, quality_gate_params_from_config(config)),
    ]
    return with_leakage(specs, config) if include_leakage else specs
