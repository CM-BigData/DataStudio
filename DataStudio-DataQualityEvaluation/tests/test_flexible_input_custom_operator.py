import json
from pathlib import Path

from quality_eval.cli import main
from quality_eval.runtime.executor import WorkflowExecutor
from quality_eval.runtime.input_adapter import InputAdapter, QualityItemNormalizer
from quality_eval.runtime.registry import load_custom_operators, registry


def test_quality_input_adapter_reads_raw_text_json_and_csv(tmp_path: Path) -> None:
    """Verify that the quality input adapter reads raw_text, JSON, and CSV.

    Business logic:
        1. Convert raw_text into a text-modality sample.
        2. Convert a JSON object into one sample.
        3. Convert each CSV row into one sample and preserve label.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_input_adapter_reads_raw_text_json_and_csv)
        True
    """
    resolver = lambda value: Path(value)
    json_path = tmp_path / "seed.json"
    json_path.write_text(json.dumps({"id": "json_seed", "text": "json text", "label": "a"}), encoding="utf-8")
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("id,text,label,topic\ncsv_1,第一段,a,topic a\ncsv_2,第二段,b,topic b\n", encoding="utf-8")

    raw_items = InputAdapter({"task_type": "text"}, {"type": "raw_text", "text": "直接评测文本"}, resolver).read()
    json_items = InputAdapter({"task_type": "text"}, {"type": "json", "path": str(json_path)}, resolver).read()
    csv_items = InputAdapter({"task_type": "text"}, {"type": "csv", "path": str(csv_path)}, resolver).read()

    assert raw_items[0]["modality"] == "text"
    assert raw_items[0]["payload"]["text"] == "直接评测文本"
    assert json_items[0]["id"] == "json_seed"
    assert json_items[0]["meta"]["label"] == "a"
    assert [item["id"] for item in csv_items] == ["csv_1", "csv_2"]
    assert csv_items[0]["payload"]["topic"] == "topic a"


def test_quality_item_normalizer_preserves_payload() -> None:
    """Verify that QualityItem normalization preserves user fields.

    Business logic:
        1. Build flexible input that does not contain payload.
        2. Run normalization.
        3. Assert that text, label, and extra fields are preserved.

    Args:
        None.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_item_normalizer_preserves_payload)
        True
    """
    item = QualityItemNormalizer({"task_type": "text"}, {"id_field": "sample_id", "text_field": "content"}).normalize(
        {"sample_id": "a", "content": "正文", "label": "ok", "extra": "保留"},
        source={"format": "csv", "line_no": 2},
    )

    assert item["id"] == "a"
    assert item["modality"] == "text"
    assert item["payload"]["text"] == "正文"
    assert item["payload"]["extra"] == "保留"
    assert item["meta"]["label"] == "ok"
    assert item["source"]["line_no"] == 2


def test_audio_workflow_maps_path_to_audio_path() -> None:
    """Verify that generic path fields route to audio_path for audio workflows.

    Business logic:
        1. Normalize an audio row that only has a generic path field.
        2. Assert that path becomes payload.audio_path, not payload.image_path.
        3. Confirm the sample modality is audio.

    Args:
        None.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_audio_workflow_maps_path_to_audio_path)
        True
    """
    item = QualityItemNormalizer({"task_type": "audio"}).normalize({"id": "a1", "path": "audio/a1.wav"})

    assert item["modality"] == "audio"
    assert item["payload"]["audio_path"] == "audio/a1.wav"
    assert "image_path" not in item["payload"]


def test_quality_workflow_runs_with_custom_operator_file(tmp_path: Path) -> None:
    """Verify that the quality workflow can execute a user custom operator.

    Business logic:
        1. Write an external Python operator file.
        2. Load that operator through workflow custom_operators.
        3. Assert that the custom operator writes the sample to result JSONL.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_workflow_runs_with_custom_operator_file)
        True
    """
    plugin_path = tmp_path / "custom_quality.py"
    plugin_path.write_text(
        """
from quality_eval.operators.common.base import BaseOperator


class CustomQualityOperator(BaseOperator):
    operator_name = "custom_quality"

    def process(self, item):
        item.setdefault("metrics", {})["custom_score"] = 1.0
        item["score"] = 100
        item["level"] = "Excellent"
        item["action"] = "keep"
        return item
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    result_path = tmp_path / "outputs" / "result.jsonl"
    config_path.write_text(
        f"""
workflow:
  id: custom_quality_eval
  task_type: text
input:
  type: raw_text
  text: 需要评测的一段文本
output:
  result_path: {result_path}
  summary_path: {tmp_path / "outputs" / "summary.json"}
  report_path: {tmp_path / "reports" / "report.md"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: custom_quality
""",
        encoding="utf-8",
    )

    assert main(["run", "-c", str(config_path), "--task-id", "custom_quality", "--allow-root", str(tmp_path)]) == 0

    content = result_path.read_text(encoding="utf-8")
    assert "custom_score" in content
    assert "custom_quality" in registry.names()
    assert "需要评测的一段文本" not in content


def test_quality_executor_loads_custom_operator_before_validation(tmp_path: Path) -> None:
    """Verify that direct executor calls load custom operators before validation.

    Business logic:
        1. Write an external Python operator file.
        2. Instantiate WorkflowExecutor directly without command-line preloading.
        3. Assert that the workflow passes registry validation and writes results.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_executor_loads_custom_operator_before_validation)
        True
    """
    plugin_path = tmp_path / "direct_quality.py"
    plugin_path.write_text(
        """
from quality_eval.operators.common.base import BaseOperator


class DirectQualityOperator(BaseOperator):
    operator_name = "direct_quality_operator"

    def process(self, item):
        item.setdefault("metrics", {})["direct_score"] = 1
        item["score"] = 100
        item["level"] = "Excellent"
        item["action"] = "keep"
        return item
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    result_path = tmp_path / "outputs" / "direct_result.jsonl"
    config = {
        "workflow": {"id": "direct_custom_quality", "task_type": "text"},
        "input": {"type": "raw_text", "text": "直接执行器测试文本"},
        "output": {
            "result_path": str(result_path),
            "summary_path": str(tmp_path / "outputs" / "direct_summary.json"),
            "report_path": str(tmp_path / "reports" / "direct_report.md"),
        },
        "custom_operators": [str(plugin_path)],
        "steps": [{"id": "custom", "operator": "direct_quality_operator"}],
    }

    summary = WorkflowExecutor(config=config, config_path=config_path, task_id="direct_custom").run()

    assert summary["completed_count"] == 1
    assert "direct_score" in result_path.read_text(encoding="utf-8")


def test_quality_workflow_csv_field_mapping_reaches_real_reader(tmp_path: Path) -> None:
    """Verify that workflow CSV field mapping reaches the real reader path.

    Business logic:
        1. Write a CSV with non-default field names.
        2. Declare id, text, and label mappings explicitly in workflow input.
        3. Run the built-in schema operator and assert the result uses mapped fields.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_workflow_csv_field_mapping_reaches_real_reader)
        True
    """
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("sample,body,category\nrow_1,字段映射正文,news\n", encoding="utf-8")
    config_path = tmp_path / "workflow.yaml"
    result_path = tmp_path / "outputs" / "mapped_result.jsonl"
    config_path.write_text(
        f"""
workflow:
  id: mapped_csv_quality
  task_type: text
input:
  type: csv
  path: {csv_path}
  id_field: sample
  text_field: body
  label_field: category
output:
  result_path: {result_path}
  summary_path: {tmp_path / "outputs" / "mapped_summary.json"}
  report_path: {tmp_path / "reports" / "mapped_report.md"}
steps:
  - id: text_dataset_eval
    operator: text_dataset_eval
    params:
      enabled_checks:
        - schema
""",
        encoding="utf-8",
    )

    assert main(["run", "-c", str(config_path), "--task-id", "mapped_csv", "--allow-root", str(tmp_path)]) == 0

    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["sample_id"] == "row_1"
    assert rows[0]["metrics"]["schema_valid"] is True
    assert rows[0]["trace"][0]["source"]["format"] == "csv"
    assert rows[0]["trace"][0]["source"]["line_no"] == 2
    assert "missing_text_field" not in rows[0]["issues"]


def test_quality_operator_template_command_generates_loadable_template(tmp_path: Path) -> None:
    """Verify that quality operator-template generates a loadable template.

    Business logic:
        1. Call the command-line to generate a text custom-operator template.
        2. Assert that the template includes BaseOperator input guidance.
        3. Assert that the template can be loaded into the registry.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_operator_template_command_generates_loadable_template)
        True
    """
    output_path = tmp_path / "plugins" / "my_quality_operator.py"

    code = main(
        [
            "operator-template",
            "--type",
            "text",
            "--name",
            "my_quality_operator",
            "--output",
            str(output_path),
            "--allow-root",
            str(tmp_path),
        ]
    )

    text = output_path.read_text(encoding="utf-8")
    load_custom_operators([str(output_path)], base_dir=tmp_path)
    assert code == 0
    assert "BaseOperator" in text
    assert "custom_operators" in text
    assert "class MyQualityOperatorOperator" in text
    assert registry.get("my_quality_operator")


def test_quality_validate_loads_custom_operator_and_rejects_unknown_input(tmp_path: Path) -> None:
    """Verify that quality validate-config checks custom operators and input types.

    Business logic:
        1. Write a valid custom operator and workflow.
        2. Assert that validate-config passes.
        3. Change to an unknown input.type and assert that validate-config fails.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Pytest assertions express the expected behavior.

    Examples:
        >>> callable(test_quality_validate_loads_custom_operator_and_rejects_unknown_input)
        True
    """
    plugin_path = tmp_path / "validate_operator.py"
    plugin_path.write_text(
        """
from quality_eval.operators.common.base import BaseOperator


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
  id: validate_quality
  task_type: text
input:
  type: raw_text
  text: demo
output:
  result_path: {tmp_path / "outputs" / "result.jsonl"}
  summary_path: {tmp_path / "outputs" / "summary.json"}
  report_path: {tmp_path / "reports" / "report.md"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: validate_operator
"""
    config_path.write_text(workflow_text, encoding="utf-8")

    valid = main(["validate-config", "-c", str(config_path), "--allow-root", str(tmp_path)])
    invalid_text = workflow_text.replace("type: raw_text", "type: unknown")
    config_path.write_text(invalid_text, encoding="utf-8")
    invalid = main(["validate-config", "-c", str(config_path), "--allow-root", str(tmp_path)])

    assert valid == 0
    assert invalid != 0
