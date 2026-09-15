from __future__ import annotations

from typing import Any


def build_distribution_profile(schema: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """根据结构化 schema 构建字段分布画像

    业务逻辑：
        1. 遍历 schema 字段
        2. 提取 categorical 与 numeric 配置
        3. 返回供后续报告消费的 distribution profile

    Args:
        schema (list[dict[str, Any]]): 结构化字段定义列表。

    Returns:
        dict[str, dict[str, Any]]: 字段分布画像。

    Examples:
        >>> build_distribution_profile([{'name': 'age', 'type': 'integer'}])['age']['type']
        'integer'
    """
    distribution: dict[str, dict[str, Any]] = {}
    for field in schema:
        name = field["name"]
        if "choices" in field:
            distribution[name] = {"type": "categorical", "choices": field["choices"]}
        elif field.get("type") in {"integer", "float"}:
            distribution[name] = {
                "type": field.get("type"),
                "min": field.get("min"),
                "max": field.get("max"),
                "start": field.get("start"),
                "step": field.get("step", 1 if field.get("type") == "integer" else 0.1),
            }
    return distribution


def generate_structured_record(
    schema: list[dict[str, Any]],
    item_id: str,
    source_index: int = 0,
) -> dict[str, object]:
    """根据 schema 生成确定性结构化记录

    业务逻辑：
        1. 按 schema 顺序遍历字段
        2. 根据字段类型和 source_index 生成稳定值
        3. 返回完整 record

    Args:
        schema (list[dict[str, Any]]): 结构化字段定义列表。
        item_id (str): 样本 ID。
        source_index (int): 输入样本索引。

    Returns:
        dict[str, object]: 生成的结构化 record。

    Examples:
        >>> generate_structured_record([{'name': 'x', 'type': 'integer'}], 'a')['x']
        100
    """
    record: dict[str, object] = {}
    for index, field in enumerate(schema):
        name = field["name"]
        field_type = field.get("type", "string")
        record[name] = value_for_structured_field(field_type, item_id, index, field, source_index)
    return record


def value_for_structured_field(
    field_type: str,
    item_id: str,
    index: int,
    field: dict[str, Any],
    source_index: int = 0,
) -> object:
    """根据字段定义生成单个字段值

    业务逻辑：
        1. 计算 offset
        2. 根据 choices、numeric、boolean、string 分支生成值
        3. 对 numeric 值应用 min/max 约束

    Args:
        field_type (str): 字段类型。
        item_id (str): 样本 ID。
        index (int): 字段序号。
        field (dict[str, Any]): 字段定义。
        source_index (int): 输入样本索引。

    Returns:
        object: 生成的字段值。

    Examples:
        >>> value_for_structured_field('boolean', 'a', 0, {'name': 'ok'})
        True
    """
    offset = source_index + index
    if "choices" in field:
        choices = field["choices"]
        return choices[offset % len(choices)]
    if field_type == "integer":
        value = int(field.get("start", 100)) + offset
        if "max" in field:
            value = min(value, int(field["max"]))
        if "min" in field:
            value = max(value, int(field["min"]))
        return value
    if field_type == "float":
        value = float(field.get("start", 0.75)) + offset * float(field.get("step", 0.1))
        if "max" in field:
            value = min(value, float(field["max"]))
        if "min" in field:
            value = max(value, float(field["min"]))
        return round(value, 3)
    if field_type == "boolean":
        return offset % 2 == 0
    return f"{field.get('prefix', field['name'])}_{item_id}_{index}"


def validate_structured_schema(record: dict[str, Any], schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验结构化记录字段完整性

    业务逻辑：
        1. 遍历 schema 中声明的字段
        2. 检查 record 是否缺失字段
        3. 返回缺失字段 issue 列表

    Args:
        record (dict[str, Any]): 已生成记录。
        schema (list[dict[str, Any]]): 结构化字段定义列表。

    Returns:
        list[dict[str, Any]]: 缺字段问题列表。

    Examples:
        >>> validate_structured_schema({}, [{'name': 'a'}])[0]['field']
        'a'
    """
    issues: list[dict[str, Any]] = []
    for field in schema:
        name = field["name"]
        if name not in record:
            issues.append({"type": "missing_field", "field": name})
    return issues


def validate_structured_consistency(
    record: dict[str, Any],
    schema: list[dict[str, Any]],
    consistency_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验结构化记录的枚举、数值范围和跨字段一致性

    业务逻辑：
        1. 校验字段 choices 与 numeric 边界
        2. 执行 consistency_rules 中的跨字段比较
        3. 返回累计 issue 列表

    Args:
        record (dict[str, Any]): 已生成记录。
        schema (list[dict[str, Any]]): 结构化字段定义列表。
        consistency_rules (list[dict[str, Any]]): 跨字段规则列表。

    Returns:
        list[dict[str, Any]]: 一致性问题列表。

    Examples:
        >>> validate_structured_consistency({'x': 1}, [{'name': 'x', 'min': 2, 'type': 'integer'}], [])[0]['type']
        'below_min'
    """
    issues: list[dict[str, Any]] = []
    for field in schema:
        name = field["name"]
        if name not in record:
            continue
        value = record[name]
        if "choices" in field and value not in field["choices"]:
            issues.append({"type": "invalid_choice", "field": name, "value": value})
        if field.get("type") in {"integer", "float"}:
            if "min" in field and value < field["min"]:
                issues.append({"type": "below_min", "field": name, "value": value})
            if "max" in field and value > field["max"]:
                issues.append({"type": "above_max", "field": name, "value": value})

    for rule in consistency_rules:
        left = rule.get("left")
        right = rule.get("right")
        op = rule.get("op")
        if left in record and right in record and not compare_structured_values(record[left], record[right], op):
            issues.append({"type": "consistency_rule_failed", "rule": rule})
    return issues


def compare_structured_values(left: Any, right: Any, op: str | None) -> bool:
    """比较两个结构化字段值

    业务逻辑：
        1. 根据 op 选择比较方式
        2. 支持常见大小比较与不等比较
        3. 未声明 op 时默认做相等比较

    Args:
        left (Any): 左值。
        right (Any): 右值。
        op (str | None): 比较运算符。

    Returns:
        bool: 比较结果。

    Examples:
        >>> compare_structured_values(1, 2, '<')
        True
    """
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "!=":
        return left != right
    return left == right
