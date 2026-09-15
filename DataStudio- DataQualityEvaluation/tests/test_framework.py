from pathlib import Path

import pytest

from quality_eval.cli import main
from quality_eval.operators.common.base import BaseOperator
from quality_eval.runtime.checkpoint import CheckpointManager
from quality_eval.runtime.dag import DAGBuilder
from quality_eval.runtime.registry import OperatorRegistry
from quality_eval.runtime.scheduler import TaskScheduler


def test_list_operators_command(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that the operator-list command-line command runs.

    Business logic:
        1. Call the `list-operators` subcommand.
        2. Confirm the command returns a successful exit code.
        3. Indirectly verify that operator modules have been imported and registered.

    Args:
        capsys: Pytest output capture fixture.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_list_operators_command)
        True
    """
    assert main(["list-operators"]) == 0
    names = set(capsys.readouterr().out.splitlines())
    assert {"image_dataset_eval", "text_dataset_eval"}.issubset(names)
    assert "text_length_eval" not in names
    assert "image_decode_eval" not in names


@pytest.mark.parametrize("command", ["validate", "validate-config"])
def test_validate_commands_validate_workflow(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that both validation command spellings run the same workflow validation."""
    assert main([command, "-c", "workflows/text_dataset_eval.yaml"]) == 0
    output = capsys.readouterr().out
    assert "valid_config=" in output


def test_dag_scheduler_orders_dependencies() -> None:
    """Verify that the DAG scheduler orders nodes by dependencies.

    Business logic:
        1. Build an explicit schema -> quality -> score DAG.
        2. Use TaskScheduler to generate the execution order.
        3. Assert that dependency nodes always appear before dependent nodes.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_dag_scheduler_orders_dependencies)
        True
    """
    dag = DAGBuilder().build(
        {
            "workflow": {"mode": "dag"},
            "steps": [
                {"id": "final", "operator": "text_dataset_eval", "depends_on": ["prepare"]},
                {"id": "prepare", "operator": "text_dataset_eval"},
            ],
        }
    )
    ordered = [node.id for node in TaskScheduler().order(dag)]
    assert ordered.index("prepare") < ordered.index("final")


def test_registry_requires_snake_case_and_does_not_register_class_alias() -> None:
    """Verify that the registry accepts only snake_case registration names.

    Business logic:
        1. Define valid and invalid test operator classes.
        2. Register the valid operator and confirm the class-name alias is unavailable.
        3. Assert that registering the invalid operator raises an error.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_registry_requires_snake_case_and_does_not_register_class_alias)
        True
    """

    class DemoOperator(BaseOperator):
        operator_name = "demo_operator"  # Valid snake_case test operator registration name.

    class BadOperator(BaseOperator):
        operator_name = "BadOperator"  # Invalid PascalCase test operator registration name.

    registry = OperatorRegistry()
    registry.register(DemoOperator)
    try:
        registry.get("DemoOperator")
    except KeyError:
        pass
    else:
        raise AssertionError("class alias should not be registered")
    try:
        registry.register(BadOperator)
    except ValueError:
        pass
    else:
        raise AssertionError("PascalCase operator_name should fail")


def test_checkpoint_records_resume_audit_fields(tmp_path: Path) -> None:
    """Verify that quality checkpoints write unified resume audit fields.

    Business logic:
        1. Create a checkpoint manager and start it in resume mode.
        2. Mark one sample complete and finish the task.
        3. Assert that the checkpoint contains unified resume audit fields.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_checkpoint_records_resume_audit_fields)
        True
    """
    manager = CheckpointManager(tmp_path / "checkpoint.json", "task", "workflow", resume_enabled=True)
    manager.load()
    manager.start(2, skipped_count=1)
    manager.state["samples"]["old"] = {
        "sample_id": "old",
        "current_step": "done",
        "status": "success",
        "action": "keep",
        "quality_score": 100,
    }
    manager.mark_sample("s1", "success", "done", "keep", 100)
    manager.finish()

    assert manager.state["resume_enabled"] is True
    assert manager.state["skipped_count"] == 1
    assert manager.state["processed_count"] == 1
    assert manager.state["newly_processed_count"] == 1
    assert manager.state["current_completed_count"] == 2
    assert manager.state["pending_count"] == 0
