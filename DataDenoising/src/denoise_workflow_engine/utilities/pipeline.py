from __future__ import annotations

import time
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


StageSpec = tuple[type[BaseOperator], dict[str, Any]]


def run_stage_specs(
    item: dict[str, Any],
    specs: list[StageSpec],
    runtime_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按顺序执行内部 stage 列表

    业务逻辑：
        1. 为样本补齐 issues、metrics、intermediate、operator_trace 基础字段
        2. 逐个实例化 stage，执行 setup -> process -> teardown 生命周期
        3. 记录内部 trace，返回处理后的统一样本

    Args:
        item (dict[str, Any]): 当前待处理样本
        specs (list[StageSpec]): 内部 stage 配置列表

    Returns:
        dict[str, Any]: 执行完所有 stage 的样本

    Examples:
        >>> run_stage_specs({"operator_trace": []}, [])
        {'operator_trace': [], 'issues': [], 'metrics': {}, 'intermediate': {}}
    """
    item.setdefault("issues", [])
    item.setdefault("metrics", {})
    item.setdefault("intermediate", {})
    item.setdefault("operator_trace", [])

    for stage_cls, stage_config in specs:
        merged_config = dict(stage_config)
        if runtime_config is not None:
            merged_config["_runtime"] = runtime_config
        stage = stage_cls(merged_config)
        started_at = time.time()
        try:
            stage.setup()
            item = stage.process(item)
            append_internal_trace(item, stage.operator_name, "success", started_at)
        finally:
            stage.teardown()

    return item


def append_internal_trace(item: dict[str, Any], stage_name: str, status: str, started_at: float) -> None:
    """写入内部 stage trace

    业务逻辑：
        1. 读取当前样本的 id、issues 和 action
        2. 生成内部 stage 的 trace 记录
        3. 追加到样本的 operator_trace 中

    Args:
        item (dict[str, Any]): 当前样本
        stage_name (str): stage 名称
        status (str): 执行状态
        started_at (float): stage 开始时间戳

    Returns:
        None: 结果直接写回 item

    Examples:
        >>> sample = {"operator_trace": []}
        >>> append_internal_trace(sample, "demo", "success", time.time())
        >>> sample["operator_trace"][0]["internal"]
        True
    """
    item.setdefault("operator_trace", []).append(
        {
            "sample_id": item.get("id"),
            "operator": stage_name,
            "internal": True,
            "status": status,
            "latency_ms": round((time.time() - started_at) * 1000, 3),
            "issues": list(item.get("issues", [])),
            "action": item.get("action", "pending"),
        }
    )


def ensure_modality(item: dict[str, Any], modality: str) -> None:
    """在专用端到端算子里补齐模态

    业务逻辑：
        1. 读取样本当前模态
        2. 当模态缺失或为 unknown 时写入目标模态
        3. 其余情况保持原值不变

    Args:
        item (dict[str, Any]): 当前样本
        modality (str): 目标模态

    Returns:
        None: 结果直接写回 item

    Examples:
        >>> sample = {}
        >>> ensure_modality(sample, "text")
        >>> sample["modality"]
        'text'
    """
    if not item.get("modality") or item.get("modality") == "unknown":
        item["modality"] = modality
