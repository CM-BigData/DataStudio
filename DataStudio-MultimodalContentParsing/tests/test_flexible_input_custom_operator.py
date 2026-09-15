import json
from pathlib import Path

import parse_engine.operators  # noqa: F401
from click.testing import CliRunner

from parse_engine.cli.main import cli
from parse_engine.runtime.config import load_workflow_config
from parse_engine.runtime.executor import WorkflowExecutor
from parse_engine.runtime.input_adapter import DataItemNormalizer, InputAdapter
from parse_engine.runtime.registry import load_custom_operators, registry


def test_parse_input_adapter_reads_raw_text_json_and_csv(tmp_path: Path) -> None:
    """Verify that the parse input adapter reads raw_text, JSON, and CSV.

    Business logic:
        1. Convert raw_text into a single DataItem.
        2. Convert a JSON object into a single DataItem.
        3. Convert each CSV row into one DataItem while preserving extra fields.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Assertions express expectations through pytest.

    Examples:
        >>> callable(test_parse_input_adapter_reads_raw_text_json_and_csv)
        True
    """
    json_path = tmp_path / "seed.json"
    json_path.write_text(json.dumps({"id": "json_seed", "modality": "word", "text": "json text"}), encoding="utf-8")
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("id,modality,text,topic\ncsv_1,unknown,first paragraph,topic a\ncsv_2,unknown,second paragraph,topic b\n", encoding="utf-8")

    raw_items = list(InputAdapter({"type": "raw_text", "text": "parse this text directly"}, tmp_path).read())
    json_items = list(InputAdapter({"type": "json", "path": str(json_path)}, tmp_path).read())
    csv_items = list(InputAdapter({"type": "csv", "path": str(csv_path)}, tmp_path).read())

    assert raw_items[0].id.startswith("sample_")
    assert raw_items[0].payload["text"] == "parse this text directly"
    assert json_items[0].id == "json_seed"
    assert json_items[0].modality == "word"
    assert [item.id for item in csv_items] == ["csv_1", "csv_2"]
    assert csv_items[0].payload["topic"] == "topic a"


def test_parse_data_item_normalizer_preserves_payload() -> None:
    """Verify that DataItem normalization preserves user fields.

    Business logic:
        1. Construct loose input that does not include payload.
        2. Run normalization.
        3. Assert that text and extra fields are preserved.

    Args:
        None: No input arguments.

    Returns:
        None: Assertions express expectations through pytest.

    Examples:
        >>> callable(test_parse_data_item_normalizer_preserves_payload)
        True
    """
    item = DataItemNormalizer({"id_field": "sample_id", "text_field": "content"}).normalize(
        {"sample_id": "a", "content": "body text", "extra": "preserve"},
        source={"type": "csv", "line": 2},
    )

    assert item.id == "a"
    assert item.payload["text"] == "body text"
    assert item.payload["extra"] == "preserve"
    assert item.source["input_source"]["line"] == 2


def test_parse_workflow_runs_with_custom_operator_file(tmp_path: Path) -> None:
    """Verify that the parse workflow can execute a user-defined operator.

    Business logic:
        1. Write an external Python operator file.
        2. Let the workflow load that operator through custom_operators.
        3. Assert that the custom operator writes sample data into artifacts.jsonl.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Assertions express expectations through pytest.

    Examples:
        >>> callable(test_parse_workflow_runs_with_custom_operator_file)
        True
    """
    plugin_path = tmp_path / "custom_text_parse.py"
    plugin_path.write_text(
        """
from parse_engine.models import Artifact, SourceTrace
from parse_engine.operators.base import BaseOperator


class CustomTextParseOperator(BaseOperator):
    operator_name = "custom_text_parse"

    def process(self, item):
        item.artifacts.append(Artifact(
            id=f"{item.id}_custom",
            type="text",
            text=item.payload.get("text", ""),
            data={"custom": True},
            source_trace=SourceTrace(file=item.source.get("path", item.id), operator=self.operator_name),
        ))
        item.metrics["custom_score"] = 1.0
        item.action = "parsed"
        return item
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: custom_parse
input:
  type: raw_text
  text: parse a piece of text
output:
  type: jsonl
  path: {tmp_path / "runs"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: custom_text_parse
    params: {{}}
""",
        encoding="utf-8",
    )

    config = load_workflow_config(config_path)
    load_custom_operators(config.custom_operators, base_dir=tmp_path)
    run_dir = WorkflowExecutor(config, config_path).run()

    artifacts = (run_dir / "artifacts.jsonl").read_text(encoding="utf-8")
    assert "custom_text_parse" in registry._operators
    assert "custom_score" in artifacts
    assert "parse a piece of text" in artifacts


def test_parse_operator_template_command_generates_loadable_template(tmp_path: Path) -> None:
    """Verify that the parse operator-template command generates a loadable template.

    Business logic:
        1. Call the command-line to generate a text-type custom operator template.
        2. Assert that the template contains DataItem input guidance.
        3. Assert that the template can be loaded into the global registry.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Assertions express expectations through pytest.

    Examples:
        >>> callable(test_parse_operator_template_command_generates_loadable_template)
        True
    """
    output_path = tmp_path / "plugins" / "my_parse_operator.py"
    runner = CliRunner()

    result = runner.invoke(cli, ["operator-template", "--type", "text", "--name", "my_parse_operator", "--output", str(output_path)])

    text = output_path.read_text(encoding="utf-8")
    load_custom_operators([str(output_path)], base_dir=tmp_path)
    assert result.exit_code == 0
    assert "DataItem" in text
    assert "custom_operators" in text
    assert "class MyParseOperatorOperator" in text
    assert registry.create("my_parse_operator", {})


def test_parse_validate_loads_custom_operator_and_rejects_unknown_input(tmp_path: Path) -> None:
    """Verify that parse validate loads custom operators and rejects unknown input types.

    Business logic:
        1. Write a valid custom operator and workflow.
        2. Assert that validate succeeds.
        3. Change input.type to an unknown value and assert that validate fails.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Assertions express expectations through pytest.

    Examples:
        >>> callable(test_parse_validate_loads_custom_operator_and_rejects_unknown_input)
        True
    """
    plugin_path = tmp_path / "validate_operator.py"
    plugin_path.write_text(
        """
from parse_engine.operators.base import BaseOperator


class ValidateOperator(BaseOperator):
    operator_name = "validate_operator"

    def process(self, item):
        return item
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    workflow_text = f"""
workflow:
  id: validate_parse
input:
  type: raw_text
  text: demo
output:
  type: jsonl
  path: {tmp_path / "runs"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: validate_operator
    params: {{}}
"""
    config_path.write_text(workflow_text, encoding="utf-8")
    runner = CliRunner()

    valid = runner.invoke(cli, ["validate", "-c", str(config_path)])
    invalid_text = workflow_text.replace("type: raw_text", "type: unknown")
    config_path.write_text(invalid_text, encoding="utf-8")
    invalid = runner.invoke(cli, ["validate", "-c", str(config_path)])

    assert valid.exit_code == 0
    assert "OK: validate_parse" in valid.output
    assert invalid.exit_code != 0
    assert "unsupported input.type" in str(invalid.exception)
