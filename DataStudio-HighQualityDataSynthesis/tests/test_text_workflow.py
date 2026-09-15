from pathlib import Path

import synthesis_engine.operators  # noqa: F401
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor


def test_text_workflow_outputs_generated_jsonl(tmp_path: Path) -> None:
    """Verify that the text workflow outputs generated samples

    Business logic:
        1. Write a temporary seed and text-workflow config
        2. Execute the workflow to generate output files
        3. Check that generated.jsonl contains the sample and quality score

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses test results through assertions.

    Examples:
        >>> callable(test_text_workflow_outputs_generated_jsonl)
        True
    """
    seed_path = tmp_path / "seed.yaml"
    output_dir = tmp_path / "runs"
    seed_path.write_text(
        """
items:
  - id: sample_text
    task_type: text
    prompt: Generate a text sample.
    payload:
      topic: local workflow
      audience: developer
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  id: test_text
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
        text_template_synthesis: {{}}
        text_format_validate:
          min_length: 20
        diversity_score: {{}}
        quality_gate:
          pass_score: 0.7
""",
        encoding="utf-8",
    )

    run_dir = WorkflowExecutor(load_workflow_config(config_path), config_path).run()
    generated = (run_dir / "generated.jsonl").read_text(encoding="utf-8")
    assert "sample_text" in generated
    assert "quality_score" in generated
