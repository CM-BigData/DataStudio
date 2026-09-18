import json
from pathlib import Path
from typing import Any

import synthesis_engine.operators  # noqa: F401
from click.testing import CliRunner

from synthesis_engine.cli.main import cli
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor
from synthesis_engine.runtime.input_adapter import InputAdapter, GenerationItemNormalizer
from synthesis_engine.runtime.registry import load_custom_operators, registry


def test_synthesis_input_adapter_reads_raw_text_json_and_csv(tmp_path: Path) -> None:
    """Verify that the synthesis input adapter reads raw_text, JSON, and CSV

    Business logic:
        1. Convert raw_text into a text-type GenerationItem
        2. Convert a JSON object into a single GenerationItem
        3. Convert each CSV row into one GenerationItem

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses expectations through pytest assertions.

    Examples:
        >>> callable(test_synthesis_input_adapter_reads_raw_text_json_and_csv)
        True
    """
    json_path = tmp_path / "seed.json"
    json_path.write_text(json.dumps({"id": "json_seed", "task_type": "text", "prompt": "json prompt"}), encoding="utf-8")
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("id,task_type,prompt,topic\ncsv_1,text,make text,topic a\ncsv_2,text,make more,topic b\n", encoding="utf-8")

    raw_items = list(InputAdapter({"type": "raw_text", "text": "direct synthesis prompt"}, tmp_path).read())
    json_items = list(InputAdapter({"type": "json", "path": str(json_path)}, tmp_path).read())
    csv_items = list(InputAdapter({"type": "csv", "path": str(csv_path)}, tmp_path).read())

    assert raw_items[0].id.startswith("sample_")
    assert raw_items[0].task_type == "text"
    assert raw_items[0].prompt == "direct synthesis prompt"
    assert json_items[0].id == "json_seed"
    assert [item.id for item in csv_items] == ["csv_1", "csv_2"]
    assert csv_items[0].payload["topic"] == "topic a"


def test_synthesis_generation_item_normalizer_preserves_payload() -> None:
    """Verify that GenerationItem normalization preserves user fields

    Business logic:
        1. Build flexible input without an explicit payload
        2. Run normalization
        3. Assert that prompt and extra fields are preserved

    Args:
        None: No input parameters.

    Returns:
        None: Expresses expectations through pytest assertions.

    Examples:
        >>> callable(test_synthesis_generation_item_normalizer_preserves_payload)
        True
    """
    item = GenerationItemNormalizer({"id_field": "sample_id", "prompt_field": "content"}).normalize(
        {"sample_id": "a", "task_type": "text", "content": "prompt", "extra": "keep"},
        source={"type": "csv", "line": 2},
    )

    assert item.id == "a"
    assert item.prompt == "prompt"
    assert item.payload["extra"] == "keep"
    assert item.lineage["input_source"]["line"] == 2


def test_synthesis_workflow_runs_with_custom_operator_file(tmp_path: Path) -> None:
    """Verify that the synthesis workflow can execute a user-defined operator

    Business logic:
        1. Write an external Python operator file
        2. Load that operator through workflow custom_operators
        3. Assert that the custom operator writes the sample into generated.jsonl

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses expectations through pytest assertions.

    Examples:
        >>> callable(test_synthesis_workflow_runs_with_custom_operator_file)
        True
    """
    plugin_path = tmp_path / "custom_accept.py"
    plugin_path.write_text(
        """
from synthesis_engine.operators.base import BaseOperator


class CustomAcceptOperator(BaseOperator):
    operator_name = "custom_accept"

    def process(self, item):
        item.generated["items"] = [{"instruction": item.prompt, "input": "", "output": "ok"}]
        item.metrics["custom_score"] = 1.0
        item.action = "accepted"
        return item
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: custom_synthesis
input:
  type: raw_text
  text: Generate a test sample
output:
  type: jsonl
  path: {tmp_path / "runs"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: custom_accept
    params: {{}}
""",
        encoding="utf-8",
    )

    config = load_workflow_config(config_path)
    load_custom_operators(config.custom_operators, base_dir=tmp_path)
    run_dir = WorkflowExecutor(config, config_path).run()

    generated = (run_dir / "generated.jsonl").read_text(encoding="utf-8")
    assert "custom_accept" in registry._operators
    assert "custom_score" in generated
    assert "Generate a test sample" in generated


def test_synthesis_operator_template_command_generates_loadable_template(tmp_path: Path) -> None:
    """Verify that the synthesis operator-template command generates a loadable template

    Business logic:
        1. Call the command-line to generate a text-type custom operator template
        2. Assert that the template contains GenerationItem input guidance
        3. Assert that the template can be loaded into the global registry

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses expectations through pytest assertions.

    Examples:
        >>> callable(test_synthesis_operator_template_command_generates_loadable_template)
        True
    """
    output_path = tmp_path / "plugins" / "my_synthesis_operator.py"
    runner = CliRunner()

    result = runner.invoke(cli, ["operator-template", "--type", "text", "--name", "my_synthesis_operator", "--output", str(output_path)])

    text = output_path.read_text(encoding="utf-8")
    load_custom_operators([str(output_path)], base_dir=tmp_path)
    assert result.exit_code == 0
    assert "GenerationItem" in text
    assert "custom_operators" in text
    assert "class MySynthesisOperatorOperator" in text
    assert registry.create("my_synthesis_operator", {})


def test_synthesis_validate_loads_custom_operator_and_rejects_unknown_input(tmp_path: Path) -> None:
    """Verify that synthesis validate loads custom operators and rejects unknown input types

    Business logic:
        1. Write a valid custom operator and workflow
        2. Assert that validate succeeds
        3. Change input.type to an unknown value and assert that validate fails

    Args:
        tmp_path (Path): Temporary pytest directory.

    Returns:
        None: Expresses expectations through pytest assertions.

    Examples:
        >>> callable(test_synthesis_validate_loads_custom_operator_and_rejects_unknown_input)
        True
    """
    plugin_path = tmp_path / "validate_operator.py"
    plugin_path.write_text(
        """
from synthesis_engine.operators.base import BaseOperator


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
  id: validate_synthesis
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
    assert "OK: validate_synthesis" in valid.output
    assert invalid.exit_code != 0
    assert "unsupported input.type" in str(invalid.exception)
