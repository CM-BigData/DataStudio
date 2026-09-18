from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    executor: str = "local"  # Workflow config: executor type requested by workflow runtime.
    workers: int = 1  # Workflow config: number of worker processes available to parallel-safe DAG levels.
    batch_size: int = 0  # Workflow config: batch size passed to operators; 0 means each operator decides for itself.
    checkpoint: bool = True  # Workflow config: whether to write step checkpoints for auditability and resume support.
    resume: bool = False  # Workflow config: whether to continue from the latest successful checkpoint.
    allow_parallel_steps: bool = False  # Workflow config: whether safe steps in the same DAG level may run in parallel.
    device: str = "cpu"  # Workflow config: compute device label passed to operators through runtime context.


def load_runtime_config(config: dict[str, Any]) -> RuntimeConfig:
    """Read normalized runtime settings from workflow config.

    Business logic:
        1. Read the runtime section and workflow-compatible fallback settings separately.
        2. Apply lower-bound constraints to workers and batch_size.
        3. Return the RuntimeConfig used by the executor.

    Args:
        config (dict[str, Any]): Full workflow configuration dictionary.

    Returns:
        RuntimeConfig: Runtime config with defaults and bounds applied.

    Examples:
        >>> load_runtime_config({"runtime": {"workers": 0}}).workers
        1
    """
    runtime = dict(config.get("runtime", {}))
    workflow = dict(config.get("workflow", {}))
    return RuntimeConfig(
        executor=str(runtime.get("executor", "local")),
        workers=max(1, int(runtime.get("workers", 1))),
        batch_size=max(0, int(runtime.get("batch_size", workflow.get("batch_size", 0) or 0))),
        checkpoint=bool(runtime.get("checkpoint", workflow.get("checkpoint", True))),
        resume=bool(runtime.get("resume", workflow.get("resume", False))),
        allow_parallel_steps=bool(runtime.get("allow_parallel_steps", False)),
        device=str(runtime.get("device", "cpu")),
    )
