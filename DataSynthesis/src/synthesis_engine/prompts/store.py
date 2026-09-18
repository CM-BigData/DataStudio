from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RenderedPromptTemplate:
    """Represent a rendered prompt template

    Business logic:
        1. Keep rendered metadata for prompt-library introspection
        2. Keep fully rendered OpenAI-compatible messages
        3. Keep an optional output schema for downstream validation hints

    Args:
        metadata (dict[str, Any]): Rendered template metadata.
        messages (list[dict[str, str]]): Rendered message list.
        output_schema (dict[str, Any]): Rendered output schema.

    Returns:
        None: Dataclass instances expose rendered prompt parts.

    Examples:
        >>> RenderedPromptTemplate({}, [], {}).metadata
        {}
    """

    metadata: dict[str, Any]
    messages: list[dict[str, str]]
    output_schema: dict[str, Any]


class PromptTemplateStore:
    def __init__(self, prompt_dir: str | Path | None = None) -> None:
        """Initialize the prompt template store

        Business logic:
            1. Accept an external prompt directory
            2. Use the package default prompts directory when none is provided
            3. Store the path for later template loading

        Args:
            prompt_dir (str | Path | None): Prompt template directory.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> PromptTemplateStore('x').prompt_dir.name
            'x'
        """
        self.prompt_dir = Path(prompt_dir) if prompt_dir else Path(__file__).resolve().parent  # Directory containing prompt YAML templates.

    def render(self, template_name: str, variables: dict[str, Any]) -> list[dict[str, str]]:
        """Render a prompt template into a message list

        Business logic:
            1. Load the YAML file by template name
            2. Normalize legacy or structured template fields
            3. Return OpenAI-compatible messages for existing callers

        Args:
            template_name (str): Template name, optionally without the .yaml suffix.
            variables (dict[str, Any]): Render variables.

        Returns:
            list[dict[str, str]]: System and user message list.

        Examples:
            >>> callable(PromptTemplateStore.render)
            True
        """
        return self.render_prompt(template_name, variables).messages

    def render_prompt(self, template_name: str, variables: dict[str, Any]) -> RenderedPromptTemplate:
        """Render a prompt template into a structured prompt object

        Business logic:
            1. Load the YAML file by template name
            2. Normalize legacy or structured template fields
            3. Render metadata, messages, and output schema with the provided variables

        Args:
            template_name (str): Template name, optionally without the .yaml suffix.
            variables (dict[str, Any]): Render variables.

        Returns:
            RenderedPromptTemplate: Structured rendered prompt.

        Examples:
            >>> isinstance(PromptTemplateStore().render_prompt('instruction_generation', {}), RenderedPromptTemplate)
            True
        """
        raw = self._load_template(template_name)
        normalized = self._normalize_template(template_name, raw)
        metadata = _render_mapping(normalized["metadata"], variables)
        messages = _render_messages(normalized["messages"], variables)
        output_schema = _render_mapping(normalized["output_schema"], variables)
        if not messages:  # An empty template cannot form callable model messages.
            raise ValueError(f"Prompt template '{template_name}' has no callable messages")
        return RenderedPromptTemplate(metadata=metadata, messages=messages, output_schema=output_schema)

    def _load_template(self, template_name: str) -> dict[str, Any]:
        """Load a prompt YAML template

        Business logic:
            1. Normalize the template filename
            2. Read YAML from prompt_dir
            3. Validate that the template root node is a dictionary

        Args:
            template_name (str): Template name.

        Returns:
            dict[str, Any]: Template configuration.

        Examples:
            >>> callable(PromptTemplateStore._load_template)
            True
        """
        filename = template_name if template_name.endswith(".yaml") else f"{template_name}.yaml"
        path = self.prompt_dir / filename
        if not path.exists():  # Expose bad template names before runtime work begins.
            raise FileNotFoundError(f"Prompt template not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):  # Prompt-template root nodes must be mappings.
            raise ValueError(f"Prompt template must be a mapping: {path}")
        return raw

    def _normalize_template(self, template_name: str, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize legacy and structured prompt templates

        Business logic:
            1. Accept legacy top-level system and user templates without changes
            2. Accept structured metadata, messages, and output_schema templates
            3. Validate the minimal fields needed for prompt rendering

        Args:
            template_name (str): Template name for error messages.
            raw (dict[str, Any]): Raw YAML mapping.

        Returns:
            dict[str, Any]: Normalized template fields.

        Examples:
            >>> PromptTemplateStore()._normalize_template('x', {'system': 'a', 'user': 'b'})['messages'][0]['role']
            'system'
        """
        if "messages" not in raw:
            messages: list[dict[str, Any]] = []
            system = str(raw.get("system", ""))
            user = str(raw.get("user", ""))
            if system:  # The system prompt is optional, but must be the first message when present.
                messages.append({"role": "system", "content": system})
            if user:  # The user prompt carries seed variables and output requirements.
                messages.append({"role": "user", "content": user})
            return {"metadata": {}, "messages": messages, "output_schema": {}}

        metadata = raw.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):  # Metadata must remain an object for prompt-library tooling.
            raise ValueError(f"Prompt template '{template_name}' metadata must be a mapping")

        output_schema = raw.get("output_schema", {})
        if output_schema is None:
            output_schema = {}
        if not isinstance(output_schema, dict):  # Schema metadata must remain an object for downstream inspection.
            raise ValueError(f"Prompt template '{template_name}' output_schema must be a mapping")

        messages_raw = raw.get("messages")
        if not isinstance(messages_raw, list):  # Structured templates must expose an ordered message list.
            raise ValueError(f"Prompt template '{template_name}' messages must be a list")

        messages: list[dict[str, Any]] = []
        for index, message in enumerate(messages_raw):
            if not isinstance(message, dict):  # Each message must be an object with role/content fields.
                raise ValueError(f"Prompt template '{template_name}' message {index} must be a mapping")
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or not role.strip():
                raise ValueError(f"Prompt template '{template_name}' message {index} role must be a non-empty string")
            if not isinstance(content, str):
                raise ValueError(f"Prompt template '{template_name}' message {index} content must be a string")
            normalized_message = dict(message)
            normalized_message["role"] = role.strip()
            normalized_message["content"] = content
            messages.append(normalized_message)
        return {"metadata": metadata, "messages": messages, "output_schema": output_schema}


def _render_text(template: str, variables: dict[str, Any]) -> str:
    """Render double-brace variables

    Business logic:
        1. Match variables in the {{ name }} form
        2. Read values from the variable table and cast them to strings
        3. Replace missing variables with empty strings

    Args:
        template (str): Raw template text.
        variables (dict[str, Any]): Variable dictionary.

    Returns:
        str: Rendered text.

    Examples:
        >>> _render_text('Hello {{ name }}', {'name': 'Codex'})
        'Hello Codex'
    """
    rendered = template
    for key, value in variables.items():  # Replace double-brace variables one by one to avoid adding regex dependencies.
        rendered = rendered.replace("{{ " + str(key) + " }}", str(value))
        rendered = rendered.replace("{{" + str(key) + "}}", str(value))
    return rendered


def _render_messages(messages: list[dict[str, Any]], variables: dict[str, Any]) -> list[dict[str, str]]:
    """Render a structured message list

    Business logic:
        1. Render each string field in every message
        2. Preserve the original message ordering
        3. Return OpenAI-compatible dictionaries for model clients

    Args:
        messages (list[dict[str, Any]]): Raw message templates.
        variables (dict[str, Any]): Render variables.

    Returns:
        list[dict[str, str]]: Rendered message list.

    Examples:
        >>> _render_messages([{'role': 'user', 'content': 'Hi {{ name }}'}], {'name': 'Codex'})[0]['content']
        'Hi Codex'
    """
    return [_render_mapping(message, variables) for message in messages]


def _render_mapping(template: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """Render a mapping recursively

    Business logic:
        1. Walk each key and preserve the original structure
        2. Render string values recursively in nested lists and mappings
        3. Leave non-string scalar values unchanged

    Args:
        template (dict[str, Any]): Mapping to render.
        variables (dict[str, Any]): Render variables.

    Returns:
        dict[str, Any]: Rendered mapping.

    Examples:
        >>> _render_mapping({'title': '{{ topic }}'}, {'topic': 'Safety'})['title']
        'Safety'
    """
    return {str(key): _render_value(value, variables) for key, value in template.items()}


def _render_value(value: Any, variables: dict[str, Any]) -> Any:
    """Render nested template values

    Business logic:
        1. Render string values with double-brace variables
        2. Render nested mappings and lists recursively
        3. Preserve non-string scalar values without conversion

    Args:
        value (Any): Template value.
        variables (dict[str, Any]): Render variables.

    Returns:
        Any: Rendered value with the same container shape.

    Examples:
        >>> _render_value(['{{ topic }}'], {'topic': 'Quality'})[0]
        'Quality'
    """
    if isinstance(value, str):
        return _render_text(value, variables)
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return _render_mapping(value, variables)
    return value
