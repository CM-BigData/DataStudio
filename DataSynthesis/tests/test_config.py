import json
from pathlib import Path
import threading
import time

import synthesis_engine.operators  # noqa: F401
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor
from synthesis_engine.runtime.registry import OperatorRegistry, registry


def test_load_text_workflow_config() -> None:
    """Verify that the text workflow config can be loaded

    Business logic:
        1. Read the text-synthesis workflow config
        2. Validate the workflow id
        3. Validate that the workflow exposes one end-to-end step

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_load_text_workflow_config)
        True
    """
    config = load_workflow_config(Path("workflows/text_synthesis.yaml"))
    assert config.workflow.id == "text_synthesis_v1"
    assert len(config.steps) == 1
    assert config.steps[0].operator == "text_synthesis"


def test_registered_operators_can_be_created() -> None:
    """Verify that all configured operators can be created

    Business logic:
        1. Read the structured-synthesis workflow config
        2. Create an operator for each configured step
        3. Assert that each operator exposes a name

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_registered_operators_can_be_created)
        True
    """
    config = load_workflow_config(Path("workflows/structured_synthesis.yaml"))
    for step in config.steps:  # Every configured step must map to a registered operator.
        operator = registry.create(step.operator, step.params)
        assert operator.operator_name


def test_registry_requires_snake_case_and_does_not_register_class_alias() -> None:
    """Verify that the registry accepts only snake_case operator names

    Business logic:
        1. Build valid and invalid test operator classes
        2. Register the valid operator and confirm that its class-name alias is unavailable
        3. Assert that registering the invalid operator raises an error

    Args:
        None.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_registry_requires_snake_case_and_does_not_register_class_alias)
        True
    """

    class DemoOperator(BaseOperator):
        operator_name = "demo_operator"  # Valid snake_case operator name for tests.

    class BadOperator(BaseOperator):
        operator_name = "BadOperator"  # Invalid PascalCase operator name for tests.

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


def test_workflow_resume_skips_accepted_generated_items(tmp_path: Path) -> None:
    """Verify that workflow resume skips already accepted samples

    Business logic:
        1. Create two text seed samples and a text-template synthesis workflow
        2. Prewrite one accepted sample into generated.jsonl
        3. Execute with resume and output.path pointing at existing outputs, then assert that accepted samples are not written twice

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_workflow_resume_skips_accepted_generated_items)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    seed_path.write_text(
        """
items:
  - id: done
    task_type: text
    prompt: done
    payload:
      topic: done
      audience: dev
  - id: pending
    task_type: text
    prompt: pending
    payload:
      topic: pending
      audience: dev
""",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "generated.jsonl").write_text(
        '{"id":"external","task_type":"text","prompt":"external","payload":{},"generated":{"text":"external"},'
        '"metrics":{"quality_score":1},"issues":[],"action":"accepted","lineage":{}}\n'
        '{"id":"done","task_type":"text","prompt":"done","payload":{},"generated":{"text":"done"},'
        '"metrics":{"quality_score":1},"issues":[],"action":"accepted","lineage":{}}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: resume_synthesis
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {run_dir.as_posix()}
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      profile: template
      stages:
        text_template_synthesis: {{}}
        text_format_validate:
          min_length: 5
        diversity_score: {{}}
        quality_gate:
          pass_score: 0.1
""",
        encoding="utf-8",
    )

    WorkflowExecutor(load_workflow_config(config_path), config_path, resume=True).run()

    rows = [line for line in (run_dir / "generated.jsonl").read_text(encoding="utf-8").splitlines() if line]
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


def test_workflow_resume_report_keeps_input_total_when_all_items_completed(tmp_path: Path) -> None:
    """Verify that all-skipped resume reports keep input-total and current-run counts separate

    Business logic:
        1. Create two seed samples and prewrite both as accepted generated samples.
        2. Execute with resume and output.path pointing at existing outputs.
        3. Assert the report shows total input samples separately from zero newly processed samples.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_workflow_resume_report_keeps_input_total_when_all_items_completed)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    seed_path.write_text(
        """
items:
  - id: done_1
    task_type: text
    prompt: done 1
    payload:
      topic: done 1
      audience: dev
  - id: done_2
    task_type: text
    prompt: done 2
    payload:
      topic: done 2
      audience: dev
""",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "generated.jsonl").write_text(
        "\n".join(
            [
                '{"id":"done_1","task_type":"text","prompt":"done 1","payload":{},"generated":{"text":"done 1"},'
                '"metrics":{"quality_score":1},"issues":[],"action":"accepted","lineage":{}}',
                '{"id":"done_2","task_type":"text","prompt":"done 2","payload":{},"generated":{"text":"done 2"},'
                '"metrics":{"quality_score":1},"issues":[],"action":"accepted","lineage":{}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: resume_synthesis
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {run_dir.as_posix()}
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      profile: template
      stages:
        text_template_synthesis: {{}}
        text_format_validate:
          min_length: 5
        diversity_score: {{}}
        quality_gate:
          pass_score: 0.1
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
    """Verify that the synthesis workflow processes samples in parallel at sample level

    Business logic:
        1. Register a test operator that records concurrency overlap
        2. Execute three seed samples with concurrency=2
        3. Assert that overlap occurs and output order still matches input order

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses results through assertions.

    Examples:
        >>> callable(test_workflow_concurrency_processes_samples_in_parallel)
        True
    """

    class SlowSynthesisOperator(BaseOperator):
        operator_name = "slow_synthesis_operator"  # Operator name used by the concurrency test.
        active = 0  # Number of samples currently being processed, used to observe overlap.
        max_active = 0  # Maximum concurrent sample count observed during the test.
        lock = threading.Lock()  # Lock protecting active and max_active.

        def process(self, item: GenerationItem) -> GenerationItem:
            """Record concurrency overlap and accept the sample

            Business logic:
                1. Increase the active counter when processing starts
                2. Sleep briefly to create a concurrency window
                3. Decrease the active counter on exit and mark the sample as accepted

            Args:
                item (GenerationItem): Current generated sample.

            Returns:
                GenerationItem: Sample marked as accepted.

            Examples:
                >>> hasattr(SlowSynthesisOperator, "operator_name")
                True
            """
            with self.lock:
                type(self).active += 1
                type(self).max_active = max(type(self).max_active, type(self).active)
            time.sleep(0.05)
            with self.lock:
                type(self).active -= 1
            item.generated["text"] = item.prompt
            item.action = "accepted"
            return item

    try:
        registry.register(SlowSynthesisOperator)
    except ValueError:
        pass
    seed_path = tmp_path / "seed.yaml"
    seed_path.write_text(
        """
items:
  - id: a
    task_type: text
    prompt: a
  - id: b
    task_type: text
    prompt: b
  - id: c
    task_type: text
    prompt: c
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: concurrent_synthesis
  concurrency: 2
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: slow
    operator: slow_synthesis_operator
    params: {{}}
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()

    assert run_dir == output_dir
    rows = [line for line in (run_dir / "generated.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert [('"id": "a"' in rows[0]), ('"id": "b"' in rows[1]), ('"id": "c"' in rows[2])]
    assert SlowSynthesisOperator.max_active >= 2
    metrics = (run_dir / "metrics.json").read_text(encoding="utf-8")
    assert '"concurrency": 2' in metrics
    assert '"concurrency_enabled": true' in metrics
