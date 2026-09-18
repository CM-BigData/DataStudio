from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel, Field


class StepConfig(BaseModel):
    id: str  # Step identifier: stable step id referenced inside the workflow.
    operator: str  # Operator name: operator_name to instantiate for the current step.
    params: Dict[str, Any] = Field(default_factory=dict)  # Operator params: configuration passed into the operator constructor.


class IOConfig(BaseModel):
    type: str = "file_dir"  # I/O type: how input or output paths should be interpreted.
    path: str | None = None  # I/O path: input directory, input file, or output root directory.
    report_path: str | None = None  # Report path: explicit location of report.md.
    text: str | None = None  # Inline text: used directly as sample content for raw_text input.
    id_field: str | None = None  # Field mapping: sample ID field in structured input.
    modality_field: str | None = None  # Field mapping: modality field in structured input.
    path_field: str | None = None  # Field mapping: file path field in structured input.
    text_field: str | None = None  # Field mapping: body text field in structured input.


class WorkflowMeta(BaseModel):
    id: str  # Workflow identifier: stable id used by runs, reports, and checkpoints.
    name: str = ""  # Workflow name: human-readable name used in reports and displays.
    mode: str = "pipeline"  # Execution mode: orchestration mode of the current workflow.
    batch_size: int = 16  # Batch size: number of data items handled in a single batch.
    concurrency: int = 1  # Concurrency: number of parallel executions allowed by the workflow.
    checkpoint: bool = True  # Checkpoint flag: whether run progress should be recorded.


class WorkflowConfig(BaseModel):
    workflow: WorkflowMeta  # Workflow metadata: id, name, and execution parameters.
    input: IOConfig  # Input config: source path and type for samples.
    output: IOConfig  # Output config: where run artifacts are written.
    custom_operators: List[str] = Field(default_factory=list)  # Custom operators: list of external Python files or module references.
    steps: List[StepConfig]  # Step list: operator configuration executed in order.


def load_workflow_config(path: str | Path) -> WorkflowConfig:
    """Load and validate workflow YAML configuration.

    Business logic:
        1. Convert the incoming path to a Path object.
        2. Read the configuration dictionary with yaml.safe_load.
        3. Validate the structure using the WorkflowConfig Pydantic model.

    Args:
        path: Path to the workflow YAML configuration file.

    Returns:
        WorkflowConfig: Workflow configuration object that has passed structural validation.

    Examples:
        >>> isinstance("workflows/pdf_parse.yaml", str)
        True"""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return WorkflowConfig.model_validate(raw)
