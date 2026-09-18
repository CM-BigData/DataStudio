from __future__ import annotations

from typing import Any, Dict, List

from synthesis_engine.models import GenerationItem


class BaseOperator:
    operator_name = "base_operator"  # Operator registry name used as a stable snake_case identifier in workflow configs.
    operator_version = "1.0.0"  # Operator version used for later auditing and compatibility marking.

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """Initialize operator configuration

        Business logic:
            1. Accept operator configuration from external callers
            2. Use an empty dictionary when config is missing
            3. Store config for subclass sample processing

        Args:
            config (Dict[str, Any] | None): Operator configuration dictionary.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> BaseOperator({'a': 1}).config['a']
            1
        """
        self.config = config or {}  # Operator configuration dictionary passed by the current workflow step.

    def setup(self) -> None:
        """Run operator startup preparation

        Business logic:
            1. Preserve a unified lifecycle entry point
            2. Perform no extra initialization by default
            3. Allow subclasses to override resource setup logic

        Args:
            None.

        Returns:
            None: Produces only lifecycle side effects.

        Examples:
            >>> BaseOperator().setup()
        """
        pass

    def process(self, item: GenerationItem) -> GenerationItem:
        """Process a single generation sample

        Business logic:
            1. Define the operator processing interface
            2. Require concrete subclasses to implement business logic
            3. Raise NotImplementedError when not implemented

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Processed sample.

        Examples:
            >>> callable(BaseOperator().process)
            True
        """
        raise NotImplementedError

    def process_batch(self, items: List[GenerationItem]) -> List[GenerationItem]:
        """Process generation samples in batch

        Business logic:
            1. Accept a list of samples
            2. Call the single-sample processor one by one
            3. Return results in the original order

        Args:
            items (List[GenerationItem]): List of samples to process.

        Returns:
            List[GenerationItem]: List of processed samples.

        Examples:
            >>> BaseOperator().process_batch([])
            []
        """
        return [self.process(item) for item in items]

    def teardown(self) -> None:
        """Run operator shutdown cleanup

        Business logic:
            1. Preserve a unified lifecycle exit point
            2. Perform no extra cleanup by default
            3. Allow subclasses to override resource-release logic

        Args:
            None.

        Returns:
            None: Produces only lifecycle side effects.

        Examples:
            >>> BaseOperator().teardown()
        """
        pass
