from __future__ import annotations

from pathlib import Path

from quality_eval.runtime.registry import _validate_operator_name


OPERATOR_TYPE_GUIDANCE = {  # Template config describing inputs and example logic for different operator types.
    "text": {
        "input": "item['payload']['text'], item['metrics'], and item['issues']",
        "read": "text = str(item.get(\"payload\", {}).get(\"text\", \"\"))",
        "example": 'self.metric(item, "custom_text_length", len(text))\nif not text.strip():\n    self.add_issue(item, "empty_text")\n    item["action"] = "review"',
    },
    "image": {
        "input": "item['payload']['image_path'], item['metrics'], and item['issues']",
        "read": "image_path = item.get(\"payload\", {}).get(\"image_path\")",
        "example": 'self.metric(item, "custom_image_present", bool(image_path))\nif not image_path:\n    self.add_issue(item, "missing_image_path")\n    item["action"] = "review"',
    },
    "score": {
        "input": "item['metrics'], item['issues'], and item['score']",
        "read": "issues = item.get(\"issues\", [])\nmetrics = item.setdefault(\"metrics\", {})",
        "example": 'metrics["custom_issue_count"] = len(issues)\nitem["score"] = max(0, 100 - len(issues) * 10)\nitem["level"] = "excellent" if item["score"] >= 90 else "review_required"',
    },
    "governor": {
        "input": "item['action'], item['suggestions'], and quality issues",
        "read": "issues = item.get(\"issues\", [])",
        "example": 'if issues:\n    item["action"] = "review"\n    item.setdefault("suggestions", []).append("Please review the custom quality issues.")',
    },
}


def render_operator_template(operator_type: str, operator_name: str) -> str:
    """Render a custom operator template for quality-eval.

    Business logic:
        1. Validate the operator type and `operator_name`.
        2. Select dict sample input and output guidance by type.
        3. Return Python source code that can be loaded directly.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Registered operator name.

    Returns:
        str: Python template source code.

    Examples:
        >>> "BaseOperator" in render_operator_template("text", "my_operator")
        True
    """
    if operator_type not in OPERATOR_TYPE_GUIDANCE:  # Only predefined template types can be generated.
        allowed = ", ".join(sorted(OPERATOR_TYPE_GUIDANCE))
        raise ValueError(f"unsupported operator template type: {operator_type}. Allowed: {allowed}")
    _validate_operator_name(operator_name)
    class_name = _operator_class_name(operator_name)
    guidance = OPERATOR_TYPE_GUIDANCE[operator_type]
    read_block = _indent(str(guidance["read"]), 8)
    example_block = _indent(str(guidance["example"]), 8)
    return f'''from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator


class {class_name}(BaseOperator):
    """Custom {operator_type} quality-evaluation operator template.

    Usage:
        1. Add this file path to the top-level workflow `custom_operators`.
        2. Use `operator: {operator_name}` in `steps`.
        3. Modify only the code inside the business-logic area of the `process` method.

    Workflow example:
        custom_operators:
          - ./plugins/{operator_name}.py
        steps:
          - id: {operator_name}
            operator: {operator_name}
    """

    operator_name = "{operator_name}"
    operator_version = "1.0.0"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Process one quality-evaluation sample.

        Input contract:
            - Recommended fields for this type: {guidance["input"]}
            - Read operator config from `self.config` or `self.rules`, for example `self.rules.get("threshold")`

        Output contract:
            - Write quality, count, or debug metrics into `item["metrics"]`.
            - Append issue codes into `item["issues"]`.
            - Write scoring results into `item["score"]` and `item["level"]`.
            - Append handling suggestions into `item["suggestions"]`.
            - You may set `item["action"]` to `keep`, `review`, or `drop`.
            - Do not remove core fields such as `id`, `modality`, `source`, `payload`, `meta`, `intermediate`, `metrics`, `issues`, or `action`.

        Args:
            item (dict[str, Any]): Standard quality-evaluation sample provided by the workflow.

        Returns:
            dict[str, Any]: Processed quality-evaluation sample.

        Examples:
            >>> {class_name}({{}}).process({{"id": "a", "payload": {{"text": "x"}}}})["id"]
            'a'
        """
{read_block}

        # Business-logic area: start editing here.
        # The code below is only an example; rewrite it to match your real rules.
{example_block}
        # Business-logic area: end here.

        return item
'''


def write_operator_template(operator_type: str, operator_name: str, output_path: Path) -> Path:
    """Write a custom operator template for quality-eval.

    Business logic:
        1. Render the template for the specified type and name.
        2. Create the output directory automatically.
        3. Write a UTF-8 Python file.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Registered operator name.
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
    """Convert a snake_case operator name to a class name.

    Business logic:
        1. Split the registered name by underscores.
        2. Capitalize each segment and concatenate them.
        3. Append the `Operator` suffix.

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
        2. Preserve blank-line structure.
        3. Return text that can be embedded into the template.

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
