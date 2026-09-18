from __future__ import annotations

from typing import Any


def validate_text_length(text: str, min_length: int) -> list[dict[str, str]]:
    """校验文本长度

    业务逻辑：
        1. 接收文本和最小长度阈值
        2. 比较当前长度与阈值
        3. 当文本过短时返回统一 issue

    Args:
        text (str): 待校验文本。
        min_length (int): 最小长度阈值。

    Returns:
        list[dict[str, str]]: 校验问题列表。

    Examples:
        >>> validate_text_length('short', 8)[0]['type']
        'format_invalid'
    """
    if len(text) < min_length:
        return [{"type": "format_invalid", "message": "Text is too short"}]
    return []


def extract_first_rewrite_text(rewrites: Any) -> str:
    """提取首个改写结果中的文本

    业务逻辑：
        1. 仅接受非空 list
        2. 读取第一个元素中的 text 字段
        3. 无可用文本时返回空字符串

    Args:
        rewrites (Any): 改写结果容器。

    Returns:
        str: 首个改写文本。

    Examples:
        >>> extract_first_rewrite_text([{'text': 'hello'}])
        'hello'
    """
    if isinstance(rewrites, list) and rewrites:
        first = rewrites[0]
        if isinstance(first, dict):
            return str(first.get("text", ""))
    return ""
