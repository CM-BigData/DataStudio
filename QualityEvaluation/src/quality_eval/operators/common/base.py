from __future__ import annotations

from typing import Any


class BaseOperator:
    operator_name: str = "base"  # Registered operator name used to map configured steps to the default base class.
    operator_version: str = "1.0.0"  # Operator version used by execution audit logs to record the implementation version.

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the shared operator configuration.

        Business logic:
            1. Store the full operator config injected by the workflow.
            2. Extract `rules` as a shortcut entry for quality rules.
            3. Let subclasses read thresholds and penalty settings in `process` and `setup`.

        Args:
            config (dict[str, Any]): Merged operator runtime config from the workflow.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> BaseOperator({"rules": {"min_text_length": 5}}).rules["min_text_length"]
            5
        """
        self.config = config  # Full operator config that preserves workflow, runtime, and step context.
        self.rules = config.get("rules", {})  # Quality rule config that provides thresholds and issue weights.

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Prepare operator state before batch processing starts.

        Business logic:
            1. Receive the full sample collection and task context.
            2. Create no state by default so subclasses can override it for indexes or caches.
            3. Keep the default implementation side-effect free so regular operators can inherit it directly.

        Args:
            items (list[dict[str, Any]]): Samples to be processed by this workflow run.
            context (dict[str, Any]): Task context dictionary shared across operators.

        Returns:
            None: The setup phase does not return a business value.

        Examples:
            >>> BaseOperator({}).setup([], {})
        """
        pass

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Process one sample.

        Business logic:
            1. Define the per-sample processing interface for all operators.
            2. Provide no default quality-evaluation logic in the base class.
            3. Require subclasses to override this method and return the updated sample.

        Args:
            item (dict[str, Any]): Unified sample structure.

        Returns:
            dict[str, Any]: Processed sample.

        Examples:
            >>> BaseOperator({}).process({})
            Traceback (most recent call last):
            ...
            NotImplementedError
        """
        raise NotImplementedError

    def process_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process a batch of samples in order.

        Business logic:
            1. Iterate through each sample in the input batch.
            2. Call the subclass implementation of `process` for each sample.
            3. Preserve batch order and return the processed results.

        Args:
            items (list[dict[str, Any]]): Batch of samples to process.

        Returns:
            list[dict[str, Any]]: Processed results in the same order as the input.

        Examples:
            >>> BaseOperator({}).process_batch([])
            []
        """
        return [self.process(item) for item in items]

    def teardown(self) -> None:
        """Release operator state after batch processing finishes.

        Business logic:
            1. Provide a unified cleanup hook at workflow shutdown.
            2. Release no resources by default so subclasses can override it for files or connections.
            3. Keep the execution path simple for ordinary stateless operators.

        Args:
            None.

        Returns:
            None: The teardown phase does not return a business value.

        Examples:
            >>> BaseOperator({}).teardown()
        """
        pass

    def add_issue(self, item: dict[str, Any], issue: str) -> None:
        """Append a deduplicated issue code to a sample.

        Business logic:
            1. Ensure the sample contains an `issues` list.
            2. Append the issue only when it is not already present.
            3. Prevent the same issue from being recorded repeatedly by one or multiple operators.

        Args:
            item (dict[str, Any]): Current sample.
            issue (str): Issue code to record.

        Returns:
            None: Modifies the sample issue list in place.

        Examples:
            >>> sample = {}
            >>> BaseOperator({}).add_issue(sample, "empty_text")
            >>> sample["issues"]
            ['empty_text']
        """
        if issue not in item.setdefault("issues", []):  # Deduplicate issue codes to avoid double-counting in reports.
            item["issues"].append(issue)

    def metric(self, item: dict[str, Any], key: str, value: Any) -> None:
        """Write a sample-level metric.

        Business logic:
            1. Ensure the sample contains a `metrics` dictionary.
            2. Write the metric value produced by the current operator under the metric name.
            3. Expose sample features to scoring, reporting, and audit logs.

        Args:
            item (dict[str, Any]): Current sample.
            key (str): Metric name.
            value (Any): Metric value.

        Returns:
            None: Modifies the sample metrics dictionary in place.

        Examples:
            >>> sample = {}
            >>> BaseOperator({}).metric(sample, "length", 3)
            >>> sample["metrics"]["length"]
            3
        """
        item.setdefault("metrics", {})[key] = value
