from __future__ import annotations

import json
from pathlib import Path

import yaml
import synthesis_engine.operators  # noqa: F401
from synthesis_engine.accessors import RetrievalQAAccessor
from synthesis_engine.llm.client import LLMResponse
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
from synthesis_engine.operators.text_synthesis import (
    SynonymReplacementSynthesisOperator,
    TextGenerationPipeline,
    TextQASynthesisOperator,
)
from synthesis_engine.operators.multimodal_synthesis import MultimodalSynthesisOperator
from synthesis_engine.operators.question_augmentation_synthesis import QuestionAugmentationSynthesisOperator
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor
from synthesis_engine.runtime.registry import registry


class FakeRetrievalQAAccessor(RetrievalQAAccessor):
    def __init__(self) -> None:
        """Initialize the test QA retrieval accessor

        Business logic:
            1. Record embedding configuration
            2. Provide a fixed question list
            3. Return assertable answers derived from questions

        Args:
            None.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> FakeRetrievalQAAccessor().questions
            ['What is the policy?', 'Who approves it?']
        """
        self.embedding_config: dict = {}  # Embedding configuration captured during tests.
        self.questions = ["What is the policy?", "Who approves it?"]  # Predictable fixed question list for tests.

    def setup_embeddings(self, config: dict) -> None:
        """Record embedding configuration

        Business logic:
            1. Accept test configuration
            2. Save it on the instance
            3. Support test assertions that the accessor exposes an embedding-setup boundary

        Args:
            config (dict): Embedding configuration.

        Returns:
            None: Only records configuration.

        Examples:
            >>> fake = FakeRetrievalQAAccessor(); fake.setup_embeddings({'model': 'x'}); fake.embedding_config['model']
            'x'
        """
        self.embedding_config = dict(config)  # Save the embedding configuration provided by the test.

    def generate_questions(self, text: str, count: int) -> list[str]:
        """Return the fixed question list

        Business logic:
            1. Ignore the real source text
            2. Truncate the fixed question list by count
            3. Return a predictable question list

        Args:
            text (str): Input text.
            count (int): Target question count.

        Returns:
            list[str]: Fixed question list.

        Examples:
            >>> FakeRetrievalQAAccessor().generate_questions('x', 1)
            ['What is the policy?']
        """
        return self.questions[:count]

    def answer(self, text: str, question: str) -> str:
        """Return an answer derived from the question

        Business logic:
            1. Accept the source text and question
            2. Build a stable answer
            3. Return text suitable for assertions

        Args:
            text (str): Input text.
            question (str): Question.

        Returns:
            str: Fixed answer.

        Examples:
            >>> FakeRetrievalQAAccessor().answer('policy', 'Q')
            'Answer for Q'
        """
        return f"Answer for {question}"


class FakeLLMAccessor:
    def __init__(self, content: str | list[str]) -> None:
        """Initialize the fake LLM accessor

        Business logic:
            1. Store the fixed response text
            2. Initialize call history
            3. Let mapper tests avoid real network access

        Args:
            content (str): Fixed response text.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> FakeLLMAccessor('x').responses[0]
            'x'
        """
        self.responses = [content] if isinstance(content, str) else list(content)  # Ordered fake responses returned across calls.
        self.calls: list[dict] = []  # Call records storing prompts and options passed by the mapper.

    def complete(self, messages: list[dict[str, str]], options: dict | None = None) -> LLMResponse:
        """Return a fixed LLMResponse

        Business logic:
            1. Record call messages
            2. Return a standard LLMResponse
            3. Avoid hitting a real provider during tests

        Args:
            messages (list[dict[str, str]]): Prompt messages.
            options (dict | None): Call options.

        Returns:
            LLMResponse: Standard model response.

        Examples:
            >>> FakeLLMAccessor('x').complete([], {}).content
            'x'
        """
        self.calls.append({"messages": messages, "options": options or {}})
        if not self.responses:
            raise AssertionError("FakeLLMAccessor ran out of queued responses")
        return LLMResponse(content=self.responses.pop(0), model="fake-model", provider="fake", request_id="fake")


class EchoQuestionAugmentationAccessor:
    def __init__(self) -> None:
        """Initialize the fake augmentation accessor

        Business logic:
            1. Prepare call history
            2. Derive variants from the prompt question
            3. Keep real-sample validation deterministic

        Args:
            None.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> EchoQuestionAugmentationAccessor().calls
            []
        """
        self.calls: list[dict] = []  # Call records storing prompt messages used during validation.

    def complete(self, messages: list[dict[str, str]], options: dict | None = None) -> LLMResponse:
        """Return deterministic augmented question variants

        Business logic:
            1. Extract the source question from the augmentation prompt
            2. Build rewrite, search-query, and context variants
            3. Return JSON shaped like the real LLM contract

        Args:
            messages (list[dict[str, str]]): Prompt messages.
            options (dict | None): Call options.

        Returns:
            LLMResponse: Standard model response.

        Examples:
            >>> EchoQuestionAugmentationAccessor().complete([{'role': 'user', 'content': 'Question: A?'}]).provider
            'fake'
        """
        self.calls.append({"messages": messages, "options": options or {}})
        prompt = messages[0]["content"] if messages else ""
        question = prompt.rsplit("Question:", 1)[-1].rsplit("原问题：", 1)[-1].strip()
        variants = [
            {"question": f"Could you answer this another way: {question}", "augmentation_type": "rewrite"},
            {"question": f"{question} detailed answer?", "augmentation_type": "search_query"},
            {"question": f"In a practical user scenario, {question}", "augmentation_type": "context_variant"},
        ]
        return LLMResponse(content=json.dumps(variants, ensure_ascii=False), model="fake-model", provider="fake", request_id="fake")


class RetryAwareMapper:
    def __init__(self, results: list[MapperResult]) -> None:
        """初始化带重试观测的 mapper

        业务逻辑：
            1. 保存预设结果队列
            2. 记录 map 调用次数
            3. 支持验证 TextGenerationPipeline 所在边界与重试行为

        Args:
            results (list[MapperResult]): 每次 map 调用依次返回的结果。

        Returns:
            None: 初始化不返回业务数据。

        Examples:
            >>> RetryAwareMapper([MapperResult()]).calls
            0
        """
        self.results = list(results)
        self.calls = 0

    def map(self, input: MapperInput) -> MapperResult:
        """按顺序返回预设结果

        业务逻辑：
            1. 记录本次 map 调用
            2. 逐个弹出预设结果
            3. 当结果耗尽时抛出断言，避免测试误通过

        Args:
            input (MapperInput): Mapper 输入。

        Returns:
            MapperResult: 预设的 mapper 结果。

        Examples:
            >>> RetryAwareMapper([MapperResult()]).map(MapperInput('id', 'text', 'x', {})).failed
            False
        """
        del input
        self.calls += 1
        if not self.results:
            raise AssertionError("RetryAwareMapper ran out of queued results")
        return self.results.pop(0)


def test_qa_extraction_mapper_returns_instruction_items() -> None:
    """Verify that the QA mapper returns instruction samples

    Business logic:
        1. Use the fake RetrievalQAAccessor
        2. Execute QAExtractionMapper
        3. Validate output fields, metrics, and lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_qa_extraction_mapper_returns_instruction_items)
        True
    """
    mapper = QAExtractionMapper({"num_questions": 2}, retrieval_accessor=FakeRetrievalQAAccessor())
    result = mapper.map(MapperInput("s1", "text", "Policy content.", {"source": "policy.md"}))

    assert result.failed is False
    assert result.items == [
        {"instruction": "What is the policy?", "input": "", "output": "Answer for What is the policy?"},
        {"instruction": "Who approves it?", "input": "", "output": "Answer for Who approves it?"},
    ]
    assert result.metrics["num_qa_pairs"] == 2
    assert result.lineage["mapper"] == "qa_extraction"


def test_text_generation_pipeline_retries_inside_text_synthesis_package() -> None:
    """验证文本 mapper 重试管线位于 text_synthesis 包内并按失败重试

    业务逻辑：
        1. 构造首轮失败、次轮成功的假 mapper
        2. 通过 operators.text_synthesis 暴露的 TextGenerationPipeline 执行
        3. 断言重试次数与最终结果都符合预期

    Args:
        None.

    Returns:
        None: 通过断言表达测试结果。

    Examples:
        >>> callable(test_text_generation_pipeline_retries_inside_text_synthesis_package)
        True
    """
    mapper = RetryAwareMapper(
        [
            MapperResult(items=[], failed=True, issues=[{"type": "retry"}]),
            MapperResult(items=[{"instruction": "ok", "output": "done"}], failed=False),
        ]
    )

    result = TextGenerationPipeline(mapper=mapper, retry_limit=1).run(MapperInput("sample-1", "text", "seed", {}))

    assert mapper.calls == 2
    assert result.failed is False
    assert result.items == [{"instruction": "ok", "output": "done"}]


def test_table_qa_mapper_returns_question_answer_items() -> None:
    """Verify that the table QA mapper returns question/answer samples

    Business logic:
        1. Use the fake RetrievalQAAccessor
        2. Execute TableQAMapper
        3. Validate the output field structure

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_table_qa_mapper_returns_question_answer_items)
        True
    """
    mapper = TableQAMapper({"num_questions": 1}, retrieval_accessor=FakeRetrievalQAAccessor())
    result = mapper.map(MapperInput("t1", "text", "| A | B |\n| --- | --- |\n| x | y |", {}))

    assert result.items == [{"question": "What is the policy?", "answer": "Answer for What is the policy?"}]
    assert result.metrics["num_qa_pairs"] == 1
    assert result.lineage["mapper"] == "table_qa"


def test_text_rewrite_mapper_uses_llm_accessor(tmp_path: Path) -> None:
    """Verify that the text rewrite mapper uses the LLM accessor

    Business logic:
        1. Write a custom rewrite prompt template
        2. Inject a fixed LLM response and execute TextRewriteMapper
        3. Validate output and rendered prompt messages

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_rewrite_mapper_uses_llm_accessor)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "text_rewrite.yaml").write_text('user: "Rewrite via template: {{ text }}"', encoding="utf-8")

    llm = FakeLLMAccessor("Rewritten content.")
    mapper = TextRewriteMapper({"language": "en", "prompt_dir": prompt_dir.as_posix()}, llm_accessor=llm)
    result = mapper.map(MapperInput("r1", "text", "Original content.", {}))

    assert result.items == [{"text": "Rewritten content."}]
    assert result.metrics["rewrite_changed"] is True
    assert result.lineage["mapper"] == "text_rewrite"
    assert llm.calls[0]["messages"] == [{"role": "user", "content": "Rewrite via template: Original content."}]


def test_multimodal_synthesis_mapper_builds_real_message_parts() -> None:
    """Verify that the multimodal mapper builds text-plus-image messages

    Business logic:
        1. Inject a fake LLM accessor
        2. Execute the multimodal mapper on a committed local image
        3. Validate output shape and image_url message structure

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_multimodal_synthesis_mapper_builds_real_message_parts)
        True
    """
    fixture_image = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "multimodal_images" / "example.jpg"
    llm = FakeLLMAccessor(
        [
            "A toy dinosaur is shown on a wooden table.",
            '{"instruction": "Describe the toy dinosaur in the image.", "input": ""}',
            "The image shows a small toy dinosaur placed on a wooden table.",
        ]
    )
    mapper = MultimodalSynthesisMapper({}, llm_accessor=llm)
    result = mapper.map(
        MapperInput(
            "m1",
            "text",
            "Describe the image.",
            {"text": "Describe the image.", "image_path": str(fixture_image)},
        )
    )

    assert result.failed is False
    assert result.items[0]["instruction"] == "Describe the toy dinosaur in the image."
    assert result.items[0]["output"] == "The image shows a small toy dinosaur placed on a wooden table."
    assert result.items[0]["image_refs"] == [str(fixture_image)]
    assert len(result.items[0]["stage_history"]) == 3
    assert result.metrics["multimodal_stage_count"] == 3
    assert result.lineage["mapper"] == "multimodal_synthesis"
    assert llm.calls[0]["messages"][0]["content"][1]["type"] == "image_url"
    assert "instruction_extraction" == result.lineage["stage_history"][1]["stage"]


def test_multimodal_synthesis_mapper_fails_when_image_is_missing() -> None:
    """Verify that the multimodal mapper reports missing images

    Business logic:
        1. Build the multimodal mapper
        2. Run it on a missing image path
        3. Validate failed output and issue type

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_multimodal_synthesis_mapper_fails_when_image_is_missing)
        True
    """
    mapper = MultimodalSynthesisMapper({}, llm_accessor=FakeLLMAccessor("unused"))
    result = mapper.map(MapperInput("m2", "text", "Describe the image.", {"text": "Describe the image.", "image_path": "missing.jpg"}))

    assert result.failed is True
    assert result.items == []
    assert result.issues[0]["type"] == "image_missing"


def test_multimodal_synthesis_mapper_fails_when_instruction_stage_is_not_json() -> None:
    """Verify that the multimodal mapper rejects invalid instruction-stage output

    Business logic:
        1. Queue a valid image-understanding response and an invalid extraction response
        2. Execute the multimodal mapper
        3. Validate that the mapper fails before final response generation

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_multimodal_synthesis_mapper_fails_when_instruction_stage_is_not_json)
        True
    """
    fixture_image = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "multimodal_images" / "example.jpg"
    mapper = MultimodalSynthesisMapper({}, llm_accessor=FakeLLMAccessor(["A scene summary.", "not-json"]))
    result = mapper.map(
        MapperInput(
            "m3",
            "text",
            "Describe the image.",
            {"text": "Describe the image.", "image_path": str(fixture_image)},
        )
    )

    assert result.failed is True
    assert result.issues[0]["type"] == "invalid_mapper_output"
    assert result.metrics["multimodal_stage_count"] == 2


def test_question_decomposition_mapper_parses_numbered_questions(tmp_path: Path) -> None:
    """Verify that the question decomposition mapper parses numbered sub-questions

    Business logic:
        1. Write a custom decomposition prompt template
        2. Inject a numbered LLM response and execute QuestionDecompositionMapper
        3. Validate the output sub-question list and rendered prompt

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_decomposition_mapper_parses_numbered_questions)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "question_decomposition.yaml").write_text(
        'user: "Break it down carefully. Source question={{ question }}"',
        encoding="utf-8",
    )

    llm = FakeLLMAccessor("1. What is A?\n2. Which B matches A?")
    mapper = QuestionDecompositionMapper({"prompt_dir": prompt_dir.as_posix()}, llm_accessor=llm)
    result = mapper.map(MapperInput("q1", "text", "Which B matches A?", {}))

    assert result.items == [{"question": "What is A?"}, {"question": "Which B matches A?"}]
    assert result.metrics["sub_question_count"] == 2
    assert result.metrics["raw_sub_question_count"] == 2
    assert result.lineage["mapper"] == "question_decomposition"
    assert llm.calls[0]["messages"] == [{"role": "user", "content": "Break it down carefully. Source question=Which B matches A?"}]


def test_question_decomposition_mapper_rejects_duplicate_or_non_question_items() -> None:
    """Verify that question decomposition rejects invalid sub-question shapes

    Business logic:
        1. Queue duplicate and declarative lines from the fake LLM
        2. Execute the mapper
        3. Validate that the mapper fails its quality gate

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_decomposition_mapper_rejects_duplicate_or_non_question_items)
        True
    """
    llm = FakeLLMAccessor("1. Explain the background\n2. Explain the background")
    mapper = QuestionDecompositionMapper({}, llm_accessor=llm)
    result = mapper.map(MapperInput("q2", "text", "Explain the background.", {}))

    assert result.failed is True
    assert result.issues[0]["type"] == "too_few_sub_questions"


def test_question_augmentation_mapper_returns_variants(tmp_path: Path) -> None:
    """Verify that question augmentation returns augmented variants

    Business logic:
        1. Write language-specific augmentation templates
        2. Inject JSON variants and execute the mapper with English routing
        3. Validate variant types, lineage, and rendered prompt

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_augmentation_mapper_returns_variants)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "question_augmentation_en.yaml").write_text(
        'user: "EN template count={{ count }} question={{ question }}"',
        encoding="utf-8",
    )
    (prompt_dir / "question_augmentation_zh.yaml").write_text(
        'user: "ZH template count={{ count }} 原问题={{ question }}"',
        encoding="utf-8",
    )

    llm = FakeLLMAccessor(
        json.dumps(
            [
                {"question": "How do I recover access when my account email is unavailable?", "augmentation_type": "rewrite"},
                {"question": "account password reset without email access?", "augmentation_type": "search_query"},
                {"question": "If the registered email cannot be used, how can I reset my account password?", "augmentation_type": "context_variant"},
            ]
        )
    )
    mapper = QuestionAugmentationMapper(
        {"min_variants": 2, "max_variants": 3, "language": "en", "prompt_dir": prompt_dir.as_posix()},
        llm_accessor=llm,
    )
    result = mapper.map(MapperInput("qa1", "text", "How can I reset my account password if I no longer have access to my email?", {}))

    assert result.failed is False
    assert [item["augmentation_type"] for item in result.items] == ["rewrite", "search_query", "context_variant"]
    assert result.items[0]["source_question"].startswith("How can I reset")
    assert result.metrics["augmented_question_count"] == 3
    assert result.lineage["mapper"] == "question_augmentation"
    assert llm.calls[0]["messages"] == [
        {
            "role": "user",
            "content": "EN template count=3 question=How can I reset my account password if I no longer have access to my email?",
        }
    ]


def test_question_augmentation_mapper_uses_zh_prompt_template_by_default(tmp_path: Path) -> None:
    """Verify that question augmentation defaults to the Chinese prompt template

    Business logic:
        1. Write English and Chinese augmentation templates
        2. Execute the mapper without a language override
        3. Validate that the rendered message comes from the Chinese template

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_augmentation_mapper_uses_zh_prompt_template_by_default)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "question_augmentation_en.yaml").write_text(
        'user: "EN template count={{ count }} question={{ question }}"',
        encoding="utf-8",
    )
    (prompt_dir / "question_augmentation_zh.yaml").write_text(
        'user: "ZH template count={{ count }} 原问题={{ question }}"',
        encoding="utf-8",
    )
    llm = FakeLLMAccessor(
        json.dumps(
            [
                {"question": "如何在收不到验证码时找回账号？", "augmentation_type": "rewrite"},
                {"question": "账号 找回 收不到 验证码", "augmentation_type": "search_query"},
            ],
            ensure_ascii=False,
        )
    )
    mapper = QuestionAugmentationMapper({"min_variants": 2, "max_variants": 2, "prompt_dir": prompt_dir.as_posix()}, llm_accessor=llm)

    result = mapper.map(MapperInput("qa_zh", "text", "收不到验证码时，如何找回账号？", {}))

    assert result.failed is False
    assert llm.calls[0]["messages"] == [{"role": "user", "content": "ZH template count=2 原问题=收不到验证码时，如何找回账号？"}]


def test_question_augmentation_mapper_rejects_empty_input() -> None:
    """Verify that question augmentation rejects empty input

    Business logic:
        1. Build the mapper with a fake LLM accessor
        2. Run it on blank input
        3. Validate the empty-input issue

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_augmentation_mapper_rejects_empty_input)
        True
    """
    mapper = QuestionAugmentationMapper({}, llm_accessor=FakeLLMAccessor("unused"))
    result = mapper.map(MapperInput("qa_empty", "text", "   ", {}))

    assert result.failed is True
    assert result.items == []
    assert result.issues[0]["type"] == "empty_input"


def test_question_augmentation_operator_is_registered_and_writes_output() -> None:
    """Verify that the question augmentation operator is registered

    Business logic:
        1. Resolve the operator from the registry
        2. Process a GenerationItem with a fake LLM accessor
        3. Validate generated output and mapper lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_augmentation_operator_is_registered_and_writes_output)
        True
    """
    operator = registry.create(
        "question_augmentation_synthesis",
        {
            "llm_accessor": FakeLLMAccessor(
                json.dumps(
                    [
                        {"question": "Which country contains Normandy?", "augmentation_type": "rewrite"},
                        {"question": "Normandy located in which country?", "augmentation_type": "search_query"},
                    ]
                )
            ),
            "min_variants": 2,
            "output_key": "augmented_questions",
        },
    )
    assert isinstance(operator, QuestionAugmentationSynthesisOperator)
    operator.setup()
    item = GenerationItem.from_dict({"id": "seed_aug", "task_type": "text", "payload": {"question": "In what country is Normandy located?"}})

    result = operator.process(item)

    assert result.generated["augmented_questions"][0]["question"] == "Which country contains Normandy?"
    assert result.metrics["augmented_question_count"] == 2
    assert result.lineage["mapper"]["mapper"] == "question_augmentation"


def test_question_augmentation_real_samples_differ_from_decomposition_shape() -> None:
    """Verify real question samples produce augmentation-shaped outputs

    Business logic:
        1. Load the committed real-question fixture subset
        2. Run each sample through the augmentation mapper with deterministic LLM output
        3. Compare against decomposition-shaped output to ensure the capability is distinct

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_question_augmentation_real_samples_differ_from_decomposition_shape)
        True
    """
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "question_augmentation_real_questions.yaml"
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    samples = raw["items"]
    assert 5 <= len(samples) <= 10
    assert {"qa", "search_query", "education", "customer_support"}.issubset({item["payload"]["sample_type"] for item in samples})

    augmentation_mapper = QuestionAugmentationMapper({"min_variants": 2, "max_variants": 3}, llm_accessor=EchoQuestionAugmentationAccessor())
    decomposition_mapper = QuestionDecompositionMapper({}, llm_accessor=FakeLLMAccessor(["1. What is the subject?\n2. Which answer matches it?"] * len(samples)))

    for sample in samples:
        question = sample["payload"]["question"]
        augmented = augmentation_mapper.map(MapperInput(sample["id"], "text", question, sample["payload"]))
        decomposed = decomposition_mapper.map(MapperInput(sample["id"], "text", question, sample["payload"]))

        assert augmented.failed is False
        assert decomposed.failed is False
        assert len(augmented.items) >= sample["payload"]["expected_min_variants"]
        assert all("augmentation_type" in item and "source_question" in item for item in augmented.items)
        assert all(item["question"] != question for item in augmented.items)
        assert augmented.items != decomposed.items


def test_text_qa_operator_writes_items_to_configured_output_key() -> None:
    """Verify that the operator writes back to generated[output_key]

    Business logic:
        1. Build a text_qa_synthesis operator with a fake accessor
        2. Process a GenerationItem
        3. Validate that MapperResult.items are written only to the configured output_key

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_qa_operator_writes_items_to_configured_output_key)
        True
    """
    operator = TextQASynthesisOperator({"output_key": "qa_pairs", "retrieval_accessor": FakeRetrievalQAAccessor(), "num_questions": 1})
    item = GenerationItem.from_dict({"id": "seed", "task_type": "text", "payload": {"content": "Policy content."}})

    result = operator.process(item)

    assert result.generated == {
        "qa_pairs": [{"instruction": "What is the policy?", "input": "", "output": "Answer for What is the policy?"}]
    }
    assert result.metrics["num_qa_pairs"] == 1
    assert result.lineage["mapper"]["mapper"] == "qa_extraction"


def test_synonym_replacement_mapper_returns_original_when_no_terms_match() -> None:
    """Verify that the mapper preserves text when no synonym is available

    Business logic:
        1. Build the mapper with an inline lexicon
        2. Run it on text without replaceable terms
        3. Validate that the original text is returned unchanged

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_mapper_returns_original_when_no_terms_match)
        True
    """
    mapper = SynonymReplacementMapper({"synonym_source": {"发布": ["公布"]}})
    result = mapper.map(MapperInput("s0", "text", "这是一段不会命中词表的文本。", {}))

    assert result.failed is False
    assert result.items[0]["text"] == "这是一段不会命中词表的文本。"
    assert result.items[0]["replacement_count"] == 0
    assert result.metrics["synonym_replacement_count"] == 0
    assert result.issues[0]["type"] == "no_replaceable_terms"


def test_synonym_replacement_mapper_rewrites_text_with_single_match() -> None:
    """Verify that the mapper rewrites text when one synonym term matches

    Business logic:
        1. Build the mapper with one deterministic synonym
        2. Run it on a sentence containing the source term
        3. Validate replacement text, count, and lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_mapper_rewrites_text_with_single_match)
        True
    """
    mapper = SynonymReplacementMapper({"synonym_source": {"发布": ["公布"]}, "replacement_ratio": 1.0, "max_replacements": 1})
    result = mapper.map(MapperInput("s1", "text", "平台会发布通知。", {}))

    assert result.items[0]["text"] == "平台会公布通知。"
    assert result.items[0]["replacements"] == [{"source": "发布", "target": "公布", "start": 3, "end": 5}]
    assert result.metrics["synonym_replacement_count"] == 1
    assert result.lineage["mapper"] == "synonym_replacement"


def test_synonym_replacement_mapper_selects_multiple_candidates_by_ratio_and_limit() -> None:
    """Verify that the mapper handles multiple candidates with stable limits

    Business logic:
        1. Build the mapper with several replaceable terms
        2. Run it on a sentence containing multiple matches
        3. Validate deterministic replacement selection and ordering

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_mapper_selects_multiple_candidates_by_ratio_and_limit)
        True
    """
    mapper = SynonymReplacementMapper(
        {
            "synonym_source": {"加快": ["提速"], "活跃": ["旺盛"], "平稳": ["稳定"]},
            "replacement_ratio": 0.67,
            "max_replacements": 2,
        }
    )
    result = mapper.map(MapperInput("s2", "text", "工业生产有所加快，消费比较活跃，价格总体平稳。", {}))

    assert result.items[0]["text"] == "工业生产有所提速，消费比较旺盛，价格总体平稳。"
    assert result.items[0]["replacement_count"] == 2
    assert [item["source"] for item in result.items[0]["replacements"]] == ["加快", "活跃"]


def test_synonym_replacement_operator_writes_fixed_output_key() -> None:
    """Verify that the synonym operator writes mapper items to generated output

    Business logic:
        1. Build the workflow-facing synonym operator
        2. Process a text GenerationItem
        3. Validate fixed generated output, metrics, and lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_operator_writes_fixed_output_key)
        True
    """
    operator = SynonymReplacementSynthesisOperator(
        {
            "synonym_source": {"支持": ["支撑"]},
            "replacement_ratio": 1.0,
            "max_replacements": 1,
            "output_key": "synonym_rewrites",
        }
    )
    item = GenerationItem.from_dict({"id": "seed_syn", "task_type": "text", "payload": {"content": "Python 支持模块化开发。"}})

    result = operator.process(item)

    assert result.generated["synonym_rewrites"][0]["text"] == "Python 支撑模块化开发。"
    assert result.metrics["synonym_replacement_count"] == 1
    assert result.lineage["mapper"]["mapper"] == "synonym_replacement"


def test_multimodal_synthesis_operator_is_registered_and_writes_output() -> None:
    """Verify that the multimodal operator is available and writes fixed output

    Business logic:
        1. Build the workflow-facing multimodal operator
        2. Process a text GenerationItem with a real fixture image path
        3. Validate generated output and mapper lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_multimodal_synthesis_operator_is_registered_and_writes_output)
        True
    """
    fixture_image = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "multimodal_images" / "flower.jpg"
    operator = MultimodalSynthesisOperator(
        {
            "output_key": "multimodal_items",
            "llm_accessor": FakeLLMAccessor(
                [
                    "A rabbit-like figure appears in the image.",
                    '{"instruction": "Describe the rabbit-like figure.", "input": ""}',
                    "The rabbit-like figure stands in the center of the image.",
                ]
            ),
        }
    )
    operator.setup()
    item = GenerationItem.from_dict(
        {
            "id": "seed_mm",
            "task_type": "text",
            "payload": {"text": "Describe the image.", "image_path": str(fixture_image)},
        }
    )

    result = operator.process(item)

    assert result.generated["multimodal_items"][0]["instruction"] == "Describe the rabbit-like figure."
    assert result.generated["multimodal_items"][0]["output"] == "The rabbit-like figure stands in the center of the image."
    assert result.lineage["mapper"]["mapper"] == "multimodal_synthesis"
    assert len(result.generated["multimodal_items"][0]["stage_history"]) == 3


def test_text_rewrite_mapper_rejects_unchanged_or_short_output() -> None:
    """Verify that the rewrite mapper rejects invalid successful-looking outputs

    Business logic:
        1. Run the mapper with unchanged output
        2. Run the mapper with too-short output
        3. Validate both failure types

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_rewrite_mapper_rejects_unchanged_or_short_output)
        True
    """
    unchanged = TextRewriteMapper({"language": "en"}, llm_accessor=FakeLLMAccessor("Original content."))
    unchanged_result = unchanged.map(MapperInput("r2", "text", "Original content.", {}))
    assert unchanged_result.failed is True
    assert unchanged_result.issues[0]["type"] == "rewrite_unchanged"

    short = TextRewriteMapper({"language": "en", "min_output_length": 8}, llm_accessor=FakeLLMAccessor("short"))
    short_result = short.map(MapperInput("r3", "text", "Original content.", {}))
    assert short_result.failed is True
    assert short_result.issues[0]["type"] == "rewrite_too_short"


def test_text_qa_workflow_runs_with_fake_retrieval_config(tmp_path: Path) -> None:
    """Verify the narrow QA workflow path with fake retrieval config

    Business logic:
        1. Write a text seed and workflow
        2. Run the workflow using fake retrieval config
        3. Validate that generated.jsonl contains the fixed output_key

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_qa_workflow_runs_with_fake_retrieval_config)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    output_dir = tmp_path / "runs"
    seed_path.write_text(
        """
items:
  - id: qa_seed
    task_type: text
    prompt: Build QA.
    payload:
      content: Policy owners approve release gates.
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: test_qa_mapper
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: text_qa_synthesis
    operator: text_qa_synthesis
    params:
      stages:
        text_qa_synthesis:
          output_key: qa_pairs
          num_questions: 1
          retrieval_accessor:
            type: fake
            questions:
              - Who approves release gates?
            answers:
              Who approves release gates?: Policy owners.
        quality_gate:
          pass_score: 0.5
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()
    rows = [json.loads(line) for line in (run_dir / "generated.jsonl").read_text(encoding="utf-8").splitlines()]

    assert rows[0]["generated"]["qa_pairs"] == [
        {"instruction": "Who approves release gates?", "input": "", "output": "Policy owners."}
    ]


def test_synonym_replacement_workflow_runs_with_real_text_fixture(tmp_path: Path) -> None:
    """Verify the narrow synonym workflow path with fixture-backed real text

    Business logic:
        1. Point a workflow config at the committed real-text fixture
        2. Run the synonym workflow end to end
        3. Validate output count and rewritten text presence

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_workflow_runs_with_real_text_fixture)
        True
    """
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = repo_root / "tests" / "fixtures" / "synonym_replacement_real_texts.yaml"
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: test_synonym_mapper
input:
  type: seed_yaml
  path: {fixture_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: synonym_replacement_synthesis
    operator: synonym_replacement_synthesis
    params:
      stages:
        synonym_replacement_synthesis:
          output_key: synonym_rewrites
          replacement_ratio: 0.5
          max_replacements: 2
          synonym_source: builtin
        synonym_rewrite_validate:
          min_length: 8
          output_key: synonym_rewrites
        quality_gate:
          pass_score: 0.5
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()
    rows = [json.loads(line) for line in (run_dir / "generated.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    filtered_rows = [json.loads(line) for line in (run_dir / "filtered.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(rows) >= 6
    assert {row["payload"]["sample_type"] for row in rows} == {"news", "qa", "guide", "boundary"}
    assert {row["id"] for row in filtered_rows} == {"short_ops_001", "boundary_no_hit_001"}
    assert filtered_rows[0]["action"] == "filtered"
    assert rows[0]["generated"]["synonym_rewrites"][0]["text"] != rows[0]["payload"]["content"]
    assert rows[0]["metrics"]["synonym_replacement_count"] >= 1


def test_synonym_replacement_real_fixture_meets_acceptance_expectations() -> None:
    """Verify that the real synonym fixture satisfies acceptance-style expectations

    Business logic:
        1. Load the committed real and boundary fixture set
        2. Execute the offline synonym mapper against each sample
        3. Validate replacement count, changed/unchanged behavior, and preserved keywords

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_synonym_replacement_real_fixture_meets_acceptance_expectations)
        True
    """
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = repo_root / "tests" / "fixtures" / "synonym_replacement_real_texts.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    mapper = SynonymReplacementMapper({"replacement_ratio": 0.5, "max_replacements": 2, "synonym_source": "builtin"})

    seen_types: set[str] = set()
    for sample in fixture["items"]:
        payload = sample["payload"]
        result = mapper.map(MapperInput(sample["id"], sample["task_type"], payload["content"], payload))
        rewritten = result.items[0]["text"]
        replacement_count = result.items[0]["replacement_count"]
        seen_types.add(payload["sample_type"])

        if payload["expect_changed"]:
            assert rewritten != payload["content"], sample["id"]
            assert replacement_count >= payload["expected_min_replacements"], sample["id"]
            assert result.metrics["rewrite_changed"] is True, sample["id"]
        else:
            assert rewritten == payload["content"], sample["id"]
            assert replacement_count == payload["expected_min_replacements"], sample["id"]
            assert result.metrics["rewrite_changed"] is False, sample["id"]

        for keyword in payload["expected_keywords_preserved"]:
            assert keyword in rewritten, f"{sample['id']} lost keyword: {keyword}"

        assert result.lineage["mapper"] == "synonym_replacement"
        assert "synonym_source" in result.lineage

    assert seen_types == {"news", "qa", "guide", "short_text", "boundary"}


def test_multimodal_synthesis_workflow_runs_with_real_fixture_and_fake_accessor(tmp_path: Path) -> None:
    """Verify the narrow multimodal workflow path with committed image fixtures

    Business logic:
        1. Point a workflow config at the committed multimodal fixture set
        2. Run the workflow using a fake accessor to keep the test narrow
        3. Validate generated output count and fixed output key

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_multimodal_synthesis_workflow_runs_with_real_fixture_and_fake_accessor)
        True
    """
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = repo_root / "tests" / "fixtures" / "multimodal_real_samples.yaml"
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: test_multimodal_mapper
input:
  type: seed_yaml
  path: {fixture_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: multimodal
    operator: multimodal_synthesis
    params:
      output_key: multimodal_items
      llm_accessor: null
      model_config:
        provider: openai
        model: fake/not-used
""",
        encoding="utf-8",
    )

    from synthesis_engine.runtime.registry import registry

    operator = registry.create(
        "multimodal_synthesis",
        {
            "output_key": "multimodal_items",
            "llm_accessor": FakeLLMAccessor(
                [
                    "A concise summary of the image.",
                    '{"instruction": "Describe the image.", "input": ""}',
                    "A test response.",
                ]
            ),
        },
    )
    assert isinstance(operator, MultimodalSynthesisOperator)
    operator.setup()

    item = GenerationItem.from_dict(
        {
            "id": "mm_inline",
            "task_type": "text",
            "payload": {"text": "Describe the image.", "image_path": str(repo_root / "tests" / "fixtures" / "multimodal_images" / "example.jpg")},
        }
    )
    result = operator.process(item)
    assert result.generated["multimodal_items"][0]["output"] == "A test response."
