from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import OperatorRegistry
from .input_adapter import SUPPORTED_INPUT_TYPES, InputAdapter


class SchemaValidator:
    REQUIRED_SECTIONS: tuple[str, ...] = ("workflow", "input", "output", "steps")  # Required sections for basic workflow structure validation.
    REQUIRED_OUTPUTS: tuple[str, ...] = ("result_path", "summary_path", "report_path")  # Required output paths so results, summaries, and reports can be written.

    def validate_config(self, config: dict[str, Any], registry: OperatorRegistry | None = None) -> None:
        """Validate the workflow configuration structure and operator references.

        Business logic:
            1. Ensure the config is a mapping object.
            2. Validate required top-level sections and output paths.
            3. Validate workflow mode, task type, batch size, and concurrency.
            4. Ensure the step list is non-empty and step IDs are unique.
            5. Confirm each operator is registered when a registry is provided.

        Args:
            config (dict[str, Any]): Workflow configuration dictionary.
            registry (OperatorRegistry | None, optional): Optional operator registry.

        Returns:
            None: No business value is returned when validation succeeds.

        Examples:
            >>> SchemaValidator().validate_config({"workflow": {"task_type": "text"}, "input": {}, "output": {"result_path": "a", "summary_path": "b", "report_path": "c"}, "steps": [{"operator": "op"}]})
        """
        if not isinstance(config, dict):  # The workflow config must be a mapping before named sections can be read.
            raise ValueError("Workflow config must be an object.")
        for section in self.REQUIRED_SECTIONS:  # Missing top-level sections would block later executor initialization.
            if section not in config:  # Check each section individually so the error can point to the missing name.
                raise ValueError(f"Missing required workflow section: {section}")

        workflow = config["workflow"]
        if workflow.get("mode", "pipeline") not in {"pipeline", "dag"}:  # The scheduler currently supports only linear pipelines and explicit DAGs.
            raise ValueError("workflow.mode must be pipeline or dag.")
        if workflow.get("task_type") not in {"text", "image", "audio"}:  # Current evaluation operators cover text, image, and audio data.
            raise ValueError("workflow.task_type must be text, image, or audio.")
        if int(workflow.get("batch_size", 1) or 1) <= 0:  # Batch size must be positive so sample slicing can proceed.
            raise ValueError("workflow.batch_size must be greater than 0.")
        if int(workflow.get("concurrency", 1) or 1) <= 0:  # Concurrency must be positive so the worker pool can run.
            raise ValueError("workflow.concurrency must be greater than 0.")

        output = config["output"]
        for key in self.REQUIRED_OUTPUTS:  # All three output paths are used by command-line output and report validation.
            if key not in output:  # Report the exact missing output field for easier debugging.
                raise ValueError(f"Missing output path: output.{key}")

        steps = config["steps"]
        if not isinstance(steps, list) or not steps:  # A workflow must contain at least one operator step.
            raise ValueError("steps must be a non-empty list.")
        seen_step_ids: set[str] = set()
        for index, step in enumerate(steps, start=1):  # Validate step by step while preserving the configured order.
            if "operator" not in step:  # Each step must declare an operator so the executor can instantiate it.
                raise ValueError(f"Step #{index} is missing operator.")
            step_id = step.get("id") or f"step_{index}"
            if step_id in seen_step_ids:  # Duplicate step IDs make DAG dependency resolution ambiguous.
                raise ValueError(f"Duplicate step id: {step_id}")
            seen_step_ids.add(step_id)
            if registry is not None:  # command-line validation should expose unregistered operators early.
                registry.get(step["operator"])

    def validate_paths(self, config: dict[str, Any], resolver: Any) -> None:
        """Validate the existence of workflow input paths.

        Business logic:
            1. Read `input.type` to determine the input data type.
            2. Require JSONL and CSV inputs to point to existing files.
            3. Require `image_folder` inputs to have both the image root directory and annotation file.
            4. Raise an error directly for unsupported input types.

        Args:
            config (dict[str, Any]): Workflow configuration dictionary.
            resolver (Any): Path resolver that takes a configured path and returns the actual Path.

        Returns:
            None: No business value is returned when validation succeeds.

        Examples:
            >>> callable(SchemaValidator().validate_paths)
            True
        """
        input_config = config["input"]
        input_type = input_config.get("type")
        if input_type in {"jsonl", "csv"}:  # Text inputs are provided as a single file.
            path = resolver(input_config["path"])
            if not Path(path).exists():  # A missing input file would fail the run immediately, so expose it early.
                raise FileNotFoundError(f"Input file does not exist: {path}")
        elif input_type == "image_folder":
            root = resolver(input_config["path"])
            if not Path(root).exists():  # Missing image roots prevent resolving relative paths from the annotation file.
                raise FileNotFoundError(f"Image dataset folder does not exist: {root}")
            annotation_path = resolver(input_config.get("annotation_path", Path(root) / "annotations.json"))
            if not Path(annotation_path).exists():  # Image-folder inputs depend on the annotation file to build the sample list.
                raise FileNotFoundError(f"Annotation file does not exist: {annotation_path}")
        elif input_type in SUPPORTED_INPUT_TYPES:
            InputAdapter(config.get("workflow", {}), input_config, resolver).validate_config()
        else:
            raise ValueError(f"Unsupported input.type: {input_type}")
