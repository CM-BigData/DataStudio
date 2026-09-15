from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class CheckpointManager:
    def __init__(self, run_dir: Path, enabled: bool = True) -> None:
        """Create a checkpoint manager for a single workflow run.

        Business logic:
            1. Store whether checkpointing is enabled for the current run.
            2. Resolve the checkpoints directory under run_dir.
            3. Create the directory when enabled so later step and runtime state can be written.

        Args:
            run_dir (Path): Output directory for the current workflow run.
            enabled (bool, optional): Whether checkpoint reads and writes are enabled. Defaults to True.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> manager = CheckpointManager(Path("runs/demo"), enabled=False)
            >>> manager.enabled
            False
        """
        self.enabled = enabled  # Workflow config: controls whether the current run performs checkpoint I/O.
        self.checkpoint_dir = run_dir / "checkpoints"  # Workflow config: directory storing step checkpoints and runtime state.
        if enabled:  # Create the directory only when checkpointing is part of this run.
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def write_step(self, step_id: str, operator_name: str, state: dict[str, Any]) -> None:
        """Write the execution state for a single workflow step.

        Business logic:
            1. Return immediately when checkpointing is disabled.
            2. Combine the step id, operator name, write time, and execution state.
            3. Write checkpoints/<step_id>.json for audit and resume decisions.

        Args:
            step_id (str): Stable workflow step id.
            operator_name (str): Operator name that executed the step.
            state (dict[str, Any]): Step status and counters collected by the executor.

        Returns:
            None: The state is written to disk and nothing is returned.

        Examples:
            >>> manager = CheckpointManager(Path("runs/demo"), enabled=False)
            >>> manager.write_step("normalize", "TextNormalizeForDedupOperator", {"status": "success"})
        """
        if not self.enabled:  # Disabled runs must not leave checkpoint files behind.
            return
        payload = {
            "step_id": step_id,
            "operator": operator_name,
            "checkpointed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            **state,
        }
        path = self.checkpoint_dir / f"{step_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_step(self, step_id: str) -> dict[str, Any] | None:
        """Read the checkpoint state for a single workflow step.

        Business logic:
            1. Locate the checkpoint JSON file by step id.
            2. Return None when checkpointing is disabled or the file does not exist.
            3. Parse JSON and return the state dictionary when the file exists.

        Args:
            step_id (str): Stable workflow step id.

        Returns:
            dict[str, Any] | None: Step state dictionary, or None when no readable state exists.

        Examples:
            >>> CheckpointManager(Path("runs/demo"), enabled=False).read_step("missing") is None
            True
        """
        path = self.checkpoint_dir / f"{step_id}.json"
        if not self.enabled or not path.exists():  # Missing checkpoints are normal for fresh or disabled runs.
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_runtime_state(self, step_id: str, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Write resumable dataset and workflow context state.

        Business logic:
            1. Skip runtime-state writes when checkpointing is disabled.
            2. Save the items produced after the current step.
            3. Persist only the context fields needed for resume and reporting.

        Args:
            step_id (str): Successful step id associated with this runtime state.
            items (list[dict[str, Any]]): Sample records produced by the step.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            None: The runtime state is written to disk and nothing is returned.

        Examples:
            >>> manager = CheckpointManager(Path("runs/demo"), enabled=False)
            >>> manager.write_runtime_state("step", [], {})
        """
        if not self.enabled:  # Runtime state is meaningful only for resumable checkpointed runs.
            return
        payload = {
            "step_id": step_id,
            "items": items,
            "context": {
                key: value
                for key, value in context.items()  # Keep only JSON-safe context needed to resume or report a run.
                if key in {"duplicate_edges", "duplicate_groups", "operator_logs", "workflow_id", "modality", "cwd", "runtime"}
            },
        }
        path = self.checkpoint_dir / f"{step_id}.state.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read_runtime_state(self, step_id: str) -> dict[str, Any] | None:
        """Read resumable runtime state for a specific step.

        Business logic:
            1. Locate the .state.json file by step id.
            2. Return None when checkpointing is disabled or the file does not exist.
            3. Parse and return the items/context payload when the file exists.

        Args:
            step_id (str): Step id whose runtime state should be restored.

        Returns:
            dict[str, Any] | None: Runtime-state payload, or None when no resumable state exists.

        Examples:
            >>> CheckpointManager(Path("runs/demo"), enabled=False).read_runtime_state("step") is None
            True
        """
        path = self.checkpoint_dir / f"{step_id}.state.json"
        if not self.enabled or not path.exists():  # A missing state file means the step cannot be used as a resume point.
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_successful_state(self, step_ids: list[str]) -> tuple[int, dict[str, Any]] | None:
        """Find the latest successful step state that can be used for resume.

        Business logic:
            1. Scan step ids backward from the end of the execution plan.
            2. Skip steps without a successful checkpoint.
            3. Return the first step that has both a successful status and runtime state.

        Args:
            step_ids (list[str]): Step ids in execution order.

        Returns:
            tuple[int, dict[str, Any]] | None: Index and state of the resumable step, or None when it does not exist.

        Examples:
            >>> CheckpointManager(Path("runs/demo"), enabled=False).latest_successful_state(["a"]) is None
            True
        """
        for index in range(len(step_ids) - 1, -1, -1):  # Search backward so resume starts from the latest completed step.
            step_id = step_ids[index]
            step = self.read_step(step_id)
            if not step or step.get("status") != "success":  # Failed or incomplete steps are unsafe resume anchors.
                continue
            state = self.read_runtime_state(step_id)
            if state:  # A status checkpoint without dataset state cannot restore processing.
                return index, state
        return None
