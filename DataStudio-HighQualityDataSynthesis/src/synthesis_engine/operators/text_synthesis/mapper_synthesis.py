from __future__ import annotations

from typing import Any

from synthesis_engine.accessors import FakeRetrievalQAAccessor, LLMAccessor, RetrievalQAAccessor
from synthesis_engine.mappers import MapperInput, MapperResult
from synthesis_engine.mappers.text import (
    MultimodalSynthesisMapper,
    QAExtractionMapper,
    QuestionAugmentationMapper,
    QuestionDecompositionMapper,
    SynonymReplacementMapper,
    TableQAMapper,
    TextRewriteMapper,
)
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.operators.text_synthesis.pipeline import TextGenerationPipeline


class TextMapperSynthesisOperator(BaseOperator):
    mapper_cls = QAExtractionMapper  # Mapper class wrapped by the current operator.
    default_input_key = "content"  # Default input field read from payload as mapper content.
    default_output_key = "items"  # Default output key written into item.generated.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Run the text mapper and write back to a fixed output key

        Business logic:
            1. Skip non-text samples
            2. Build MapperInput and run the pipeline
            3. Always write item.generated[output_key] = result.items

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            GenerationItem: Sample updated with mapper results.

        Examples:
            >>> TextMapperSynthesisOperator().default_output_key
            'items'
        """
        if item.task_type != "text":  # The text mapper operator only handles text samples.
            return item

        output_key = str(self.config.get("output_key", self.default_output_key))
        result = self._run_mapper(item)
        item.generated[output_key] = result.items
        item.metrics.update(result.metrics)
        item.issues.extend(result.issues)
        item.lineage["mapper"] = result.lineage
        if result.failed:  # Route mapper failures to the configured action, defaulting to workflow retry.
            item.action = str(self.config.get("failed_action", "needs_retry"))
        return item

    def _run_mapper(self, item: GenerationItem) -> MapperResult:
        """Run the mapper pipeline

        Business logic:
            1. Build the mapper from config
            2. Build MapperInput from the item
            3. Execute TextGenerationPipeline

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            MapperResult: Mapper output.

        Examples:
            >>> callable(TextMapperSynthesisOperator()._run_mapper)
            True
        """
        mapper = self._build_mapper()
        pipeline = TextGenerationPipeline(mapper, int(self.config.get("retry_limit", 0)))
        return pipeline.run(self._build_input(item))

    def _build_input(self, item: GenerationItem) -> MapperInput:
        """Build MapperInput

        Business logic:
            1. Read the input_key setting
            2. Read content from payload and fall back to prompt
            3. Return a workflow-independent MapperInput

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            MapperInput: Mapper input.

        Examples:
            >>> TextMapperSynthesisOperator()._build_input(GenerationItem('a', 'text', 'p')).content
            'p'
        """
        input_key = str(self.config.get("input_key", self.default_input_key))
        content = item.payload.get(input_key, item.prompt)
        return MapperInput(sample_id=item.id, task_type=item.task_type, content=str(content or ""), payload=dict(item.payload))

    def _build_mapper(self) -> Any:
        """Build the concrete mapper

        Business logic:
            1. Read the mapper class bound to the current operator
            2. Inject an accessor by mapper type
            3. Return the mapper instance

        Args:
            None.

        Returns:
            Any: Mapper instance.

        Examples:
            >>> TextMapperSynthesisOperator().mapper_cls is QAExtractionMapper
            True
        """
        if self.mapper_cls in {QAExtractionMapper, TableQAMapper}:  # QA-style mappers depend on RetrievalQAAccessor.
            return self.mapper_cls(self.config, retrieval_accessor=self._build_retrieval_accessor())
        if self.mapper_cls is SynonymReplacementMapper:  # Offline synonym replacement does not depend on LLM accessors.
            return self.mapper_cls(self.config)
        return self.mapper_cls(self.config, llm_accessor=self._build_llm_accessor())

    def _build_retrieval_accessor(self) -> RetrievalQAAccessor:
        """Build RetrievalQAAccessor

        Business logic:
            1. Prefer a test-injected accessor
            2. Support workflow fake-retrieval config
            3. Otherwise create the lightweight local RetrievalQAAccessor

        Args:
            None.

        Returns:
            RetrievalQAAccessor: QA retrieval accessor.

        Examples:
            >>> isinstance(TextMapperSynthesisOperator({'retrieval_accessor': {'type': 'fake'}})._build_retrieval_accessor(), RetrievalQAAccessor)
            True
        """
        configured = self.config.get("retrieval_accessor")
        if isinstance(configured, RetrievalQAAccessor):  # Unit tests may inject an accessor instance directly.
            return configured
        if isinstance(configured, dict) and configured.get("type") == "fake":  # Narrow workflow tests use config-driven fake retrieval.
            return FakeRetrievalQAAccessor(
                questions=[str(question) for question in configured.get("questions", [])],
                answers={str(key): str(value) for key, value in dict(configured.get("answers", {})).items()},
            )
        return RetrievalQAAccessor()

    def _build_llm_accessor(self) -> Any:
        """Build LLMAccessor

        Business logic:
            1. Prefer a test-injected accessor
            2. Read model_config to create LLMAccessor
            3. Return a callable object for the mapper

        Args:
            None.

        Returns:
            Any: LLM accessor。

        Examples:
            >>> hasattr(TextMapperSynthesisOperator({'llm_accessor': object()})._build_llm_accessor(), '__class__')
            True
        """
        configured = self.config.get("llm_accessor")
        if configured is not None and hasattr(configured, "complete"):  # Unit tests may inject a fake LLM accessor directly.
            return configured
        return LLMAccessor(model_config=dict(self.config.get("model_config", {})))


class TextQASynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "text_qa_synthesis"  # Registry name for the document QA synthesis workflow entry.
    mapper_cls = QAExtractionMapper  # Mapper class for document QA extraction.
    default_input_key = "content"  # Default input field for document content.
    default_output_key = "qa_pairs"  # Default output key where QA pairs are written.


class TableQASynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "table_qa_synthesis"  # Registry name for the table QA synthesis workflow entry.
    mapper_cls = TableQAMapper  # Mapper class for table QA.
    default_input_key = "table"  # Default input field for table text.
    default_output_key = "qa_pairs"  # Default output key where table QA pairs are written.

    def _build_input(self, item: GenerationItem) -> MapperInput:
        """Build MapperInput for table QA

        Business logic:
            1. Prefer the table field
            2. Fall back to content when table is missing
            3. Return MapperInput

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            MapperInput: Mapper input.

        Examples:
            >>> TableQASynthesisOperator().default_input_key
            'table'
        """
        input_key = str(self.config.get("input_key", self.default_input_key))
        content = item.payload.get(input_key, item.payload.get("content", item.prompt))
        return MapperInput(sample_id=item.id, task_type=item.task_type, content=str(content or ""), payload=dict(item.payload))


class TextRewriteSynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "text_rewrite_synthesis"  # Registry name for the text-rewrite synthesis workflow entry.
    mapper_cls = TextRewriteMapper  # Mapper class for text rewriting.
    default_input_key = "content"  # Default input field for source text to rewrite.
    default_output_key = "rewrites"  # Default output key where rewrites are written.


class SynonymReplacementSynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "synonym_replacement_synthesis"  # Registry name for the synonym-replacement synthesis workflow entry.
    mapper_cls = SynonymReplacementMapper  # Mapper class for offline synonym replacement.
    default_input_key = "content"  # Default input field for source text.
    default_output_key = "synonym_rewrites"  # Fixed output key where rewritten text entries are written.


class MultimodalSynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "multimodal_synthesis"  # Registry name for the multimodal synthesis workflow entry.
    mapper_cls = MultimodalSynthesisMapper  # Mapper class for real text+image synthesis.
    default_input_key = "text"  # Default input field for the text side of the multimodal request.
    default_output_key = "multimodal_items"  # Fixed output key where multimodal items are written.


class QuestionAugmentationSynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "question_augmentation_synthesis"  # Registry name for the question-augmentation workflow entry.
    mapper_cls = QuestionAugmentationMapper  # Mapper class for question augmentation variants.
    default_input_key = "question"  # Default input field for the source question.
    default_output_key = "augmented_questions"  # Default output key where augmented questions are written.

    def _build_input(self, item: GenerationItem) -> MapperInput:
        """Build MapperInput for question augmentation

        Business logic:
            1. Prefer the question field
            2. Fall back to content when question is missing
            3. Return MapperInput

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            MapperInput: Mapper input.

        Examples:
            >>> QuestionAugmentationSynthesisOperator().default_output_key
            'augmented_questions'
        """
        input_key = str(self.config.get("input_key", self.default_input_key))
        content = item.payload.get(input_key, item.payload.get("content", item.prompt))
        return MapperInput(sample_id=item.id, task_type=item.task_type, content=str(content or ""), payload=dict(item.payload))


class QuestionDecompositionSynthesisOperator(TextMapperSynthesisOperator):
    operator_name = "question_decomposition_synthesis"  # Registry name for the question-decomposition workflow entry.
    mapper_cls = QuestionDecompositionMapper  # Mapper class for complex-question decomposition.
    default_input_key = "question"  # Default input field for the complex question.
    default_output_key = "sub_questions"  # Default output key where sub-questions are written.

    def _build_input(self, item: GenerationItem) -> MapperInput:
        """Build MapperInput for question decomposition

        Business logic:
            1. Prefer the question field
            2. Fall back to content when question is missing
            3. Return MapperInput

        Args:
            item (GenerationItem): Workflow generation sample.

        Returns:
            MapperInput: Mapper input.

        Examples:
            >>> QuestionDecompositionSynthesisOperator().default_input_key
            'question'
        """
        input_key = str(self.config.get("input_key", self.default_input_key))
        content = item.payload.get(input_key, item.payload.get("content", item.prompt))
        return MapperInput(sample_id=item.id, task_type=item.task_type, content=str(content or ""), payload=dict(item.payload))
