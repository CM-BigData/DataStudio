from __future__ import annotations

from typing import Any

from synthesis_engine.accessors import LLMAccessor
from synthesis_engine.llm import LLMClientError
from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult
from synthesis_engine.prompts import PromptTemplateStore


class QuestionDecompositionMapper(BaseMapper):
    mapper_name = "question_decomposition"  # Mapper name identifying the complex-question decomposition capability.
    mapper_version = "1.1.0"  # Mapper version used for lineage auditing.

    def __init__(self, config: dict[str, Any] | None = None, llm_accessor: Any | None = None) -> None:
        """Initialize the question decomposition mapper

        Business logic:
            1. Store mapper configuration
            2. Inject or create an LLMAccessor
            3. Prepare the complex-question decomposition call

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            llm_accessor (Any | None): LLM accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> QuestionDecompositionMapper().mapper_name
            'question_decomposition'
        """
        super().__init__(config)
        self.llm_accessor = llm_accessor or LLMAccessor(model_config=dict(self.config.get("model_config", {})))  # LLM accessor used to call the decomposition model.
        self.prompt_store = PromptTemplateStore(self.config.get("prompt_dir"))  # Prompt store used to render decomposition messages from template files.

    def map(self, input: MapperInput) -> MapperResult:
        """Decompose a complex question

        Business logic:
            1. Validate the input question
            2. Call the LLM to generate sub-questions
            3. Parse, normalize, and validate sub-questions before returning success

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Sub-question result.

        Examples:
            >>> parse_decomposed_questions('1. A?')
            ['A?']
        """
        question = input.content.strip()
        if not question:  # An empty question cannot be decomposed into valid sub-questions.
            return MapperResult(items=[], issues=[{"type": "empty_input", "message": "Input question is empty"}], lineage={"mapper": self.mapper_name}, failed=True)
        messages = self.prompt_store.render(
            str(self.config.get("prompt_template", "question_decomposition")),
            _build_decomposition_prompt_variables(question),
        )
        try:
            response = self.llm_accessor.complete(messages, dict(self.config.get("call_options", {})))
        except LLMClientError as exc:
            return MapperResult(items=[], issues=[{"type": "llm_call_failed", "message": str(exc)}], lineage={"mapper": self.mapper_name}, failed=True)
        questions = parse_decomposed_questions(response.content)
        if not questions:  # Mark a format failure when model output cannot be parsed into sub-questions.
            return MapperResult(
                items=[],
                issues=[{"type": "invalid_mapper_output", "message": "No sub-questions could be parsed"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        normalized_questions = _normalize_questions(questions)
        min_questions = max(1, int(self.config.get("min_questions", 2)))
        max_questions = max(min_questions, int(self.config.get("max_questions", 6)))
        if len(normalized_questions) < min_questions:
            return MapperResult(
                items=[],
                issues=[{"type": "too_few_sub_questions", "message": f"Expected at least {min_questions} sub-questions"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        if len(normalized_questions) > max_questions:
            return MapperResult(
                items=[],
                issues=[{"type": "too_many_sub_questions", "message": f"Expected at most {max_questions} sub-questions"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        if any(not _looks_like_question(item) for item in normalized_questions):
            return MapperResult(
                items=[],
                issues=[{"type": "invalid_sub_question_shape", "message": "At least one sub-question is not shaped like a usable question"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        return MapperResult(
            items=[{"question": item} for item in normalized_questions],
            metrics={
                "sub_question_count": len(normalized_questions),
                "raw_sub_question_count": len(questions),
            },
            issues=[],
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "model": response.model, "provider": response.provider},
            failed=False,
        )


def parse_decomposed_questions(text: str) -> list[str]:
    """Parse numbered sub-questions."""
    questions: list[str] = []
    for line in str(text or "").splitlines():  # Parse sub-questions line by line from numbered or bulleted output.
        cleaned = _strip_question_prefix(line.strip())
        if cleaned:  # Skip empty lines and empty results after prefix removal.
            questions.append(cleaned)
    return questions


def _strip_question_prefix(text: str) -> str:
    """Remove numbering prefixes from a sub-question."""
    stripped = text.strip()
    if stripped.startswith(("-", "•")):  # Remove a leading bullet marker directly.
        return stripped[1:].strip()
    if stripped.startswith(("(", "（")):  # Parenthesized numbering requires locating the matching closing bracket first.
        close = ")" if stripped.startswith("(") else "）"
        close_index = stripped.find(close)
        if close_index > 0 and stripped[1:close_index].isdigit():  # Treat a numeric value inside the brackets as numbering.
            return stripped[close_index + 1 :].strip()
    index = 0
    while index < len(stripped) and stripped[index].isdigit():  # Capture leading numeric numbering.
        index += 1
    if index > 0 and index < len(stripped) and stripped[index] in {".", ")"}:  # Handle numeric prefixes followed by a period or right parenthesis.
        return stripped[index + 1 :].strip()
    return stripped


def _build_decomposition_prompt_variables(question: str) -> dict[str, str]:
    """Build template variables for question decomposition

    Business logic:
        1. Preserve the source question as a template variable
        2. Keep the rendered prompt contract minimal
        3. Return a serializable mapping for PromptTemplateStore

    Args:
        question (str): Complex question to decompose.

    Returns:
        dict[str, str]: Prompt variables.

    Examples:
        >>> _build_decomposition_prompt_variables('Why?')["question"]
        'Why?'
    """
    return {"question": question}


def _normalize_questions(questions: list[str]) -> list[str]:
    """Deduplicate normalized sub-questions while preserving order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for question in questions:
        value = " ".join(question.split()).strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
    return normalized


def _looks_like_question(text: str) -> bool:
    """Check whether one sub-question looks usable for downstream QA."""
    lowered = text.lower().strip()
    if len(lowered) < 6:
        return False
    if "?" in lowered or "？" in lowered:
        return True
    starters = ("what", "why", "how", "which", "who", "when", "where", "whether", "is ", "are ", "can ", "should ")
    chinese_markers = ("什么", "为何", "为什么", "如何", "哪些", "哪个", "谁", "是否", "怎么")
    return lowered.startswith(starters) or any(marker in lowered for marker in chinese_markers)
