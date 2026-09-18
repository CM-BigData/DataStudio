from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.common.postprocess.clustering import DuplicateClusterOperator, DuplicateEdgeFusionOperator
from dedup_workflow_engine.operators.common.postprocess.selectors import BestAudioSelector
from dedup_workflow_engine.operators.audio_dedup.asr import ASRTextDeduplicator, ASRTranscribeOperator
from dedup_workflow_engine.operators.audio_dedup.embedding import AudioEmbeddingOperator
from dedup_workflow_engine.operators.audio_dedup.fingerprint import AudioFingerprintDeduplicator
from dedup_workflow_engine.operators.audio_dedup.fusion import AudioDupFusionOperator
from dedup_workflow_engine.operators.audio_dedup.hashing import AudioFileHashDeduplicator, AudioPCMHashDeduplicator
from dedup_workflow_engine.operators.audio_dedup.normalize import AudioNormalizeOperator
from dedup_workflow_engine.operators.audio_dedup.similarity import MFCCSimilarityOperator


def run_audio_dedup(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """运行音频端到端去重编排

    业务逻辑：
        1. 按 profile 组装音频规范化、哈希、指纹、声学特征与 ASR 阶段
        2. 依次执行融合、聚类与最优样本选择阶段
        3. 返回带有最终 keep/remove/review 决策的样本列表

    Args:
        items (list[dict[str, Any]]): 当前工作流中的音频样本列表
        context (dict[str, Any]): 共享工作流上下文字典
        config (dict[str, Any]): 当前端到端去重算子的参数配置

    Returns:
        list[dict[str, Any]]: 完成音频去重后的样本列表

    Examples:
        >>> run_audio_dedup([], {}, {})
        []
    """
    profile = _profile(config)
    stages = [
        AudioNormalizeOperator(_stage_config(config, "normalize")),
        AudioFileHashDeduplicator(_method_config(config, "file_hash")),
        AudioPCMHashDeduplicator(_method_config(config, "pcm_hash")),
    ]
    if profile == "strict":
        stages.extend(
            [
                AudioFingerprintDeduplicator(_method_config(config, "fingerprint", {"bins": 64, "similarity_threshold": 0.92})),
                MFCCSimilarityOperator(_method_config(config, "mfcc", {"bins": 64, "similarity_threshold": 0.995})),
                AudioEmbeddingOperator(_method_config(config, "embedding", _audio_embedding_defaults())),
                ASRTranscribeOperator(_method_config(config, "asr", _asr_defaults())),
                ASRTextDeduplicator(_method_config(config, "asr_text", {"max_hamming_distance": 8})),
                AudioDupFusionOperator(_stage_config(config, "fusion", {"weights": _audio_fusion_weights()})),
            ]
        )
    else:
        stages.append(DuplicateEdgeFusionOperator(_stage_config(config, "fusion")))
    stages.extend(
        [
            DuplicateClusterOperator(_cluster_config(config, {"min_score": 0.99 if profile != "strict" else 0.85})),
            BestAudioSelector(_stage_config(config, "selector")),
        ]
    )
    return _run_stages(items, context, stages)


def _run_stages(items: list[dict[str, Any]], context: dict[str, Any], stages: list[Any]) -> list[dict[str, Any]]:
    """顺序执行音频去重内部阶段

    业务逻辑：
        1. 先统一 setup 所有内部阶段实例
        2. 按顺序把完整数据集传给每个阶段处理
        3. 最终统一 teardown 释放阶段资源

    Args:
        items (list[dict[str, Any]]): 当前样本列表
        context (dict[str, Any]): 共享工作流上下文
        stages (list[Any]): 内部阶段实例列表

    Returns:
        list[dict[str, Any]]: 经过所有阶段后的样本列表

    Examples:
        >>> _run_stages([], {}, [])
        []
    """
    result = items
    for stage in stages:
        stage.setup()
    try:
        for stage in stages:
            result = stage.process_dataset(result, context)
        return result
    finally:
        for stage in stages:
            stage.teardown()


def _profile(config: dict[str, Any]) -> str:
    """读取音频去重 profile

    业务逻辑：
        1. 从配置中读取 profile 字段
        2. 缺失时回退到 basic
        3. 统一转换成小写字符串返回

    Args:
        config (dict[str, Any]): 当前端到端去重算子的参数配置

    Returns:
        str: 规范化后的 profile 名称

    Examples:
        >>> _profile({"profile": "Strict"})
        'strict'
    """
    return str(config.get("profile", "basic")).lower()


def _stage_config(config: dict[str, Any], name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """合并音频内部阶段配置

    业务逻辑：
        1. 拷贝默认参数字典
        2. 叠加同名阶段的显式配置
        3. 返回合并后的阶段参数

    Args:
        config (dict[str, Any]): 当前端到端去重算子的参数配置
        name (str): 内部阶段名称
        defaults (dict[str, Any] | None): 阶段默认参数

    Returns:
        dict[str, Any]: 合并后的阶段参数

    Examples:
        >>> _stage_config({"x": {"a": 1}}, "x")["a"]
        1
    """
    merged = dict(defaults or {})
    merged.update(dict(config.get(name, {})))
    return merged


def _method_config(config: dict[str, Any], name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """合并音频算法配置

    业务逻辑：
        1. 先基于阶段配置生成初始参数
        2. 再从 methods 白名单中读取算法级覆盖项
        3. 支持布尔开关写法映射到 enabled 字段

    Args:
        config (dict[str, Any]): 当前端到端去重算子的参数配置
        name (str): methods 下的算法名称
        defaults (dict[str, Any] | None): 算法默认参数

    Returns:
        dict[str, Any]: 合并后的算法参数

    Examples:
        >>> _method_config({"methods": {"a": {"enabled": False}}}, "a")["enabled"]
        False
    """
    merged = _stage_config(config, name, defaults)
    methods = config.get("methods", {})
    if isinstance(methods, dict):
        value = methods.get(name, {})
        if isinstance(value, dict):
            merged.update(value)
        elif isinstance(value, bool):
            merged["enabled"] = value
    return merged


def _cluster_config(config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """合并音频聚类配置

    业务逻辑：
        1. 先拷贝默认聚类参数
        2. 允许 thresholds.cluster_min_score 覆盖 min_score
        3. 最后叠加顶层 cluster 配置

    Args:
        config (dict[str, Any]): 当前端到端去重算子的参数配置
        defaults (dict[str, Any]): 聚类默认参数

    Returns:
        dict[str, Any]: 合并后的聚类参数

    Examples:
        >>> _cluster_config({"thresholds": {"cluster_min_score": 0.7}}, {"min_score": 0.5})["min_score"]
        0.7
    """
    merged = dict(defaults)
    thresholds = config.get("thresholds", {})
    if isinstance(thresholds, dict) and "cluster_min_score" in thresholds:
        merged["min_score"] = thresholds["cluster_min_score"]
    merged.update(dict(config.get("cluster", {})))
    return merged


def _audio_embedding_defaults() -> dict[str, Any]:
    """返回音频向量默认参数

    业务逻辑：
        1. 默认关闭外部 audio embedding
        2. 保留环境变量命名约定
        3. 保留默认维度、召回和阈值参数

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 音频向量默认参数

    Examples:
        >>> _audio_embedding_defaults()["enabled"]
        False
    """
    return {
        "enabled": False,
        "dimensions": 128,
        "recall": True,
        "similarity_threshold": 0.995,
        "api_base_env": "AUDIO_EMBEDDING_API_BASE",
        "endpoint_path": "/embeddings",
        "api_key_env": "AUDIO_EMBEDDING_API_KEY",
        "model_env": "AUDIO_EMBEDDING_MODEL",
        "input_field": "audio_base64",
    }


def _asr_defaults() -> dict[str, Any]:
    """返回音频 ASR 默认参数

    业务逻辑：
        1. 默认关闭外部 ASR
        2. 保留环境变量命名约定
        3. 保留请求字段和响应字段约定

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 音频 ASR 默认参数

    Examples:
        >>> _asr_defaults()["enabled"]
        False
    """
    return {
        "enabled": False,
        "api_base_env": "AUDIO_ASR_API_BASE",
        "endpoint_path": "/audio/transcriptions",
        "api_key_env": "AUDIO_ASR_API_KEY",
        "model_env": "AUDIO_ASR_MODEL",
        "input_field": "audio_base64",
        "response_text_field": "text",
    }


def _audio_fusion_weights() -> dict[str, float]:
    """返回音频融合权重默认值

    业务逻辑：
        1. 设置文件与 PCM 哈希权重
        2. 设置指纹、MFCC 与 embedding 权重
        3. 设置 ASR 文本相似度权重

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, float]: 音频融合权重默认值

    Examples:
        >>> round(_audio_fusion_weights()["file_hash"], 2)
        1.0
    """
    return {
        "file_hash": 1.0,
        "pcm_hash": 0.95,
        "fingerprint": 0.9,
        "mfcc": 0.88,
        "embedding": 0.9,
        "asr_text": 0.8,
    }
