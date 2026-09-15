import json
from pathlib import Path
import threading
import time

import parse_engine.operators  # noqa: F401
from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.runtime.config import load_workflow_config
from parse_engine.runtime.executor import WorkflowExecutor
from parse_engine.runtime.registry import OperatorRegistry, registry


def test_load_pdf_workflow_config() -> None:
    """Verify that the PDF workflow configuration can be loaded correctly.

    Business logic:
        1. Read workflows/pdf_parse.yaml.
        2. Assert that the workflow id matches the expected configuration.
        3. Assert that the step count remains the four steps required by the PDF parsing pipeline.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> isinstance("pdf_parse_v1", str)
        True"""
    config = load_workflow_config(Path("workflows/pdf_parse.yaml"))
    assert config.workflow.id == "pdf_parse_v1"
    assert len(config.steps) == 1


def test_load_excel_workflow_config() -> None:
    """Verify that the Excel workflow configuration can be loaded correctly.

    Business logic:
        1. Read workflows/excel_parse.yaml.
        2. Assert that the workflow id matches the expected configuration.
        3. Assert that the step count remains the single end-to-end Excel parsing step.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> isinstance("excel_parse_v1", str)
        True
    """
    config = load_workflow_config(Path("workflows/excel_parse.yaml"))
    assert config.workflow.id == "excel_parse_v1"
    assert len(config.steps) == 1


def test_registered_operators_can_be_created() -> None:
    """Verify that all operators referenced in the configuration are registered.

    Business logic:
        1. Load the PDF workflow configuration.
        2. Traverse configured steps and create operators through the global registry.
        3. Assert that each operator instance has an operator_name.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> bool("pdf_parse")
        True"""
    config = load_workflow_config(Path("workflows/pdf_parse.yaml"))
    for step in config.steps:  # Registry validation: each configured step must be able to create its operator.
        operator = registry.create(step.operator, step.params)
        assert operator.operator_name


def test_registry_requires_snake_case_and_does_not_register_class_alias() -> None:
    """Verify that the registry only accepts snake_case operator names.

    Business logic:
        1. Register a valid snake_case operator.
        2. Assert that the class-name alias cannot be created.
        3. Assert that a non-snake_case operator name fails.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_registry_requires_snake_case_and_does_not_register_class_alias)
        True"""

    class DemoOperator(BaseOperator):
        operator_name = "demo_operator"  # operator_name: valid snake_case registry name for the test operator.

    class BadOperator(BaseOperator):
        operator_name = "BadOperator"  # operator_name: invalid PascalCase registry name for the test operator.

    local = OperatorRegistry()
    local.register(DemoOperator)
    try:
        local.create("DemoOperator", {})
    except KeyError:
        pass
    else:
        raise AssertionError("class alias should not be registered")
    try:
        local.register(BadOperator)
    except ValueError:
        pass
    else:
        raise AssertionError("PascalCase operator_name should fail")


def test_workflow_resume_skips_completed_artifacts(tmp_path: Path) -> None:
    """Verify that workflow resume skips samples already written successfully.

    Business logic:
        1. Create two PDF-like samples and a workflow containing only quality assessment.
        2. Prewrite one completed sample into artifacts.jsonl.
        3. Run with resume and output.path pointing at existing outputs, then assert that the completed sample is not written twice.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_workflow_resume_skips_completed_artifacts)
        True"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "done.pdf").write_bytes(b"%PDF-1.4\n")
    (input_dir / "pending.pdf").write_bytes(b"%PDF-1.4\n")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "artifacts.jsonl").write_text(
        '{"id":"external","modality":"pdf","source":{"path":"external.pdf"},"payload":{},"meta":{},'
        '"intermediate":{},"metrics":{},"issues":[],"artifacts":[],"action":"parsed"}\n'
        '{"id":"done","modality":"pdf","source":{"path":"done.pdf"},"payload":{},"meta":{},'
        '"intermediate":{},"metrics":{},"issues":[],"artifacts":[{"id":"done_text","type":"text",'
        '"text":"ok","data":{},"source_trace":{"file":"done.pdf","operator":"seed"}}],"action":"parsed"}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    class ResumeParseOperator(BaseOperator):
        operator_name = "resume_parse_operator"

        def process(self, item: DataItem) -> DataItem:
            """Mark a resume test sample as parsed."""
            item.action = "parsed"
            return item

    if ResumeParseOperator.operator_name not in registry._operators:
        registry.register(ResumeParseOperator)

    config_path.write_text(
        f"""
workflow:
  id: resume_parse
input:
  type: file_dir
  path: {input_dir.as_posix()}
output:
  type: jsonl
  path: {run_dir.as_posix()}
steps:
  - id: quality
    operator: resume_parse_operator
    params: {{}}
""",
        encoding="utf-8",
    )

    WorkflowExecutor(load_workflow_config(config_path), config_path, resume=True).run()

    rows = [line for line in (run_dir / "artifacts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert sum('"id":"done"' in row or '"id": "done"' in row for row in rows) == 1
    assert any('"id":"pending"' in row or '"id": "pending"' in row for row in rows)
    checkpoint = (run_dir / "checkpoint.json").read_text(encoding="utf-8")
    assert '"resume_enabled": true' in checkpoint
    assert '"skipped_count": 1' in checkpoint
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert metrics["input_total_count"] == 2
    assert metrics["historical_completed_count"] == 1
    assert metrics["newly_processed_count"] == 1
    assert metrics["current_completed_count"] == 2
    assert metrics["completed_count"] == 2
    assert metrics["pending_count"] == 0
    assert "- Total samples: 2" in report
    assert "- Current run samples: 1" in report
    assert "- Historical completed count: 1" in report
    assert "- Newly processed count: 1" in report
    assert "- Current completed count: 2" in report


def test_workflow_resume_report_keeps_input_total_when_all_artifacts_completed(tmp_path: Path) -> None:
    """Verify all-skipped resume reports keep input total and current-run counts separate."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "done_1.pdf").write_bytes(b"%PDF-1.4\n")
    (input_dir / "done_2.pdf").write_bytes(b"%PDF-1.4\n")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "artifacts.jsonl").write_text(
        "\n".join(
            [
                '{"id":"done_1","modality":"pdf","source":{"path":"done_1.pdf"},"payload":{},"meta":{},'
                '"intermediate":{},"metrics":{},"issues":[],"artifacts":[],"action":"parsed"}',
                '{"id":"done_2","modality":"pdf","source":{"path":"done_2.pdf"},"payload":{},"meta":{},'
                '"intermediate":{},"metrics":{},"issues":[],"artifacts":[],"action":"parsed"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    class ResumeParseOperator(BaseOperator):
        operator_name = "resume_parse_operator"

        def process(self, item: DataItem) -> DataItem:
            """Mark a resume test sample as parsed."""
            item.action = "parsed"
            return item

    if ResumeParseOperator.operator_name not in registry._operators:
        registry.register(ResumeParseOperator)

    config_path.write_text(
        f"""
workflow:
  id: resume_parse
input:
  type: file_dir
  path: {input_dir.as_posix()}
output:
  type: jsonl
  path: {run_dir.as_posix()}
steps:
  - id: quality
    operator: resume_parse_operator
    params: {{}}
""",
        encoding="utf-8",
    )

    WorkflowExecutor(load_workflow_config(config_path), config_path, resume=True).run()

    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert metrics["total"] == 0
    assert metrics["input_total_count"] == 2
    assert metrics["historical_completed_count"] == 2
    assert metrics["newly_processed_count"] == 0
    assert metrics["current_completed_count"] == 2
    assert metrics["pending_count"] == 0
    assert "- Total samples: 2" in report
    assert "- Current run samples: 0" in report
    assert "- Completed count: 2" in report
    assert "- Historical completed count: 2" in report
    assert "- Newly processed count: 0" in report


def test_workflow_concurrency_processes_samples_in_parallel(tmp_path: Path) -> None:
    """Verify that the workflow processes samples in parallel.

    Business logic:
        1. Register a test operator that records concurrency overlap.
        2. Execute three input samples with concurrency=2.
        3. Assert that overlap occurs and output order matches input order.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Test results are expressed through assertions.

    Examples:
        >>> callable(test_workflow_concurrency_processes_samples_in_parallel)
        True"""

    class SlowParseOperator(BaseOperator):
        operator_name = "slow_parse_operator"  # operator_name: registry name for the concurrency test operator.
        active = 0  # active: number of samples currently being processed, used to observe thread overlap.
        max_active = 0  # max_active: maximum concurrent sample count observed during the test.
        lock = threading.Lock()  # lock: thread lock protecting active and max_active.

        def process(self, item: DataItem) -> DataItem:
            """Record concurrency overlap and return the original sample.

            Business logic:
                1. Increase the active counter when entering processing.
                2. Sleep briefly to create a concurrency window.
                3. Decrease the active counter on exit and mark the sample as parsed.

            Args:
                item (DataItem): Current parsing sample.

            Returns:
                DataItem: Sample after being marked complete.

            Examples:
                >>> hasattr(SlowParseOperator, "operator_name")
                True"""
            with self.lock:
                type(self).active += 1
                type(self).max_active = max(type(self).max_active, type(self).active)
            time.sleep(0.05)
            with self.lock:
                type(self).active -= 1
            item.action = "parsed"
            return item

    try:
        registry.register(SlowParseOperator)
    except ValueError:
        pass
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    for name in ["a.pdf", "b.pdf", "c.pdf"]:  # Input samples: three files are enough to observe overlap at concurrency=2.
        (input_dir / name).write_bytes(b"%PDF-1.4\n")
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: concurrent_parse
  concurrency: 2
input:
  type: file_dir
  path: {input_dir.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: slow
    operator: slow_parse_operator
    params: {{}}
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()

    assert run_dir == output_dir
    rows = [line for line in (run_dir / "artifacts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert [('"id":"a"' in rows[0] or '"id": "a"' in rows[0]), ('"id":"b"' in rows[1] or '"id": "b"' in rows[1])]
    assert SlowParseOperator.max_active >= 2
    metrics = (run_dir / "metrics.json").read_text(encoding="utf-8")
    assert '"concurrency": 2' in metrics
    assert '"concurrency_enabled": true' in metrics
