from __future__ import annotations

from pathlib import Path

from parse_engine.runtime.registry import _validate_operator_name


OPERATOR_TYPE_GUIDANCE = {  # Template config: input fields and example logic for end-to-end parse operators.
    "document": {
        "input": "item.payload['path'], item.source, and item.modality",
        "read": "path = item.payload.get(\"path\")\nsource = item.source",
        "example": 'item.artifacts.append(Artifact(id=f"{item.id}_custom_text", type="text", text=f"parsed: {path}", data={}, source_trace=SourceTrace(file=str(path or item.id), operator=self.operator_name)))\nitem.action = "parsed"',
    },
    "image": {
        "input": "item.payload['path'] and item.metrics",
        "read": "path = item.payload.get(\"path\")\nmetrics = item.metrics",
        "example": 'metrics["custom_image_checked"] = bool(path)\nitem.action = "parsed"',
    },
    "audio": {
        "input": "item.payload['path'] and item.intermediate",
        "read": "path = item.payload.get(\"path\")\nintermediate = item.intermediate",
        "example": 'intermediate["custom_audio_note"] = f"audio path: {path}"\nitem.action = "parsed"',
    },
    "text": {
        "input": "item.payload['text'], item.payload, and item.artifacts",
        "read": "text = str(item.payload.get(\"text\", \"\"))\npayload = item.payload",
        "example": 'item.artifacts.append(Artifact(id=f"{item.id}_custom_text", type="text", text=text.strip(), data={"payload_keys": sorted(payload)}, source_trace=SourceTrace(file=item.source.get("path", item.id), operator=self.operator_name)))\nitem.action = "parsed"',
    },
    "quality_gate": {
        "input": "item.artifacts, item.issues, item.metrics, and item.action",
        "read": "artifacts = item.artifacts\nissues = item.issues",
        "example": 'item.metrics["custom_artifact_count"] = len(artifacts)\nif issues:\n    item.action = "needs_review"',
    },
}


def render_operator_template(operator_type: str, operator_name: str) -> str:
    """Render a custom end-to-end parsing operator template.

    Business logic:
        1. Validate operator type and operator_name.
        2. Select DataItem input and output guidance by type.
        3. Return Python source for an end-to-end operator that can be loaded directly.

    Args:
        operator_type (str): Operator type.
        operator_name (str): Operator registry name.

    Returns:
        str: Python template source code.

    Examples:
        >>> "DataItem" in render_operator_template("text", "my_operator")
        True
    """
    if operator_type not in OPERATOR_TYPE_GUIDANCE:  # Only generate templates for defined types.
        allowed = ", ".join(sorted(OPERATOR_TYPE_GUIDANCE))
        raise ValueError(f"unsupported operator template type: {operator_type}. Allowed: {allowed}")
    _validate_operator_name(operator_name)
    class_name = _operator_class_name(operator_name)
    guidance = OPERATOR_TYPE_GUIDANCE[operator_type]
    read_block = _indent(str(guidance["read"]), 8)
    example_block = _indent(str(guidance["example"]), 8)
    return f'''from __future__ import annotations

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class {class_name}(BaseOperator):
    """Template for a user-defined end-to-end {operator_type} parsing operator.

    Usage:
        1. Add this file path to the top-level custom_operators section of the workflow.
        2. Use operator: {operator_name} inside steps.
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

    def process(self, item: DataItem) -> DataItem:
        """Process a single parsing sample as one end-to-end operator.

        Input contract:
            - Recommended fields to read for the current type: {guidance["input"]}
            - Read operator configuration from self.config, for example self.config.get("threshold")

        Output contract:
            - Append final parsing outputs to item.artifacts.
            - Keep intermediate extraction, OCR, ASR, chunking, or quality logic inside this operator.
            - Write quality, count, or debug metrics to item.metrics.
            - Append issue objects to item.issues, for example {{"type": "custom_issue", "message": "details"}}.
            - You may set item.action to parsed, needs_review, or failed.
            - Do not delete core fields such as id, modality, source, payload, artifacts, metrics, or issues.

        Args:
            item (DataItem): Standard parsing sample passed in by the workflow.

        Returns:
            DataItem: Processed parsing sample.

        Examples:
            >>> isinstance({class_name}().process(DataItem(id="a", source={{}}, payload={{}})), DataItem)
            True
        """
{read_block}

        # Business logic area: start modifying from here.
        # The code below is only an example. Rewrite it according to your actual rules.
{example_block}
        # Business logic area: stop modifying here.

        return item
'''


def write_operator_template(operator_type: str, operator_name: str, output_path: Path) -> Path:
    """Write a custom parse operator template.

    Business logic:
        1. Render the template for the specified type and name.
        2. Create the output directory automatically.
        3. Write a UTF-8 Python file.

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
    """Convert a snake_case operator name into a class name.

    Business logic:
        1. Split the registry name by underscores.
        2. Capitalize each segment and join them.
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
        2. Preserve blank-line structure.
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
