from __future__ import annotations

from typing import Any

from denoise_workflow_engine.utilities.config import model_ref_from_config, quality_gate_params_from_config, thresholds_from_config, with_leakage
from denoise_workflow_engine.operators.common.quality_gate import QualityGateOperator
from denoise_workflow_engine.utilities.pipeline import ensure_modality, run_stage_specs
from denoise_workflow_engine.operators.text_denoising.clean import HTMLCleanOperator, MarkdownCleanOperator
from denoise_workflow_engine.operators.text_denoising.filters import LowInfoDensityFilter, RepetitionFilter, TextLengthFilter
from denoise_workflow_engine.operators.text_denoising.language import LanguageDetectOperator
from denoise_workflow_engine.operators.text_denoising.llm import LLMSemanticQualityOperator
from denoise_workflow_engine.operators.text_denoising.normalize import ChineseNormalizeOperator, EncodingDetectOperator, UnicodeRepairOperator, WhitespaceNormalizeOperator
from denoise_workflow_engine.operators.text_denoising.safety import SensitiveContentFilter
from denoise_workflow_engine.operators.text_denoising.scoring import TextQualityScorer
from denoise_workflow_engine.operators.text_denoising.text_sensitive import TextSensitiveDetectOperator


def process_text_denoise(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """执行端到端文本去噪流程

    业务逻辑：
        1. 补齐文本模态
        2. 组装文本内部 stage 列表
        3. 顺序执行所有 stage 并返回标准样本

    Args:
        item (dict[str, Any]): 当前样本
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 处理后的样本

    Examples:
        >>> callable(process_text_denoise)
        True
    """
    ensure_modality(item, "text")
    return run_stage_specs(item, build_text_stage_specs(config), config.get("_runtime"))


def build_text_stage_specs(config: dict[str, Any], include_leakage: bool = True) -> list[tuple[type[Any], dict[str, Any]]]:
    """构建文本去噪内部 stage 列表

    业务逻辑：
        1. 读取阈值与模型配置
        2. 固化文本去噪内部执行顺序
        3. 返回可直接运行的 stage 配置

    Args:
        config (dict[str, Any]): 端到端算子配置
        include_leakage (bool): 是否注入防泄露 stage

    Returns:
        list[tuple[type[Any], dict[str, Any]]]: 文本 stage 列表

    Examples:
        >>> build_text_stage_specs({}, include_leakage=False)[0][0].__name__
        'EncodingDetectOperator'
    """
    thresholds = thresholds_from_config(config)
    model_ref = model_ref_from_config(config)
    specs: list[tuple[type[Any], dict[str, Any]]] = [
        (EncodingDetectOperator, {"min_confidence": thresholds.get("encoding_min_confidence", 0.35)}),
        (UnicodeRepairOperator, {}),
        (ChineseNormalizeOperator, {"remove_cjk_inner_spaces": True}),
        (WhitespaceNormalizeOperator, {}),
        (HTMLCleanOperator, {}),
        (MarkdownCleanOperator, {}),
        (LanguageDetectOperator, {"allowed_languages": ["zh", "mixed"], "min_confidence": thresholds.get("language_min_confidence", 0.25)}),
        (TextLengthFilter, {"min_length": thresholds.get("min_length", 12), "max_length": thresholds.get("max_length", 2000)}),
        (RepetitionFilter, {"max_repetition_ratio": thresholds.get("max_repetition_ratio", 0.35)}),
        (LowInfoDensityFilter, {"min_info_density": thresholds.get("min_info_density", 0.28), "min_unique_char_ratio": thresholds.get("min_unique_char_ratio", 0.06)}),
        (TextSensitiveDetectOperator, {}),
        (SensitiveContentFilter, {}),
        (LLMSemanticQualityOperator, {"stage": "post", "add_quality_issues": True, "mark_repairable": False, "min_semantic_score": thresholds.get("min_semantic_score", 0.55), "review_semantic_score": thresholds.get("review_semantic_score", 0.72), "llm": model_ref.get("llm", {})}),
        (TextQualityScorer, {}),
        (QualityGateOperator, quality_gate_params_from_config(config)),
    ]
    return with_leakage(specs, config) if include_leakage else specs
