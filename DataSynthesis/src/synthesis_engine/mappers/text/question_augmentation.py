from __future__ import annotations

import json
from typing import Any

from synthesis_engine.accessors import LLMAccessor
from synthesis_engine.llm import LLMClientError
from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult
from synthesis_engine.prompts import PromptTemplateStore


class QuestionAugmentationMapper(BaseMapper):
    mapper_name = "question_augmentation"  # Question augmentation mapper: the registry uses this to identify the standalone augmentation capability.
    mapper_version = "1.0.0"  # Lineage version: audit trails record the active mapper version for augmented results.

    def __init__(self, config: dict[str, Any] | None = None, llm_accessor: Any | None = None) -> None:
        """Initialize the question augmentation mapper

        Business logic:
            1. Store mapper configuration
            2. Inject or create an LLMAccessor
            3. Prepare question augmentation calls

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            llm_accessor (Any | None): LLM accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> QuestionAugmentationMapper().mapper_name
            'question_augmentation'
        """
        super().__init__(config)
        self.llm_accessor = llm_accessor or LLMAccessor(model_config=dict(self.config.get("model_config", {})))  # Model accessor: performs the actual question-variant generation.
        self.prompt_store = PromptTemplateStore(self.config.get("prompt_dir"))  # Prompt store used to render augmentation messages from template files.

    def map(self, input: MapperInput) -> MapperResult:
        """Generate augmented question variants

        Business logic:
            1. Validate the source question
            2. Ask the LLM for rewrite, search-style, and context variants
            3. Parse and validate variants as augmentation rather than decomposition

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Augmented question variants.

        Examples:
            >>> parse_augmented_questions('[{"question": "How can I reset my password?", "augmentation_type": "rewrite"}]')[0]["augmentation_type"]
            'rewrite'
        """
        question = input.content.strip()

        if not question:  # Empty questions cannot produce useful augmented variants.
            return MapperResult(items=[], issues=[{"type": "empty_input", "message": "Input question is empty"}], lineage={"mapper": self.mapper_name}, failed=True)

        messages = self.prompt_store.render(
            _resolve_augmentation_template_name(self.config),
            _build_augmentation_prompt_variables(question, self.config),
        )
        try:
            response = self.llm_accessor.complete(messages, dict(self.config.get("call_options", {})))
        except LLMClientError as exc:
            return MapperResult(items=[], issues=[{"type": "llm_call_failed", "message": str(exc)}], lineage={"mapper": self.mapper_name}, failed=True)

        variants = parse_augmented_questions(response.content)
        model = response.model
        provider = response.provider

        normalized = _normalize_variants(question, variants)
        min_variants = max(1, int(self.config.get("min_variants", 2)))
        max_variants = max(min_variants, int(self.config.get("max_variants", 5)))

        if not normalized:  # Enter the failure path when model output cannot produce valid augmented questions.
            return MapperResult(
                items=[],
                issues=[{"type": "invalid_mapper_output", "message": "No augmented question variants could be parsed"}],
                lineage={"mapper": self.mapper_name, "model": model},
                failed=True,
            )

        if len(normalized) < min_variants:  # Too few variants reduce the coverage of training samples.
            return MapperResult(
                items=[],
                issues=[{"type": "too_few_augmented_questions", "message": f"Expected at least {min_variants} augmented questions"}],
                lineage={"mapper": self.mapper_name, "model": model},
                failed=True,
            )

        if any(  # Question augmentation must not degrade into decomposed reasoning steps.
            _looks_like_decomposition_step(question, item["question"]) for item in normalized if item["augmentation_type"] != "search_query"
        ):
            return MapperResult(
                items=[],
                issues=[{"type": "decomposition_like_output", "message": "Augmentation output contains decomposition-style sub-questions"}],
                lineage={"mapper": self.mapper_name, "model": model},
                failed=True,
            )

        trimmed = normalized[:max_variants]

        return MapperResult(
            items=trimmed,
            metrics={
                "augmented_question_count": len(trimmed),
                "raw_augmented_question_count": len(variants),
                "augmentation_types": sorted({item["augmentation_type"] for item in trimmed}),
            },
            issues=[],
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "model": model, "provider": provider},
            failed=False,
        )


def parse_augmented_questions(text: str) -> list[dict[str, str]]:
    """Parse augmented question variants from model text

    Business logic:
        1. Prefer structured JSON variants
        2. Fall back to numbered or bulleted text lines
        3. Return a uniform question/type list

    Args:
        text (str): Raw model response text.

    Returns:
        list[dict[str, str]]: Parsed augmented question rows.

    Examples:
        >>> parse_augmented_questions('1. How can I reset it?')[0]['question']
        'How can I reset it?'
    """
    parsed = _parse_json_variants(text)

    if parsed:  # Structured JSON is the preferred contract for LLM responses.
        return parsed

    variants: list[dict[str, str]] = []

    for line in str(text or "").splitlines():  # Fallback accepts numbered or bulleted model output.
        cleaned = _strip_variant_prefix(line.strip())

        if cleaned:  # Non-empty fallback lines are treated as generic variants.
            variants.append({"question": cleaned, "augmentation_type": "variant"})

    return variants


def _parse_json_variants(text: str) -> list[dict[str, str]]:
    """Parse JSON variants from model output

    Business logic:
        1. Normalize raw text and remove optional Markdown fences
        2. Decode either a JSON array or a dictionary containing variants
        3. Keep only rows that expose a concrete question value

    Args:
        text (str): Raw model response text.

    Returns:
        list[dict[str, str]]: Parsed JSON variant rows.

    Examples:
        >>> _parse_json_variants('[{"question": "What now?", "type": "rewrite"}]')[0]['augmentation_type']
        'rewrite'
    """
    raw = str(text or "").strip()

    if not raw:  # Empty model responses cannot be decoded into variants.
        return []

    if raw.startswith("```"):  # Remove a fenced JSON wrapper when the model returns one.
        raw = raw.strip("`").removeprefix("json").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    rows = data.get("variants", data) if isinstance(data, dict) else data

    if not isinstance(rows, list):  # The mapper only accepts a list-shaped variant contract.
        return []

    variants: list[dict[str, str]] = []

    for row in rows:  # Decode each model-provided variant row into the local contract.
        if isinstance(row, str):  # Plain string rows are tolerated as generic variants.
            variants.append({"question": row, "augmentation_type": "variant"})
            continue

        if not isinstance(row, dict):  # Unknown row shapes are ignored rather than guessed.
            continue

        question = str(row.get("question", row.get("text", ""))).strip()
        augmentation_type = str(row.get("augmentation_type", row.get("type", "variant"))).strip() or "variant"

        if question:  # Only rows with concrete question text are usable downstream.
            variants.append({"question": question, "augmentation_type": augmentation_type})

    return variants


def _normalize_variants(source_question: str, variants: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate and validate augmented variants

    Business logic:
        1. Remove invalid or non-question outputs
        2. Deduplicate against the source question and prior variants
        3. Attach source-question lineage to each valid variant

    Args:
        source_question (str): Original question being augmented.
        variants (list[dict[str, str]]): Raw parsed model variants.

    Returns:
        list[dict[str, str]]: Normalized augmented variants.

    Examples:
        >>> _normalize_variants('What is A?', [{'question': 'Which thing is A?', 'augmentation_type': 'rewrite'}])[0]['source_question']
        'What is A?'
    """
    source_key = _question_key(source_question)
    seen: set[str] = {source_key}
    normalized: list[dict[str, str]] = []

    for variant in variants:  # Normalize each raw model row independently.
        question = " ".join(str(variant.get("question", "")).split()).strip()

        if not _looks_like_question(question):  # Declarative or too-short text is not a valid question variant.
            continue

        key = _question_key(question)

        if not key or key in seen:  # Repeated variants do not add augmentation value.
            continue

        seen.add(key)
        normalized.append(
            {
                "question": question,
                "augmentation_type": _normalize_type(str(variant.get("augmentation_type", "variant"))),
                "source_question": source_question,
            }
        )

    return normalized


def _build_augmentation_prompt_variables(question: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build template variables for question augmentation

    Business logic:
        1. Read target variant count and language preference
        2. Preserve the source question as a template variable
        3. Return a serializable variable mapping for PromptTemplateStore

    Args:
        question (str): Source question to augment.
        config (dict[str, Any]): Mapper configuration.

    Returns:
        dict[str, Any]: Prompt variables.

    Examples:
        >>> _build_augmentation_prompt_variables('How can I reset my password?', {'language': 'en'})["count"]
        4
    """
    count = max(2, int(config.get("target_variants", config.get("max_variants", 4))))
    language = str(config.get("language", "zh"))
    return {"question": question, "count": count, "language": language}


def _resolve_augmentation_template_name(config: dict[str, Any]) -> str:
    """Resolve the prompt-template name for question augmentation

    Business logic:
        1. Respect an explicit prompt_template override first
        2. Choose the English template when language=en
        3. Default to the Chinese template for all other languages

    Args:
        config (dict[str, Any]): Mapper configuration.

    Returns:
        str: Template name consumed by PromptTemplateStore.

    Examples:
        >>> _resolve_augmentation_template_name({'language': 'en'})
        'question_augmentation_en'
    """
    explicit = str(config.get("prompt_template", "")).strip()
    if explicit:
        return explicit
    return "question_augmentation_en" if str(config.get("language", "zh")) == "en" else "question_augmentation_zh"


def _strip_variant_prefix(text: str) -> str:
    """Remove numbering prefixes from an augmented variant

    Business logic:
        1. Trim surrounding whitespace
        2. Remove bullet or numbered-list prefixes
        3. Return the cleaned variant text

    Args:
        text (str): Candidate variant line.

    Returns:
        str: Variant line without list prefix.

    Examples:
        >>> _strip_variant_prefix('1. How can I reset it?')
        'How can I reset it?'
    """
    stripped = text.strip()

    if stripped.startswith(("-", "•")):  # Bullet prefixes appear in fallback model output.
        return stripped[1:].strip()

    index = 0

    while index < len(stripped) and stripped[index].isdigit():
        index += 1

    if index > 0 and index < len(stripped) and stripped[index] in {".", ")"}:  # Numbered prefixes are common in non-JSON answers.
        return stripped[index + 1 :].strip()

    return stripped


def _looks_like_question(text: str) -> bool:
    """Check whether text looks like a usable question or search query

    Business logic:
        1. Reject empty and very short text
        2. Accept explicit English or Chinese question markers
        3. Allow keyword-style search queries with enough terms

    Args:
        text (str): Candidate question variant.

    Returns:
        bool: Whether the text can be used as an augmented question.

    Examples:
        >>> _looks_like_question('password reset without email?')
        True
    """
    value = text.strip()

    if len(value) < 4:  # Very short strings are usually malformed model fragments.
        return False

    lowered = value.lower()
    starters = ("what", "why", "how", "which", "who", "when", "where", "can ", "should ", "is ", "are ")
    chinese_markers = ("什么", "为何", "为什么", "如何", "哪些", "哪个", "谁", "是否", "怎么", "吗", "？")

    if "?" in value or "？" in value or lowered.startswith(starters) or any(  # Explicit question markers are accepted directly.
        marker in value for marker in chinese_markers
    ):
        return True

    return any(char.isalpha() for char in value) and len(value.split()) >= 2


def _looks_like_decomposition_step(source_question: str, candidate: str) -> bool:
    """Detect narrow intermediate sub-questions that look like decomposition

    Business logic:
        1. Compare source and candidate token overlap
        2. Reject overly narrow intermediate steps
        3. Detect common decomposition markers

    Args:
        source_question (str): Original question.
        candidate (str): Candidate augmented question.

    Returns:
        bool: Whether the candidate looks like a decomposition step.

    Examples:
        >>> _looks_like_decomposition_step('How do I reset my password?', 'First, what is the account?')
        True
    """
    source_tokens = set(_question_key(source_question).split())
    candidate_tokens = set(_question_key(candidate).split())

    if len(candidate) < max(12, len(source_question) // 2) and len(candidate_tokens - source_tokens) <= 1:  # Short near-subsets are usually sub-questions.
        return True

    decomposition_markers = (" first ", " next ", " intermediate ", "子问题", "第一步", "先确定", "再判断")
    lowered = f" {candidate.lower()} "

    return any(marker in lowered for marker in decomposition_markers)


def _normalize_type(value: str) -> str:
    """Normalize augmentation type names

    Business logic:
        1. Lowercase and normalize separators
        2. Keep known augmentation types
        3. Fold unknown values into variant

    Args:
        value (str): Raw augmentation type.

    Returns:
        str: Normalized augmentation type.

    Examples:
        >>> _normalize_type('context-variant')
        'context_variant'
    """
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    allowed = {"rewrite", "search_query", "context_variant", "variant"}

    return normalized if normalized in allowed else "variant"


def _question_key(text: str) -> str:
    """Build a loose deduplication key for question variants

    Business logic:
        1. Normalize case
        2. Normalize Chinese question marks to ASCII question marks
        3. Collapse whitespace and trailing question punctuation

    Args:
        text (str): Question text.

    Returns:
        str: Loose deduplication key.

    Examples:
        >>> _question_key('What is A?')
        'what is a'
    """

    return " ".join(str(text or "").lower().replace("？", "?").split()).strip(" ?")
