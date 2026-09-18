from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ErrorQueue:
    def __init__(self, path: Path) -> None:
        """Initialize the error queue file.

        Business logic:
            1. Store the JSONL path of the error queue.
            2. Ensure the parent directory exists.
            3. Create an empty file so later error records can be appended.

        Args:
            path (Path): Path to the error queue JSONL file.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> queue = ErrorQueue(Path("tmp/errors.jsonl"))
            >>> queue.path.name
            'errors.jsonl'
        """
        self.path = path  # Error queue path used to record per-sample operator failures.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def push(self, item: dict[str, Any], error: str, operator: str | None = None) -> None:
        """Append one sample error record.

        Business logic:
            1. Assemble the sample ID, operator name, error message, and original sample.
            2. Append the record to the error queue in JSONL format.
            3. Preserve original-language content to support later manual investigation.

        Args:
            item (dict[str, Any]): Sample that failed.
            error (str): Error message.
            operator (str | None, optional): Name of the operator that raised the error.

        Returns:
            None: Appends directly to the error queue file.

        Examples:
            >>> queue = ErrorQueue(Path("tmp/errors_push.jsonl"))
            >>> queue.push({"id": "s1"}, "boom", "op")
        """
        payload = {
            "sample_id": item.get("id") or item.get("sample_id"),
            "operator": operator,
            "error": error,
            "item": item,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
