from __future__ import annotations

from typing import Any


def thresholds_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """读取阈值配置

    业务逻辑：
        1. 从端到端配置中取出 thresholds 字段
        2. 校验其是否为字典
        3. 返回可供内部 stage 使用的阈值表

    Args:
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 阈值配置字典

    Examples:
        >>> thresholds_from_config({"thresholds": {"a": 1}})
        {'a': 1}
    """
    thresholds = config.get("thresholds", {})
    return thresholds if isinstance(thresholds, dict) else {}


def model_ref_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """读取模型引用配置

    业务逻辑：
        1. 从端到端配置中取出 model_ref 字段
        2. 校验其是否为字典
        3. 返回可供内部 stage 使用的模型配置

    Args:
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 模型引用配置字典

    Examples:
        >>> model_ref_from_config({"model_ref": {"llm": {"model": "x"}}})
        {'llm': {'model': 'x'}}
    """
    model_ref = config.get("model_ref", {})
    return model_ref if isinstance(model_ref, dict) else {}


def leakage_params_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """读取防泄露 stage 参数

    业务逻辑：
        1. 从 thresholds 中读取 forbidden_keys
        2. 仅保留防泄露 stage 所需字段
        3. 返回内部 stage 参数

    Args:
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 防泄露配置

    Examples:
        >>> leakage_params_from_config({"thresholds": {"forbidden_keys": ["x"]}})
        {'forbidden_keys': ['x']}
    """
    thresholds = thresholds_from_config(config)
    return {"forbidden_keys": thresholds.get("forbidden_keys", [])}


def quality_gate_params_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """读取质量门配置

    业务逻辑：
        1. 从 thresholds 中读取 keep_score、review_score 等配置
        2. 合并默认 hard-fail issues
        3. 返回质量门 stage 参数

    Args:
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 质量门配置

    Examples:
        >>> quality_gate_params_from_config({"thresholds": {"keep_score": 0.1}})["keep_score"]
        0.1
    """
    thresholds = thresholds_from_config(config)
    return {
        "keep_score": thresholds.get("keep_score", 0.75),
        "review_score": thresholds.get("review_score", 0.55),
        "hard_fail_issues": thresholds.get("hard_fail_issues", default_hard_fail_issues()),
        "review_issues": thresholds.get("review_issues", []),
    }


def with_leakage(specs: list[tuple[type[Any], dict[str, Any]]], config: dict[str, Any]) -> list[tuple[type[Any], dict[str, Any]]]:
    """为内部 stage 列表注入防泄露检查

    业务逻辑：
        1. 读取防泄露配置
        2. 将防泄露 stage 放到内部流程首位
        3. 返回带防泄露的 stage 列表

    Args:
        specs (list[tuple[type[Any], dict[str, Any]]]): 原始 stage 列表
        config (dict[str, Any]): 端到端算子配置

    Returns:
        list[tuple[type[Any], dict[str, Any]]]: 注入防泄露后的 stage 列表

    Examples:
        >>> len(with_leakage([], {}))
        1
    """
    from denoise_workflow_engine.operators.common.leakage import DataLeakageGuardOperator

    return [(DataLeakageGuardOperator, leakage_params_from_config(config)), *specs]


def default_hard_fail_issues() -> list[str]:
    """返回默认硬失败 issue 列表

    业务逻辑：
        1. 定义多模态去噪统一的硬失败标签
        2. 供端到端质量门作为默认值使用
        3. 避免在公开 workflow 中暴露内部 stage 细节

    Args:
        None: 无输入参数

    Returns:
        list[str]: 默认硬失败标签列表

    Examples:
        >>> "data_leakage_suspected" in default_hard_fail_issues()
        True
    """
    return [
        "data_leakage_suspected",
        "unknown_modality",
        "empty_text",
        "image_missing",
        "decode_failed",
        "invalid_json",
        "unsupported_language",
        "language_mismatch",
        "too_short",
        "text_too_short",
        "repetition_high",
        "low_info_density",
        "text_sensitive_masked",
        "sensitive_content",
        "semantic_low_quality",
        "low_resolution",
        "pure_color",
        "qrcode_detected",
        "watermark_detected",
        "logo_detected",
        "image_safety_risk",
        "safety_risk",
        "pair_missing_image",
        "pair_missing_text",
        "clip_mismatch",
        "vlm_contradiction",
        "ocr_key_field_conflict",
        "pair_safety_risk",
        "video_missing",
        "no_video_stream",
        "ffprobe_failed",
        "black_frames",
        "freeze_frames",
        "video_qrcode_detected",
        "video_safety_risk",
        "sensitive_speech_text",
        "audio_visual_inconsistent",
        "speech_subtitle_inconsistent",
        "video_too_short",
        "low_video_resolution",
    ]
