import json
from pathlib import Path

from dedup_workflow_engine.cli.main import _display_path, main
from dedup_workflow_engine.runtime.executor import WorkflowExecutor, _safe_run_child_path
from dedup_workflow_engine.runtime.input_adapter import DedupItemNormalizer, InputAdapter
from dedup_workflow_engine.runtime.loader import load_workflow_config
from dedup_workflow_engine.runtime.registry import build_default_registry, load_custom_operators


def test_dedup_input_adapter_reads_raw_text_json_and_csv(tmp_path: Path) -> None:
    """Verify that the dedup input adapter reads raw_text, JSON, and CSV.

    Business logic:
        1. Convert raw_text into a text-modality sample.
        2. Convert a JSON object into a single sample.
        3. Convert each CSV row into one sample while preserving extra fields.

    Args:
        tmp_path (Path): pytest temporary directory.

    Returns:
        None: pytest expresses expectations through assertions.

    Examples:
        >>> callable(test_dedup_input_adapter_reads_raw_text_json_and_csv)
        True
    """
    json_path = tmp_path / "seed.json"
    json_path.write_text(json.dumps({"id": "json_seed", "text": "json text"}), encoding="utf-8")
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("id,text,topic\ncsv_1,第一段,topic a\ncsv_2,第二段,topic b\n", encoding="utf-8")

    raw_items = list(InputAdapter({"type": "raw_text", "text": "直接去重文本"}, tmp_path).read())
    json_items = list(InputAdapter({"type": "json", "path": str(json_path)}, tmp_path).read())
    csv_items = list(InputAdapter({"type": "csv", "path": str(csv_path)}, tmp_path).read())

    assert raw_items[0]["modality"] == "text"
    assert raw_items[0]["payload"]["text"] == "直接去重文本"
    assert json_items[0]["id"] == "json_seed"
    assert json_items[0]["payload"]["text"] == "json text"
    assert [item["id"] for item in csv_items] == ["csv_1", "csv_2"]
    assert csv_items[0]["payload"]["topic"] == "topic a"


def test_dedup_item_normalizer_preserves_payload() -> None:
    """Verify that DedupItem normalization preserves user fields.

    Business logic:
        1. Build flexible input without a payload field.
        2. Run normalization.
        3. Assert that text and extra fields are preserved.

    Args:
        None: No input parameters.

    Returns:
        None: pytest expresses expectations through assertions.

    Examples:
        >>> callable(test_dedup_item_normalizer_preserves_payload)
        True
    """
    item = DedupItemNormalizer({"id_field": "sample_id", "text_field": "content"}).normalize(
        {"sample_id": "a", "content": "正文", "extra": "保留"},
        source={"type": "csv", "line": 2},
    )

    assert item["id"] == "a"
    assert item["modality"] == "text"
    assert item["payload"]["text"] == "正文"
    assert item["payload"]["extra"] == "保留"
    assert item["meta"]["input_source"]["line"] == 2


def test_dedup_media_id_uses_pure_path_without_filesystem_resolution() -> None:
    """Verify media payload paths generate IDs without resolving filesystem paths."""
    item = DedupItemNormalizer().normalize({"payload": {"image_path": "../outside/private/sample.png"}})
    windows_item = DedupItemNormalizer().normalize({"payload": {"audio_path": r"C:\private\voice.wav"}})

    assert item["id"] == "sample"
    assert item["payload"]["image_path"] == "../outside/private/sample.png"
    assert windows_item["id"] == "voice"


def test_dedup_cli_display_hides_external_absolute_directory(tmp_path: Path) -> None:
    """Verify CLI path display does not expose external absolute directories."""
    assert _display_path(tmp_path / "private" / "summary.json") == "summary.json"


def test_dedup_run_child_path_rejects_escape(tmp_path: Path) -> None:
    """Verify run output filenames cannot escape the workflow run directory."""
    try:
        _safe_run_child_path(tmp_path, "../outside.jsonl", "kept_path")
    except ValueError as exc:
        assert "workflow run directory" in str(exc)
    else:  # pragma: no cover - defensive assertion branch
        raise AssertionError("expected ValueError")


def test_dedup_workflow_runs_with_custom_operator_file(tmp_path: Path) -> None:
    """Verify that a dedup workflow can execute a user-defined operator.

    Business logic:
        1. Write an external Python operator file.
        2. Load that operator through workflow custom_operators.
        3. Assert that the custom operator writes samples into kept.jsonl.

    Args:
        tmp_path (Path): pytest temporary directory.

    Returns:
        None: pytest expresses expectations through assertions.

    Examples:
        >>> callable(test_dedup_workflow_runs_with_custom_operator_file)
        True
    """
    plugin_path = tmp_path / "custom_mark.py"
    plugin_path.write_text(
        """
from dedup_workflow_engine.operators.base import BaseOperator


class CustomMarkOperator(BaseOperator):
    operator_name = "custom_mark"

    def process_dataset(self, items, context):
        for item in items:  # Mark every sample as kept for the smoke workflow.
            item.setdefault("metrics", {})["custom_score"] = 1.0
            item["action"] = "keep"
        return items
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: custom_dedup
  modality: text
input:
  type: raw_text
  text: 需要去重的一段文本
output:
  run_dir: {tmp_path / "runs"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: custom_mark
    params: {{}}
""",
        encoding="utf-8",
    )

    config = load_workflow_config(config_path)
    registry = build_default_registry()
    load_custom_operators(registry, config["custom_operators"], base_dir=tmp_path)
    summary = WorkflowExecutor(config, registry).run()

    kept = (Path(summary["report_path"]).parent / "kept.jsonl").read_text(encoding="utf-8")
    assert "custom_score" in kept
    assert "需要去重的一段文本" in kept


def test_dedup_operator_template_command_generates_loadable_template(tmp_path: Path) -> None:
    """Verify that the dedup operator-template command generates a loadable template.

    Business logic:
        1. Call the command-line to generate a text-type custom operator template.
        2. Assert that the template includes BaseOperator input guidance.
        3. Assert that the template can be loaded into the registry.

    Args:
        tmp_path (Path): pytest temporary directory.

    Returns:
        None: pytest expresses expectations through assertions.

    Examples:
        >>> callable(test_dedup_operator_template_command_generates_loadable_template)
        True
    """
    output_path = tmp_path / "plugins" / "my_dedup_operator.py"

    code = main(["operator-template", "--type", "text", "--name", "my_dedup_operator", "--output", str(output_path)])

    text = output_path.read_text(encoding="utf-8")
    registry = build_default_registry()
    load_custom_operators(registry, [str(output_path)], base_dir=tmp_path)
    assert code == 0
    assert "BaseOperator" in text
    assert "custom_operators" in text
    assert "class MyDedupOperatorOperator" in text
    assert registry.create("my_dedup_operator", {})


def test_dedup_validate_loads_custom_operator_and_rejects_unknown_input(tmp_path: Path) -> None:
    """Verify that dedup validate checks custom operators and input types.

    Business logic:
        1. Write a valid custom operator and workflow.
        2. Assert that validate succeeds.
        3. Change input.type to an unknown value and assert that validate fails.

    Args:
        tmp_path (Path): pytest temporary directory.

    Returns:
        None: pytest expresses expectations through assertions.

    Examples:
        >>> callable(test_dedup_validate_loads_custom_operator_and_rejects_unknown_input)
        True
    """
    plugin_path = tmp_path / "validate_operator.py"
    plugin_path.write_text(
        """
from dedup_workflow_engine.operators.base import BaseOperator


class ValidateOperator(BaseOperator):
    operator_name = "validate_operator"
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    workflow_text = f"""
workflow:
  id: validate_dedup
  modality: text
input:
  type: raw_text
  text: demo
output:
  run_dir: {tmp_path / "runs"}
custom_operators:
  - {plugin_path}
steps:
  - id: custom
    operator: validate_operator
    params: {{}}
"""
    config_path.write_text(workflow_text, encoding="utf-8")

    valid = main(["validate", "-c", str(config_path)])
    invalid_text = workflow_text.replace("type: raw_text", "type: unknown")
    config_path.write_text(invalid_text, encoding="utf-8")
    invalid = main(["validate", "-c", str(config_path)])

    assert valid == 0
    assert invalid == 2
