from __future__ import annotations

import regex as re
from pathlib import Path
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.utilities.image.base import OpenAICompatibleVisionClient, bounded_float

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None

DEFAULT_SYNONYMS: dict[str, set[str]] = {  # Synonym groups used by image-text keyword similarity.
    "chair": {"seat", "椅子"},
    "plug": {"socket", "插头"},
    "bicycle": {"bike", "自行车"},
    "circuit": {"pcb", "电路板"},
    "desk": {"table", "桌面"},
    "receiver": {"reciever", "接收器"},
    "reciever": {"receiver", "接收器"},
    "fruit": {"水果"},
    "toy": {"玩具"},
    "waterhouse": {"水屋"},
    "book": {"书本"},
    "printer": {"打印机"},
    "ball": {"球"},
    "comproom": {"computerroom", "机房"},
    "classroom": {"教室"},
    "planandsofa": {"sofa", "plant", "沙发", "植物"},
    "person": {"people", "human", "人物"},
    "document": {"paper", "sign", "文档", "标牌"},
}

known_cjk_terms = {term for values in DEFAULT_SYNONYMS.values() for term in values if re.search(r"[\u4e00-\u9fff]", term)}  # Known CJK business terms used by this module.

def metric_or_default(metrics: dict, key: str, default: float) -> float:
    """Read a metric value or fall back to a default score.

    Business logic:
        1. Read the metric by key.
        2. Return the default when the metric is missing or empty.
        3. Normalize the metric into a bounded float when present.

    Args:
            metrics (dict): Metrics dictionary.
            key (str): Metric key.
            default (float): Default value.

    Returns:
        float: Metric value or default.

    Examples:
        >>> metric_or_default
        metric_or_default
    """
    value = metrics.get(key)
    if value is None or value == "":  # Return the default when the metric is missing.
        return default
    return bounded_float(value, default)

def load_synonyms(config_value: Any) -> dict[str, set[str]]:
    """Load synonym groups for image-text matching.

    Business logic:
        1. Start from the built-in synonym mapping.
        2. Merge any user-provided synonym overrides.
        3. Return the resulting synonym map.

    Args:
            config_value (Any): Config value.

    Returns:
        dict[str, set[str]]: Loaded synonym map.

    Examples:
        >>> load_synonyms
        load_synonyms
    """
    synonyms = {key: set(values) for key, values in DEFAULT_SYNONYMS.items()}
    if isinstance(config_value, dict):  # Merge only dictionary-shaped synonym overrides.
        for key, values in config_value.items():  # Merge each override entry into the synonym map.
            if isinstance(values, str):  # Accept single-string synonym overrides.
                synonyms.setdefault(str(key).lower(), set()).add(values.lower())
            elif isinstance(values, list):
                synonyms.setdefault(str(key).lower(), set()).update(str(value).lower() for value in values)
    return synonyms

def expand_synonyms(tokens: set[str], synonyms: dict[str, set[str]]) -> set[str]:
    """Expand a token set through synonym closure.

    Business logic:
        1. Normalize the starting token set to lowercase.
        2. Repeatedly expand any synonym group that intersects the current set.
        3. Return the fully expanded token set.

    Args:
            tokens (set[str]): Token set.
            synonyms (dict[str, set[str]]): Synonym mapping.

    Returns:
        set[str]: Expanded synonym set.

    Examples:
        >>> expand_synonyms
        expand_synonyms
    """
    expanded = {token.lower() for token in tokens if token}
    changed = True
    while changed:
        changed = False
        for key, values in synonyms.items():  # Expand the full synonym group when any member is already present.
            group = {key.lower()} | {value.lower() for value in values}
            if expanded & group:  # Expand the whole group once any token intersects it.
                before = len(expanded)
                expanded |= group
                changed = changed or len(expanded) > before
    return expanded

def extract_key_fields(text: str) -> dict[str, set[str]]:
    """Extract key fields from OCR text and captions.

    Business logic:
        1. Extract dates, numbers, and code-like fields from the text.
        2. Exclude date fragments from generic number matching.
        3. Return the extracted key-field groups.

    Args:
            text (str): Input text content.

    Returns:
        dict[str, set[str]]: Extracted key-field groups.

    Examples:
        >>> extract_key_fields
        extract_key_fields
    """
    upper_text = str(text or "").upper()
    date_matches = re.findall(r"\d{4}[-年/]\d{1,2}(?:[-月/]\d{1,2})?", upper_text)
    dates = {normalize_date(match) for match in date_matches}
    date_parts = set()
    for date_match in date_matches:  # Exclude date digits from generic number conflicts.
        date_parts.update(re.findall(r"\d+", date_match))
    numbers = set(re.findall(r"(?<!\d)\d{2,8}(?!\d)", upper_text)) - date_parts
    codes = set(re.findall(r"\b[A-Z]{2,}[A-Z0-9-]{0,12}\b", upper_text))
    return {
        "numbers": {value for value in numbers if value},
        "dates": {value for value in dates if value},
        "codes": {value for value in codes if value},
    }

def normalize_date(value: str) -> str:
    """Normalize date-like text into a canonical dashed form.

    Business logic:
        1. Replace Chinese and slash separators with dashes.
        2. Remove trailing day markers.
        3. Strip redundant boundary dashes.

    Args:
            value (str): Value to normalize.

    Returns:
        str: Normalized date text.

    Examples:
        >>> normalize_date
        normalize_date
    """
    normalized = value.replace("年", "-").replace("月", "-").replace("日", "")
    normalized = normalized.replace("/", "-")
    return normalized.strip("-")

def normalize_tokens(text: str) -> set[str]:
    """Normalize free-form text into a token set.

    Business logic:
        1. Lowercase the text and split on non-semantic separators.
        2. Keep both generic tokens and multi-character CJK segments.
        3. Add known business CJK terms when they appear in the source text.

    Args:
            text (str): Input text content.

    Returns:
        set[str]: Normalized text tokens.

    Examples:
        >>> normalize_tokens
        normalize_tokens
    """
    source = str(text or "").lower()
    raw = re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", source)
    tokens: set[str] = set()
    for token in raw:  # Traverse token splits and drop empty fragments.
        token = token.strip("_- ")
        if not token:  # Empty tokens do not participate in similarity calculations.
            continue
        tokens.add(token)
        for zh in re.findall(r"[\u4e00-\u9fff]{2,}", token):  # Preserve contiguous CJK phrases needed for image-text matching.
            tokens.add(zh)
    for term in known_cjk_terms:  # Add known business CJK terms directly to avoid tokenization loss.
        if term in source:  # Keep the term when it appears in the original text.
            tokens.add(term)
    return tokens

def token_overlap(left: str, right: str) -> float:
    """Compute token overlap between two text strings.

    Business logic:
        1. Normalize both strings into token sets.
        2. Expand both token sets through synonym closure.
        3. Return the best overlap score, optionally boosted by rapidfuzz.

    Args:
            left (str): Left-side text.
            right (str): Right-side text.

    Returns:
        float: Token-overlap score.

    Examples:
        >>> token_overlap
        token_overlap
    """
    left_tokens = normalize_tokens(left)
    right_tokens = normalize_tokens(right)
    if not left_tokens or not right_tokens:  # Return zero similarity when either side lacks valid tokens.
        return 0.0
    expanded_left = expand_synonyms(left_tokens, DEFAULT_SYNONYMS)
    expanded_right = expand_synonyms(right_tokens, DEFAULT_SYNONYMS)
    overlap = len(expanded_left & expanded_right) / max(len(expanded_left), 1)
    if fuzz is None:  # Fall back to token overlap only when rapidfuzz is unavailable.
        return overlap
    rapidfuzz_score = float(fuzz.token_set_ratio(str(left), str(right)) / 100.0)
    return max(0.0, min(1.0, max(overlap, rapidfuzz_score)))
