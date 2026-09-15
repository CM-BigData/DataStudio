from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.common.postprocess.clustering import DuplicateClusterOperator, DuplicateEdgeFusionOperator
from dedup_workflow_engine.operators.common.postprocess.selectors import BestTextSelector
from dedup_workflow_engine.operators.text_dedup.embedding import TextEmbeddingOperator
from dedup_workflow_engine.operators.text_dedup.fusion import TextDupFusionOperator
from dedup_workflow_engine.operators.text_dedup.hashing import ExactHashDeduplicator
from dedup_workflow_engine.operators.text_dedup.minhash import MinHashLSHDeduplicator
from dedup_workflow_engine.operators.text_dedup.normalize import TextNormalizeForDedupOperator
from dedup_workflow_engine.operators.text_dedup.recall import ANNRecallOperator
from dedup_workflow_engine.operators.text_dedup.rerank import CrossEncoderRerankOperator
from dedup_workflow_engine.operators.text_dedup.simhash import SimHashDeduplicator


def run_text_dedup(items: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """运行文本端到端去重编排

    业务逻辑：
        1. 按 profile 组装文本规范化、哈希、召回、重排与融合阶段
        2. 依次执行聚类与最优样本选择阶段
        3. 返回带有最终 keep/remove/review 决策的样本列表

    Args:
        items (list[dict[str, Any]]): 当前工作流中的文本样本列表
        context (dict[str, Any]): 共享工作流上下文字典
        config (dict[str, Any]): 当前端到端去重算子的参数配置

    Returns:
        list[dict[str, Any]]: 完成文本去重后的样本列表

    Examples:
        >>> run_text_dedup([], {}, {})
        []
    """
    profile = _profile(config)
    stages = [
        TextNormalizeForDedupOperator(_stage_config(config, "normalize", _text_normalize_defaults())),
        ExactHashDeduplicator(_method_config(config, "exact_hash")),
        SimHashDeduplicator(_method_config(config, "simhash", {"bit_size": 64, "ngram": 2, "max_hamming_distance": 10})),
        MinHashLSHDeduplicator(_method_config(config, "minhash", {"shingle_size": 5, "min_length": 35, "jaccard_threshold": 0.55})),
    ]
    if profile == "strict":
        stages.extend(
            [
                TextEmbeddingOperator(_method_config(config, "embedding", _text_embedding_defaults())),
                ANNRecallOperator(_method_config(config, "ann_recall", {"threshold": 0.82, "top_k": 0})),
                CrossEncoderRerankOperator(_method_config(config, "rerank", _text_rerank_defaults())),
                TextDupFusionOperator(_stage_config(config, "fusion", {"weights": _text_fusion_weights()})),
            ]
        )
    else:
        stages.append(DuplicateEdgeFusionOperator(_stage_config(config, "fusion")))
    stages.extend(
        [
            DuplicateClusterOperator(_cluster_config(config, {"min_score": 0.55})),
            BestTextSelector(_stage_config(config, "selector")),
        ]
    )
    return _run_stages(items, context, stages)


def _run_stages(items: list[dict[str, Any]], context: dict[str, Any], stages: list[Any]) -> list[dict[str, Any]]:
    """顺序执行文本去重内部阶段

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
    """读取文本去重 profile

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
    """合并内部阶段配置

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
    """合并文本算法配置

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
    """合并文本聚类配置

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


def _text_normalize_defaults() -> dict[str, Any]:
    """返回文本规范化默认参数

    业务逻辑：
        1. 默认开启大小写归一化
        2. 默认开启 HTML 清理
        3. 默认开启空白与标点归一化

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 文本规范化默认参数

    Examples:
        >>> _text_normalize_defaults()["lowercase"]
        True
    """
    return {"lowercase": True, "remove_html": True, "normalize_space": True, "normalize_punctuation": True}


def _text_embedding_defaults() -> dict[str, Any]:
    """返回文本向量默认参数

    业务逻辑：
        1. 默认关闭外部 embedding
        2. 保留环境变量命名约定
        3. 保留默认向量维度

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 文本向量默认参数

    Examples:
        >>> _text_embedding_defaults()["enabled"]
        False
    """
    return {
        "enabled": False,
        "dimensions": 1024,
        "api_base_env": "TEXT_EMBEDDING_API_BASE",
        "endpoint_path": "/embeddings",
        "api_key_env": "TEXT_EMBEDDING_API_KEY",
        "model_env": "TEXT_EMBEDDING_MODEL",
    }


def _text_rerank_defaults() -> dict[str, Any]:
    """返回文本重排默认参数

    业务逻辑：
        1. 默认关闭外部 rerank
        2. 保留环境变量命名约定
        3. 保留默认阈值

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, Any]: 文本重排默认参数

    Examples:
        >>> _text_rerank_defaults()["enabled"]
        False
    """
    return {
        "enabled": False,
        "similarity_threshold": 0.82,
        "api_base_env": "TEXT_RERANK_API_BASE",
        "endpoint_path": "/rerank",
        "api_key_env": "TEXT_RERANK_API_KEY",
        "model_env": "TEXT_RERANK_MODEL",
    }


def _text_fusion_weights() -> dict[str, float]:
    """返回文本融合权重默认值

    业务逻辑：
        1. 设置 exact hash 与 simhash 权重
        2. 设置 minhash 与 embedding 权重
        3. 设置 rerank 权重

    Args:
        None: 不需要外部输入参数

    Returns:
        dict[str, float]: 文本融合权重默认值

    Examples:
        >>> round(_text_fusion_weights()["exact_hash"], 2)
        1.0
    """
    return {"exact_hash": 1.0, "simhash": 0.75, "minhash": 0.65, "embedding": 0.8, "rerank": 0.9}
