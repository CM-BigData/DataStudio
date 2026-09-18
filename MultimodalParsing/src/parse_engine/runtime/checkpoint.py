from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class CheckpointStore:
    def __init__(self, run_dir: Path) -> None:
        """Create a run checkpoint store.

        Business logic:
            1. Resolve the checkpoint.json path from the run directory.
            2. Initialize status, processed count, success count, failure count, and update timestamp fields.
            3. Wait until update is called before creating directories and writing to disk.

        Args:
            run_dir: Current workflow run directory.

        Returns:
            None: The constructor only initializes in-memory state.

        Examples:
            >>> CheckpointStore(Path("runs/demo")).path.name
            'checkpoint.json'"""
        self.path = run_dir / "checkpoint.json"  # Checkpoint path: location of the checkpoint.json file for the current run.
        self.state: Dict[str, Any] = {  # Checkpoint state: run state maintained before writing to disk.
            "status": "initialized",
            "processed": 0,
            "success": 0,
            "failed": 0,
            "resume_enabled": False,
            "resume_count": 0,
            "input_total_count": 0,
            "historical_completed_count": 0,
            "newly_processed_count": 0,
            "current_completed_count": 0,
            "pending_count": 0,
            "completed_count": 0,
            "completed_ids": [],
            "skipped_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "updated_at": None,
        }

    def update(self, **kwargs: Any) -> None:
        """Update and persist the run checkpoint.

        Business logic:
            1. Merge caller-provided state fields into the current checkpoint state.
            2. Write the current UTC update timestamp.
            3. Ensure the run directory exists, then serialize the state to checkpoint.json.

        Args:
            kwargs: Checkpoint fields to overwrite or add.

        Returns:
            None: The checkpoint state is written directly to the disk file.

        Examples:
            >>> isinstance({"status": "running"}, dict)
            True"""
        self.state.update(kwargs)
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
