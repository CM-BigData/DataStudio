from __future__ import annotations

import html
import re
import unicodedata


def normalize_text(
    text: str,
    lowercase: bool = True,
    remove_html: bool = True,
    normalize_space: bool = True,
    normalize_punctuation: bool = True,
) -> str:
    """执行文本去重前的纯文本归一化

    业务逻辑：
        1. 先做 HTML entity 反转义和 NFKC Unicode 归一化
        2. 按配置清理 HTML、URL、大小写和标点差异
        3. 按配置压缩空白并返回去首尾空白后的文本

    Args:
        text (str): 原始文本
        lowercase (bool, optional): 是否转小写，默认 True
        remove_html (bool, optional): 是否去掉 HTML 标签，默认 True
        normalize_space (bool, optional): 是否压缩空白，默认 True
        normalize_punctuation (bool, optional): 是否把常见标点替换成空格，默认 True

    Returns:
        str: 归一化后的文本

    Examples:
        >>> normalize_text("Hello， WORLD")
        'hello world'
    """
    value = html.unescape(text)
    value = unicodedata.normalize("NFKC", value)
    if remove_html:
        value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"https?://\S+", " ", value)
    if lowercase:
        value = value.lower()
    if normalize_punctuation:
        value = re.sub(r"[\u3000]", " ", value)
        value = re.sub(r"[，。！？；：“”‘’、,.!?;:\"'`~\-_=+*/\\|()[\]{}<>]", " ", value)
    if normalize_space:
        value = re.sub(r"\s+", " ", value)
    return value.strip()
