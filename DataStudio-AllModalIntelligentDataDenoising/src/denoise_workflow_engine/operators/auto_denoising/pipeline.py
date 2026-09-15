from __future__ import annotations

from typing import Any

from denoise_workflow_engine.utilities.config import leakage_params_from_config, quality_gate_params_from_config
from denoise_workflow_engine.operators.common.leakage import DataLeakageGuardOperator
from denoise_workflow_engine.operators.common.quality_gate import QualityGateOperator
from denoise_workflow_engine.operators.common.router import ModalityRouterOperator
from denoise_workflow_engine.operators.image_denoising.pipeline import build_image_stage_specs
from denoise_workflow_engine.operators.image_text_pair_denoising.pipeline import build_image_text_pair_stage_specs
from denoise_workflow_engine.utilities.pipeline import run_stage_specs
from denoise_workflow_engine.operators.text_denoising.pipeline import build_text_stage_specs
from denoise_workflow_engine.operators.video_denoising.pipeline import build_video_stage_specs


def process_auto_denoise(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """执行混合输入自动路由端到端去噪流程

    业务逻辑：
        1. 先执行防泄露与模态路由
        2. 根据模态选择对应去噪内部 stage 列表
        3. 对未知模态退化到质量门判定

    Args:
        item (dict[str, Any]): 当前样本
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 处理后的样本

    Examples:
        >>> callable(process_auto_denoise)
        True
    """
    runtime_config = config.get("_runtime")
    item = run_stage_specs(item, [(DataLeakageGuardOperator, leakage_params_from_config(config)), (ModalityRouterOperator, {})], runtime_config)
    modality = item.get("modality")
    if modality == "text":
        return run_stage_specs(item, build_text_stage_specs(config, include_leakage=False), runtime_config)
    if modality == "image":
        return run_stage_specs(item, build_image_stage_specs(config, include_leakage=False), runtime_config)
    if modality == "image_text_pair":
        return run_stage_specs(item, build_image_text_pair_stage_specs(config, include_leakage=False), runtime_config)
    if modality == "video":
        return run_stage_specs(item, build_video_stage_specs(config, include_leakage=False), runtime_config)
    return run_stage_specs(item, [(QualityGateOperator, quality_gate_params_from_config(config))], runtime_config)
