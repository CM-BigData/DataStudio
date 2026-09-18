from __future__ import annotations

from pathlib import Path

from denoise_workflow_engine.runtime.registry import _validate_operator_name


OPERATOR_TYPE_GUIDANCE = {  # Template guidance for each end-to-end custom operator type.
    "text_denoise": {
        "input": "payload.text",
        "read": 'text = str(item.get("payload", {}).get("text", ""))',
        "example": 'if "advertisement" in text.lower():\n            self.add_issue(item, "custom_text_issue")\n            item["action"] = "drop"',
    },
    "image_denoise": {
        "input": "payload.image_path",
        "read": 'image_path = str(item.get("payload", {}).get("image_path", ""))',
        "example": 'if not image_path:\n            self.add_issue(item, "custom_image_missing")\n            item["action"] = "review"',
    },
    "video_denoise": {
        "input": "payload.video_path",
        "read": 'video_path = str(item.get("payload", {}).get("video_path", ""))',
        "example": 'if not video_path:\n            self.add_issue(item, "custom_video_missing")\n            item["action"] = "review"',
    },
    "image_text_pair_denoise": {
        "input": "payload.image_path and payload.text",
        "read": 'payload = item.get("payload", {})\n        image_path = str(payload.get("image_path", ""))\n        text = str(payload.get("text", ""))',
        "example": 'if image_path and text:\n            self.set_metric(item, "custom_pair_checked", True)',
    },
    "auto_denoise": {
        "input": "payload.text, payload.image_path, or payload.video_path",
        "read": 'payload = item.get("payload", {})\n        text = str(payload.get("text", ""))\n        image_path = str(payload.get("image_path", ""))\n        video_path = str(payload.get("video_path", ""))',
        "example": 'if not any([text, image_path, video_path]):\n            self.add_issue(item, "custom_unknown_payload")\n            item["action"] = "review"',
    },
}


def render_operator_template(operator_type: str, operator_name: str) -> str:
    """Render a Python template for a custom operator.

    Business logic:
        1. Validate the operator type and operator name.
        2. Select type-specific input guidance and example logic.
        3. Return Python source text ready to import and register.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registration name.

    Returns:
        str: Custom operator template source code.

    Examples:
        >>> "class MyFilterOperator" in render_operator_template("text_denoise", "my_filter")
        True
    """
    if operator_type not in OPERATOR_TYPE_GUIDANCE:  # Allow template generation only for predefined operator types.
        allowed = ", ".join(sorted(OPERATOR_TYPE_GUIDANCE))
        raise ValueError(f"unsupported operator template type: {operator_type}. Allowed: {allowed}")
    _validate_operator_name(operator_name)
    class_name = _operator_class_name(operator_name)
    guidance = OPERATOR_TYPE_GUIDANCE[operator_type]
    read_block = _indent(str(guidance["read"]), 8)
    example_block = _indent(str(guidance["example"]), 8)
    return f'''from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class {class_name}(BaseOperator):
    """User-defined {operator_type} operator template.

    Usage:
        1. Add this file path to the top-level `custom_operators` field in the workflow.
        2. Use `operator: {operator_name}` inside `steps`.
        3. Only edit the code inside the business-logic section of `process`.

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

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Process a single sample.

        Input contract:
            - Recommended fields for this operator type: {guidance["input"]}
            - Read operator config from `self.config`, for example `self.config.get("threshold")`

        Output contract:
            - Use `self.add_issue(item, "issue_name")` to append issue tags.
            - Use `self.set_metric(item, "metric_name", value)` to write metrics.
            - You may write intermediate results into `item["intermediate"]`.
            - You may set `item["action"]` to `keep`, `drop`, or `review`.
            - Do not remove core fields such as `id`, `payload`, `meta`, `metrics`, `issues`, or `operator_trace`.

        Args:
            item (dict[str, Any]): Standard DataItem provided by the workflow.

        Returns:
            dict[str, Any]: Processed DataItem.

        Examples:
            >>> isinstance({class_name}().process({{"payload": {{}}, "issues": [], "metrics": {{}}}}), dict)
            True
        """
{read_block}

        # Start editing business logic here.
        # The code below is only an example and should be rewritten for real rules.
{example_block}
        # End of business-logic editing area.

        return item
'''


def write_operator_template(operator_type: str, operator_name: str, output_path: Path) -> Path:
    """Write a rendered custom operator template to disk.

    Business logic:
        1. Render the operator template for the requested type and name.
        2. Create the output directory automatically when needed.
        3. Write a UTF-8 Python file and return its path.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registration name.
        output_path (Path): Output file path.

    Returns:
        Path: Path of the written template file.

    Examples:
        >>> isinstance(write_operator_template, object)
        True
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_operator_template(operator_type, operator_name), encoding="utf-8")
    return output_path


def _operator_class_name(operator_name: str) -> str:
    """Convert a snake_case operator name into a Python class name.

    Business logic:
        1. Split the registration name on underscores.
        2. Capitalize each segment and concatenate them.
        3. Append the `Operator` suffix.

    Args:
        operator_name (str): snake_case operator registration name.

    Returns:
        str: Python class name.

    Examples:
        >>> _operator_class_name("my_text_filter")
        'MyTextFilterOperator'
    """
    return "".join(part.capitalize() for part in operator_name.split("_")) + "Operator"


def _indent(text: str, spaces: int) -> str:
    """Indent a multi-line template block.

    Business logic:
        1. Add the requested number of spaces to each line.
        2. Preserve blank lines unchanged.
        3. Return a block ready to embed inside the template.

    Args:
        text (str): Original multi-line text.
        spaces (int): Number of indentation spaces.

    Returns:
        str: Indented text.

    Examples:
        >>> _indent("x", 2)
        '  x'
    """
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())
