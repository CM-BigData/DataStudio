from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class CheckpointStore:
    def __init__(self, run_dir: Path) -> None:
        """Initialize the checkpoint store

        Business logic:
            1. Locate checkpoint.json from the run directory
            2. Set initial state fields
            3. Wait for later update calls to persist to disk

        Args:
            run_dir (Path): Workflow run directory.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> CheckpointStore(Path('/tmp/run')).state['status']
            'initialized'
        """
        self.path = run_dir / "checkpoint.json"  # Checkpoint state file path under the current run directory.
        self.state: Dict[str, Any] = {  # Checkpoint state recording progress and sample-action counts.
            "status": "initialized",
            "processed": 0,
            "accepted": 0,
            "filtered": 0,
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
        """Update and persist checkpoint state

        Business logic:
            1. Merge incoming state fields
            2. Refresh the update timestamp
            3. Create directories and write the JSON file

        Args:
            kwargs (Any): State fields to merge.

        Returns:
            None: Writes state to checkpoint.json.

        Examples:
            >>> callable(CheckpointStore(Path('/tmp/run')).update)
            True
        """
        self.state.update(kwargs)
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
