from __future__ import annotations

from collections import Counter
from typing import Any


def issue_distribution(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count the distribution of sample issue labels.

    Business logic:
        1. Iterate over workflow output samples.
        2. Read the issues list from each sample.
        3. Aggregate the occurrence count for each issue label.

    Args:
        items (list[dict[str, Any]]): Sample records after operator processing.

    Returns:
        dict[str, int]: Mapping of issue labels to occurrence counts.

    Examples:
        >>> issue_distribution([{"issues": ["a", "a"]}, {"issues": ["b"]}])
        {'a': 2, 'b': 1}
    """
    counter: Counter[str] = Counter()
    for item in items:  # Each item can contribute multiple issue labels to the run summary.
        counter.update(item.get("issues", []))
    return dict(counter)


def action_count(items: list[dict[str, Any]], action: str) -> int:
    """Count how many samples have a given action.

    Business logic:
        1. Iterate over workflow output samples.
        2. Read the action field from each sample.
        3. Count samples whose action exactly matches the target action.

    Args:
        items (list[dict[str, Any]]): Sample records containing an action field.
        action (str): Action name to count.

    Returns:
        int: Number of samples whose action matches.

    Examples:
        >>> action_count([{"action": "keep"}, {"action": "remove"}], "keep")
        1
    """
    return sum(1 for item in items if item.get("action") == action)
