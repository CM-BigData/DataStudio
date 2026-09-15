from __future__ import annotations

from pathlib import Path
from typing import Any


class BaseOperator:
    operator_name = "base"  # Workflow config: default registered operator name referenced in workflow config.
    operator_version = "1.0.0"  # Workflow config: operator implementation version used for audit and delivery notes.

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize operator config.

        Business logic:
            1. Accept workflow step params.
            2. Use an empty config dictionary when none is provided.
            3. Save the config on the instance for setup and process_dataset.

        Args:
            config (dict[str, Any] | None, optional): Operator config for the current step.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> BaseOperator({"threshold": 0.8}).config["threshold"]
            0.8
        """
        self.config = config or {}  # Workflow config: step-level config parameters used by the current operator instance.

    def setup(self) -> None:
        """Run pre-execution operator initialization.

        Business logic:
            1. Provide an extension point for subclasses to load models or external resources.
            2. The default implementation performs no resource initialization.
            3. The executor calls this method before process_dataset.

        Args:
            None: The default setup takes no parameters.

        Returns:
            None: Nothing is returned after setup completes.

        Examples:
            >>> BaseOperator().setup()
        """
        pass

    def process(self, item: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Default implementation for processing a single sample.

        Business logic:
            1. Accept one sample and optional context.
            2. Leave the sample unchanged by default.
            3. Return the original sample so simple operators can reuse the behavior.

        Args:
            item (dict[str, Any]): Single sample record.
            context (dict[str, Any] | None, optional): Shared workflow context.

        Returns:
            dict[str, Any]: Processed sample record.

        Examples:
            >>> BaseOperator().process({"id": "1"})["id"]
            '1'
        """
        return item

    def process_batch(self, items: list[dict[str, Any]], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Process a batch of samples one by one.

        Business logic:
            1. Iterate over the input sample list.
            2. Call process for each sample.
            3. Collect and return the processed sample list.

        Args:
            items (list[dict[str, Any]]): Batch of samples to process.
            context (dict[str, Any] | None, optional): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Processed sample list.

        Examples:
            >>> BaseOperator().process_batch([{"id": "1"}])[0]["id"]
            '1'
        """
        return [self.process(item, context=context) for item in items]

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Default implementation for processing a full dataset.

        Business logic:
            1. Accept the full sample list for the current workflow.
            2. Perform no cross-sample processing by default.
            3. Return the original list so subclasses can override as needed.

        Args:
            items (list[dict[str, Any]]): Input sample list for the current step.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Processed sample list.

        Examples:
            >>> BaseOperator().process_dataset([{"id": "1"}], {})[0]["id"]
            '1'
        """
        return items

    def teardown(self) -> None:
        """Release operator runtime resources.

        Business logic:
            1. Provide an extension point for subclasses to close models, connections, or temporary resources.
            2. The default implementation performs no cleanup.
            3. The executor calls this method after a step succeeds or fails.

        Args:
            None: The default teardown takes no parameters.

        Returns:
            None: Nothing is returned after cleanup completes.

        Examples:
            >>> BaseOperator().teardown()
        """
        pass

    def add_issue(self, item: dict[str, Any], issue: str) -> None:
        """Append a deduplication-processing issue to a sample.

        Business logic:
            1. Ensure the sample has an issues list.
            2. Check whether the target issue already exists.
            3. Append only new issues to avoid duplicate labels.

        Args:
            item (dict[str, Any]): Sample that needs an issue label.
            issue (str): Issue label name.

        Returns:
            None: The sample's issues list is modified in place.

        Examples:
            >>> item = {}
            >>> BaseOperator().add_issue(item, "empty")
            >>> item["issues"]
            ['empty']
        """
        issues = item.setdefault("issues", [])
        if issue not in issues:  # Record each issue only once to avoid double-counting in metrics.
            issues.append(issue)

    def set_metric(self, item: dict[str, Any], key: str, value: Any) -> None:
        """Write a sample-level metric.

        Business logic:
            1. Ensure the sample has a metrics dictionary.
            2. Write the given key as value.
            3. Allow later reports or debugging commands to read the metric.

        Args:
            item (dict[str, Any]): Sample that needs a metric written.
            key (str): Metric name.
            value (Any): Metric value.

        Returns:
            None: The sample's metrics dictionary is modified in place.

        Examples:
            >>> item = {}
            >>> BaseOperator().set_metric(item, "length", 3)
            >>> item["metrics"]["length"]
            3
        """
        item.setdefault("metrics", {})[key] = value

    def set_intermediate(self, item: dict[str, Any], key: str, value: Any) -> None:
        """Write an intermediate sample result.

        Business logic:
            1. Ensure the sample has an intermediate dictionary.
            2. Write the operator-generated intermediate value under the given key.
            3. Allow later operators to continue processing from intermediate results.

        Args:
            item (dict[str, Any]): Sample that needs an intermediate result written.
            key (str): Intermediate field name.
            value (Any): Intermediate result value.

        Returns:
            None: The sample's intermediate dictionary is modified in place.

        Examples:
            >>> item = {}
            >>> BaseOperator().set_intermediate(item, "normalized_text", "hello")
            >>> item["intermediate"]["normalized_text"]
            'hello'
        """
        item.setdefault("intermediate", {})[key] = value

    def resolve_path(self, item: dict[str, Any], context: dict[str, Any], payload_key: str) -> Path | None:
        """Resolve a file path from sample payload.

        Business logic:
            1. Read the path string from the specified payload field.
            2. Return None when the path is missing.
            3. Return absolute paths unchanged and resolve relative paths against context.cwd.

        Args:
            item (dict[str, Any]): Sample record containing payload.
            context (dict[str, Any]): Shared workflow context, expected to contain cwd.
            payload_key (str): Payload field name containing the path.

        Returns:
            Path | None: Resolved path, or None when the sample has no such path.

        Examples:
            >>> BaseOperator().resolve_path({"payload": {}}, {"cwd": "."}, "image_path") is None
            True
        """
        payload = item.get("payload", {})
        path_value = payload.get(payload_key)
        if not path_value:  # Concrete operators decide whether missing file paths should become issues.
            return None
        path = Path(path_value)
        if path.is_absolute():  # Absolute paths are already directly usable and do not need cwd prefixing.
            return path
        return Path(context["cwd"]) / path

    def add_duplicate_edge(
        self,
        context: dict[str, Any],
        left_id: str,
        right_id: str,
        score: float,
        reason: str,
        duplicate_type: str,
    ) -> None:
        """Append one duplicate candidate edge to workflow context.

        Business logic:
            1. Ignore self-loops where left and right ids are the same.
            2. Sort the two ids to keep pair direction stable.
            3. Write score, reason, duplicate_type, and the current operator name.

        Args:
            context (dict[str, Any]): Shared workflow context.
            left_id (str): Left sample id.
            right_id (str): Right sample id.
            score (float): Duplicate confidence score.
            reason (str): Business reason that produced this edge.
            duplicate_type (str): Duplicate type, such as exact_duplicate or near_duplicate.

        Returns:
            None: Appends to context["duplicate_edges"] in place.

        Examples:
            >>> context = {}
            >>> BaseOperator().add_duplicate_edge(context, "b", "a", 1.0, "same", "exact_duplicate")
            >>> context["duplicate_edges"][0]["left_id"]
            'a'
        """
        if left_id == right_id:  # A sample cannot form a duplicate edge with itself.
            return
        left, right = sorted([left_id, right_id])
        context.setdefault("duplicate_edges", []).append(
            {
                "left_id": left,
                "right_id": right,
                "score": round(float(score), 6),
                "reason": reason,
                "duplicate_type": duplicate_type,
                "operator": self.operator_name,
            }
        )
