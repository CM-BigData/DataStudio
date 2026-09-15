from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import yaml

from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult


BUILTIN_SYNONYM_LEXICON: dict[str, list[str]] = {
    "加快": ["提速", "加速"],
    "活跃": ["旺盛", "踊跃"],
    "平稳": ["稳定", "平顺"],
    "继续": ["持续", "接着"],
    "发布": ["公布", "出台"],
    "表示": ["指出", "提到"],
    "支持": ["支撑", "助力"],
    "使用": ["采用", "运用"],
    "需要": ["须要", "有赖于"],
    "帮助": ["协助", "帮忙"],
    "说明": ["表明", "显示"],
    "模块": ["模组", "功能模块"],
    "编写": ["撰写", "编制"],
    "维护": ["维护管理", "保养"],
    "balanced": ["well-rounded", "varied"],
    "regularly": ["consistently", "frequently"],
    "important": ["key", "crucial"],
    "primary": ["main", "basic"],
    "describe": ["explain", "outline"],
    "function": ["role", "purpose"],
    "module": ["component", "package"],
    "motherboard": ["mainboard"],
}


class SynonymReplacementMapper(BaseMapper):
    mapper_name = "synonym_replacement"
    mapper_version = "1.0.0"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the offline synonym replacement mapper

        Business logic:
            1. Store mapper configuration through BaseMapper
            2. Load a built-in lexicon and optionally merge file-based entries
            3. Prepare deterministic replacement controls for later map calls

        Args:
            config (dict[str, Any] | None): Mapper configuration.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> SynonymReplacementMapper().mapper_name
            'synonym_replacement'
        """
        super().__init__(config)
        self.replacement_ratio = max(0.0, min(1.0, float(self.config.get("replacement_ratio", 0.3))))
        self.max_replacements = max(0, int(self.config.get("max_replacements", 3)))
        self.lexicon = _load_synonym_lexicon(self.config.get("synonym_source"))
        self.source_label = _resolve_source_label(self.config.get("synonym_source"))

    def map(self, input: MapperInput) -> MapperResult:
        """Replace matched words with deterministic synonyms

        Business logic:
            1. Validate the input text and discover replaceable spans from the lexicon
            2. Select a bounded number of non-overlapping replacements by ratio and max count
            3. Return the rewritten text, metrics, lineage, and structured replacement details

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Synonym replacement result.

        Examples:
            >>> SynonymReplacementMapper().map(MapperInput('x', 'text', 'plain text', {})).failed
            False
        """
        text = input.content.strip()
        if not text:
            return MapperResult(
                items=[],
                metrics={"synonym_candidate_count": 0, "synonym_replacement_count": 0},
                issues=[{"type": "empty_input", "message": "Input text is empty"}],
                lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "synonym_source": self.source_label},
                failed=True,
            )

        matches = _find_replaceable_matches(text, self.lexicon)
        if not matches:
            return MapperResult(
                items=[{"text": text, "replacements": [], "replacement_count": 0}],
                metrics={"synonym_candidate_count": 0, "synonym_replacement_count": 0, "rewrite_changed": False},
                issues=[{"type": "no_replaceable_terms", "message": "No replaceable terms matched the synonym lexicon"}],
                lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "synonym_source": self.source_label},
                failed=False,
            )

        selected = _select_matches(matches, self.replacement_ratio, self.max_replacements)
        rewritten_text, replacements = _apply_replacements(text, selected)

        return MapperResult(
            items=[{"text": rewritten_text, "replacements": replacements, "replacement_count": len(replacements)}],
            metrics={
                "synonym_candidate_count": len(matches),
                "synonym_replacement_count": len(replacements),
                "rewrite_changed": rewritten_text != text,
            },
            issues=[],
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "synonym_source": self.source_label},
            failed=False,
        )


def _load_synonym_lexicon(source: Any) -> dict[str, list[str]]:
    """Load and normalize the synonym lexicon

    Business logic:
        1. Start from the built-in offline synonym lexicon
        2. Merge optional inline or file-based entries
        3. Keep only non-empty keys and unique candidate values

    Args:
        source (Any): None, mapping, or file path describing extra lexicon entries.

    Returns:
        dict[str, list[str]]: Normalized synonym lexicon.

    Examples:
        >>> _load_synonym_lexicon({'publish': ['announce']})['publish'][0]
        'announce'
    """
    merged: dict[str, list[str]] = dict(BUILTIN_SYNONYM_LEXICON)
    if source is None or source == "builtin":
        return _normalize_lexicon(merged)
    if isinstance(source, dict):
        merged.update({str(key): [str(value) for value in values] for key, values in source.items()})
        return _normalize_lexicon(merged)

    path = Path(str(source)).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Synonym lexicon file not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        loaded = yaml.safe_load(raw_text) or {}
    elif path.suffix.lower() == ".json":
        loaded = json.loads(raw_text)
    else:
        raise ValueError(f"Unsupported synonym lexicon format: {path.suffix}")
    if not isinstance(loaded, dict):
        raise ValueError("Synonym lexicon file must contain a mapping")
    merged.update({str(key): [str(value) for value in values] for key, values in loaded.items()})
    return _normalize_lexicon(merged)


def _normalize_lexicon(raw_lexicon: dict[str, list[str]]) -> dict[str, list[str]]:
    """Normalize lexicon keys and values

    Business logic:
        1. Trim keys and candidate values
        2. Drop empty items and self-replacements
        3. Preserve input order while removing duplicates

    Args:
        raw_lexicon (dict[str, list[str]]): Raw synonym lexicon.

    Returns:
        dict[str, list[str]]: Cleaned synonym lexicon.

    Examples:
        >>> _normalize_lexicon({'a': ['a', 'b', 'b']})['a']
        ['b']
    """
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_values in raw_lexicon.items():
        key = str(raw_key).strip()
        if not key:
            continue
        deduped: list[str] = []
        for raw_value in raw_values:
            value = str(raw_value).strip()
            if not value or value == key or value in deduped:
                continue
            deduped.append(value)
        if deduped:
            normalized[key] = deduped
    return normalized


def _resolve_source_label(source: Any) -> str:
    """Resolve a stable source label for lineage reporting

    Business logic:
        1. Report built-in mode when no external source is configured
        2. Report file mode for path-like sources
        3. Report inline mode for mapping sources

    Args:
        source (Any): Configured synonym source.

    Returns:
        str: Source label.

    Examples:
        >>> _resolve_source_label(None)
        'builtin'
    """
    if source is None or source == "builtin":
        return "builtin"
    if isinstance(source, dict):
        return "inline"
    return str(source)


def _find_replaceable_matches(text: str, lexicon: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Find non-overlapping replaceable spans from the synonym lexicon

    Business logic:
        1. Scan each lexicon term across the source text
        2. Apply word boundaries for ASCII terms and direct matching for CJK terms
        3. Keep the longest non-overlapping matches in source order

    Args:
        text (str): Source text.
        lexicon (dict[str, list[str]]): Synonym lexicon.

    Returns:
        list[dict[str, Any]]: Replaceable match records.

    Examples:
        >>> _find_replaceable_matches('publish news', {'publish': ['announce']})[0]['term']
        'publish'
    """
    candidates: list[dict[str, Any]] = []
    for term, replacements in lexicon.items():
        pattern = _build_search_pattern(term)
        for occurrence_index, matched in enumerate(pattern.finditer(text)):
            candidates.append(
                {
                    "start": matched.start(),
                    "end": matched.end(),
                    "term": term,
                    "replacement": replacements[occurrence_index % len(replacements)],
                }
            )
    candidates.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
    selected: list[dict[str, Any]] = []
    cursor = -1
    for candidate in candidates:
        if candidate["start"] < cursor:
            continue
        selected.append(candidate)
        cursor = candidate["end"]
    return selected


def _build_search_pattern(term: str) -> re.Pattern[str]:
    """Build a regex pattern for one synonym term

    Business logic:
        1. Detect whether the term is ASCII word-like text
        2. Add word boundaries for ASCII tokens
        3. Escape direct text for CJK and mixed-symbol tokens

    Args:
        term (str): Synonym source term.

    Returns:
        re.Pattern[str]: Compiled search pattern.

    Examples:
        >>> bool(_build_search_pattern('module').search('a module'))
        True
    """
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z][A-Za-z' -]*", term):
        return re.compile(rf"\b{escaped}\b", flags=re.IGNORECASE)
    return re.compile(escaped)


def _select_matches(matches: list[dict[str, Any]], replacement_ratio: float, max_replacements: int) -> list[dict[str, Any]]:
    """Select a deterministic subset of matches for replacement

    Business logic:
        1. Compute the desired replacement count from ratio and configured max
        2. Preserve source order to keep output deterministic
        3. Return the selected prefix of matches

    Args:
        matches (list[dict[str, Any]]): Replaceable match records.
        replacement_ratio (float): Target replacement ratio.
        max_replacements (int): Maximum number of replacements.

    Returns:
        list[dict[str, Any]]: Selected match records.

    Examples:
        >>> len(_select_matches([{'start': 0, 'end': 1}], 1.0, 1))
        1
    """
    if not matches or replacement_ratio <= 0 or max_replacements <= 0:
        return []
    desired = max(1, int(math.ceil(len(matches) * replacement_ratio)))
    return matches[: min(len(matches), max_replacements, desired)]


def _apply_replacements(text: str, matches: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Apply selected replacements to source text

    Business logic:
        1. Walk through source text from left to right
        2. Copy untouched spans and append replacement text
        3. Return the rewritten text and structured replacement trace

    Args:
        text (str): Source text.
        matches (list[dict[str, Any]]): Selected replacements.

    Returns:
        tuple[str, list[dict[str, Any]]]: Rewritten text and replacement details.

    Examples:
        >>> _apply_replacements('publish news', [{'start': 0, 'end': 7, 'term': 'publish', 'replacement': 'announce'}])[0]
        'announce news'
    """
    if not matches:
        return text, []
    cursor = 0
    chunks: list[str] = []
    applied: list[dict[str, Any]] = []
    for match in matches:
        chunks.append(text[cursor : match["start"]])
        chunks.append(match["replacement"])
        applied.append(
            {
                "source": text[match["start"] : match["end"]],
                "target": match["replacement"],
                "start": match["start"],
                "end": match["end"],
            }
        )
        cursor = match["end"]
    chunks.append(text[cursor:])
    return "".join(chunks), applied
