from __future__ import annotations

from typing import Any

from denoise_workflow_engine.utilities.config import model_ref_from_config, quality_gate_params_from_config, thresholds_from_config, with_leakage
from denoise_workflow_engine.operators.common.quality_gate import QualityGateOperator
from denoise_workflow_engine.utilities.pipeline import ensure_modality, run_stage_specs
from denoise_workflow_engine.operators.video_denoising.aigc import VideoAIGCDetectOperator
from denoise_workflow_engine.operators.video_denoising.audio import AudioExtractOperator, AudioQualityOperator
from denoise_workflow_engine.operators.video_denoising.frames import BlackFrameDetectOperator, FrameQRCodeDetectOperator, FrameQualityOperator, FreezeFrameDetectOperator, KeyFrameExtractOperator, VideoBlurDetectOperator, VLMFrameDescribeOperator
from denoise_workflow_engine.operators.video_denoising.ocr_asr import SubtitleOCROperator, VideoASROperator
from denoise_workflow_engine.operators.video_denoising.probe import VideoDecodeCheckOperator, VideoProbeOperator
from denoise_workflow_engine.operators.video_denoising.repair import VideoRepairOperator
from denoise_workflow_engine.operators.video_denoising.safety import AudioVisualConsistencyOperator, SpeechSubtitleConsistencyOperator, VideoSafetyFusionOperator
from denoise_workflow_engine.operators.video_denoising.scoring import VideoQualityScorer


def process_video_denoise(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """执行端到端视频去噪流程

    业务逻辑：
        1. 补齐视频模态
        2. 组装视频内部 stage 列表
        3. 顺序执行所有 stage 并返回标准样本

    Args:
        item (dict[str, Any]): 当前样本
        config (dict[str, Any]): 端到端算子配置

    Returns:
        dict[str, Any]: 处理后的样本

    Examples:
        >>> callable(process_video_denoise)
        True
    """
    ensure_modality(item, "video")
    return run_stage_specs(item, build_video_stage_specs(config), config.get("_runtime"))


def build_video_stage_specs(config: dict[str, Any], include_leakage: bool = True) -> list[tuple[type[Any], dict[str, Any]]]:
    """构建视频去噪内部 stage 列表

    业务逻辑：
        1. 读取阈值与模型配置
        2. 固化视频去噪内部执行顺序
        3. 返回可直接运行的 stage 配置

    Args:
        config (dict[str, Any]): 端到端算子配置
        include_leakage (bool): 是否注入防泄露 stage

    Returns:
        list[tuple[type[Any], dict[str, Any]]]: 视频 stage 列表

    Examples:
        >>> build_video_stage_specs({}, include_leakage=False)[0][0].__name__
        'VideoProbeOperator'
    """
    thresholds = thresholds_from_config(config)
    model_ref = model_ref_from_config(config)
    specs: list[tuple[type[Any], dict[str, Any]]] = [
        (VideoProbeOperator, {"min_bytes": thresholds.get("min_bytes", 1024), "min_duration": thresholds.get("min_duration", 1.0), "min_width": thresholds.get("min_video_width", 160), "min_height": thresholds.get("min_video_height", 120), "min_fps": thresholds.get("min_fps", 10.0)}),
        (VideoDecodeCheckOperator, {"timeout": thresholds.get("decode_timeout", 60)}),
        (KeyFrameExtractOperator, {"sample_fps": thresholds.get("sample_fps", 1.0), "max_frames": thresholds.get("max_frames", 4), "timeout": thresholds.get("keyframe_timeout", 60)}),
        (BlackFrameDetectOperator, {"black_brightness": thresholds.get("black_brightness", 12.0), "max_black_frame_ratio": thresholds.get("max_black_frame_ratio", 0.5)}),
        (VideoBlurDetectOperator, {"min_video_sharpness": thresholds.get("min_video_sharpness", 3.0)}),
        (FrameQualityOperator, {"max_bad_frame_ratio": thresholds.get("max_bad_frame_ratio", 0.5), "max_frame_noise": thresholds.get("max_frame_noise", 24.0)}),
        (FreezeFrameDetectOperator, {"freeze_diff_threshold": thresholds.get("freeze_diff_threshold", 1.5), "max_freeze_frame_ratio": thresholds.get("max_freeze_frame_ratio", 0.75)}),
        (FrameQRCodeDetectOperator, {"max_scan_frames": thresholds.get("max_scan_frames", 4)}),
        (AudioExtractOperator, {"timeout": thresholds.get("audio_timeout", 60)}),
        (AudioQualityOperator, {"timeout": thresholds.get("audio_timeout", 60), "silent_max_volume_db": thresholds.get("silent_max_volume_db", -50.0), "low_mean_volume_db": thresholds.get("low_mean_volume_db", -38.0)}),
        (SubtitleOCROperator, {"max_ocr_frames": thresholds.get("max_ocr_frames", 2), "ocr": model_ref.get("ocr", {})}),
        (VideoASROperator, {"asr": model_ref.get("asr", {})}),
        (VLMFrameDescribeOperator, {"max_vlm_frames": thresholds.get("max_vlm_frames", 2), "max_warning_red_ratio": thresholds.get("max_warning_red_ratio", 0.12), "vlm": model_ref.get("vlm", {})}),
        (SpeechSubtitleConsistencyOperator, {"min_consistency": thresholds.get("min_speech_subtitle_consistency", 0.25)}),
        (AudioVisualConsistencyOperator, {"min_consistency": thresholds.get("min_audio_visual_consistency", 0.25)}),
        (VideoSafetyFusionOperator, {}),
        (VideoRepairOperator, {"output_dir": thresholds.get("video_repair_output_dir", thresholds.get("output_dir")), "audio_volume_factor": thresholds.get("audio_volume_factor", 3.0), "timeout": thresholds.get("video_repair_timeout", 90)}),
        (VideoAIGCDetectOperator, {"detector_backend": "fallback", "video_aigc_threshold": thresholds.get("video_aigc_threshold", 0.55), "freeze_frame_risk_threshold": thresholds.get("freeze_frame_risk_threshold", 0.9), "max_repeated_visual_keywords": thresholds.get("max_repeated_visual_keywords", 3)}),
        (VideoQualityScorer, {}),
        (QualityGateOperator, quality_gate_params_from_config(config)),
    ]
    return with_leakage(specs, config) if include_leakage else specs
