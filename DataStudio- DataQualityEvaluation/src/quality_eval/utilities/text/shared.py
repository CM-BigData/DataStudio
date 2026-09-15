from __future__ import annotations

import regex as re
from collections import Counter
from typing import Any

from quality_eval.operators.common.base import BaseOperator
from quality_eval.utilities.metrics import action_from_issues, level_from_score, suggestions_for
from quality_eval.utilities.schema import ISSUE_PENALTIES
from quality_eval.runtime.registry import registry

__all__ = [
    "Any",
    "BaseOperator",
    "Counter",
    "ISSUE_PENALTIES",
    "action_from_issues",
    "level_from_score",
    "re",
    "registry",
    "suggestions_for",
    "_is_abnormal_char",
    "_normalize_text",
    "_text_value",
]

def _text_value(item: dict[str, Any]) -> str:
    """Read text content from the unified sample structure.

    Business logic:
        1. Read the raw text field from `payload.text`.
        2. Return the value only when it is a string.
        3. Return an empty string for missing or non-string values so later operators can check emptiness consistently.

    Args:
        item (dict[str, Any]): Unified sample structure.

    Returns:
        str: Sample text content or an empty string.

    Examples:
        >>> _text_value({"payload": {"text": "hello"}})
        'hello'
    """
    value = item.get("payload", {}).get("text")
    return value if isinstance(value, str) else ""

def _is_abnormal_char(char: str) -> bool:
    """Check whether a character should be treated as abnormal text content.

    Business logic:
        1. Treat whitespace, Chinese characters, and alphanumeric characters as normal.
        2. Treat common Chinese and English punctuation and symbols as normal.
        3. Treat all other characters as abnormal for garbled-text or dirty-character ratio checks.

    Args:
        char (str): Single character to inspect.

    Returns:
        bool: Returns True for abnormal characters, otherwise False.

    Examples:
        >>> _is_abnormal_char("\\u4f60")
        False
    """
    if char.isspace():  # Whitespace only affects formatting and is not treated as garbled or abnormal.
        return False
    if "\u4e00" <= char <= "\u9fff":  # CJK unified ideographs are normal content in Chinese datasets.
        return False
    if char.isalnum():  # Letters and digits are normal text content.
        return False
    if char in "，。！？；：、“”‘’（）《》,.!?;:-_()[]{}<>/\\@#%&+=*'\"":  # Common punctuation is not counted as abnormal.
        return False
    return True

def _normalize_text(text: str) -> str:
    """Normalize text for duplicate detection.

    Business logic:
        1. Trim leading and trailing whitespace.
        2. Collapse consecutive whitespace into a single space.
        3. Convert to lowercase to reduce case-related differences during duplicate detection.

    Args:
        text (str): Raw text.

    Returns:
        str: Normalized text.

    Examples:
        >>> _normalize_text(" A\\nA ")
        'a a'
    """
    return re.sub(r"\s+", " ", text.strip()).lower()
