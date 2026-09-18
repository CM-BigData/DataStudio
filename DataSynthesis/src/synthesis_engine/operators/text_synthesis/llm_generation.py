from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from synthesis_engine.llm import LLMClientConfig, LLMClientError, LLMResponse, OpenAIClient
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.prompts import PromptTemplateStore


class TextLLMSynthesisOperator(BaseOperator):
    operator_name: str = "text_llm_synthesis"  # LLM text synthesis operator name used in workflows.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Call the LLM to synthesize instruction-style text samples

        Business logic:
            1. Skip non-text task samples
            2. Render the prompt and call the LLM client
            3. Validate JSON output and write generated fields plus lineage

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Sample updated with LLM output or retry issues.

        Examples:
            >>> TextLLMSynthesisOperator().operator_name
            'text_llm_synthesis'
        """
        if item.task_type != "text":  # The LLM text operator only handles text samples.
            return item

        template_name = str(self.config.get("prompt_template", "instruction_generation"))
        variables = self._build_prompt_variables(item)
        rendered_prompt = PromptTemplateStore(self.config.get("prompt_dir")).render_prompt(template_name, variables)
        messages = rendered_prompt.messages
        client = self._build_client()
        try:
            response = client.complete(messages, self._call_options())
        except LLMClientError as exc:  # Route model-call failures into the retry path instead of failing the batch.
            return self._mark_retry(item, "llm_call_failed", str(exc), {"valid": False, "error": "llm_call_failed"})

        parsed = _parse_json_object(response.content)
        if not parsed["valid"]:  # Non-JSON output cannot enter later quality gates, so request a retry first.
            return self._mark_retry(
                item,
                "llm_response_invalid_json",
                parsed["message"],
                {"valid": False, "error": "invalid_json"},
                response,
                template_name,
                variables,
                rendered_prompt.metadata,
                rendered_prompt.output_schema,
            )

        validated = _validate_instruction_payload(parsed["data"])
        if not validated["valid"]:  # Missing fields or wrong types count as schema failures.
            return self._mark_retry(
                item,
                "llm_response_schema_invalid",
                validated["message"],
                {"valid": False, "error": "schema_invalid", "details": validated["details"]},
                response,
                template_name,
                variables,
                rendered_prompt.metadata,
                rendered_prompt.output_schema,
            )

        data = parsed["data"]
        item.generated["instruction"] = data["instruction"]
        item.generated["input"] = data["input"]
        item.generated["output"] = data["output"]
        item.generated["text"] = _join_text(data)
        item.generated["format"] = "instruction_json"
        self._write_lineage(
            item,
            response,
            template_name,
            variables,
            {"valid": True},
            rendered_prompt.metadata,
            rendered_prompt.output_schema,
        )
        return item

    def _build_prompt_variables(self, item: GenerationItem) -> dict[str, Any]:
        """Build prompt-rendering variables

        Business logic:
            1. Copy business variables from the sample payload
            2. Fill in seed_id, prompt, topic, audience, and style
            3. Return the variables required for template rendering

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            dict[str, Any]: Prompt variables.

        Examples:
            >>> TextLLMSynthesisOperator()._build_prompt_variables(GenerationItem('a', 'text', 'p'))['seed_id']
            'a'
        """
        variables = dict(item.payload)
        variables.setdefault("seed_id", item.id)
        variables.setdefault("prompt", item.prompt)
        variables.setdefault("topic", item.payload.get("topic", item.prompt))
        variables.setdefault("audience", item.payload.get("audience", "data engineer"))
        variables.setdefault("style", item.payload.get("style", "concise"))
        return variables

    def _build_client(self) -> Any:
        """Create or retrieve the LLM client

        Business logic:
            1. Allow tests to inject a client object directly
            2. Build a local fake client from fake config
            3. Otherwise create OpenAIClient from model_config

        Args:
            None.

        Returns:
            Any: Client object exposing a complete method.

        Examples:
            >>> hasattr(TextLLMSynthesisOperator({'llm_client': {'type': 'fake', 'content': '{}'}})._build_client(), 'complete')
            True
        """
        configured = self.config.get("llm_client")
        if configured is not None and hasattr(configured, "complete"):  # Unit tests may inject a fake client object.
            return configured
        if isinstance(configured, dict) and configured.get("type") == "fake":  # Workflow tests use a config-driven fake client.
            return _FakeLLMClient(str(configured.get("content", "{}")))
        model_config = self._resolve_model_config()
        return OpenAIClient(LLMClientConfig.from_dict(model_config))

    def _resolve_model_config(self) -> dict[str, Any]:
        """Resolve model registration configuration

        Business logic:
            1. Prefer inline operator model_config
            2. Otherwise read the model registry through model_ref
            3. Validate that the model exists and is enabled

        Args:
            None.

        Returns:
            dict[str, Any]: Model configuration.

        Examples:
            >>> TextLLMSynthesisOperator({'model_config': {'model': 'test'}})._resolve_model_config()['model']
            'test'
        """
        if self.config.get("model_config"):  # Prefer inline config to support single-file workflow examples.
            return dict(self.config["model_config"])
        model_ref = str(self.config.get("model_ref", "text_generation"))
        registry_path = Path(self.config.get("model_registry_path", "configs/model_registry.yaml"))
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        models = raw.get("models", {})
        if model_ref not in models:  # model_ref must point to an entry in the registry.
            raise LLMClientError(f"Model ref not found: {model_ref}")
        model_config = dict(models[model_ref])
        if not model_config.get("enabled", False):  # Disabled models must not be called silently at runtime.
            raise LLMClientError(f"Model ref is disabled: {model_ref}")
        return model_config

    def _call_options(self) -> dict[str, Any]:
        """Read per-call override options for the model request

        Business logic:
            1. Read response_format from operator config
            2. Convert JSON mode into an OpenAI-compatible response_format
            3. Return options that can be passed to the LLM client

        Args:
            None.

        Returns:
            dict[str, Any]: Call override options.

        Examples:
            >>> TextLLMSynthesisOperator({'response_format': 'json'})._call_options()['response_format']['type']
            'json_object'
        """
        options = dict(self.config.get("call_options", {}))
        if self.config.get("response_format") == "json":  # Try to request a JSON object directly from the provider.
            options["response_format"] = {"type": "json_object"}
        return options

    def _mark_retry(
        self,
        item: GenerationItem,
        issue_type: str,
        message: str,
        schema_validation: dict[str, Any],
        response: LLMResponse | None = None,
        template_name: str | None = None,
        variables: dict[str, Any] | None = None,
        prompt_metadata: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> GenerationItem:
        """Mark a sample as needing retry

        Business logic:
            1. Set action to needs_retry
            2. Append a structured issue
            3. Write auditable lineage

        Args:
            item (GenerationItem): Sample to mark.
            issue_type (str): Issue type.
            message (str): Issue description.
            schema_validation (dict[str, Any]): Schema validation result.
            response (LLMResponse | None): Optional model response.
            template_name (str | None): Prompt template name.
            variables (dict[str, Any] | None): Prompt variables.
            prompt_metadata (dict[str, Any] | None): Rendered template metadata.
            output_schema (dict[str, Any] | None): Rendered template output schema.

        Returns:
            GenerationItem: Marked sample.

        Examples:
            >>> TextLLMSynthesisOperator()._mark_retry(GenerationItem('a', 'text', 'p'), 'x', 'm', {'valid': False}).action
            'needs_retry'
        """
        item.action = "needs_retry"
        item.issues.append({"type": issue_type, "message": message})
        if response and template_name and variables is not None:  # Preserve full call auditing when a model response exists.
            self._write_lineage(
                item,
                response,
                template_name,
                variables,
                schema_validation,
                prompt_metadata or {},
                output_schema or {},
            )
        else:
            item.lineage["generator"] = self.operator_name
            item.lineage["schema_validation"] = schema_validation
        return item

    def _write_lineage(
        self,
        item: GenerationItem,
        response: LLMResponse,
        template_name: str,
        variables: dict[str, Any],
        schema_validation: dict[str, Any],
        prompt_metadata: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> None:
        """Write LLM call audit lineage

        Business logic:
            1. Record the generator, model, and prompt template
            2. Record request id, usage, and latency
            3. Record schema validation results

        Args:
            item (GenerationItem): Generated sample.
            response (LLMResponse): Model response.
            template_name (str): Prompt template name.
            variables (dict[str, Any]): Prompt variables.
            schema_validation (dict[str, Any]): Schema validation result.
            prompt_metadata (dict[str, Any]): Rendered template metadata.
            output_schema (dict[str, Any]): Rendered template output schema.

        Returns:
            None: Mutates item.lineage directly.

        Examples:
            >>> callable(TextLLMSynthesisOperator()._write_lineage)
            True
        """
        item.lineage["generator"] = self.operator_name
        item.lineage["model_provider"] = response.provider
        item.lineage["model"] = response.model
        item.lineage["prompt_template"] = template_name
        item.lineage["prompt_variables"] = variables
        item.lineage["prompt_metadata"] = prompt_metadata
        item.lineage["prompt_output_schema"] = output_schema
        item.lineage["llm_request_id"] = response.request_id
        item.lineage["llm_usage"] = response.usage
        item.lineage["llm_latency_ms"] = response.latency_ms
        item.lineage["schema_validation"] = schema_validation


class _FakeLLMClient:
    def __init__(self, content: str) -> None:
        """Initialize the local fake LLM client

        Business logic:
            1. Store the configured response text
            2. Let workflow tests avoid real network calls
            3. Return a standard LLMResponse

        Args:
            content (str): Fake response content.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> _FakeLLMClient('{}').content
            '{}'
        """
        self.content = content  # Fixed content returned by the fake client.

    def complete(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> LLMResponse:
        """Return a fake model response

        Business logic:
            1. Ignore external messages and options
            2. Return fixed JSON text
            3. Keep the same interface as the real client

        Args:
            messages (list[dict[str, str]]): Prompt messages.
            options (dict[str, Any] | None): Call options.

        Returns:
            LLMResponse: Normalized fake response.

        Examples:
            >>> _FakeLLMClient('{}').complete([], {}).provider
            'openai'
        """
        return LLMResponse(content=self.content, model="openai/fake", provider="openai", request_id="fake")


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse an LLM JSON-object response

    Business logic:
        1. Remove common Markdown code fences
        2. Parse the object with json.loads
        3. Return a parse result containing a valid flag

    Args:
        content (str): Model response text.

    Returns:
        dict[str, Any]: Parse result.

    Examples:
        >>> _parse_json_object('{"a": 1}')['valid']
        True
    """
    cleaned = _strip_json_fence(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:  # Enter the retry path when the provider returns natural language.
        return {"valid": False, "message": f"LLM response is not valid JSON: {exc.msg}", "data": None}
    if not isinstance(data, dict):  # The first-version schema requires the top level to be an object.
        return {"valid": False, "message": "LLM response JSON must be an object", "data": None}
    return {"valid": True, "message": "", "data": data}


def _strip_json_fence(content: str) -> str:
    """Remove JSON code fences

    Business logic:
        1. Trim leading and trailing whitespace
        2. Support ```json fenced code blocks
        3. Return text ready for json.loads

    Args:
        content (str): Raw model text.

    Returns:
        str: Cleaned text.

    Examples:
        >>> _strip_json_fence('```json\\n{}\\n```')
        '{}'
    """
    text = content.strip()
    if text.startswith("```"):  # Support model responses occasionally wrapped in Markdown fences.
        lines = text.splitlines()
        if lines:  # The first line is ``` or ```json.
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":  # The last line is the closing fence.
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _validate_instruction_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the instruction-sample JSON schema

    Business logic:
        1. Check required instruction, input, and output fields
        2. Ensure all fields are strings
        3. Ensure instruction and output are not empty

    Args:
        data (dict[str, Any]): LLM output object.

    Returns:
        dict[str, Any]: Validation result.

    Examples:
        >>> _validate_instruction_payload({'instruction': 'i', 'input': '', 'output': 'o'})['valid']
        True
    """
    required = ["instruction", "input", "output"]
    missing = [field for field in required if field not in data]
    if missing:  # Missing required fields prevent construction of a training sample.
        return {"valid": False, "message": f"Missing required fields: {', '.join(missing)}", "details": {"missing": missing}}
    wrong_types = [field for field in required if not isinstance(data[field], str)]
    if wrong_types:  # Instruction-sample fields must all be strings.
        return {
            "valid": False,
            "message": f"Fields must be strings: {', '.join(wrong_types)}",
            "details": {"wrong_types": wrong_types},
        }
    empty = [field for field in ["instruction", "output"] if not data[field].strip()]
    if empty:  # instruction and output are the minimum fields for a usable sample.
        return {"valid": False, "message": f"Fields cannot be empty: {', '.join(empty)}", "details": {"empty": empty}}
    return {"valid": True, "message": "", "details": {}}


def _join_text(data: dict[str, str]) -> str:
    """Join generated text in a format compatible with existing text validation

    Business logic:
        1. Read instruction, input, and output fields
        2. Concatenate them into plain text with stable labels
        3. Return text used by format validation and deduplication

    Args:
        data (dict[str, str]): Instruction-sample fields.

    Returns:
        str: Joined text.

    Examples:
        >>> 'Instruction:' in _join_text({'instruction': 'i', 'input': '', 'output': 'o'})
        True
    """
    return f"Instruction: {data['instruction']}\nInput: {data['input']}\nOutput: {data['output']}"
