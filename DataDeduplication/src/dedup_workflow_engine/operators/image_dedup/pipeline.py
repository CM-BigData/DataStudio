from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.common.postprocess.clustering import DuplicateClusterOperator, DuplicateEdgeFusionOperator
from dedup_workflow_engine.operators.common.postprocess.selectors import BestImageSelector
from dedup_workflow_engine.operators.image_dedup.embedding import ImageEmbeddingOperator
from dedup_workflow_engine.operators.image_dedup.fusion import ImageDupFusionOperator
from dedup_workflow_engine.operators.image_dedup.hashing import ImageFileHashDeduplicator, ImagePHashDeduplicator
from dedup_workflow_engine.operators.image_dedup.normalize import ImageNormalizeForDedupOperator
from dedup_workflow_engine.operators.image_dedup.recall import ImageANNRecallOperator
from dedup_workflow_engine.operators.image_dedup.similarity import ImageSSIMOperator, ObjectRegionSimilarityOperator


def run_image_dedup(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """运行图像端到端去重编排

    业务逻辑：
        1. 按 profile 组装图像规范化、哈希、相似度与召回阶段
        2. 依次执行融合、聚类与最优样本选择阶段
        3. 返回带有最终 keep/remove/review 决策的样本列表

    Args:
        items (list[dict[str, Any]]): 当前工作流中的图像样本列表
        context (dict[str, Any]): 共享工作流上下文字典
        config (dict[str, Any]): 当前端到端去重算子的参数配置

    Returns:
        list[dict[str, Any]]: 完成图像去重后的样本列表

    Examples:
        >>> run_image_dedup([], {}, {})
        []
    """
    profile = _profile(config)
    stages = [
        ImageNormalizeForDedupOperator(_stage_config(config, "normalize")),
        ImageFileHashDeduplicator(_method_config(config, "file_hash")),
        ImagePHashDeduplicator(_method_config(config, "phash", {"hash_size": 8, "max_hamming_distance": 4})),
    ]
    if profile == "strict":
        stages.extend(
            [
                ImageSSIMOperator(_method_config(config, "ssim", {"threshold": 0.88})),
                ImageEmbeddingOperator(_method_config(config, "embedding", _image_embedding_defaults())),
                ImageANNRecallOperator(_method_config(config, "ann_recall", {"threshold": 0.90, "top_k": 0})),
                ObjectRegionSimilarityOperator(_method_config(config, "region_similarity", {"threshold": 0.88})),
                ImageDupFusionOperator(_stage_config(config, "fusion", {"weights": _image_fusion_weights()})),
            ]
        )
    else:
        stages.append(DuplicateEdgeFusionOperator(_stage_config(config, "fusion")))
    stages.extend(
        [
            DuplicateClusterOperator(_cluster_config(config, {"min_score": 0.9 if profile != "strict" else 0.85})),
            BestImageSelector(_stage_config(config, "selector")),
        ]
    )
    return _run_stages(items, context, stages)


def _run_stages(items: list[dict[str, Any]], context: dict[str, Any], stages: list[Any]) -> list[dict[str, Any]]:
    """顺序执行图像去重内部阶段

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
    """读取图像去重 profile

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
    """合并图像内部阶段配置

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
    """合并图像算法配置

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
    """合并图像聚类配置

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


def _image_embedding_defaults() -> dict[str, Any]:
    """返回图像向量默认参数

    业务逻辑：
        1. 默认关闭外部 image embedding
        2. 保留环境变量命名约定
        3. 保留默认向量维度

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 图像向量默认参数

    Examples:
        >>> _image_embedding_defaults()["enabled"]
        False
    """
    return {
        "enabled": False,
        "dimensions": 128,
        "api_base_env": "IMAGE_EMBEDDING_API_BASE",
        "endpoint_path": "/embeddings",
        "api_key_env": "IMAGE_EMBEDDING_API_KEY",
        "model_env": "IMAGE_EMBEDDING_MODEL",
    }


def _image_fusion_weights() -> dict[str, float]:
    """返回图像融合权重默认值

    业务逻辑：
        1. 设置 file hash 与 perceptual hash 权重
        2. 设置结构相似度与 embedding 权重
        3. 设置区域相似度权重

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, float]: 图像融合权重默认值

    Examples:
        >>> round(_image_fusion_weights()["file_hash"], 2)
        1.0
    """
    return {"file_hash": 1.0, "phash": 0.8, "ssim": 0.78, "embedding": 0.82, "region_similarity": 0.8}
