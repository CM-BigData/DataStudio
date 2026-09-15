from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class StepConfig:
    id: str  # Step identifier used to locate a single execution step inside the workflow.
    operator: str  # Snake_case operator name used to create the operator from the registry.
    params: Dict[str, Any] = field(default_factory=dict)  # Step parameters passed to the operator constructor.


@dataclass
class IOConfig:
    type: str  # Workflow IO type such as seed_yaml or jsonl.
    path: str = ""  # Path to the input seed or output run directory.
    report_path: str | None = None  # Optional override path for report output.
    text: str | None = None  # Input text used directly as a single generation prompt for raw_text mode.
    id_field: str | None = None  # Field mapping for the sample ID in input records.
    task_type_field: str | None = None  # Field mapping for the task type in input records.
    prompt_field: str | None = None  # Field mapping for the prompt in input records.


@dataclass
class WorkflowMeta:
    id: str  # Workflow identifier used in run directories, checkpoints, and reports.
    name: str = ""  # Human-readable workflow description.
    mode: str = "pipeline"  # Execution mode; the current implementation uses a serial pipeline.
    batch_size: int = 16  # Batch size reserved for future batch-processing expansion.
    concurrency: int = 1  # Concurrency level reserved for future concurrent execution.
    checkpoint: bool = True  # Checkpoint switch controlling whether run state is recorded.
    retry_limit: int = 0  # Maximum number of retry rounds allowed by quality-gate requests.


@dataclass
class WorkflowConfig:
    workflow: WorkflowMeta  # Workflow metadata including run ID, name, and retry settings.
    input: IOConfig  # Input configuration describing the seed source.
    output: IOConfig  # Output configuration describing the run-artifact directory.
    steps: List[StepConfig]  # Ordered operator configuration list.
    custom_operators: List[str] = field(default_factory=list)  # User-provided Python files or modules for custom operators.


def load_workflow_config(path: str | Path) -> WorkflowConfig:
    """Load workflow YAML configuration

    Business logic:
        1. Convert the input path into a Path object
        2. Read the raw YAML config
        3. Convert it into WorkflowConfig structures

    Args:
        path (str | Path): Workflow config file path.

    Returns:
        WorkflowConfig: Normalized workflow configuration.

    Examples:
        >>> callable(load_workflow_config)
        True
    """
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return WorkflowConfig(
        workflow=WorkflowMeta(**raw["workflow"]),
        input=IOConfig(**raw["input"]),
        output=IOConfig(**raw["output"]),
        steps=[StepConfig(**step) for step in raw["steps"]],
        custom_operators=list(raw.get("custom_operators", [])),
    )
