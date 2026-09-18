import json
from pathlib import Path
from typing import Any

from denoise_workflow_engine.cli.main import main
from denoise_workflow_engine.runtime.executor import WorkflowExecutor
from denoise_workflow_engine.runtime.input_adapter import InputAdapter, DataItemNormalizer
from denoise_workflow_engine.runtime.registry import OperatorRegistry, build_default_registry


def test_input_adapter_reads_json_object_and_array(tmp_path: Path) -> None:
    """Verify that JSON object and array input normalize into DataItem records.

    Business logic:
        1. Write a JSON object and read it as one sample.
        2. Write a JSON array and read it as multiple samples.
        3. Assert that missing fields are filled and text lands in `payload.text`.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_input_adapter_reads_json_object_and_array)
        True
    """
    object_path = tmp_path / "one.json"
    object_path.write_text(json.dumps({"text": "one text row"}), encoding="utf-8")
    array_path = tmp_path / "many.json"
    array_path.write_text(json.dumps([{"text": "first row"}, {"id": "b", "payload": {"text": "second row"}}]), encoding="utf-8")

    one = list(InputAdapter({"type": "json", "path": str(object_path)}, tmp_path).read())
    many = list(InputAdapter({"type": "auto", "path": str(array_path)}, tmp_path).read())

    assert one[0]["payload"]["text"] == "one text row"
    assert one[0]["modality"] == "text"
    assert one[0]["action"] == "pending"
    assert [item["payload"]["text"] for item in many] == ["first row", "second row"]
    assert many[1]["id"] == "b"


def test_input_adapter_reads_csv_file_directory_and_raw_text(tmp_path: Path) -> None:
    """Verify CSV, single-file, directory, and raw-text input paths.

    Business logic:
        1. Convert each CSV row into one sample.
        2. Convert a single text file into `payload.text`.
        3. Infer samples from directory contents by extension.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_input_adapter_reads_csv_file_directory_and_raw_text)
        True
    """
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("sample_id,content,label\n1,first line,a\n2,second line,b\n", encoding="utf-8")
    text_path = tmp_path / "note.txt"
    text_path.write_text("file text", encoding="utf-8")
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "a.txt").write_text("directory text", encoding="utf-8")
    (directory / "b.jpg").write_bytes(b"\xff\xd8\xff")

    csv_items = list(InputAdapter({"type": "csv", "path": str(csv_path), "id_field": "sample_id", "text_field": "content"}, tmp_path).read())
    file_items = list(InputAdapter({"type": "file", "path": str(text_path)}, tmp_path).read())
    directory_items = list(InputAdapter({"type": "directory", "path": str(directory)}, tmp_path).read())
    raw_items = list(InputAdapter({"type": "raw_text", "text": "direct input"}, tmp_path).read())

    assert [item["id"] for item in csv_items] == ["1", "2"]
    assert csv_items[0]["payload"]["text"] == "first line"
    assert csv_items[0]["payload"]["label"] == "a"
    assert file_items[0]["payload"]["text"] == "file text"
    assert raw_items[0]["payload"]["text"] == "direct input"
    assert {item["modality"] for item in directory_items} == {"text", "image"}


def test_workflow_runs_with_custom_operator_file(tmp_path: Path) -> None:
    """Verify that a workflow can load and run a user-defined custom operator file.

    Business logic:
        1. Write an external Python operator file.
        2. Load it through `workflow.custom_operators`.
        3. Assert that output samples include the custom issue, metric, and action.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_workflow_runs_with_custom_operator_file)
        True
    """
    plugin_path = tmp_path / "custom_text_filter.py"
    plugin_path.write_text(
        """
from denoise_workflow_engine.operators.base import BaseOperator


class MyTextFilterOperator(BaseOperator):
    operator_name = "my_text_filter"

    def process(self, item):
        item.setdefault("issues", []).append("custom_hit")
        item.setdefault("metrics", {})["custom_score"] = 0.1
        item["action"] = "drop"
        return item
""".strip(),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"id": "x", "text": "promotional text"}), encoding="utf-8")
    run_dir = tmp_path / "run"
    config = {
        "workflow": {"id": "custom_operator_demo", "checkpoint": False},
        "input": {"type": "json", "path": str(input_path)},
        "output": {"run_dir": str(run_dir), "clean_path": "clean.jsonl", "dropped_path": "dropped.jsonl", "review_path": "review.jsonl"},
        "custom_operators": [str(plugin_path)],
        "steps": [{"id": "custom", "operator": "my_text_filter", "params": {}}],
    }
    registry = build_default_registry(custom_operators=config["custom_operators"], base_dir=tmp_path)

    summary = WorkflowExecutor(config, registry).run()

    rows = [json.loads(line) for line in (run_dir / "dropped.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert summary["drop_count"] == 1
    assert rows[0]["issues"] == ["custom_hit"]
    assert rows[0]["metrics"]["custom_score"] == 0.1


def test_custom_operator_validation_rejects_invalid_and_duplicate(tmp_path: Path) -> None:
    """Verify that custom-operator validation rejects invalid and duplicate operators.

    Business logic:
        1. Write an external file that is not a BaseOperator subclass.
        2. Write an external file that reuses a built-in `operator_name`.
        3. Assert that registry construction fails immediately.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_custom_operator_validation_rejects_invalid_and_duplicate)
        True
    """
    invalid_path = tmp_path / "invalid.py"
    invalid_path.write_text("class BadOperator:\n    operator_name = 'bad_operator'\n", encoding="utf-8")
    duplicate_path = tmp_path / "duplicate.py"
    duplicate_path.write_text(
        """
from denoise_workflow_engine.operators.base import BaseOperator


class DuplicateOperator(BaseOperator):
    operator_name = "text_denoise"

    def process(self, item):
        return item
""".strip(),
        encoding="utf-8",
    )

    try:
        build_default_registry(custom_operators=[str(invalid_path)], base_dir=tmp_path)
    except ValueError as exc:
        assert "No BaseOperator subclass" in str(exc)
    else:
        raise AssertionError("invalid external operator should fail")

    try:
        build_default_registry(custom_operators=[str(duplicate_path)], base_dir=tmp_path)
    except ValueError as exc:
        assert "Duplicate operator name" in str(exc)
    else:
        raise AssertionError("duplicate external operator should fail")


def test_operator_template_command_generates_loadable_template(tmp_path: Path) -> None:
    """Verify that the `operator-template` command generates a loadable template.

    Business logic:
        1. Invoke the command-line to generate a text-type custom operator template.
        2. Assert that the template contains detailed comments and workflow guidance.
        3. Assert that the generated template can be registered.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_operator_template_command_generates_loadable_template)
        True
    """
    output_path = tmp_path / "plugins" / "my_template_filter.py"

    exit_code = main(["operator-template", "--type", "text_denoise", "--name", "my_template_filter", "--output", str(output_path)])

    text = output_path.read_text(encoding="utf-8")
    registry = build_default_registry(custom_operators=[str(output_path)], base_dir=tmp_path)
    assert exit_code == 0
    assert "payload.text" in text
    assert "custom_operators" in text
    assert "class MyTemplateFilterOperator" in text
    assert registry.create("my_template_filter", {})


def test_validate_command_loads_custom_operator_and_rejects_unknown_input(tmp_path: Path, capsys: Any) -> None:
    """Verify that `validate` checks custom operators and rejects unknown input types.

    Business logic:
        1. Generate a valid workflow plus a custom operator file.
        2. Assert that `validate` succeeds.
        3. Change the input type to an unknown value and assert that `validate` fails.

    Args:
        tmp_path (Path): Pytest temporary directory.
        capsys: Pytest stdout/stderr capture fixture.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_validate_command_loads_custom_operator_and_rejects_unknown_input)
        True
    """
    plugin_path = tmp_path / "ok_operator.py"
    plugin_path.write_text(
        """
from denoise_workflow_engine.operators.base import BaseOperator


class OkOperator(BaseOperator):
    operator_name = "ok_operator"

    def process(self, item):
        return item
""".strip(),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.txt"
    input_path.write_text("hello", encoding="utf-8")
    config_path = tmp_path / "workflow.json"
    config = {
        "workflow": {"id": "validate_custom"},
        "input": {"type": "file", "path": str(input_path)},
        "output": {"run_dir": str(tmp_path / "run")},
        "custom_operators": [str(plugin_path)],
        "steps": [{"id": "ok", "operator": "ok_operator", "params": {}}],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert main(["validate", "-c", str(config_path), "--allow-root", str(tmp_path)]) == 0
    valid_output = capsys.readouterr()
    assert "workflow config is valid" in valid_output.out

    config["input"]["type"] = "unknown"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["validate", "-c", str(config_path), "--allow-root", str(tmp_path)]) == 2
    invalid_output = capsys.readouterr()
    assert "unsupported input.type" in invalid_output.err


def test_run_command_uses_workflow_directory_for_relative_paths(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verify that the `run` command resolves relative paths from the workflow directory.

    Business logic:
        1. Write relative input and output configuration inside a workflow subdirectory.
        2. Call `validate` and `run` from another current directory.
        3. Assert that both commands find the input and write output relative to the workflow directory.

    Args:
        tmp_path (Path): Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Pytest stdout/stderr capture fixture.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_run_command_uses_workflow_directory_for_relative_paths)
        True
    """
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    input_path = workflow_dir / "input.jsonl"
    input_path.write_text(json.dumps({"id": "x", "payload": {"text": "relative-path input text is long enough"}}) + "\n", encoding="utf-8")
    config_path = workflow_dir / "relative.json"
    config = {
        "workflow": {"id": "relative_paths", "checkpoint": False},
        "input": {"type": "jsonl", "path": "input.jsonl"},
        "output": {"run_dir": "run", "clean_path": "clean.jsonl", "dropped_path": "dropped.jsonl", "review_path": "review.jsonl"},
        "steps": [{"id": "text_denoise", "operator": "text_denoise", "params": {"thresholds": {"keep_score": 0.0, "review_score": 0.0, "hard_fail_issues": []}}}],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    other_cwd = tmp_path / "caller"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    assert main(["validate", "-c", str(config_path), "--allow-root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["run", "-c", str(config_path), "--allow-root", str(tmp_path)]) == 0

    assert (workflow_dir / "run" / "clean.jsonl").exists()


def test_data_item_normalizer_preserves_original_fields() -> None:
    """Verify that the normalizer preserves user-provided original fields.

    Business logic:
        1. Build a flexible input object without a payload.
        2. Normalize it with explicit field mappings.
        3. Assert that core fields are normalized while extra fields are preserved.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_data_item_normalizer_preserves_original_fields)
        True
    """
    item = DataItemNormalizer({"id_field": "sample_id", "text_field": "content"}).normalize(
        {"sample_id": "a", "content": "body text", "extra": "preserved"},
        source={"type": "csv", "path": "input.csv", "line": 2},
    )

    assert item["id"] == "a"
    assert item["payload"]["text"] == "body text"
    assert item["payload"]["extra"] == "preserved"
    assert item["meta"]["input_source"]["line"] == 2
