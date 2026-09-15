from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    id: str  # Workflow config: stable step identifier used for dependency resolution and checkpoint filenames.
    operator: str  # Workflow config: registered operator name referenced by the workflow step.
    params: dict[str, Any]  # Workflow config: step-level config parameters passed to the operator instance.
    depends_on: tuple[str, ...]  # Workflow config: upstream step ids that must complete before this step runs.
    raw: dict[str, Any]  # Workflow config: original step config retained for fields such as parallel_safe.


def build_execution_plan(steps: list[dict[str, Any]], mode: str = "pipeline") -> list[list[WorkflowStep]]:
    """Convert raw workflow steps into executable levels.

    Business logic:
        1. Normalize the step dictionaries in config into WorkflowStep objects.
        2. In pipeline mode, execute steps one by one in declaration order.
        3. In DAG mode, generate dependency-safe execution levels that may run in parallel.

    Args:
        steps (list[dict[str, Any]]): Steps list from workflow config.
        mode (str, optional): Execution mode. Defaults to "pipeline".

    Returns:
        list[list[WorkflowStep]]: Execution levels, where each inner list represents one dependency level.

    Examples:
        >>> build_execution_plan([{"operator": "A"}])[0][0].operator
        'A'
    """
    normalized = normalize_steps(steps)
    if mode != "dag":  # Pipeline mode preserves author order and runs one step per level.
        return [[step] for step in normalized]
    return build_dag_levels(normalized)


def normalize_steps(steps: list[dict[str, Any]]) -> list[WorkflowStep]:
    """Normalize workflow step config.

    Business logic:
        1. Generate step_N ids in declaration order for steps missing an id.
        2. Validate that step ids are unique.
        3. Support depends_on, needs, and after as dependency fields.

    Args:
        steps (list[dict[str, Any]]): Raw step list parsed from JSON or YAML.

    Returns:
        list[WorkflowStep]: Steps with id, operator, params, and depends_on populated.

    Raises:
        ValueError: Raised when two steps resolve to the same id.

    Examples:
        >>> normalize_steps([{"operator": "A", "depends_on": "root"}])[0].depends_on
        ('root',)
    """
    normalized: list[WorkflowStep] = []
    seen: set[str] = set()
    for index, step in enumerate(steps, start=1):  # Preserve declared order while assigning fallback ids.
        step_id = str(step.get("id") or f"step_{index}")
        if step_id in seen:  # Duplicate ids would make DAG edges and checkpoints ambiguous.
            raise ValueError(f"duplicate workflow step id: {step_id}")
        seen.add(step_id)
        depends_on = step.get("depends_on", step.get("needs", step.get("after", [])))
        if isinstance(depends_on, str):  # Allow a single dependency to be written as a scalar.
            depends = (depends_on,)
        else:
            depends = tuple(str(dep) for dep in depends_on)
        normalized.append(
            WorkflowStep(
                id=step_id,
                operator=str(step["operator"]),
                params=dict(step.get("params", {})),
                depends_on=depends,
                raw=step,
            )
        )
    return normalized


def build_dag_levels(steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
    """Build DAG execution levels from dependencies.

    Business logic:
        1. Build an index from step id to step object.
        2. Validate that every dependency points to an existing step.
        3. Repeatedly select steps whose dependencies have all completed as the next level.

    Args:
        steps (list[WorkflowStep]): Normalized steps with dependency information.

    Returns:
        list[list[WorkflowStep]]: Dependency-safe DAG execution levels.

    Raises:
        ValueError: Raised when a dependency is unknown or the dependency graph cannot progress.

    Examples:
        >>> steps = normalize_steps([{"id": "a", "operator": "A"}, {"id": "b", "operator": "B", "depends_on": "a"}])
        >>> [level[0].id for level in build_dag_levels(steps)]
        ['a', 'b']
    """
    by_id = {step.id: step for step in steps}
    for step in steps:  # Validate all edges before scheduling any level.
        missing = [dep for dep in step.depends_on if dep not in by_id]
        if missing:  # Unknown dependencies are configuration errors, not runtime skips.
            raise ValueError(f"step {step.id} depends on unknown step(s): {', '.join(missing)}")

    completed: set[str] = set()
    remaining = {step.id for step in steps}
    levels: list[list[WorkflowStep]] = []
    while remaining:  # Repeatedly promote currently unblocked steps into the next level.
        ready = [step for step in steps if step.id in remaining and all(dep in completed for dep in step.depends_on)]
        if not ready:  # No ready step while work remains means the graph cannot progress.
            cycle = ", ".join(sorted(remaining))
            raise ValueError(f"workflow DAG has a cycle or unsatisfied dependency among: {cycle}")
        levels.append(ready)
        for step in ready:  # Mark the whole level complete before searching the next level.
            remaining.remove(step.id)
            completed.add(step.id)
    return levels


def flatten_plan(levels: list[list[WorkflowStep]]) -> list[WorkflowStep]:
    """Flatten execution levels into a deterministic step order.

    Business logic:
        1. Traverse the execution plan in level order.
        2. Preserve the existing order inside each level.
        3. Return the linear step list used by the executor for checkpoint and resume.

    Args:
        levels (list[list[WorkflowStep]]): Execution levels returned by build_execution_plan.

    Returns:
        list[WorkflowStep]: Flattened workflow step list.

    Examples:
        >>> flatten_plan([[WorkflowStep("a", "A", {}, (), {})]])[0].id
        'a'
    """
    return [step for level in levels for step in level]
