import json
from pathlib import Path
import shutil
import time

from quality_eval.cli import main
from quality_eval.runtime.report import write_markdown_report


def _wait_for_file(path: Path, timeout_seconds: float = 2.0) -> Path:
    """Wait for a workflow output file to become readable.

    Business logic:
        1. Poll the target path until it exists or the timeout expires.
        2. Return the path immediately once the file appears.
        3. Raise FileNotFoundError when the file is still missing after the timeout.

    Args:
        path (Path): Expected output file path.
        timeout_seconds (float, optional): Maximum wait time in seconds.

    Returns:
        Path: The same readable path.

    Examples:
        >>> isinstance(_wait_for_file, object)
        True
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists():
            return path
        time.sleep(0.05)
    raise FileNotFoundError(path)


def test_text_workflow_outputs_expected_issues() -> None:
    """Verify that the text workflow outputs expected issue codes.

    Business logic:
        1. Run the full evaluation with the sample text JSONL workflow.
        2. Read the result JSONL.
        3. Assert that empty text, missing fields, length, abnormal characters, duplicates, and label issues are detected.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_text_workflow_outputs_expected_issues)
        True
    """
    output_dir = "test_runs/pytest_text"
    assert main(["run", "-c", "workflows/text_dataset_eval.yaml", "--task-id", "pytest_text", "--output-dir", output_dir]) == 0
    result_path = Path(output_dir) / "text_eval_result.jsonl"
    content = result_path.read_text(encoding="utf-8")
    for issue in [  # The sample text data intentionally covers these quality issues.
        "empty_text",
        "missing_text_field",
        "too_short",
        "too_long",
        "abnormal_chars",
        "duplicate_text",
        "high_repetition",
        "missing_label",
        "missing_id",
    ]:
        assert issue in content


def test_validate_text_punctuation_pairing_config() -> None:
    """Verify that the punctuation-pairing workflow config passes validation.

    Business logic:
        1. Run the `validate-config` subcommand for the dedicated punctuation workflow.
        2. Load the workflow configuration and registered operator names.
        3. Confirm that config structure, operator references, and input paths are valid.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_validate_text_punctuation_pairing_config)
        True
    """
    assert main(["validate-config", "-c", "workflows/text_punctuation_pairing_eval.yaml"]) == 0


def test_validate_text_consecutive_punctuation_config() -> None:
    """Verify that the consecutive-punctuation workflow config passes validation.

    Business logic:
        1. Run the `validate-config` subcommand for the dedicated consecutive-punctuation workflow.
        2. Load the workflow configuration and registered operator names.
        3. Confirm that config structure, operator references, and input paths are valid.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_validate_text_consecutive_punctuation_config)
        True
    """
    assert main(["validate-config", "-c", "workflows/text_consecutive_punctuation_eval.yaml"]) == 0


def test_validate_text_special_characters_config() -> None:
    """Verify that the special-characters workflow config passes validation.

    Business logic:
        1. Run the `validate-config` subcommand for the dedicated special-characters workflow.
        2. Load the workflow configuration and registered operator names.
        3. Confirm that config structure, operator references, and input paths are valid.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_validate_text_special_characters_config)
        True
    """
    assert main(["validate-config", "-c", "workflows/text_special_characters_eval.yaml"]) == 0


def test_csv_text_workflow_runs() -> None:
    """Verify that the CSV text workflow runs and detects core issues.

    Business logic:
        1. Run the full evaluation with the CSV text workflow.
        2. Read the CSV result JSONL.
        3. Assert that empty-text and duplicate-text issues are detected.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_csv_text_workflow_runs)
        True
    """
    output_dir = "test_runs/pytest_text_csv"
    assert main(["run", "-c", "workflows/text_dataset_csv_eval.yaml", "--task-id", "pytest_text_csv", "--output-dir", output_dir]) == 0
    content = (Path(output_dir) / "text_csv_eval_result.jsonl").read_text(encoding="utf-8")
    assert "empty_text" in content
    assert "duplicate_text" in content


def test_text_workflow_persists_audit_trace() -> None:
    """Verify that the text workflow persists audit-grade traces.

    Business logic:
        1. Run the text evaluation workflow and read result, summary, report, and operator log files.
        2. Assert that every result contains trace_id, trace_summary, and a full trace.
        3. Assert that summary/report content shows the traceability summary and log path.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_text_workflow_persists_audit_trace)
        True
    """
    output_dir = Path("test_runs/pytest_text_trace").resolve()
    shutil.rmtree(output_dir, ignore_errors=True)
    assert main(["run", "-c", "workflows/text_dataset_eval.yaml", "--task-id", "pytest_text_trace", "--output-dir", str(output_dir)]) == 0

    result_path = output_dir / "text_eval_result.jsonl"
    summary_path = output_dir / "text_eval_summary.json"
    report_path = output_dir / "text_eval_report.md"
    log_path = output_dir / "logs" / "pytest_text_trace_operators.jsonl"

    result_path = _wait_for_file(result_path)
    summary_path = _wait_for_file(summary_path)
    report_path = _wait_for_file(report_path)
    log_path = _wait_for_file(log_path)

    results = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    first = results[0]
    assert first["trace_id"] == "pytest_text_trace:text_001"
    assert first["trace_summary"]["trace_log_path"] == str(log_path.resolve())
    assert first["trace_summary"]["step_count"] == len(first["trace"])
    assert first["trace_summary"]["failed_step"] is None
    assert first["trace"]
    required_step_fields = {
        "step_id",
        "operator",
        "status",
        "retry_attempt",
        "input_hash",
        "output_hash",
        "config_hash",
        "latency_ms",
    }
    assert required_step_fields.issubset(first["trace"][0])

    logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert logs
    assert logs[0]["trace_id"] == first["trace_id"]
    assert logs[0]["run_id"] == "pytest_text_trace"
    assert logs[0]["workflow_id"] == "text_dataset_eval_v1"
    assert logs[0]["source"]["line_no"] == 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["traceability"]["trace_enabled"] is True
    assert summary["traceability"]["trace_coverage"] == 1.0
    assert summary["traceability"]["traced_sample_count"] == len(results)
    assert summary["traceability"]["trace_event_count"] == len(logs)
    assert summary["traceability"]["trace_log_path"] == str(log_path.resolve())
    report_content = report_path.read_text(encoding="utf-8")
    assert "## Traceability" in report_content
    assert str(log_path.resolve()) in report_content
    assert "优秀" not in report_content
    assert "良好" not in report_content
    assert "一般" not in report_content
    assert "较差" not in report_content
    assert "Excellent" in report_content
    assert "Dimension (EN)" in report_content
    assert "Dimension (ZH)" in report_content
    assert "Implemented/Planned Metrics (EN)" in report_content
    assert "Implemented/Planned Metrics (ZH)" in report_content
    assert "合规性" in report_content


def test_text_workflow_resume_preserves_existing_trace_logs() -> None:
    """Verify that old trace logs are preserved after resume.

    Business logic:
        1. Run the text evaluation workflow once to generate trace logs.
        2. Resume with the same task-id and output-dir.
        3. Assert that old results and operator logs still contribute to final traceability summary.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_text_workflow_resume_preserves_existing_trace_logs)
        True
    """
    output_dir = Path("test_runs/pytest_text_trace_resume").resolve()
    args = ["run", "-c", "workflows/text_dataset_eval.yaml", "--task-id", "pytest_text_trace_resume", "--output-dir", str(output_dir)]
    assert main(args) == 0
    log_path = output_dir / "logs" / "pytest_text_trace_resume_operators.jsonl"
    before_logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert before_logs

    assert main([*args, "--resume"]) == 0

    after_logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = json.loads((output_dir / "text_eval_summary.json").read_text(encoding="utf-8"))
    assert after_logs == before_logs
    assert summary["skipped_count"] == summary["total_count"]
    assert summary["input_total_count"] == summary["total_count"]
    assert summary["historical_completed_count"] == summary["total_count"]
    assert summary["newly_processed_count"] == 0
    assert summary["current_completed_count"] == summary["total_count"]
    assert summary["pending_count"] == 0
    assert "- Current run samples: 0" in (output_dir / "text_eval_report.md").read_text(encoding="utf-8")
    assert "- Historical completed count:" in (output_dir / "text_eval_report.md").read_text(encoding="utf-8")
    assert summary["traceability"]["trace_event_count"] == len(before_logs)
    assert summary["traceability"]["trace_coverage"] == 1.0


def test_report_normalizes_legacy_chinese_levels_and_bilingual_mapping(tmp_path: Path) -> None:
    """Verify that Markdown reports use English levels and bilingual standard mapping.

    Business logic:
        1. Build a summary that contains legacy Chinese level values.
        2. Write the Markdown report.
        3. Assert that level values are rendered in English and mapping columns are bilingual.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Assertions express the expected report contract.

    Examples:
        >>> callable(test_report_normalizes_legacy_chinese_levels_and_bilingual_mapping)
        True
    """
    report_path = tmp_path / "report.md"
    summary = {
        "task_id": "t",
        "workflow_id": "w",
        "modality": "text",
        "total_count": 1,
        "valid_count": 1,
        "abnormal_count": 0,
        "resume_enabled": False,
        "skipped_count": 0,
        "processed_count": 1,
        "completed_count": 1,
        "traceability": {},
        "paths": {},
        "base_quality_score": 100,
        "annotation_quality_score": 100,
        "comprehensive_score": 100,
        "dimension_scores": {"Compliance": 100},
        "level_distribution": {"优秀": 1},
        "issue_distribution": {},
        "duplicate_sample_ids": [],
        "low_quality_samples": [{"sample_id": "s1", "score": 95, "level": "优秀", "action": "keep", "issues": []}],
        "high_risk_samples": [],
        "annotation_problem_samples": [],
        "enhanced_metric_status": {},
        "gb_mapping": [
            {
                "dimension": "Compliance",
                "dimension_zh": "合规性",
                "implemented_metrics": "schema_valid",
                "implemented_metrics_zh": "结构校验",
                "status": "enabled",
            }
        ],
        "rectification_suggestions": [],
    }

    write_markdown_report(summary, report_path)

    content = report_path.read_text(encoding="utf-8")
    assert "Excellent" in content
    assert "优秀" not in content
    assert "Dimension (EN)" in content
    assert "Dimension (ZH)" in content
    assert "Implemented/Planned Metrics (EN)" in content
    assert "Implemented/Planned Metrics (ZH)" in content
    assert "合规性" in content
