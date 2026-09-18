from __future__ import annotations

from pathlib import Path

from synthesis_engine.runtime.registry import _validate_operator_name


OPERATOR_TYPE_GUIDANCE = {  # Template guidance mapping operator types to input fields and example logic.
    "text": {
        "input": "item.prompt and item.payload",
        "read": "prompt = item.prompt\npayload = item.payload",
        "example": 'item.generated["items"] = [{"instruction": prompt, "input": "", "output": "Example output"}]\nitem.metrics["custom_score"] = 1.0\nitem.action = "accepted"',
    },
    "image": {
        "input": "item.prompt and item.payload",
        "read": "prompt = item.prompt\npayload = item.payload",
        "example": 'item.generated["image_prompt"] = prompt\nitem.metrics["custom_image_ready"] = True',
    },
    "structured": {
        "input": "schema or field constraints inside item.payload",
        "read": "payload = item.payload\nschema = payload.get(\"schema\", {})",
        "example": 'item.generated["records"] = []\nitem.metrics["custom_structured_ready"] = bool(schema)',
    },
    "quality_gate": {
        "input": "item.issues and item.metrics",
        "read": "issues = item.issues\nmetrics = item.metrics",
        "example": 'item.action = "filtered" if issues else "accepted"',
    },
}


def render_operator_template(operator_type: str, operator_name: str) -> str:
    """Render a synthesis custom-operator template

    Business logic:
        1. Validate the operator type and operator_name
        2. Choose GenerationItem input/output guidance by type
        3. Return loadable Python source code

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registry name.

    Returns:
        str: Python template source code.

    Examples:
        >>> "GenerationItem" in render_operator_template("text", "my_operator")
        True
    """
    if operator_type not in OPERATOR_TYPE_GUIDANCE:  # Only generate templates for supported types.
        allowed = ", ".join(sorted(OPERATOR_TYPE_GUIDANCE))
        raise ValueError(f"unsupported operator template type: {operator_type}. Allowed: {allowed}")
    _validate_operator_name(operator_name)
    class_name = _operator_class_name(operator_name)
    guidance = OPERATOR_TYPE_GUIDANCE[operator_type]
    read_block = _indent(str(guidance["read"]), 8)
    example_block = _indent(str(guidance["example"]), 8)
    return f'''from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator


class {class_name}(BaseOperator):
    """Template for a user-defined {operator_type} synthesis operator.

    Usage:
        1. Add this file path to the top-level workflow custom_operators list.
        2. Use operator: {operator_name} inside steps.
        3. Only modify the code inside the business-logic section of process.

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

    def process(self, item: GenerationItem) -> GenerationItem:
        """Process a single generated sample.

        Input contract:
            - Recommended fields for this type: {guidance["input"]}
            - Read operator config from self.config, for example self.config.get("threshold")

        Output contract:
            - Write generated results into item.generated.
            - Write quality, quantity, or debugging metrics into item.metrics.
            - Append issue objects to item.issues, for example {{"type": "custom_issue", "message": "details"}}.
            - You may set item.action to accepted, filtered, failed, or needs_retry.
            - Do not remove core fields such as id, task_type, prompt, payload, generated, metrics, issues, or lineage.

        Args:
            item (GenerationItem): Standard generated sample passed in by the workflow.

        Returns:
            GenerationItem: Processed generated sample.

        Examples:
            >>> isinstance({class_name}().process(GenerationItem("a", "text", "p")), GenerationItem)
            True
        """
{read_block}

        # Business-logic section: start modifying from here.
        # The following block is only an example; rewrite it for your real rules.
{example_block}
        # Business-logic section: stop modifying here.

        return item
'''


def write_operator_template(operator_type: str, operator_name: str, output_path: Path) -> Path:
    """Write a synthesis custom-operator template

    Business logic:
        1. Render the template for the given type and name
        2. Create the output directory automatically
        3. Write a UTF-8 Python file

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registry name.
        output_path (Path): Output file path.

    Returns:
        Path: Path to the written file.

    Examples:
        >>> isinstance(write_operator_template, object)
        True
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_operator_template(operator_type, operator_name), encoding="utf-8")
    return output_path


def _operator_class_name(operator_name: str) -> str:
    """Convert a snake_case operator name into a class name

    Business logic:
        1. Split the registry name by underscores
        2. Capitalize each segment and join them
        3. Append the Operator suffix

    Args:
        operator_name (str): Snake_case operator name.

    Returns:
        str: Python class name.

    Examples:
        >>> _operator_class_name("my_operator")
        'MyOperatorOperator'
    """
    return "".join(part.capitalize() for part in operator_name.split("_")) + "Operator"


def _indent(text: str, spaces: int) -> str:
    """Indent a template code block

    Business logic:
        1. Add the requested number of spaces to each line
        2. Preserve empty-line structure
        3. Return text ready to embed inside a template

    Args:
        text (str): Raw text.
        spaces (int): Number of indentation spaces.

    Returns:
        str: Indented text.

    Examples:
        >>> _indent("x", 2)
        '  x'
    """
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())
