from __future__ import annotations

from pathlib import Path

from dedup_workflow_engine.runtime.registry import _validate_operator_name


OPERATOR_TYPE_GUIDANCE = {  # Template config: input fields and example logic for end-to-end dedup operators.
    "text": {
        "input": "item['payload']['text'], item['intermediate'], and context['duplicate_edges']",
        "read": "text = str(item.get(\"payload\", {}).get(\"text\", \"\"))",
        "example": 'self.set_metric(item, "custom_text_length", len(text))\nif not text.strip():\n    self.add_issue(item, "empty_text")\n    item["action"] = "review"',
    },
    "image": {
        "input": "item['payload']['image_path'], item['metrics'], and context['duplicate_edges']",
        "read": "image_path = item.get(\"payload\", {}).get(\"image_path\")",
        "example": 'self.set_metric(item, "custom_image_present", bool(image_path))\nif not image_path:\n    self.add_issue(item, "missing_image_path")\n    item["action"] = "review"',
    },
    "audio": {
        "input": "item['payload']['audio_path'], item['metrics'], and context['duplicate_edges']",
        "read": "audio_path = item.get(\"payload\", {}).get(\"audio_path\")",
        "example": 'self.set_metric(item, "custom_audio_present", bool(audio_path))\nif not audio_path:\n    self.add_issue(item, "missing_audio_path")\n    item["action"] = "review"',
    },
}


def render_operator_template(operator_type: str, operator_name: str) -> str:
    """Render a custom end-to-end deduplication operator template.

    Business logic:
        1. Validate the operator type and operator_name.
        2. Select the sample input and output guidance for the modality.
        3. Return Python source code that can be loaded directly.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registration name.

    Returns:
        str: Python template source code.

    Examples:
        >>> "BaseOperator" in render_operator_template("text", "my_operator")
        True
    """

    if operator_type not in OPERATOR_TYPE_GUIDANCE:  # Only predefined types can be generated.
        allowed = ", ".join(sorted(OPERATOR_TYPE_GUIDANCE))
        raise ValueError(f"unsupported operator template type: {operator_type}. Allowed: {allowed}")

    _validate_operator_name(operator_name)
    class_name = _operator_class_name(operator_name)
    guidance = OPERATOR_TYPE_GUIDANCE[operator_type]
    read_block = _indent(str(guidance["read"]), 8)
    example_block = _indent(str(guidance["example"]), 8)

    return f'''from __future__ import annotations

from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator


class {class_name}(BaseOperator):
    """Custom end-to-end {operator_type} deduplication operator template.

    Usage:
        1. Add this file path to workflow-level custom_operators.
        2. Use operator: {operator_name} in steps.
        3. Keep this class as one end-to-end workflow step; put intermediate logic in private helpers.

    Workflow example:
        custom_operators:
          - ./plugins/{operator_name}.py
        steps:
          - id: {operator_name}
            operator: {operator_name}
            params: {{}}
    """

    operator_name = "{operator_name}"
    operator_version = "1.0.0"

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Process a full dataset as one end-to-end deduplication operator.

        Input contract:
            - Recommended fields to read for this operator type: {guidance["input"]}
            - Read operator config from self.config, for example self.config.get("threshold")

        Output contract:
            - Keep normalization, recall, fusion, clustering, and selection logic inside this operator.
            - Write temporary results into item["intermediate"].
            - Write quality, count, or debug metrics into item["metrics"].
            - Append issue labels into item["issues"].
            - Set item["action"] to keep, remove, or review before returning.
            - Do not remove core fields such as id, modality, payload, meta, intermediate, metrics, issues, or action.

        Args:
            items (list[dict[str, Any]]): Standard deduplication samples passed in by the workflow.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Processed deduplication samples.

        Examples:
            >>> {class_name}().process_dataset([], {{}})
            []
        """
        for item in items:  # Process each sample inside this single end-to-end operator.
{_indent(str(guidance["read"]), 12)}

        # Business logic area: start modifying here.
        # The code below is only an example and should be rewritten for real rules.
{_indent(str(guidance["example"]), 12)}
        # Business logic area: stop modifying here.

        return items
'''


def write_operator_template(operator_type: str, operator_name: str, output_path: Path) -> Path:
    """Write a custom deduplication operator template.

    Business logic:
        1. Render the template for the specified type and name.
        2. Create the output directory automatically.
        3. Write the UTF-8 Python file.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registration name.
        output_path (Path): Output file path.

    Returns:
        Path: Path of the written file.

    Examples:
        >>> isinstance(write_operator_template, object)
        True
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_operator_template(operator_type, operator_name), encoding="utf-8")

    return output_path


def _operator_class_name(operator_name: str) -> str:
    """Convert a snake_case operator name into a class name.

    Business logic:
        1. Split the registration name by underscores.
        2. Capitalize and join each segment.
        3. Append the Operator suffix.

    Args:
        operator_name (str): snake_case operator name.

    Returns:
        str: Python class name.

    Examples:
        >>> _operator_class_name("my_operator")
        'MyOperatorOperator'
    """

    return "".join(part.capitalize() for part in operator_name.split("_")) + "Operator"


def _indent(text: str, spaces: int) -> str:
    """Indent a template code block.

    Business logic:
        1. Add the specified number of spaces to each line.
        2. Preserve the empty-line structure.
        3. Return text that can be embedded into the template.

    Args:
        text (str): Original text.
        spaces (int): Number of indentation spaces.

    Returns:
        str: Indented text.

    Examples:
        >>> _indent("x", 2)
        '  x'
    """
    prefix = " " * spaces

    return "\n".join(prefix + line if line else line for line in text.splitlines())
