from pathlib import Path

import synthesis_engine.operators  # noqa: F401
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor


def test_retry_limit_records_retry_history(tmp_path: Path) -> None:
    """Verify that the retry limit records retry history

    Business logic:
        1. Write a temporary seed and workflow that trigger a format failure
        2. Execute the workflow with a single retry limit
        3. Check that filtered output contains retry history and issue types

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses test results through assertions.

    Examples:
        >>> callable(test_retry_limit_records_retry_history)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    output_dir = tmp_path / "runs"
    seed_path.write_text(
        """
items:
  - id: retry_text
    task_type: text
    prompt: tiny
    payload:
      topic: tiny
      audience: tester
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: retry_test
  retry_limit: 1
input:
  type: seed_yaml
  path: {seed_path.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      profile: template
      stages:
        text_template_synthesis:
          template: "x"
        text_format_validate:
          min_length: 20
        quality_gate:
          pass_score: 0.7
          retry_limit: 1
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()
    filtered = (run_dir / "filtered.jsonl").read_text(encoding="utf-8")
    assert "retry_text" in filtered
    assert "retry_history" in filtered
    assert '"retry_attempt": 1' in filtered
    assert "format_invalid" in filtered
