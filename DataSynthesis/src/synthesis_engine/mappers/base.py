from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MapperInput:
    sample_id: str  # Sample identifier sourced from the stable GenerationItem sample ID.
    task_type: str  # Task category such as text, image, or structured generation.
    content: str  # Input content consumed directly by the mapper, such as text, tables, or questions.
    payload: dict[str, Any] = field(default_factory=dict)  # Raw payload that preserves extra fields needed by the mapper.


@dataclass(frozen=True)
class MapperResult:
    items: list[dict[str, Any]]  # Generated entries written into item.generated[output_key].
    metrics: dict[str, Any] = field(default_factory=dict)  # Metrics such as generated count, latency, or similarity statistics.
    issues: list[dict[str, Any]] = field(default_factory=list)  # Structured failures or warnings emitted by the mapper.
    lineage: dict[str, Any] = field(default_factory=dict)  # Audit lineage for mapper, model, and retrieval source tracking.
    failed: bool = False  # Failure flag used by pipelines and operators to decide follow-up actions.


class BaseMapper:
    mapper_name: str = "base_mapper"  # Mapper name used in lineage and test assertions.
    mapper_version: str = "1.0.0"  # Mapper version used for generated-result auditing.

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize mapper configuration

        Business logic:
            1. Accept mapper configuration input
            2. Convert a missing config into an empty dictionary
            3. Store the config for subclass access

        Args:
            config (dict[str, Any] | None): Mapper configuration.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> BaseMapper({'a': 1}).config['a']
            1
        """
        self.config = config or {}  # Mapper configuration controlling counts, output format, and call options.

    def map(self, input: MapperInput) -> MapperResult:
        """Run the mapper transformation

        Business logic:
            1. Define the standard mapper entry point
            2. Accept a normalized MapperInput
            3. Let the base class raise NotImplementedError directly

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Mapper output.

        Examples:
            >>> callable(BaseMapper.map)
            True
        """
        raise NotImplementedError
