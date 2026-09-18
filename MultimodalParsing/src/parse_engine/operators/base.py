from __future__ import annotations

from typing import Any, Dict, List

from parse_engine.models import DataItem


class BaseOperator:
    operator_name: str = "base_operator"  # Operator name: registered name referenced in workflow config.
    operator_version: str = "1.0.0"  # Operator version: version number of the current operator implementation.

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """Initialize operator configuration.

        Business logic:
            1. Accept operator parameters passed in by a workflow step.
            2. Use an empty dictionary when parameters are missing to avoid repeated None handling in subclasses.
            3. Store the configuration on the instance for setup, process, and teardown.

        Args:
            config: The params configuration from a workflow step. May be empty.

        Returns:
            None: The constructor only initializes instance state.

        Examples:
            >>> BaseOperator({"enabled": True}).config["enabled"]
            True"""
        self.config = config or {}  # Operator config: runtime parameters passed in from the workflow step.

    def setup(self) -> None:
        """Run the operator pre-execution setup hook.

        Business logic:
            1. Provide an extension point for subclasses to load models, open connections, or initialize caches.
            2. The base class does not require resource preparation by default.
            3. The workflow executor calls this hook uniformly before processing samples.

        Args:
            None.

        Returns:
            None: The default setup stage does not return data.

        Examples:
            >>> BaseOperator().setup() is None
            True"""
        pass

    def process(self, item: DataItem) -> DataItem:
        """Abstract interface for processing a single data item.

        Business logic:
            1. Define the single-sample processing entrypoint that every operator must implement.
            2. Accept a DataItem and return the updated DataItem.
            3. Raise NotImplementedError in the base class to prevent misuse of an unimplemented operator.

        Args:
            item: Data item to be processed by the current workflow step.

        Returns:
            DataItem: Data item after subclass processing.

        Examples:
            >>> hasattr(BaseOperator, "process")
            True"""
        raise NotImplementedError

    def process_batch(self, items: List[DataItem]) -> List[DataItem]:
        """Process data items in batch order.

        Business logic:
            1. Accept a group of DataItem objects.
            2. Call process for each item to reuse single-sample logic.
            3. Return the processed item list in input order.

        Args:
            items: List of data items to process.

        Returns:
            List[DataItem]: Processed results in the same order as the input.

        Examples:
            >>> BaseOperator().process_batch([])
            []"""
        return [self.process(item) for item in items]

    def teardown(self) -> None:
        """Run the operator post-execution teardown hook.

        Business logic:
            1. Provide an extension point for subclasses to release models, close connections, or clean up temporary resources.
            2. The base class does not have resources to release by default.
            3. The workflow executor calls this hook uniformly in the finally stage.

        Args:
            None.

        Returns:
            None: The default teardown stage does not return data.

        Examples:
            >>> BaseOperator().teardown() is None
            True"""
        pass
