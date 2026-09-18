from __future__ import annotations

from typing import Any

from synthesis_engine.accessors import RetrievalQAAccessor
from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult


class QAExtractionMapper(BaseMapper):
    mapper_name = "qa_extraction"  # Mapper name identifying the document QA extraction capability.
    mapper_version = "1.0.0"  # Mapper version used for lineage auditing.

    def __init__(self, config: dict[str, Any] | None = None, retrieval_accessor: RetrievalQAAccessor | None = None) -> None:
        """Initialize the document QA extraction mapper

        Business logic:
            1. Store mapper configuration
            2. Inject or create a RetrievalQAAccessor
            3. Initialize the embedding boundary from config

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            retrieval_accessor (RetrievalQAAccessor | None): QA retrieval accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> QAExtractionMapper().mapper_name
            'qa_extraction'
        """
        super().__init__(config)
        self.retrieval_accessor = retrieval_accessor or RetrievalQAAccessor()  # QA accessor responsible for question generation and retrieval answers.
        self.retrieval_accessor.setup_embeddings(dict(self.config.get("embedding", {})))

    def map(self, input: MapperInput) -> MapperResult:
        """Generate instruction QA samples from document text

        Business logic:
            1. Validate the input text
            2. Generate questions and answer them one by one
            3. Return instruction/input/output samples

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: QA sample result.

        Examples:
            >>> QAExtractionMapper({'num_questions': 0}).map(MapperInput('a', 'text', 'x')).items
            []
        """
        text = input.content.strip()
        if not text:  # Empty text cannot generate usable QA pairs.
            return _failed_result(self.mapper_name, "empty_input", "Input text is empty")

        count = int(self.config.get("num_questions", self.config.get("num_questions_per_chunk", 1)))
        questions = [_clean_question(question) for question in self.retrieval_accessor.generate_questions(text, count)]
        questions = [question for question in questions if question]
        items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for question in questions:  # Retrieve answers per question and assemble instruction samples.
            answer = self.retrieval_accessor.answer(text, question).strip()
            if not answer:  # Keep a question-level issue and continue when retrieval produces no answer.
                issues.append({"type": "no_answer_generated", "message": f"Failed to generate answer: {question}"})
                continue
            items.append({"instruction": question, "input": "", "output": answer})

        failed = not items
        if failed and not issues:  # Return an overall failure issue when no deliverable QA pairs exist.
            issues.append({"type": "no_qa_pairs_generated", "message": "No QA pairs were generated"})
        return MapperResult(
            items=items,
            metrics={"num_qa_pairs": len(items), "question_count": len(questions)},
            issues=issues,
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version},
            failed=failed,
        )


def _clean_question(question: str) -> str:
    """Clean numbering prefixes from a question

    Business logic:
        1. Remove English prefixes such as Question1
        2. Remove numeric numbering and bullet markers
        3. Return the question after trimming surrounding whitespace

    Args:
        question (str): Raw question.

    Returns:
        str: Cleaned question.

    Examples:
        >>> _clean_question('Question1: What is A?')
        'What is A?'
    """
    text = str(question or "").strip()
    lowered = text.lower()
    if lowered.startswith("question"):  # Support the common LlamaIndex-style Question1 prefix.
        marker_index = max(text.find(":"), text.find("："))
        if marker_index >= 0:  # Remove the Question numbering label when a colon is found.
            text = text[marker_index + 1 :].strip()
    return _strip_list_prefix(text)


def _strip_list_prefix(text: str) -> str:
    """Remove list-numbering prefixes

    Business logic:
        1. Handle bullet prefixes
        2. Handle numbering like 1. and 1)
        3. Handle Chinese parenthesized numbering

    Args:
        text (str): Raw text.

    Returns:
        str: Text with numbering removed.

    Examples:
        >>> _strip_list_prefix('1. What?')
        'What?'
    """
    stripped = text.strip()
    if stripped.startswith(("-", "•")):  # Remove a leading bullet marker directly.
        return stripped[1:].strip()
    if stripped.startswith(("(", "（")):  # Parenthesized numbering requires locating the matching closing bracket first.
        close = ")" if stripped.startswith("(") else "）"
        close_index = stripped.find(close)
        if close_index > 0 and stripped[1:close_index].isdigit():  # Handle both Chinese and English bracket numbering.
            return stripped[close_index + 1 :].strip()
    index = 0
    while index < len(stripped) and stripped[index].isdigit():  # Read consecutive leading digits.
        index += 1
    if index > 0 and index < len(stripped) and stripped[index] in {".", ")"}:  # Handle numeric prefixes followed by a period or right parenthesis.
        return stripped[index + 1 :].strip()
    return stripped


def _failed_result(mapper_name: str, issue_type: str, message: str) -> MapperResult:
    """Build a failed MapperResult

    Business logic:
        1. Accept the mapper name and issue details
        2. Return a failed result with empty items
        3. Write standard lineage data

    Args:
        mapper_name (str): Mapper name.
        issue_type (str): Issue type.
        message (str): Issue description.

    Returns:
        MapperResult: Failed result.

    Examples:
        >>> _failed_result('m', 'x', 'y').failed
        True
    """
    return MapperResult(items=[], issues=[{"type": issue_type, "message": message}], lineage={"mapper": mapper_name}, failed=True)
