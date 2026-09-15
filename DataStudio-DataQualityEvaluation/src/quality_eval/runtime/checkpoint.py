from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class CheckpointManager:
    def __init__(self, path: Path, task_id: str, workflow_id: str, resume_enabled: bool = False) -> None:
        """Initialize the checkpoint state manager.

        Business logic:
            1. Store the checkpoint file path, task ID, and workflow ID.
            2. Ensure the checkpoint directory exists.
            3. Initialize task-level and sample-level state structures.

        Args:
            path (Path): Checkpoint JSON file path.
            task_id (str): Current execution task ID.
            workflow_id (str): Workflow ID from the configuration.
            resume_enabled (bool): Whether resume-audit fields are enabled.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/checkpoint.json"), "task", "workflow")
            >>> manager.state["status"]
            'created'
        """
        self.path = path  # Checkpoint file path used to save and restore task progress.
        self.task_id = task_id  # Current task ID used to identify this workflow execution.
        self.workflow_id = workflow_id  # Workflow ID used to distinguish checkpoints from different configs.
        self.resume_enabled = resume_enabled  # Resume flag used to record whether this run started in resume mode.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, Any] = {  # Checkpoint state that records task progress, sample status, and timestamps.
            "task_id": task_id,
            "workflow_id": workflow_id,
            "status": "created",
            "resume_enabled": resume_enabled,
            "resume_count": 1 if resume_enabled else 0,
            "total": 0,
            "input_total_count": 0,
            "historical_completed_count": 0,
            "newly_processed_count": 0,
            "current_completed_count": 0,
            "pending_count": 0,
            "processed": 0,
            "processed_count": 0,
            "success": 0,
            "failed": 0,
            "failed_count": 0,
            "dropped": 0,
            "completed_count": 0,
            "completed_ids": [],
            "skipped_count": 0,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "samples": {},
        }

    def load(self) -> dict[str, Any]:
        """Load checkpoint state from disk.

        Business logic:
            1. Check whether the checkpoint file exists.
            2. Read JSON from disk and replace in-memory state when it exists.
            3. Keep the initialized state when it does not exist.

        Args:
            None.

        Returns:
            dict[str, Any]: Current checkpoint state.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/missing.json"), "task", "workflow")
            >>> manager.load()["status"]
            'created'
        """
        if self.path.exists():  # In resume mode, disk state should override the initialized state.
            with self.path.open("r", encoding="utf-8") as handle:
                self.state = json.load(handle)  # Disk state used to restore processed samples and task statistics.
        return self.state

    def start(self, total: int, skipped_count: int = 0, pending_count: int | None = None) -> None:
        """Mark the task as started.

        Business logic:
            1. Update the task status to `running`.
            2. Record the total number of samples to process in this run.
            3. Save the checkpoint immediately so interrupted runs can resume.

        Args:
            total (int): Total number of samples in this workflow run.
            skipped_count (int): Number of samples skipped from the checkpoint at startup.

        Returns:
            None: Updates and saves state directly.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/start.json"), "task", "workflow")
            >>> manager.start(0)
        """
        self.state.update(
            {
                "status": "running",
                "total": total,
                "input_total_count": total,
                "historical_completed_count": skipped_count,
                "newly_processed_count": 0,
                "current_completed_count": skipped_count,
                "pending_count": total - skipped_count if pending_count is None else pending_count,
                "resume_enabled": self.resume_enabled,
                "resume_count": 1 if self.resume_enabled else 0,
                "skipped_count": skipped_count,
            }
        )
        self.save()

    def mark_sample(
        self,
        sample_id: str,
        status: str,
        current_step: str,
        action: str,
        quality_score: float,
        trace_info: dict[str, Any] | None = None,
    ) -> None:
        """Record the processing state of one sample.

        Business logic:
            1. Write the current step, status, action, and quality score of the sample.
            2. Optionally write trace indexes such as `trace_id`, completed step count, and failed step.
            3. Recompute processed, success, failed, and dropped counts from the sample-state table.
            4. Save the checkpoint after each sample finishes to support resume.

        Args:
            sample_id (str): Sample ID.
            status (str): Sample processing status.
            current_step (str): Current completed step or action.
            action (str): Sample handling action.
            quality_score (float): Sample quality score.
            trace_info (dict[str, Any] | None, optional): Sample `trace_summary`.

        Returns:
            None: Updates and saves state directly.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/sample.json"), "task", "workflow")
            >>> manager.mark_sample("s1", "success", "done", "keep", 100)
        """
        sample_state = {
            "sample_id": sample_id,
            "current_step": current_step,
            "status": status,
            "action": action,
            "quality_score": quality_score,
        }
        if trace_info:  # The checkpoint keeps only lightweight trace indexes instead of copying the full trace log.
            sample_state.update(
                {
                    "trace_id": trace_info.get("trace_id"),
                    "completed_steps": trace_info.get("step_count", 0),
                    "failed_step": trace_info.get("failed_step"),
                    "trace_status": trace_info.get("status", status),
                    "trace_event_count": trace_info.get("trace_event_count", 0),
                }
            )
        self.state["samples"][sample_id] = sample_state
        self.state["processed"] = len(self.state["samples"])
        self.state["processed_count"] = self.state["processed"]
        self.state["success"] = sum(1 for item in self.state["samples"].values() if item["status"] == "success")
        self.state["failed"] = sum(1 for item in self.state["samples"].values() if item["status"] == "failed")
        self.state["failed_count"] = self.state["failed"]
        self.state["dropped"] = sum(1 for item in self.state["samples"].values() if item["action"] == "drop")
        self.state["completed_ids"] = sorted(self.state["samples"])
        self.state["completed_count"] = len(self.state["completed_ids"])
        self.state["newly_processed_count"] = max(0, self.state["processed"] - self.state["historical_completed_count"])
        self.state["processed_count"] = self.state["newly_processed_count"]
        self.state["current_completed_count"] = self.state["historical_completed_count"] + self.state["newly_processed_count"]
        self.state["pending_count"] = max(0, self.state["input_total_count"] - self.state["current_completed_count"])
        self.save()

    def finish(self) -> None:
        """Mark the task as finished successfully.

        Business logic:
            1. Update the task status to `success`.
            2. Write the completion time.
            3. Save the final checkpoint state.

        Args:
            None.

        Returns:
            None: Updates and saves state directly.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/finish.json"), "task", "workflow")
            >>> manager.finish()
        """
        self.state["status"] = "success"
        self.state["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def save(self) -> None:
        """Save checkpoint state to disk.

        Business logic:
            1. Open the checkpoint file with UTF-8 encoding.
            2. Write the current state as JSON.
            3. Preserve non-ASCII characters and indentation for manual troubleshooting.

        Args:
            None.

        Returns:
            None: Writes directly to the file.

        Examples:
            >>> manager = CheckpointManager(Path("tmp/save.json"), "task", "workflow")
            >>> manager.save()
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=2)
