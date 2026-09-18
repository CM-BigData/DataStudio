from __future__ import annotations

from typing import Any

from synthesis_engine.accessors import RetrievalQAAccessor
from synthesis_engine.mappers import MapperInput, MapperResult
from synthesis_engine.mappers.text.qa_extraction import QAExtractionMapper, _clean_question, _failed_result


class TableQAMapper(QAExtractionMapper):
    mapper_name = "table_qa"  # Mapper name identifying the table QA generation capability.
    mapper_version = "1.0.0"  # Mapper version used for lineage auditing.

    def __init__(self, config: dict[str, Any] | None = None, retrieval_accessor: RetrievalQAAccessor | None = None) -> None:
        """Initialize the table QA mapper

        Business logic:
            1. Reuse config initialization from the QA extraction mapper
            2. Store the RetrievalQAAccessor
            3. Keep an independent mapper name for table QA

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            retrieval_accessor (RetrievalQAAccessor | None): QA retrieval accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> TableQAMapper().mapper_name
            'table_qa'
        """
        super().__init__(config, retrieval_accessor)

    def map(self, input: MapperInput) -> MapperResult:
        """Generate question/answer samples from table text

        Business logic:
            1. Validate the table text
            2. Generate questions and answer them one by one
            3. Return a list of question/answer samples

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Table QA result.

        Examples:
            >>> TableQAMapper({'num_questions': 0}).map(MapperInput('a', 'text', '| A |')).items
            []
        """
        text = input.content.strip()
        if not text:  # Empty table text cannot generate usable QA pairs.
            return _failed_result(self.mapper_name, "empty_input", "Input table text is empty")

        count = int(self.config.get("num_questions", self.config.get("num_questions_per_chunk", 1)))
        questions = [_clean_question(question) for question in self.retrieval_accessor.generate_questions(text, count)]
        questions = [question for question in questions if question]
        items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for question in questions:  # Retrieve each table answer and assemble question/answer samples.
            answer = self.retrieval_accessor.answer(text, question).strip()
            if not answer:  # Record the issue and continue when retrieval returns no answer.
                issues.append({"type": "no_answer_generated", "message": f"Failed to generate answer: {question}"})
                continue
            items.append({"question": question, "answer": answer})

        failed = not items
        if failed and not issues:  # Return an overall failure issue when no deliverable table QA pairs exist.
            issues.append({"type": "no_qa_pairs_generated", "message": "No table QA pairs were generated"})
        return MapperResult(
            items=items,
            metrics={"num_qa_pairs": len(items), "question_count": len(questions)},
            issues=issues,
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version},
            failed=failed,
        )
