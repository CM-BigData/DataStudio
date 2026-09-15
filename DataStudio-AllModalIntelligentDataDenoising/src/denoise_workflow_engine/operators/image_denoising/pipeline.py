from __future__ import annotations

from typing import Any

from denoise_workflow_engine.utilities.config import model_ref_from_config, quality_gate_params_from_config, thresholds_from_config, with_leakage
from denoise_workflow_engine.operators.common.quality_gate import QualityGateOperator
from denoise_workflow_engine.operators.image_denoising.metadata import ImageMetaOperator
from denoise_workflow_engine.operators.image_denoising.decode import ImageDecodeOperator
from denoise_workflow_engine.operators.image_denoising.quality import BlurDetectOperator, ExposureDetectOperator, NoiseEstimateOperator, ReferenceImageQualityOperator, SubjectCompletenessOperator, VLMImageQualityOperator
from denoise_workflow_engine.operators.image_denoising.repair import ImageRepairOperator
from denoise_workflow_engine.operators.image_denoising.safety import ImageSafetyOperator
from denoise_workflow_engine.operators.image_denoising.scoring import ImageQualityScorer
from denoise_workflow_engine.operators.image_denoising.signals import LogoDetectOperator, QRCodeDetectOperator, WatermarkDetectOperator
from denoise_workflow_engine.utilities.pipeline import ensure_modality, run_stage_specs


def process_image_denoise(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """执行端到端图片去噪流程

    业务逻辑：
        1. 补齐图片模态
        2. 组装图片内部 stage 列表
        3. 顺序执行所有 stage 并返回标准样本

    Args:
        item (dict[str, Any]): 当前样本
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 处理后的样本

    Examples:
        >>> callable(process_image_denoise)
        True
    """
    ensure_modality(item, "image")
    return run_stage_specs(item, build_image_stage_specs(config), config.get("_runtime"))


def build_image_stage_specs(config: dict[str, Any], include_leakage: bool = True) -> list[tuple[type[Any], dict[str, Any]]]:
    """构建图片去噪内部 stage 列表

    业务逻辑：
        1. 读取阈值与模型配置
        2. 固化图片去噪内部执行顺序
        3. 返回可直接运行的 stage 配置

    Args:
        config (dict[str, Any]): 端到端算子配置
        include_leakage (bool): 是否注入防泄露 stage

    Returns:
        list[tuple[type[Any], dict[str, Any]]]: 图片 stage 列表

    Examples:
        >>> build_image_stage_specs({}, include_leakage=False)[0][0].__name__
        'ImageDecodeOperator'
    """
    thresholds = thresholds_from_config(config)
    model_ref = model_ref_from_config(config)
    specs: list[tuple[type[Any], dict[str, Any]]] = [
        (ImageDecodeOperator, {}),
        (ImageMetaOperator, {"min_width": thresholds.get("min_width", 128), "min_height": thresholds.get("min_height", 128), "min_aspect_ratio": thresholds.get("min_aspect_ratio", 0.2), "max_aspect_ratio": thresholds.get("max_aspect_ratio", 5.0)}),
        (BlurDetectOperator, {"min_sharpness": thresholds.get("min_sharpness", 3.0)}),
        (ExposureDetectOperator, {"max_brightness": thresholds.get("max_brightness", 245), "min_brightness": thresholds.get("min_brightness", 25)}),
        (NoiseEstimateOperator, {"max_noise_sigma": thresholds.get("max_noise_sigma", 24.0)}),
        (ReferenceImageQualityOperator, {}),
        (QRCodeDetectOperator, {}),
        (WatermarkDetectOperator, {"min_watermark_score": thresholds.get("min_watermark_score", 0.72)}),
        (LogoDetectOperator, {"min_logo_score": thresholds.get("min_logo_score", 0.30)}),
        (ImageSafetyOperator, {"vlm": model_ref.get("vlm", {})}),
        (SubjectCompletenessOperator, {"min_center_score": thresholds.get("min_center_score", 0.05), "review_center_score": thresholds.get("review_center_score", 0.08), "max_crop_risk": thresholds.get("max_crop_risk", 0.62)}),
        (VLMImageQualityOperator, {"min_vlm_score": thresholds.get("min_vlm_score", 0.55), "review_vlm_score": thresholds.get("review_vlm_score", 0.72), "vlm": model_ref.get("vlm", {})}),
        (ImageRepairOperator, {}),
        (ImageQualityScorer, {}),
        (QualityGateOperator, quality_gate_params_from_config(config)),
    ]
    return with_leakage(specs, config) if include_leakage else specs
