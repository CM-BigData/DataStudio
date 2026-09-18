from __future__ import annotations

import json
from pathlib import Path

import synthesis_engine.operators  # noqa: F401
from synthesis_engine.llm.client import LLMResponse
from synthesis_engine.llm import LLMClientConfig, LLMClientError
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.text_synthesis import TextLLMSynthesisOperator
from synthesis_engine.prompts import PromptTemplateStore
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor
from pytest import MonkeyPatch


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        """Initialize the fake model client

        Business logic:
            1. Store the model text to be returned
            2. Initialize the request-history list
            3. Support test assertions for prompts and model configuration

        Args:
            content (str): Fake model response content.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> FakeLLMClient('{}').content
            '{}'
        """
        self.content = content  # Fake model response content.
        self.calls: list[dict] = []  # Model call history list.

    def complete(self, messages: list[dict[str, str]], options: dict) -> LLMResponse:
        """Return the preset model response

        Business logic:
            1. Record call messages and options
            2. Return a standard LLMResponse
            3. Avoid real network access during tests

        Args:
            messages (list[dict[str, str]]): Prompt message list.
            options (dict): Model call options.

        Returns:
            LLMResponse: Normalized model response.

        Examples:
            >>> FakeLLMClient('{}').complete([], {}).content
            '{}'
        """
        self.calls.append({"messages": messages, "options": options})
        return LLMResponse(
            content=self.content,
            model="test-model",
            provider="openai",
            request_id="fake-request",
            usage={"total_tokens": 10},
            latency_ms=3,
        )


def test_prompt_template_store_renders_instruction_generation(tmp_path: Path) -> None:
    """Verify that the prompt template can inject seed variables

    Business logic:
        1. Write a temporary prompt template
        2. Render messages through PromptTemplateStore
        3. Validate that system and user prompts include task variables

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_prompt_template_store_renders_instruction_generation)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "instruction_generation.yaml").write_text(
        """
system: "You are a {{ role }}."
user: "Topic={{ topic }}; Audience={{ audience }}; Prompt={{ prompt }}"
""",
        encoding="utf-8",
    )

    messages = PromptTemplateStore(prompt_dir).render(
        "instruction_generation",
        {"role": "data synthesizer", "topic": "quality gates", "audience": "engineers", "prompt": "Make data."},
    )

    assert messages == [
        {"role": "system", "content": "You are a data synthesizer."},
        {"role": "user", "content": "Topic=quality gates; Audience=engineers; Prompt=Make data."},
    ]


def test_prompt_template_store_uses_builtin_prompt_library() -> None:
    """Verify that the built-in prompt library can render the default template

    Business logic:
        1. Load PromptTemplateStore without a custom prompt directory
        2. Render the packaged instruction_generation template
        3. Validate that built-in variables are expanded into system and user messages

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_prompt_template_store_uses_builtin_prompt_library)
        True
    """
    messages = PromptTemplateStore().render(
        "instruction_generation",
        {
            "seed_id": "seed-001",
            "prompt": "Write a workflow summary.",
            "topic": "prompt library",
            "audience": "operators",
            "style": "concise",
        },
    )

    assert messages[0]["role"] == "system"
    assert "Return only a JSON object." in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Seed id: seed-001" in messages[1]["content"]
    assert "Topic: prompt library" in messages[1]["content"]
    assert "Audience: operators" in messages[1]["content"]


def test_prompt_template_store_renders_structured_template_with_metadata(tmp_path: Path) -> None:
    """Verify that structured prompt templates render metadata and messages

    Business logic:
        1. Write a structured prompt template with metadata and output_schema
        2. Render it through PromptTemplateStore.render_prompt
        3. Validate rendered metadata, messages, and schema fields

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_prompt_template_store_renders_structured_template_with_metadata)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "question_answering.yaml").write_text(
        """
metadata:
  task: qa
  audience: "{{ audience }}"
messages:
  - role: system
    content: "Answer {{ topic }} questions."
  - role: user
    content: "Question={{ prompt }}; Context={{ context }}"
output_schema:
  type: object
  required:
    - instruction
    - output
  properties:
    instruction:
      type: string
      description: "{{ topic }} question"
""",
        encoding="utf-8",
    )

    rendered = PromptTemplateStore(prompt_dir).render_prompt(
        "question_answering",
        {
            "topic": "workflow quality",
            "audience": "engineers",
            "prompt": "How should retries work?",
            "context": "Assume the workflow uses structured issues.",
        },
    )

    assert rendered.metadata == {"task": "qa", "audience": "engineers"}
    assert rendered.messages == [
        {"role": "system", "content": "Answer workflow quality questions."},
        {
            "role": "user",
            "content": "Question=How should retries work?; Context=Assume the workflow uses structured issues.",
        },
    ]
    assert rendered.output_schema["required"] == ["instruction", "output"]
    assert rendered.output_schema["properties"]["instruction"]["description"] == "workflow quality question"


def test_prompt_template_store_reports_missing_template(tmp_path: Path) -> None:
    """Verify that missing prompt templates fail with the resolved path

    Business logic:
        1. Create an empty prompt directory
        2. Try to render a template that does not exist
        3. Validate that the error points to the missing file path

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_prompt_template_store_reports_missing_template)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()

    try:
        PromptTemplateStore(prompt_dir).render("missing_template", {"prompt": "x"})
    except FileNotFoundError as exc:
        assert str(prompt_dir / "missing_template.yaml") in str(exc)
    else:
        raise AssertionError("missing prompt template should fail")


def test_text_llm_synthesis_operator_writes_generated_fields_and_lineage(tmp_path: Path) -> None:
    """Verify that LLM text synthesis writes output fields and lineage

    Business logic:
        1. Build a fake LLM JSON response
        2. Execute text_llm_synthesis
        3. Validate instruction/input/output/text and lineage

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_synthesis_operator_writes_generated_fields_and_lineage)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "instruction_generation.yaml").write_text(
        """
system: "Create instruction data."
user: "Topic={{ topic }}; Audience={{ audience }}"
""",
        encoding="utf-8",
    )
    llm = FakeLLMClient(
        json.dumps(
            {
                "instruction": "Explain workflow quality gates.",
                "input": "A data workflow needs validation.",
                "output": "Use schema checks, safety filters, and metrics.",
            }
        )
    )
    operator = TextLLMSynthesisOperator(
        {
            "prompt_dir": prompt_dir.as_posix(),
            "prompt_template": "instruction_generation",
            "model_ref": "text_generation",
            "llm_client": llm,
            "model_config": {"model": "test-model", "provider": "openai"},
        }
    )
    item = GenerationItem.from_dict(
        {
            "id": "seed-1",
            "task_type": "text",
            "prompt": "Generate an instruction sample.",
            "payload": {"topic": "quality gates", "audience": "engineers"},
        }
    )

    result = operator.process(item)

    assert result.generated["instruction"] == "Explain workflow quality gates."
    assert result.generated["input"] == "A data workflow needs validation."
    assert result.generated["output"] == "Use schema checks, safety filters, and metrics."
    assert "Explain workflow quality gates." in result.generated["text"]
    assert result.generated["format"] == "instruction_json"
    assert result.lineage["generator"] == "text_llm_synthesis"
    assert result.lineage["model_provider"] == "openai"
    assert result.lineage["model"] == "test-model"
    assert result.lineage["prompt_template"] == "instruction_generation"
    assert result.lineage["prompt_metadata"] == {}
    assert result.lineage["prompt_output_schema"] == {}
    assert result.lineage["llm_request_id"] == "fake-request"
    assert result.lineage["schema_validation"]["valid"] is True
    assert llm.calls[0]["messages"][1]["content"] == "Topic=quality gates; Audience=engineers"


def test_text_llm_synthesis_operator_records_structured_prompt_metadata(tmp_path: Path) -> None:
    """Verify that structured prompt template metadata is recorded in lineage

    Business logic:
        1. Write a structured question-enhancement prompt template
        2. Execute text_llm_synthesis with a fake JSON response
        3. Validate lineage prompt metadata and output schema persistence

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_synthesis_operator_records_structured_prompt_metadata)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "question_enhancement.yaml").write_text(
        """
metadata:
  task: question_enhancement
  family: augmentation
  audience: "{{ audience }}"
messages:
  - role: system
    content: "Improve user questions."
  - role: user
    content: "Question={{ prompt }}; Goal={{ enhancement_goal }}"
output_schema:
  type: object
  properties:
    instruction:
      type: string
    input:
      type: string
    output:
      type: string
""",
        encoding="utf-8",
    )
    llm = FakeLLMClient(
        json.dumps(
            {
                "instruction": "Clarify the workflow retry policy question.",
                "input": "The user needs more implementation detail.",
                "output": "What retry policy should a workflow engine use for invalid LLM JSON responses?",
            }
        )
    )
    operator = TextLLMSynthesisOperator(
        {
            "prompt_dir": prompt_dir.as_posix(),
            "prompt_template": "question_enhancement",
            "llm_client": llm,
            "model_config": {"model": "test-model", "provider": "openai"},
        }
    )
    item = GenerationItem.from_dict(
        {
            "id": "seed-structured-1",
            "task_type": "text",
            "prompt": "How do retries work?",
            "payload": {"audience": "operators", "enhancement_goal": "ask for concrete retry semantics"},
        }
    )

    result = operator.process(item)

    assert result.generated["instruction"] == "Clarify the workflow retry policy question."
    assert result.lineage["prompt_template"] == "question_enhancement"
    assert result.lineage["prompt_metadata"] == {
        "task": "question_enhancement",
        "family": "augmentation",
        "audience": "operators",
    }
    assert result.lineage["prompt_output_schema"]["type"] == "object"
    assert result.lineage["prompt_output_schema"]["properties"]["output"]["type"] == "string"
    assert llm.calls[0]["messages"] == [
        {"role": "system", "content": "Improve user questions."},
        {
            "role": "user",
            "content": "Question=How do retries work?; Goal=ask for concrete retry semantics",
        },
    ]


def test_text_llm_synthesis_operator_uses_builtin_prompt_library_by_default() -> None:
    """Verify that text_llm_synthesis works without a custom prompt directory

    Business logic:
        1. Create the operator with only a built-in prompt template name
        2. Process one text sample through the fake LLM client
        3. Validate generated fields and recorded built-in template lineage

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_synthesis_operator_uses_builtin_prompt_library_by_default)
        True
    """
    llm = FakeLLMClient(
        json.dumps(
            {
                "instruction": "Summarize the prompt library behavior.",
                "input": "",
                "output": "Use the packaged template unless prompt_dir overrides it.",
            }
        )
    )
    operator = TextLLMSynthesisOperator(
        {
            "prompt_template": "instruction_generation",
            "llm_client": llm,
            "model_config": {"model": "test-model", "provider": "openai"},
        }
    )
    item = GenerationItem.from_dict(
        {
            "id": "seed-built-in",
            "task_type": "text",
            "prompt": "Explain the default prompt behavior.",
            "payload": {"topic": "prompt library", "audience": "operators"},
        }
    )

    result = operator.process(item)

    assert result.generated["instruction"] == "Summarize the prompt library behavior."
    assert result.lineage["prompt_template"] == "instruction_generation"
    assert result.lineage["schema_validation"]["valid"] is True
    assert "Seed id: seed-built-in" in llm.calls[0]["messages"][1]["content"]
    assert "Topic: prompt library" in llm.calls[0]["messages"][1]["content"]


def test_text_llm_synthesis_operator_marks_non_json_for_retry(tmp_path: Path) -> None:
    """Verify that a non-JSON model response requests a retry

    Business logic:
        1. Build a non-JSON fake response
        2. Execute the LLM text-synthesis operator
        3. Validate that the sample enters needs_retry and records an issue

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_synthesis_operator_marks_non_json_for_retry)
        True
    """
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "instruction_generation.yaml").write_text(
        """
system: "Create instruction data."
user: "Topic={{ topic }}"
""",
        encoding="utf-8",
    )
    operator = TextLLMSynthesisOperator(
        {
            "prompt_dir": prompt_dir.as_posix(),
            "prompt_template": "instruction_generation",
            "llm_client": FakeLLMClient("not json"),
            "model_config": {"model": "test-model", "provider": "openai"},
        }
    )
    item = GenerationItem.from_dict({"id": "seed-2", "task_type": "text", "prompt": "Generate."})

    result = operator.process(item)

    assert result.action == "needs_retry"
    assert result.issues[0]["type"] == "llm_response_invalid_json"
    assert result.lineage["schema_validation"]["valid"] is False


def test_text_llm_workflow_runs_with_fake_client(tmp_path: Path) -> None:
    """Verify the narrow LLM text workflow path

    Business logic:
        1. Write temporary seed, prompt, and workflow files
        2. Execute the full workflow through the fake client
        3. Validate that generated.jsonl contains LLM synthesis fields

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_workflow_runs_with_fake_client)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    prompt_dir = tmp_path / "prompts"
    output_dir = tmp_path / "runs"
    prompt_dir.mkdir()
    seed_path.write_text(
        """
items:
  - id: llm_text
    task_type: text
    prompt: Generate a sample.
    payload:
      topic: model prompts
      audience: developers
""",
        encoding="utf-8",
    )
    (prompt_dir / "instruction_generation.yaml").write_text(
        """
system: "Create instruction data."
user: "Topic={{ topic }}; Audience={{ audience }}"
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: test_llm_text
  retry_limit: 1
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      stages:
        text_llm_synthesis:
          prompt_dir: {prompt_dir.as_posix()}
          prompt_template: instruction_generation
          llm_client:
            type: fake
            content: '{{"instruction":"Design prompts.","input":"Need synthetic data.","output":"Call an LLM and validate JSON output."}}'
          model_config:
            model: test-model
            provider: openai
        text_format_validate:
          min_length: 20
        quality_gate:
          pass_score: 0.7
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()
    generated = (run_dir / "generated.jsonl").read_text(encoding="utf-8")

    assert "llm_text" in generated
    assert "Design prompts." in generated
    assert "text_llm_synthesis" in generated


def test_llm_config_reports_missing_required_environment(monkeypatch: MonkeyPatch) -> None:
    """Verify that a missing key environment variable fails clearly

    Business logic:
        1. Clear the test environment variable
        2. Build model config from api_key_env
        3. Validate that the error message contains the missing variable name

    Args:
        monkeypatch: Environment-variable patching helper provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_llm_config_reports_missing_required_environment)
        True
    """
    monkeypatch.delenv("MISSING_LLM_KEY", raising=False)

    try:
        LLMClientConfig.from_dict({"provider": "openai", "model": "test", "api_key_env": "MISSING_LLM_KEY"})
    except LLMClientError as exc:
        assert "MISSING_LLM_KEY" in str(exc)
    else:
        raise AssertionError("missing api_key_env should fail")


def test_text_llm_operator_resolves_model_ref_from_registry(tmp_path: Path) -> None:
    """Verify that the operator can resolve model_ref from the model registry

    Business logic:
        1. Write a temporary model-registry file
        2. Create an operator configured only with model_ref
        3. Validate that the target model config is resolved correctly

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_text_llm_operator_resolves_model_ref_from_registry)
        True
    """
    registry_path = tmp_path / "model_registry.yaml"
    registry_path.write_text(
        """
models:
  text_generation:
    provider: openai
    enabled: true
    model: test-model
""",
        encoding="utf-8",
    )

    config = TextLLMSynthesisOperator(
        {"model_ref": "text_generation", "model_registry_path": registry_path.as_posix()}
    )._resolve_model_config()

    assert config["model"] == "test-model"
