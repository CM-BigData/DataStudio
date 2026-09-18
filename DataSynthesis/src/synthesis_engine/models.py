from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal


TaskType = Literal["text", "image", "structured"]


@dataclass
class GenerationItem:
    id: str  # Stable sample ID shared by seed input, run outputs, and trace queries.
    task_type: TaskType  # Task type deciding whether text, image, or structured operators handle the sample.
    prompt: str  # Original synthesis intent declared by the seed.
    payload: Dict[str, Any] = field(default_factory=dict)  # Input payload storing business fields such as schema, topic, and content.
    generated: Dict[str, Any] = field(default_factory=dict)  # Generated result content written by each operator.
    metrics: Dict[str, Any] = field(default_factory=dict)  # Sample metrics such as quality, diversity, and mapper statistics.
    issues: List[Dict[str, Any]] = field(default_factory=list)  # Issues covering format, safety, quality, and generation failures.
    action: str = "pending"  # Sample action: pending, accepted, filtered, failed, or needs_retry.
    lineage: Dict[str, Any] = field(default_factory=dict)  # Audit lineage tracking seeds, models, operators, and retry data.

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GenerationItem":
        """Build a generation sample from a raw dictionary

        Business logic:
            1. Read the sample id, task type, and prompt
            2. Copy the payload and initialize lineage
            3. Return a normalized GenerationItem instance

        Args:
            raw (Dict[str, Any]): Raw input sample dictionary.

        Returns:
            GenerationItem: Normalized generation sample.

        Examples:
            >>> GenerationItem.from_dict({'id': 'a', 'task_type': 'text'}).id
            'a'
        """
        return cls(
            id=str(raw["id"]),
            task_type=raw["task_type"],
            prompt=str(raw.get("prompt", "")),
            payload=dict(raw.get("payload", {})),
            lineage={
                "seed_id": raw.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the sample into a serializable dictionary

        Business logic:
            1. Read the current dataclass fields
            2. Recursively convert them into plain dictionaries
            3. Return data suitable for JSONL or reporting

        Args:
            None.

        Returns:
            Dict[str, Any]: Sample field dictionary.

        Examples:
            >>> GenerationItem('a', 'text', 'p').to_dict()['id']
            'a'
        """
        return asdict(self)

    def to_json(self) -> str:
        """Convert the sample into a JSON string

        Business logic:
            1. Convert the sample into a dictionary
            2. Serialize with UTF-8-friendly JSON settings
            3. Return a single-line JSON string

        Args:
            None.

        Returns:
            str: Sample JSON string.

        Examples:
            >>> '"id": "a"' in GenerationItem('a', 'text', 'p').to_json()
            True
        """
        return json.dumps(self.to_dict(), ensure_ascii=False)
