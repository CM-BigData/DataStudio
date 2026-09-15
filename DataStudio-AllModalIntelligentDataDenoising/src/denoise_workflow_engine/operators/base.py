from __future__ import annotations

from pathlib import Path
from typing import Any

from denoise_workflow_engine.runtime.loader import resolve_path, validate_path_component


class BaseOperator:
    operator_name: str = "base"  # Operator identifier placeholder; subclasses must override it with a workflow-facing name.
    operator_version: str = "1.0.0"  # Operator version written to output metadata for implementation tracking.

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Store operator configuration and reusable runtime state.

        Business logic:
            1. Accept the configuration or dependency object passed by the caller.
            2. Store reusable state needed by later methods.
            3. Avoid expensive external calls during object construction.

        Args:
                config (dict[str, Any] | None): Configuration dictionary.

        Returns:
            None: The constructor initializes the instance in place.

        Examples:
            >>> BaseOperator({"threshold": 0.8}).config["threshold"]
            0.8
        """
        self.config = config or {}  # Runtime configuration such as thresholds, paths, and API parameters.

    def setup(self) -> None:
        """Initialize external dependencies required by the operator.

        Business logic:
            1. Read client or model parameters from the operator configuration.
            2. Create external clients reused during processing.
            3. Keep setup as a no-op for operators without external dependencies.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares internal runtime state in place.

        Examples:
            >>> BaseOperator().setup() is None
            True
        """
        pass

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Process a single sample in the base operator contract.

        Business logic:
            1. Read the sample payload, issues, and existing metrics.
            2. Update issue tags, metrics, payload fields, or action hints based on operator responsibilities.
            3. Keep `item` as the shared workflow state container for downstream operators.

        Args:
                item (dict[str, Any]): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> BaseOperator().process({"id": "x"})
            Traceback (most recent call last):
            ...
            NotImplementedError
        """
        raise NotImplementedError

    def process_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process a batch of samples in input order.

        Business logic:
            1. Iterate through the sample list in input order.
            2. Call `process` on each sample.
            3. Return the processed list in the same order as the input.

        Args:
                items (list[dict[str, Any]]): Sample list.

        Returns:
            list[dict[str, Any]]: Processed sample list.

        Examples:
            >>> class Echo(BaseOperator):
            ...     def process(self, item):
            ...         item["done"] = True
            ...         return item
            >>> Echo().process_batch([{"id": "1"}])[0]["done"]
            True
        """
        return [self.process(item) for item in items]

    def teardown(self) -> None:
        """Release resources held by the operator.

        Business logic:
            1. Release operator resources after workflow execution ends.
            2. Keep a unified lifecycle hook for resource-free operators.
            3. Avoid modifying sample processing results.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook cleans internal resources in place.

        Examples:
            >>> BaseOperator().teardown() is None
            True
        """
        pass

    def add_issue(self, item: dict[str, Any], issue: str) -> None:
        """Append a unique issue tag to the sample.

        Business logic:
            1. Read the existing `issues` list, creating it when missing.
            2. Check whether the target issue already exists.
            3. Append only when it is absent to avoid duplicate counting.

        Args:
                item (dict[str, Any]): Current sample dictionary.
                issue (str): Issue tag to append.

        Returns:
            None: The method mutates `item` in place.

        Examples:
            >>> item = {"issues": ["a"]}
            >>> BaseOperator().add_issue(item, "b")
            >>> item["issues"]
            ['a', 'b']
        """
        issues = item.setdefault("issues", [])
        if issue not in issues:  # Append only when the issue is not already present.
            issues.append(issue)

    def set_metric(self, item: dict[str, Any], key: str, value: Any) -> None:
        """Record a metric value produced by the operator.

        Business logic:
            1. Read the sample `metrics` dictionary, creating it when missing.
            2. Write the current operator observation under the provided key.
            3. Preserve metrics already written by other operators.

        Args:
                item (dict[str, Any]): Current sample dictionary.
                key (str): Metric key.
                value (Any): Metric value to store.

        Returns:
            None: The method mutates `item` in place.

        Examples:
            >>> item = {}
            >>> BaseOperator().set_metric(item, "score", 0.9)
            >>> item["metrics"]["score"]
            0.9
        """
        item.setdefault("metrics", {})[key] = value

    def runtime_base_dir(self) -> Path:
        """Return the workflow directory supplied by the executor."""
        runtime = self.config.get("_runtime", {})
        return Path(str(runtime.get("base_dir") or Path.cwd())).resolve(strict=False)

    def runtime_run_dir(self) -> Path:
        """Return the authorized run directory supplied by the executor."""
        runtime = self.config.get("_runtime", {})
        return Path(str(runtime.get("run_dir") or self.runtime_base_dir())).resolve(strict=False)

    def runtime_allowed_roots(self) -> tuple[Path, ...] | None:
        """Return canonical authorized roots when path authorization is enabled."""
        values = self.config.get("_runtime", {}).get("allowed_roots")
        if values is None:
            return None
        return tuple(Path(str(value)).resolve(strict=False) for value in values)

    def resolve_runtime_path(self, value: str | Path, *, name: str, base_dir: Path | None = None) -> Path:
        """Resolve an operator path using the executor's authorization context."""
        allowed_roots = self.runtime_allowed_roots()
        effective_base = base_dir or (self.runtime_base_dir() if allowed_roots is not None else Path.cwd())
        return resolve_path(
            value,
            effective_base,
            allowed_roots=allowed_roots,
            name=name,
        )

    def safe_item_id(self, item: dict[str, Any], fallback: str = "sample") -> str:
        """Return a sample ID that is safe to use as one filename component."""
        return validate_path_component(item.get("id") or fallback, "sample id")
